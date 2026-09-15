"""Build a scoped glossary draft from a consistent, possibly partial collection.

Uses the v1 lexical tables; official source relations and cross-dictionary label
candidates stay separate. No retrieval, API call, LLM, or canonical promotion.
"""
import argparse
from collections import Counter
from contextlib import closing
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from . import glossary_v1 as v1
from . import glossary_definitions as local
from .collect_moleg_knowledge import _atomic_json
from .glossary_alignment import Matcher, compact
from .glossary_enrichment import relation_target, validate_response, source_ids
from lawrag.sources.moleg_knowledge import ENDPOINTS, parse_xml_page

VERSION = 'glossary-assembly-v2'


def tables(db):
    v1.create_tables(db)
    local.tables(db)
    db.executescript('''
      CREATE TABLE definition_record(id TEXT PRIMARY KEY,source_id TEXT,label TEXT,kind TEXT,
        content_type TEXT,text TEXT,payload TEXT,request_id TEXT,response_sha256 TEXT);
      CREATE TABLE definition_candidate(entry_id TEXT REFERENCES entry(id),definition_id TEXT REFERENCES definition_record(id),
        match_kind TEXT,PRIMARY KEY(entry_id,definition_id,match_kind));
      CREATE TABLE scope_entry(entry_id TEXT PRIMARY KEY REFERENCES entry(id),role TEXT);
      CREATE TABLE source_request(id TEXT PRIMARY KEY,term_id TEXT,parameters TEXT,status TEXT,
        response BLOB,response_sha256 TEXT,records TEXT,error TEXT);
      CREATE TABLE official_relation(id TEXT PRIMARY KEY,source_id TEXT REFERENCES entry(id),
        target_id TEXT REFERENCES entry(id),code TEXT,label TEXT,request_id TEXT REFERENCES source_request(id),payload TEXT);
      CREATE INDEX official_target ON official_relation(target_id);
      CREATE TABLE external_candidate(id TEXT PRIMARY KEY,external_id TEXT REFERENCES entry(id),
        matched_entry_id TEXT REFERENCES entry(id),legal_entry_id TEXT REFERENCES entry(id),
        surface_key TEXT,basis TEXT,relation_id TEXT REFERENCES official_relation(id),status TEXT);
      CREATE INDEX external_candidate_entry ON external_candidate(external_id);
      CREATE TABLE classification(entry_id TEXT PRIMARY KEY REFERENCES entry(id),corpus_class TEXT);
      CREATE TABLE review_queue(entry_id TEXT PRIMARY KEY REFERENCES entry(id),status TEXT,candidate_count INTEGER);
      CREATE INDEX occurrence_key ON occurrence(key);
      CREATE INDEX surface_key ON surface(key);
    ''')


