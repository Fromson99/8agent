"""Lexical definition evidence, scoped to immutable source document versions.

These records are source hints, never canonical legal definitions or inferred
applicability. No API/model calls, background-word extraction or alias inference.
"""
import hashlib
import json
import re
from . import glossary_v1 as v1
from .glossary_alignment import compact

# Keep the existing quoted-definition vocabulary policy, with offsets intact.
QUOTED = re.compile(r'["“「]([^"”」\n]{1,100})["”」]\s*(?:이란|란|이라\s*함은|라\s*함은)')
SCOPE = re.compile(r'이\s*(법률|법|시행령|시행규칙|규정|규칙|세칙|지침|장|절|관|조|항|호)\s*에서')
END = re.compile(r'(?:말한다|뜻한다|의미한다)\s*[.]')
REFERENCE = re.compile(r'「([^」]+)」\s*(제\s*\d+(?:\s*-\s*\d+)*\s*조(?:의\s*\d+)?(?:\s*제\s*\d+\s*항)?)[^。\n.]{0,80}?(?:따른|정한|정하는)')


def tables(db):
    db.executescript('''
      CREATE TABLE corpus_document(document_id TEXT PRIMARY KEY,name TEXT,source_sha256 TEXT);
      CREATE TABLE corpus_definition(id TEXT PRIMARY KEY REFERENCES entry(id),key TEXT,
        document_id TEXT REFERENCES corpus_document(document_id),block_id TEXT,unit_id TEXT,
        term_start INTEGER,term_end INTEGER,definition_start INTEGER,definition_end INTEGER,
        source_text TEXT,source_text_sha256 TEXT,definition_status TEXT,scope_status TEXT,
        scope_hint TEXT,location TEXT,reference_hints TEXT);
      CREATE INDEX corpus_definition_key ON corpus_definition(key);
      CREATE VIEW entry_corpus_link AS SELECT e.id AS entry_id,o.*,d.name AS document_name,
        d.source_sha256 FROM entry e JOIN occurrence o ON o.key=e.key
        JOIN corpus_document d ON d.document_id=o.document_id;
      CREATE VIEW entry_definition_link AS SELECT e.id AS entry_id,d.id AS definition_id,
        CASE WHEN e.id=d.id THEN 'SOURCE_DEFINITION' ELSE 'LABEL_CANDIDATE' END AS match_kind
        FROM entry e JOIN corpus_definition d ON d.key=e.key;
    ''')


def location_for(unit, units):
    chain=[];seen=set()
    while unit is not None and str(unit) in units:
        unit=str(unit)
        if unit in seen:raise ValueError('Cyclic source unit ancestry')
        seen.add(unit);parent,raw=units[unit]
        data=json.loads(raw)
        chain.append({'unit_id':unit,'family':data.get('family'),
                      'surface':data.get('surface'),'title':data.get('title')})
        unit=parent
    return chain


def add(db, source, corpus_hash):
    """Use the bound corpus directly; preserve candidate fragments as unreviewed."""
    for doc in source.execute('SELECT document_id,name,source_artifact_sha256 FROM document ORDER BY document_id'):
        did,name,source_hash=doc
        db.execute('INSERT INTO corpus_document VALUES (?,?,?)',(did,name,source_hash))
        units={str(u):(p,j) for u,p,j in source.execute(
            'SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,))}
        for bid,unit,text in source.execute('SELECT block_id,unit_id,text FROM source_block WHERE document_id=? ORDER BY block_id',(did,)):
            matches=list(QUOTED.finditer(text))
            for index,m in enumerate(matches):
                label=m[1]
                if not compact(label):continue
                boundary=matches[index+1].start() if index+1<len(matches) else len(text)
                closing=END.search(text,m.end(),boundary)
                end=closing.end() if closing else boundary
                start=m.start()
                status='CLOSED_SENTENCE_HINT' if closing else 'CONTINUATION_REQUIRED'
                # Only record explicit scope in the current clause, never assume document-wide.
                prefix_start=max(text.rfind('.',0,start),text.rfind('\n',0,start))+1
                scopes=list(SCOPE.finditer(text,prefix_start,start))
                scope_status='EXPLICIT_SCOPE_HINT' if len(scopes)==1 else 'UNRESOLVED'
                hints=[{'text':s[0],'kind':s[1],'start':s.start(),'end':s.end(),
                        'applies_to':'UNREVIEWED'} for s in scopes]
                references=[{'text':r[0],'document_name':r[1],'article_surface':r[2],
                             'start':r.start(),'end':r.end(),'resolution':'UNREVIEWED'}
                            for r in REFERENCE.finditer(text,m.end(),end)]
                location=location_for(unit,units)
                ident='corpus-definition:'+hashlib.sha256(v1.encode(
                    [corpus_hash,did,str(bid),m.start(1),m.end(1),start,end]).encode()).hexdigest()
                provenance={'document_id':did,'document_name':name,'source_artifact_sha256':source_hash,
                            'corpus_sha256':corpus_hash,'block_id':str(bid),'unit_id':unit,
                            'definition_start':start,'definition_end':end,'definition_status':status,
                            'scope_status':scope_status,'scope_hints':hints,'location':location,
                            'reference_hints':references,'canonical_approval':False}
                v1.add_entry(db,ident,'corpus_definition',label,text[start:end],provenance=provenance)
                db.execute('INSERT INTO corpus_definition VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (ident,compact(label),did,str(bid),unit,m.start(1),m.end(1),start,end,text,
                     hashlib.sha256(text.encode()).hexdigest(),status,scope_status,
                     v1.encode(hints),v1.encode(location),v1.encode(references)))
                # A definition's own quoted headword is exact source evidence even if
                # the general occurrence matcher rejects adjacent punctuation/josa.
                db.execute('INSERT OR IGNORE INTO occurrence VALUES (?,?,?,?,?,?)',
                           (compact(label),did,str(bid),unit,m.start(1),m.end(1)))


def counts(db):
    return {'records':db.execute('SELECT count(*) FROM corpus_definition').fetchone()[0],
            'unique_labels':db.execute('SELECT count(DISTINCT key) FROM corpus_definition').fetchone()[0],
            'definition_status':dict(db.execute('SELECT definition_status,count(*) FROM corpus_definition GROUP BY 1')),
            'scope_status':dict(db.execute('SELECT scope_status,count(*) FROM corpus_definition GROUP BY 1')),
            'finance_unique_labels':db.execute("SELECT count(DISTINCT d.key) FROM corpus_definition d JOIN entry e ON e.key=d.key WHERE e.source IN ('econedu','nts')").fetchone()[0]}
