"""Glossary v1: deterministic surface matching, explicit choices, source occurrences.

Draft lexical index, not canonical legal Concepts or a runtime RAG promotion.
No network, model, similarity score, or inferred synonym lives in this module.
"""
from collections import defaultdict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from .glossary_alignment import Matcher, compact, digest, JOSA

VERSION = 'glossary-v1.0'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''): h.update(part)
    return h.hexdigest()


def read_db(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def create_tables(db):
    db.executescript('''
      PRAGMA foreign_keys=ON;
      CREATE TABLE entry(id TEXT PRIMARY KEY,source TEXT,label TEXT,key TEXT,
        definition TEXT,english TEXT,hanja TEXT,provenance TEXT);
      CREATE INDEX entry_key ON entry(key);
      CREATE TABLE surface(key TEXT,text TEXT,entry_id TEXT REFERENCES entry(id),kind TEXT,
        PRIMARY KEY(key,entry_id,kind));
      CREATE TABLE meaning(id TEXT PRIMARY KEY,label TEXT,description TEXT,evidence TEXT);
      CREATE TABLE membership(entry_id TEXT PRIMARY KEY REFERENCES entry(id),
        meaning_id TEXT REFERENCES meaning(id));
      CREATE TABLE relation(source TEXT REFERENCES entry(id),target TEXT REFERENCES entry(id),kind TEXT,proof TEXT,
        PRIMARY KEY(source,target,kind));
      CREATE TABLE occurrence(key TEXT,document_id TEXT,block_id TEXT,unit_id TEXT,start INTEGER,end INTEGER,
        PRIMARY KEY(key,document_id,block_id,start,end));
      CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
    ''')


def add_entry(db, ident, source, label, definition='', english='', hanja='', provenance=None):
    if not isinstance(label, str) or not compact(label): raise ValueError('Empty entry label')
    db.execute('INSERT INTO entry VALUES (?,?,?,?,?,?,?,?)',
               (ident, source, label, compact(label), definition or '', english or '', hanja or '', encode(provenance or {})))
    db.execute('INSERT INTO surface VALUES (?,?,?,?)', (compact(label), label, ident, 'SOURCE_LABEL'))
    if english and compact(english) != compact(label):
        db.execute('INSERT OR IGNORE INTO surface VALUES (?,?,?,?)', (compact(english), english, ident, 'SOURCE_ENGLISH'))
    # Closed label shapes only. These are source label parts, NOT approved synonyms.
    # Statute-derived labels (moleg, corpus definitions) keep their literal form.
    if source in ('moleg', 'corpus_definition'): return
    for part, kind in label_parts(label):
        if compact(part) != compact(label):
            db.execute('INSERT OR IGNORE INTO surface VALUES (?,?,?,?)', (compact(part), part, ident, kind))


RENAME_NOTE = re.compile(r'\((?:제목|용어)\s*(?:개정|변경)\)')
PAREN = re.compile(r'\([^()]*\)')
LATIN_TOKEN = re.compile(r'[A-Za-z][A-Za-z0-9&.\-]{0,15}')


def trailing_gloss(text):
    """(head, inner) when text ends with one balanced parenthetical gloss, else None."""
    text = text.strip()
    if not text.endswith(')'):
        return None
    depth = 0
    for i in range(len(text) - 1, -1, -1):
        depth += {')': 1, '(': -1}.get(text[i], 0)
        if depth == 0:
            return text[:i].strip(), text[i + 1:-1]
    return None


def top_level_split(text):
    parts, depth, start = [], 0, 0
    for i, char in enumerate(text):
        depth += {'(': 1, ')': -1}.get(char, 0)
        if depth == 0 and char in ',:;':
            parts.append(text[start:i]); start = i + 1
    return [p.strip() for p in parts + [text[start:]] if p.strip()]


def gloss_part(part):
    """A Hangul name or a Latin abbreviation is a part; an English phrase is SOURCE_ENGLISH."""
    nested = trailing_gloss(part)
    if nested and nested[0]:
        return gloss_part(nested[0]) + [x for p in top_level_split(nested[1]) for x in gloss_part(p)]
    if len(compact(part)) < 2 or '(' in part:
        return []
    if re.search(r'[가-힣]', part) and len(part) <= 40:
        return [(part, 'SOURCE_LABEL_PART')]
    if LATIN_TOKEN.fullmatch(part):
        return [(part, 'SOURCE_LABEL_PART')]
    if re.fullmatch(r'[A-Za-z0-9&.\- ]{2,80}', part):
        return [(part, 'SOURCE_ENGLISH')]
    return []  # hanja glosses (受再) and mixed prose


def label_parts(label):
    """Headword parts a public glossary label spells out.

    '린치핀(Linchpin)' -> 린치핀, Linchpin; 'AML(Anti-Money Laundering System, 자금세탁방지제도)' ->
    AML, 자금세탁방지제도 and the English phrase; '접대비→ 기업업무추진비(용어변경)' -> both names;
    '관리(대상)종목' -> 관리종목 only (an infix parenthesis is optional text, not a gloss).
    """
    if '→' in label:
        result = []
        for side in label.split('→'):
            side = RENAME_NOTE.sub('', side).strip()
            if len(compact(side)) >= 2:
                result += [(side, 'SOURCE_LABEL_PART')] + label_parts(side)
        return result
    gloss = trailing_gloss(label)
    if gloss and gloss[0] and '(' not in gloss[0]:
        head, inner = gloss
        return gloss_part(head) + [x for p in top_level_split(inner) for x in gloss_part(p)]
    head = label
    while PAREN.search(head):
        head = PAREN.sub('', head)
    head = head.strip()
    return [(head, 'SOURCE_LABEL_PART')] if head != label.strip() and len(compact(head)) >= 2 else []


def apply_review(db, review):
    """Optional explicit review file: grouping is never inferred from provider IDs."""
    if set(review) - {'meanings', 'aliases'}: raise ValueError('Unknown review fields')
    for m in review.get('meanings', []):
        if set(m) != {'id', 'label', 'description', 'entry_ids', 'evidence'}:
            raise ValueError('Meaning requires id/label/description/entry_ids/evidence')
        if not all(isinstance(m[k], str) and m[k].strip() for k in ('id','label','description','evidence')) or not m['entry_ids']:
            raise ValueError('Empty reviewed meaning')
        db.execute('INSERT INTO meaning VALUES (?,?,?,?)', (m['id'],m['label'],m['description'],m['evidence']))
        for ident in m['entry_ids']:
            db.execute('INSERT INTO membership VALUES (?,?)', (ident,m['id']))
    for a in review.get('aliases', []):
        if set(a) != {'surface', 'meaning_id', 'evidence'} or not a['evidence'] or not compact(a['surface']):
            raise ValueError('Alias requires surface/meaning_id/evidence')
        members = db.execute('SELECT entry_id FROM membership WHERE meaning_id=?', (a['meaning_id'],)).fetchall()
        if not members: raise ValueError('Alias points to unknown meaning')
        for member in members:
            db.execute('INSERT OR IGNORE INTO surface VALUES (?,?,?,?)',
                       (compact(a['surface']),a['surface'],member[0],'REVIEWED_ALIAS'))


def counts(db):
    result = {t: db.execute('SELECT count(*) FROM '+t).fetchone()[0]
              for t in ('entry','surface','meaning','membership','relation','occurrence')}
    result['sources'] = dict(db.execute('SELECT source,count(*) FROM entry GROUP BY source'))
    result['corpus_present_surfaces'] = db.execute('SELECT count(DISTINCT key) FROM occurrence').fetchone()[0]
    result['unique_surfaces'] = db.execute('SELECT count(DISTINCT key) FROM surface').fetchone()[0]
    result['classification_basis'] = 'literal occurrence in the explicitly selected corpus, not legal authority'
    return result


def build(catalogue, external, corpus, output, *, completion=None, review=None, emit=print):
    from .collect_moleg_knowledge import _atomic_json
    catalogue, external, corpus, output = map(lambda p: Path(p).resolve(), (catalogue,external,corpus,output))
    if output.exists(): raise ValueError('Output already exists; select a new glossary version directory')
    manifest = json.loads((corpus/'manifest.json').read_text())
    store_hash = sha(corpus/'store.sqlite')
    if manifest.get('store_sha256') != store_hash: raise ValueError('Corpus hash mismatch')
    files = [external/source/'entries.jsonl' for source in ('econedu','nts')]
    hashes = {str(p):sha(p) for p in files}
    identity = {'version': VERSION, 'corpus': str(corpus), 'corpus_sha256': store_hash,
                'corpus_manifest_sha256':sha(corpus/'manifest.json'), 'external_sha256':hashes,
                'code_sha256':sha(__file__), 'matcher_sha256':sha(Path(__file__).with_name('glossary_alignment.py')),
                'review_sha256':sha(review) if review else None}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.'+output.name+'-', dir=output.parent))
    try:
        with closing(sqlite3.connect(temporary/'dictionary.sqlite')) as out:
            create_tables(out)
            out.execute('PRAGMA journal_mode=DELETE')
            with closing(read_db(catalogue)) as incoming:
                incoming.execute('BEGIN')
                h = hashlib.sha256()
                for row in incoming.execute('SELECT id,payload FROM terms ORDER BY id'):
                    p = json.loads(row['payload'])
                    h.update(encode([row['id'],p]).encode())
                    add_entry(out,row['id'],'moleg',p['label'],p.get('definition') or p.get('fields',{}).get('비고',''),
                              hanja=p.get('hanja',''),provenance=p)
                identity['catalogue_content_sha256'] = h.hexdigest()
            for path in files:
                with path.open() as f:
                    for line in f:
                        if line.strip():
                            r=json.loads(line)
                            add_entry(out,r['id'],r['source'],r['term'],r.get('definition',''),
                                      r.get('english',''),r.get('hanja',''),r)
            emit('glossary v1: imported source entries', flush=True)
            # Completed definitions are source-scoped. Never attach by spelling alone.
            if completion:
                h=hashlib.sha256(); n=0
                with closing(read_db(completion)) as incoming:
                    incoming.execute('BEGIN')
                    for row in incoming.execute("SELECT id,records,response_sha256 FROM request WHERE status='complete' AND endpoint='legal_term_detail' ORDER BY id"):
                        h.update(encode(list(row)).encode()); n+=1
                        for record in json.loads(row['records'] or '[]'):
                            if not record.get('definition') or not record.get('label'): continue
                            ident='moleg:definition:'+digest(record)
                            if out.execute('SELECT 1 FROM entry WHERE id=?',(ident,)).fetchone(): continue
                            add_entry(out,ident,'moleg_detail',record['label'],record['definition'],
                                      hanja=record.get('hanja',''),provenance={**record,'request_id':row['id'],
                                      'response_sha256':row['response_sha256']})
                identity['completed_definitions']={'content_sha256':h.hexdigest(),'requests':n,'path':str(Path(completion).resolve())}
            # Reuse verified, already compiled official relations without promoting RELATED to SYNONYM.
            links=manifest.get('term_links') or {}
            if links.get('enabled'):
                path=(corpus/links['path']).resolve()
                if path.parent != corpus or links.get('source_store_sha256') != store_hash or sha(path)!=links['sha256']:
                    raise ValueError('Official link generation/hash mismatch')
                def translate(ident):
                    if ident.startswith('legal:'): return 'moleg:knowledge_terms:'+ident[6:]
                    if ident.startswith('daily:'): return 'moleg:everyday_terms:'+ident[6:]
                    return ident
                with closing(read_db(path)) as incoming:
                    for row in incoming.execute('SELECT * FROM edge ORDER BY source,target,kind'):
                        a,b=translate(row['source']),translate(row['target'])
                        if all(out.execute('SELECT 1 FROM entry WHERE id=?',(v,)).fetchone() for v in (a,b)):
                            out.execute('INSERT INTO relation VALUES (?,?,?,?)',(a,b,row['kind'],row['provenance']))
                identity['official_links_sha256']=links['sha256']
            if review: apply_review(out,json.loads(Path(review).read_text()))
            out.commit()
            matcher=Matcher([(r[0],r[0]) for r in out.execute('SELECT DISTINCT key FROM surface ORDER BY key')])
            with closing(read_db(corpus/'store.sqlite')) as incoming:
                docs=[r[0] for r in incoming.execute('SELECT document_id FROM document ORDER BY document_id')]
                for index,did in enumerate(docs):
                    for row in incoming.execute('SELECT block_id,unit_id,text FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)',(did,)):
                        out.executemany('INSERT OR IGNORE INTO occurrence VALUES (?,?,?,?,?,?)',
                            ((key,did,str(row['block_id']),row['unit_id'],lo,hi) for key,lo,hi,_ in matcher.find(row['text'])))
                    out.commit()
                    if index==0 or (index+1)%20==0 or index+1==len(docs):
                        emit(f'glossary v1: corpus {index+1}/{len(docs)} documents',flush=True)
            if (sha(corpus/'store.sqlite')!=store_hash or any(sha(p)!=v for p,v in hashes.items())
                    or (review and sha(review)!=identity['review_sha256'])):
                raise ValueError('Input changed during build')
            report={'schema_version':VERSION,'status':'draft','identity':identity,'counts':counts(out),
                    'llm_calls':0,'runtime_promoted':False,'meaning_policy':'source entries are not distinct canonical meanings'}
            out.execute('INSERT INTO meta VALUES (?,?)',('report',encode(report)))
            out.commit()
            if out.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or out.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Draft integrity check failed')
        report['dictionary_sha256']=sha(temporary/'dictionary.sqlite')
        _atomic_json(temporary/'report.json',report)
        if output.exists(): raise ValueError('Output appeared during build; refusing to overwrite')
        os.rename(temporary,output)
        return {**report,'directory':str(output)}
    except Exception:
        # Keep partial work inspectable; no completed report or active pointer is published.
        emit('glossary v1: unfinished build preserved at '+str(temporary),flush=True)
        raise


class Glossary:
    def __init__(self, directory):
        self.directory=Path(directory).resolve()
        self.report=json.loads((self.directory/'report.json').read_text())
        if self.report.get('schema_version')!=VERSION or sha(self.directory/'dictionary.sqlite')!=self.report['dictionary_sha256']:
            raise ValueError('Glossary version/hash mismatch')
        identity=self.report['identity']
        if identity['code_sha256']!=sha(__file__) or identity['matcher_sha256']!=sha(Path(__file__).with_name('glossary_alignment.py')):
            raise ValueError('Glossary code/matcher changed; build a new version')
        self.db=read_db(self.directory/'dictionary.sqlite')
        self.matcher=Matcher([(r[0],r[0]) for r in self.db.execute('SELECT DISTINCT key FROM surface ORDER BY key')])

    def close(self): self.db.close()

    def _choices(self, keys):
        groups={}
        for key in keys:
            for r in self.db.execute('''SELECT e.*,s.kind,m.meaning_id FROM surface s JOIN entry e ON e.id=s.entry_id
              LEFT JOIN membership m ON m.entry_id=e.id WHERE s.key=? ORDER BY e.id,s.kind''',(key,)):
                cid=('meaning:'+r['meaning_id']) if r['meaning_id'] else 'entry:'+r['id']
                if cid not in groups:
                    meaning=self.db.execute('SELECT * FROM meaning WHERE id=?',(r['meaning_id'],)).fetchone() if r['meaning_id'] else None
                    groups[cid]={'id':cid,'kind':'reviewed_meaning' if meaning else 'source_entry_unreviewed',
                                 'label':meaning['label'] if meaning else r['label'],
                                 'description':meaning['description'] if meaning else r['definition'],
                                 'hanja':r['hanja'],'english':r['english'],
                                 'source_entries':([x[0] for x in self.db.execute(
                                     'SELECT entry_id FROM membership WHERE meaning_id=? ORDER BY entry_id',
                                     (r['meaning_id'],))] if meaning else []), 'via':[]} 
                g=groups[cid]
                if r['id'] not in g['source_entries']:g['source_entries'].append(r['id'])
                if r['kind'] not in g['via']:g['via'].append(r['kind'])
        return sorted(groups.values(),key=lambda g:g['id'])

    def query(self, question, *, selections=None, choice_limit=20):
        if not isinstance(question,str) or not question.strip() or len(question)>10000:
            raise ValueError('Question must be 1..10000 characters')
        if not 1<=choice_limit<=100: raise ValueError('choice_limit must be 1..100')
        query_id=digest({'question':question,'dictionary':self.report['dictionary_sha256']})
        selections=selections or {'query_id':query_id,'choices':{}}
        if set(selections)!={'query_id','choices'} or selections['query_id']!=query_id or not isinstance(selections['choices'],dict):
            raise ValueError('Selections must be bound to this question and dictionary')
        found=defaultdict(set)
        for key,lo,hi,_ in self.matcher.find(question):found[(lo,hi)].add(key)
        # Containment only: preserve crossing overlaps as explicit ambiguity.
        spans=sorted(found,key=lambda s:(-(s[1]-s[0]),s[0]))
        kept=[];suppressed=[]
        for lo,hi in spans:
            if any(a<=lo and hi<=b for a,b in kept):suppressed.append({'start':lo,'end':hi,'surface':question[lo:hi]})
            else:kept.append((lo,hi))
        mentions=[]
        for lo,hi in sorted(kept):
            mid=f'm:{lo}:{hi}'; options=self._choices(found[(lo,hi)])
            # Official expansion is optional and always retains the relation type.
            expansion={}
            for option in options:
                for ident in option['source_entries']:
                    for r in self.db.execute('SELECT r.*,e.key FROM relation r JOIN entry e ON e.id=r.target WHERE r.source=? ORDER BY target,kind',(ident,)):
                        target=self.db.execute('SELECT * FROM entry WHERE id=?',(r['target'],)).fetchone()
                        cid='entry:'+r['target']
                        if any(o['id']==cid for o in options):continue
                        expansion.setdefault(cid,{'id':cid,'kind':'official_relation_candidate','label':target['label'],
                            'description':target['definition'],'source_entries':[target['id']],'via':[]})['via'].append(
                                {'kind':r['kind'],'source_entry':ident,'proof':r['proof']})
            all_options={o['id']:o for o in options+list(expansion.values())}
            selected=selections['choices'].get(mid)
            if selected is not None and selected not in all_options: raise ValueError('Selected choice is not a candidate for '+mid)
            crossing=any(a<hi and lo<b and (a,b)!=(lo,hi) for a,b in kept)
            status='CHOICE_REQUIRED' if len(options)>1 else 'MATCHED_ENTRY'
            if len(options)==1 and options[0]['kind']=='reviewed_meaning':status='RESOLVED'
            if selected is not None:status='SELECTED'
            if crossing:status='OVERLAP_REVIEW_REQUIRED'
            chosen=all_options[selected] if selected else (options[0] if len(options)==1 and not crossing else None)
            ordered=list(all_options.values())
            present=any(self.db.execute('SELECT 1 FROM occurrence WHERE key=? LIMIT 1',(key,)).fetchone() for key in found[(lo,hi)])
            mentions.append({'id':mid,'surface':question[lo:hi],'start':lo,'end':hi,'status':status,
                'classification':'CORPUS_PRESENT' if present else 'GENERAL_IN_THIS_CORPUS',
                'choices':ordered[:choice_limit],'choice_count':len(ordered),'choices_truncated':len(ordered)>choice_limit,
                'selected':chosen,'source_entries_are_distinct_meanings':False})
        valid={m['id'] for m in mentions}
        if set(selections['choices'])-valid:raise ValueError('Selection refers to nonexistent mention')
        # Keep everything not matched, including negation and conditions. Closed particles are labels, not deleted text.
        mask=[False]*len(question)
        for lo,hi in kept:
            for i in range(lo,hi):mask[i]=True
        unmatched=[]; language=[]
        for token in re.finditer(r'\w+',question):
            start=token.start()
            while start<token.end():
                if mask[start]:start+=1;continue
                end=start+1
                while end<token.end() and not mask[end]:end+=1
                row={'start':start,'end':end,'text':question[start:end]}
                (language if row['text'] in JOSA else unmatched).append(row)
                start=end
        return {'schema_version':VERSION,'query_id':query_id,'question':question,'mentions':mentions,
                'suppressed':suppressed,'language_tokens':language,'unmatched':unmatched,
                'llm_calls':0,'legal_applicability':'NOT_DETERMINED'}

    def articles(self, result, *, documents=None, limit=20):
        """Read source coordinates after a query choice; occurrence is not a sense assertion."""
        if not 1<=limit<=100:raise ValueError('limit must be 1..100')
        identity=self.report['identity']; corpus=Path(identity['corpus'])
        if sha(corpus/'store.sqlite')!=identity['corpus_sha256']:
            raise ValueError('Corpus changed; rebuild the glossary')
        if result['query_id']!=digest({'question':result['question'],'dictionary':self.report['dictionary_sha256']}):
            raise ValueError('Query/index mismatch')
        with closing(read_db(corpus/'store.sqlite')) as source:
            known={r[0] for r in source.execute('SELECT document_id FROM document')}
            allowed=set(documents) if documents is not None else known
            if allowed-known:raise ValueError('Unknown document filter')
            for mention in result['mentions']:
                mention['hits']=[];mention['hit_count']=0
                if not mention['selected'] or mention['status']=='OVERLAP_REVIEW_REQUIRED':continue
                keys=set()
                for ident in mention['selected']['source_entries']:
                    keys.update(r[0] for r in self.db.execute("SELECT key FROM surface WHERE entry_id=? AND kind IN ('SOURCE_LABEL','SOURCE_LABEL_PART')",(ident,)))
                hits={}
                for key in sorted(keys):
                    for r in self.db.execute('SELECT * FROM occurrence WHERE key=? ORDER BY document_id,CAST(block_id AS INTEGER),start',(key,)):
                        if r['document_id'] not in allowed:continue
                        loc=(r['document_id'],r['block_id'])
                        if loc not in hits:hits[loc]=dict(r)
                mention['hit_count']=len(hits);mention['hits_truncated']=len(hits)>limit
                for loc,r in sorted(hits.items(),key=lambda item:(item[0][0],int(item[0][1])))[:limit]:
                    block=source.execute('SELECT * FROM source_block WHERE document_id=? AND block_id=?',loc).fetchone()
                    if not block or compact(block['text'][r['start']:r['end']])!=r['key']:raise ValueError('Occurrence evidence drift')
                    doc=source.execute('SELECT name FROM document WHERE document_id=?',(loc[0],)).fetchone()
                    uid=block['unit_id']; ancestors=[];seen=set()
                    while uid is not None:
                        uid=str(uid)
                        if uid in seen:raise ValueError('Source hierarchy cycle')
                        seen.add(uid)
                        unit=source.execute('SELECT parent_id,json FROM source_unit WHERE document_id=? AND unit_id=?',(loc[0],uid)).fetchone()
                        if not unit:break
                        payload=json.loads(unit['json'])
                        ancestors.append({'unit_id':uid,'title':payload.get('title') or payload.get('surface',''),'family':payload.get('family')})
                        uid=unit['parent_id']
                    mention['hits'].append({**r,'document_name':doc[0],'text':block['text'],
                        'ancestors':list(reversed(ancestors)),'source_sha256':block['source_artifact_sha256'],
                        'basis':'LITERAL_CORPUS_OCCURRENCE','sense_applicability':'UNREVIEWED'})
        return result