def freeze_collection(path, store_hash):
    """Hold the live SQLite read transaction only while copying the selected rows."""
    with closing(v1.read_db(path)) as db:
        db.execute('BEGIN')
        identity = json.loads(db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0])
        scope = identity.get('scope')
        if not scope or scope['identity']['store_sha256'] != store_hash or scope.get('max_relation_hops') != 1:
            raise ValueError('Collection must have the same corpus and one-hop scope')
        scope_path = Path(scope['path'])
        if v1.sha(scope_path) != scope['scope_sha256']:
            raise ValueError('Scope hash mismatch')
        with closing(v1.read_db(scope_path)) as scoped:
            seeds = {r[0] for r in scoped.execute('SELECT DISTINCT term_id FROM occurrence')}
        jobs = [dict(r) for r in db.execute("SELECT * FROM request WHERE endpoint='legal_term_relations' ORDER BY id")]
        wanted = {s for s in seeds if s.startswith('moleg:knowledge_terms:')}
        job_seeds = ['moleg:knowledge_terms:'+json.loads(r['parameters'])['MST'] for r in jobs]
        if not wanted or set(job_seeds) != wanted or len(job_seeds) != len(wanted):
            raise ValueError('Relation request plan does not exactly cover corpus knowledge terms')
        relations = []
        h = hashlib.sha256()
        for job, source in zip(jobs, job_seeds):
            job['term_id'] = source
            if job['status'] not in {'complete','pending','failed'}:
                raise ValueError('Unknown collection request status')
            h.update(v1.encode([job['id'],job['parameters'],job['status'],job['response_sha256'],job['records'],job['error']]).encode())
            if job['status'] != 'complete':
                continue
            raw = gzip.decompress(job['response'])
            if hashlib.sha256(raw).hexdigest() != job['response_sha256']:
                raise ValueError('Relation response hash mismatch')
            parameters = json.loads(job['parameters'])
            parsed = parse_xml_page(raw.decode(), ENDPOINTS['legal_term_relations'])
            validate_response('legal_term_relations', parameters, raw.decode(), parsed.records)
            expected = [dict(r, _request=parameters, _request_id=job['id']) for r in parsed.records]
            if expected != json.loads(job['records']):
                raise ValueError('Stored relation records differ from the source response')
            for record in expected:
                target = relation_target(record)
                relations.append((source,target,job['id'],record))
        ids = seeds | {r[1] for r in relations}
        entries = {}
        ordered = sorted(ids)
        for start in range(0,len(ordered),800):
            batch = ordered[start:start+800]
            for ident,payload in db.execute('SELECT id,payload FROM catalogue WHERE id IN ('+','.join('?'*len(batch))+')',batch):
                entries[ident] = json.loads(payload)
        if seeds - entries.keys():
            raise ValueError('Collection catalogue lacks a selected corpus term')
    return identity,seeds,jobs,relations,entries,h.hexdigest()


def add_definitions(db, paths, entries):
    """Keep typed source details separate from approved meaning and catalogue notes."""
    legal_ids = {}
    labels = {}
    for ident,record in entries.items():
        labels.setdefault(compact(record['label']),[]).append(ident)
        if ident.startswith('moleg:legal_terms:'):
            for source in source_ids(record['source_id']):
                legal_ids.setdefault(source,[]).append(ident)
    snapshots = []
    for path in paths:
        h=hashlib.sha256();count=0
        with closing(v1.read_db(path)) as incoming:
            incoming.execute('BEGIN')
            for job in incoming.execute("SELECT * FROM request WHERE endpoint='legal_term_detail' AND status='complete' ORDER BY id"):
                raw=gzip.decompress(job['response'])
                if hashlib.sha256(raw).hexdigest()!=job['response_sha256']:
                    raise ValueError('Definition response hash mismatch')
                params=json.loads(job['parameters'])
                parsed=parse_xml_page(raw.decode(),ENDPOINTS['legal_term_detail'])
                validate_response('legal_term_detail',params,raw.decode(),parsed.records)
                expected=[dict(r,_request=params,_request_id=job['id']) for r in parsed.records]
                if expected!=json.loads(job['records']):
                    raise ValueError('Stored definition records differ from source response')
                h.update(v1.encode([job['id'],job['response_sha256'],job['records']]).encode());count+=1
                for record in expected:
                    direct=legal_ids.get(record['source_id'],[])
                    same_label=labels.get(compact(record['label']),[])
                    if not direct and not same_label:continue
                    code=record.get('fields',{}).get('법령용어코드','')
                    kind={'011401':'EXPLANATION','011402':'EXPLANATION','011403':'TRANSLATION',
                          '011405':'NAVIGATION'}.get(code,'UNTYPED_SOURCE_CONTENT')
                    ident=hashlib.sha256(v1.encode(record).encode()).hexdigest()
                    db.execute('INSERT OR IGNORE INTO definition_record VALUES (?,?,?,?,?,?,?,?,?)',
                        (ident,record['source_id'],record['label'],code,kind,record.get('definition',''),
                         v1.encode(record),job['id'],job['response_sha256']))
                    for entry in sorted(set(direct+same_label)):
                        db.execute('INSERT OR IGNORE INTO definition_candidate VALUES (?,?,?)',
                            (entry,ident,'SOURCE_ID' if entry in direct else 'LABEL_CANDIDATE'))
        snapshots.append({'path':str(Path(path).resolve()),'completed_requests':count,'content_sha256':h.hexdigest()})
    return snapshots


def build(relations_db, external, corpus, output, *, definitions=(), emit=print):
    relations_db,external,corpus,output = [Path(x).resolve() for x in (relations_db,external,corpus,output)]
    if output.exists():
        raise ValueError('Output already exists; choose a new version directory')
    manifest = json.loads((corpus/'manifest.json').read_text())
    store_hash = v1.sha(corpus/'store.sqlite')
    if manifest.get('store_sha256') != store_hash:
        raise ValueError('Corpus hash mismatch')
    files = [external/s/'entries.jsonl' for s in ('econedu','nts')]
    external_hashes = {str(p):v1.sha(p) for p in files}
    collection,seeds,jobs,relations,entries,collection_hash = freeze_collection(relations_db,store_hash)
    code_paths = [Path(__file__),Path(v1.__file__),Path(local.__file__),Path(__file__).with_name('glossary_alignment.py'),
                  Path(__file__).with_name('glossary_enrichment.py'),Path(__file__).parents[1]/'sources/moleg_knowledge.py']
    code_hashes = {str(p):v1.sha(p) for p in code_paths}
    identity = {'corpus':str(corpus),'corpus_sha256':store_hash,
                'manifest_sha256':v1.sha(corpus/'manifest.json'),'external_sha256':external_hashes,
                'collection_path':str(relations_db),'collection_content_sha256':collection_hash,
                'collection_identity':collection,'code_sha256':code_hashes}
    output.parent.mkdir(parents=True,exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    try:
        with closing(sqlite3.connect(temp/'dictionary.sqlite')) as db:
            tables(db)
            for source,target,rid,record in relations:
                if target not in entries:
                    # New official neighbour absent from the older catalogue: retain its proved ID.
                    entries[target] = {**record,'entity_type':target.split(':')[1]}
            for ident,record in sorted(entries.items()):
                # Catalogue notes are source notes, not an explanatory dictionary definition.
                v1.add_entry(db,ident,'moleg',record['label'],record.get('definition',''),
                             hanja=record.get('hanja',''),provenance=record)
                db.execute('INSERT INTO scope_entry VALUES (?,?)',(ident,'CORPUS_SEED' if ident in seeds else 'DIRECT_NEIGHBOUR'))
            for job in jobs:
                db.execute('INSERT INTO source_request VALUES (?,?,?,?,?,?,?,?)',
                           tuple(job[k] for k in ('id','term_id','parameters','status','response','response_sha256','records','error')))
            for source,target,rid,record in relations:
                ident = hashlib.sha256(v1.encode([source,target,rid,record]).encode()).hexdigest()
                fields = record['fields']
                db.execute('INSERT OR IGNORE INTO official_relation VALUES (?,?,?,?,?,?,?)',
                           (ident,source,target,fields.get('용어관계코드',''),fields.get('용어관계',''),rid,v1.encode(record)))
                db.execute('INSERT OR IGNORE INTO surface VALUES (?,?,?,?)',
                           (compact(record['label']),record['label'],target,'OFFICIAL_RELATION_LABEL'))
            for path in files:
                with path.open(encoding='utf-8') as stream:
                    for line in stream:
                        if not line.strip():continue
                        row = json.loads(line)
                        if row['source'] != path.parent.name:
                            raise ValueError('External dictionary source mismatch')
                        v1.add_entry(db,row['id'],row['source'],row['term'],row.get('definition',''),
                                     row.get('english',''),row.get('hanja',''),row)
            identity['definitions'] = add_definitions(db,definitions,entries)
            with closing(v1.read_db(corpus/'store.sqlite')) as incoming:
                incoming.execute('BEGIN')
                local.add(db,incoming,store_hash)
            db.commit()
            progress = dict(Counter(j['status'] for j in jobs))
            complete = progress.get('complete',0) == len(jobs)
            emit(f"glossary assemble: froze {progress.get('complete',0)}/{len(jobs)} relation responses",flush=True)
            matcher = Matcher([(r[0],r[0]) for r in db.execute('SELECT DISTINCT key FROM surface ORDER BY key')])
            with closing(v1.read_db(corpus/'store.sqlite')) as incoming:
                incoming.execute('BEGIN')
                docs = [r[0] for r in incoming.execute('SELECT document_id FROM document ORDER BY document_id')]
                for index,did in enumerate(docs,1):
                    for bid,unit,text in incoming.execute('SELECT block_id,unit_id,text FROM source_block WHERE document_id=? ORDER BY block_id',(did,)):
                        db.executemany('INSERT OR IGNORE INTO occurrence VALUES (?,?,?,?,?,?)',
                            ((key,did,str(bid),unit,lo,hi) for key,lo,hi,_ in matcher.find(text)))
                    db.commit()
                    if index == 1 or index%20 == 0 or index == len(docs):
                        emit(f'glossary assemble: corpus {index}/{len(docs)}',flush=True)
            db.execute('''INSERT INTO classification SELECT e.id,CASE WHEN EXISTS
                (SELECT 1 FROM occurrence o WHERE o.key=e.key) THEN 'CORPUS_PRESENT'
                ELSE 'GENERAL_IN_THIS_CORPUS' END FROM entry e''')
            # Shared spelling supplies candidates. Even official synonyms do not approve
            # that a finance dictionary entry has the same sense as the MOLEG source.
            matches = db.execute('''SELECT DISTINCT e.id,m.entry_id,s.key,s.kind,k.role
              FROM entry e JOIN surface s ON s.entry_id=e.id
              JOIN surface m ON m.key=s.key JOIN scope_entry k ON k.entry_id=m.entry_id
              WHERE e.source IN ('econedu','nts') ORDER BY e.id,m.entry_id,s.key,s.kind''').fetchall()
            for ext,matched,key,kind,role in matches:
                paths = []
                if role == 'CORPUS_SEED':
                    paths.append((matched,None,'CORPUS_SEED_LABEL:'+kind))
                paths.extend((src,rid,'DIRECT_OFFICIAL_RELATION:'+kind) for rid,src in db.execute(
                    'SELECT id,source_id FROM official_relation WHERE target_id=? ORDER BY id',(matched,)))
                for legal,relation,basis in paths:
                    ident = hashlib.sha256(v1.encode([ext,matched,legal,key,basis,relation]).encode()).hexdigest()
                    db.execute('INSERT OR IGNORE INTO external_candidate VALUES (?,?,?,?,?,?,?,?)',
                        (ident,ext,matched,legal,key,basis,relation,'MEANING_REVIEW'))
            # Definition headword equality nominates a document-specific sense only.
            for ext,target,key in db.execute('''SELECT e.id,d.id,d.key FROM entry e
                JOIN corpus_definition d ON d.key=e.key WHERE e.source IN ('econedu','nts')
                ORDER BY e.id,d.id''').fetchall():
                ident=hashlib.sha256(v1.encode([ext,target,'LOCAL_DEFINITION_LABEL']).encode()).hexdigest()
                db.execute('INSERT INTO external_candidate VALUES (?,?,?,?,?,?,?,?)',
                    (ident,ext,target,target,key,'LOCAL_DEFINITION_LABEL',None,'MEANING_REVIEW'))
            db.execute('''INSERT INTO review_queue SELECT e.id,
                CASE WHEN count(c.id)>0 THEN 'MEANING_REVIEW'
                WHEN EXISTS (SELECT 1 FROM occurrence o WHERE o.key=e.key) THEN 'CORPUS_LINKED'
                ELSE ? END,count(c.id)
                FROM entry e LEFT JOIN external_candidate c ON c.external_id=e.id
                WHERE e.source IN ('econedu','nts') GROUP BY e.id''',
                ('UNLINKED_REVIEW' if complete else 'WAITING_FOR_RELATIONS',))
            db.commit()
            stats = v1.counts(db)
            stats['corpus_definitions'] = local.counts(db)
            stats['external_corpus_present'] = db.execute("SELECT count(*) FROM entry e JOIN classification c ON c.entry_id=e.id WHERE e.source IN ('econedu','nts') AND c.corpus_class='CORPUS_PRESENT'").fetchone()[0]
            stats['candidate_basis'] = dict(db.execute('SELECT basis,count(*) FROM external_candidate GROUP BY basis'))
            for table in ('official_relation','external_candidate','definition_record','definition_candidate'):
                stats[table] = db.execute('SELECT count(*) FROM '+table).fetchone()[0]
            stats['definition_content_types'] = dict(db.execute('SELECT content_type,count(*) FROM definition_record GROUP BY content_type'))
            stats['external_review'] = dict(db.execute('SELECT status,count(*) FROM review_queue GROUP BY status'))
            stats['classification'] = dict(db.execute('SELECT corpus_class,count(*) FROM classification GROUP BY corpus_class'))
            stats['moleg_scope'] = dict(db.execute('SELECT role,count(*) FROM scope_entry GROUP BY role'))
            stats['source_relation_codes'] = dict(db.execute('SELECT code,count(*) FROM official_relation GROUP BY code'))
            report = {'schema_version':VERSION,'status':'draft','identity':identity,'counts':stats,
                      'collection':{'requests':len(jobs),'states':progress,'complete':complete,
                        'empty_responses':sum(j['status']=='complete' and json.loads(j['records'])==[] for j in jobs)},
                      'llm_calls':0,'runtime_promoted':False,'canonical_approval':False,
                      'policy':'source relations are preserved; external label matches require meaning review',
                      'rebuild':'Run the same assemble command with a new output directory to include newly completed responses.'}
            if v1.sha(corpus/'store.sqlite') != store_hash or v1.sha(corpus/'manifest.json') != identity['manifest_sha256']:
                raise ValueError('Corpus changed during build')
            if any(v1.sha(p)!=h for p,h in {**external_hashes,**code_hashes}.items()):
                raise ValueError('Input or implementation changed during build')
            db.execute('INSERT INTO meta VALUES (?,?)',('report',v1.encode(report)));db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Glossary draft integrity failure')
        report['dictionary_sha256'] = v1.sha(temp/'dictionary.sqlite')
        _atomic_json(temp/'report.json',report)
        if output.exists():raise ValueError('Output appeared during build')
        os.rename(temp,output)
        return {**report,'directory':str(output)}
    except Exception:
        emit('glossary assemble: unfinished build preserved at '+str(temp),flush=True)
        raise


def sense_review_details(db, entry_ids, *, limit=100):
    """Version-compatible read of proposal-only lexical relationships."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='sense_assertion'").fetchone():
        return {'available':False,'assertions':[],'total':0,'truncated':False,'canonical_approval':False}
    ids=sorted(set(entry_ids))
    if not ids:return {'available':True,'assertions':[],'total':0,'truncated':False,'canonical_approval':False}
    marks=','.join('?' for _ in ids)
    where=f'(left_s.entry_id IN ({marks}) OR right_s.entry_id IN ({marks}))'
    join='FROM sense_assertion a JOIN sense_candidate left_s ON left_s.id=a.source JOIN sense_candidate right_s ON right_s.id=a.target '
    total=db.execute('SELECT count(*) '+join+'WHERE '+where,(*ids,*ids)).fetchone()[0]
    rows=db.execute('SELECT a.*,left_s.entry_id AS source_entry_id,right_s.entry_id AS target_entry_id, '
                    'left_s.payload AS source_sense,right_s.payload AS target_sense '+join+
                    'WHERE '+where+' ORDER BY a.job_id,a.axis,a.id LIMIT ?',(*ids,*ids,limit)).fetchall()
    assertions=[]
    for row in rows:
        item=dict(row)
        item['evidence']=json.loads(item.pop('evidence_json'))
        item['source_sense']=json.loads(item['source_sense'])
        item['target_sense']=json.loads(item['target_sense'])
        assertions.append(item)
    return {'available':True,'assertions':assertions,'total':total,'truncated':total>len(assertions),
            'canonical_approval':False,'semantic_support_verified':False}


def inspect(directory,term=None):
    directory = Path(directory)
    report = json.loads((directory/'report.json').read_text())
    if report['schema_version'] not in {VERSION,'glossary-assembly-v1'} or v1.sha(directory/'dictionary.sqlite') != report['dictionary_sha256']:
        raise ValueError('Glossary version/hash mismatch')
    if term is None:return report
    with closing(v1.read_db(directory/'dictionary.sqlite')) as db:
        entries = [dict(r) for r in db.execute('''SELECT DISTINCT e.*,c.corpus_class,q.status AS review_status
           FROM surface s JOIN entry e ON e.id=s.entry_id JOIN classification c ON c.entry_id=e.id
           LEFT JOIN review_queue q ON q.entry_id=e.id WHERE s.key=? ORDER BY e.id''',(compact(term),))]
        classes={'CORPUS_PRESENT':'LEGAL_TERM','GENERAL_IN_THIS_CORPUS':'EVERYDAY_TERM'}
        for entry in entries:entry['term_class']=classes[entry['corpus_class']]
        ids = [e['id'] for e in entries]
        candidates=[];official={}
        for ident in ids:
            candidates.extend(dict(r) for r in db.execute('''SELECT c.*,a.label AS matched_label,b.label AS legal_label,
                r.code AS relation_code,r.label AS relation_label FROM external_candidate c
                JOIN entry a ON a.id=c.matched_entry_id JOIN entry b ON b.id=c.legal_entry_id
                LEFT JOIN official_relation r ON r.id=c.relation_id WHERE c.external_id=? ORDER BY c.id''',(ident,)))
            for row in db.execute('''SELECT r.*,a.corpus_class AS source_corpus_class,
                b.corpus_class AS target_corpus_class FROM official_relation r
                JOIN classification a ON a.entry_id=r.source_id
                JOIN classification b ON b.entry_id=r.target_id
                WHERE r.source_id=? OR r.target_id=?''',(ident,ident)):
                relation=dict(row)
                relation['source_term_class']=classes[relation['source_corpus_class']]
                relation['target_term_class']=classes[relation['target_corpus_class']]
                official[relation['id']] = relation
        definitions=[]
        for ident in sorted(set(ids+[c['legal_entry_id'] for c in candidates])):
            definitions.extend(dict(r) for r in db.execute('''SELECT c.entry_id,c.match_kind,d.* FROM definition_candidate c
                JOIN definition_record d ON d.id=c.definition_id WHERE c.entry_id=? ORDER BY d.id''',(ident,)))
        corpus_definitions=[];occurrences=[]
        if report['schema_version']==VERSION:
            corpus_definitions=[dict(r) for r in db.execute(
                'SELECT d.*,c.name AS document_name,c.source_sha256 FROM corpus_definition d JOIN corpus_document c ON c.document_id=d.document_id WHERE d.key=? ORDER BY d.id',(compact(term),))]
            occurrences=[dict(r) for r in db.execute('''SELECT o.*,d.name AS document_name,d.source_sha256
                FROM occurrence o JOIN corpus_document d ON d.document_id=o.document_id
                WHERE o.key=? ORDER BY o.document_id,o.block_id,o.start''',(compact(term),))]
        return {'sense_review':sense_review_details(db,ids),'corpus_definitions':corpus_definitions,'corpus_occurrences':occurrences,'definitions':definitions,'term':term,'entries':entries,'candidates':candidates,'official_relations':list(official.values()),
                'classification_basis':'dictionary headword occurrence in selected corpus, independent of provider category',
                'article_connections':{'corpus_literal_occurrences':len(occurrences),
                    'official_api_links':'NOT_COMPILED_IN_THIS_DRAFT'},
                'collection':report['collection'],'canonical_approval':False}


def main(argv=None):
    p=argparse.ArgumentParser(description='용어집 v1: 본문 범위 + 공식 직접 관계 + 금융·세무 사전 대조')
    p.add_argument('--relations-db',type=Path)
    p.add_argument('--external-dir',type=Path)
    p.add_argument('--definitions-db',type=Path,action='append',default=[])
    p.add_argument('--corpus-generation',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inspect',action='store_true')
    p.add_argument('--term')
    args=p.parse_args(argv)
    if args.inspect:
        result=inspect(args.output,args.term)
    else:
        if not all((args.relations_db,args.external_dir,args.corpus_generation)):
            p.error('build requires --relations-db, --external-dir and --corpus-generation')
        if args.term:p.error('--term requires --inspect')
        import sys
        result=build(args.relations_db,args.external_dir,args.corpus_generation,args.output,definitions=args.definitions_db,
                     emit=lambda *a,**kw:print(*a,file=sys.stderr,**kw))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0
