"""Versioned term/source navigation index; source content remains immutable."""
import argparse
from collections import defaultdict
from collections.abc import Mapping
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from .contracts import sha, write, digest
from .term_tools import TermTools
from . import term_tools as term_tools_module

ARTICLE = re.compile(r'제\d+(?:-\d+)?조(?:의\d+)?')

def ro(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,check_same_thread=False)
    db.row_factory=sqlite3.Row
    return db

def text_sha(text):return hashlib.sha256(text.encode()).hexdigest()

def compile_index(store, legal, dictionary, output, *, glossary=None, linkage_report=None, knowledge=None):
    """Explicit selected stores only; no experiment products, mocks, or model calls."""
    output=Path(output)
    if output.exists():raise ValueError('immutable term index already exists')
    output.mkdir(parents=True)
    db=sqlite3.connect(output/'navigation.sqlite');db.row_factory=sqlite3.Row
    db.executescript('''
      CREATE TABLE term(id TEXT PRIMARY KEY,json TEXT);
      CREATE TABLE edge(id TEXT PRIMARY KEY,json TEXT);
      CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
      CREATE INDEX source_document ON source(document_id);
      CREATE TABLE occurrence(term_id TEXT,source_id TEXT,PRIMARY KEY(term_id,source_id));
      CREATE INDEX occurrence_source ON occurrence(source_id);
      CREATE TABLE definition(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
      CREATE INDEX definition_document ON definition(document_id);
      CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
      CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));
      CREATE TABLE source_unit_map(source_id TEXT,unit_id TEXT,parent_id TEXT,ordinal TEXT,surface TEXT,block_ids TEXT,PRIMARY KEY(source_id,unit_id));
    ''')
    lg=ro(legal);terms=[]
    columns={r['name'] for r in lg.execute('PRAGMA table_info(entry)')}
    query=("SELECT id,label,homonym FROM entry WHERE id LIKE 'moleg:knowledge_terms:%' AND length(label)>=2 ORDER BY id"
           if 'homonym' in columns else "SELECT id,label,NULL AS homonym FROM entry WHERE length(label)>=2 ORDER BY id")
    if 'source' in columns:
        query=query.replace(' ORDER BY id', " AND source!='corpus_definition' ORDER BY id")
    for r in lg.execute(query):
        t={**dict(r),'status':'SOURCE_TERM_NOT_CANONICAL_MEANING'};terms.append(t)
        db.execute('INSERT INTO term VALUES (?,?)',(t['id'],json.dumps(t,ensure_ascii=False)))
    if lg.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='edge'").fetchone():
        known={t['id'] for t in terms}
        for r in lg.execute("SELECT * FROM edge WHERE status='CONNECTED' ORDER BY id"):
            if r['source_id'] not in known or r['target_id'] not in known:continue
            e={'id':r['id'],'source':r['source_id'],'target':r['target_id'],'code':r['code'],'status':r['status'],'reason':r['reason']}
            db.execute('INSERT INTO edge VALUES (?,?)',(e['id'],json.dumps(e,ensure_ascii=False)))
    lg.close();matcher=TermTools([],terms,[]);dc=ro(dictionary);definitions=0;references=0;unresolved=0;rejected_defs=0;docs=0
    projector=None
    if glossary is not None or linkage_report is not None or knowledge is not None:
        if glossary is None or linkage_report is None:raise ValueError('glossary and linkage report must be explicit together')
        from .term_links import LinkProjector,normalized
        projector=LinkProjector(db,store,dictionary,glossary,linkage_report,knowledge)
    for doc in store.db.execute('SELECT document_id,name,source_artifact_sha256 FROM document ORDER BY document_id').fetchall():
        did=doc['document_id'];units={r['unit_id']:dict(r)|{'value':json.loads(r['json'])} for r in store.db.execute('SELECT * FROM source_unit WHERE document_id=?',(did,))}
        @lru_cache(None)
        def root(uid):
            current=uid;seen=set();chosen=None
            while current in units:
                if current in seen:raise ValueError('source ancestor cycle')
                seen.add(current);u=units[current]
                if u['value'].get('family') in ['kr_article','kr_조']:chosen=current
                current=str(u['parent_id']) if u['parent_id'] is not None else None
            return chosen or uid
        groups=defaultdict(list);block_sources={};original_blocks={}
        for b in store.db.execute('SELECT * FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)',(did,)):
            original_blocks[str(b['block_id'])]=dict(b)
            uid=root(b['unit_id']) if b['unit_id'] is not None else 'block:'+b['block_id']
            groups[uid].append({'block_id':b['block_id'],'text':b['text']})
        byid={};heads=defaultdict(list)
        for uid,blocks in groups.items():
            sid='article:'+text_sha(did+'|'+str(uid))[:24];u=units.get(uid,{}).get('value',{});surface=u.get('surface','');title=u.get('title','');heading=(surface+' '+title).strip() or blocks[0]['text'].split('\n')[0][:160]
            # Some formats embed the article label in title rather than surface.
            match=ARTICLE.match(heading);article=match.group() if match else None
            text='\n'.join(b['text'] for b in blocks)
            s={'id':sid,'document_id':did,'document_name':doc['name'],'unit_id':uid if uid in units else None,'block_id':blocks[0]['block_id'],'heading':heading,'article_coordinate':{'doc_id':did,'node':uid},'source_artifact_sha256':doc['source_artifact_sha256'],'blocks':blocks,'text':text,'text_sha256':text_sha(text)}
            byid[sid]=s
            if article:heads[article].append(sid)
            for b in blocks:block_sources[b['block_id']]=sid
            db.execute('INSERT INTO source VALUES (?,?,?,?)',(sid,did,article,json.dumps(s,ensure_ascii=False)))
            db.executemany('INSERT INTO occurrence VALUES (?,?)',[(t,sid) for t in matcher.match(text)])
            if projector:db.execute('INSERT INTO source_literal VALUES (?,?,?)',(sid,did,normalized(text)))
        # 조 안의 항·호·목 마디 — 인용 `제4조제1항` 을 그 조의 실제 첫 하위 마디로 잇는다.
        # 마커 모양(①·1)·(1))이 아니라 구조 위치와 서수로 찾으므로 틀이 달라도 같다.
        blocks_of=defaultdict(list)
        for bid,b in original_blocks.items():
            if b['unit_id'] is not None:blocks_of[str(b['unit_id'])].append(bid)
        for uid,u in units.items():
            top=root(uid)
            if top==uid or top not in groups:continue
            sid='article:'+text_sha(did+'|'+str(top))[:24]
            db.execute('INSERT OR IGNORE INTO source_unit_map VALUES (?,?,?,?,?,?)',(sid,str(uid),str(u['parent_id']) if u['parent_id'] is not None else None,
                       json.dumps(u['value'].get('ordinal')),u['value'].get('surface') or '',json.dumps(blocks_of.get(str(uid),[]))))
        if projector:projector.document(did,original_blocks,block_sources)
        for row in dc.execute('SELECT * FROM corpus_definition WHERE document_id=?',(did,)):
            d=dict(row);sid=block_sources.get(d['block_id']);s=byid.get(sid)
            if not s or not any(b['block_id']==d['block_id'] and b['text']==d['source_text'] for b in s['blocks']) or text_sha(d['source_text'])!=d['source_text_sha256']:
                rejected_defs+=1;continue
            tids=matcher.labels.get(d['key'],[])
            if projector:tids=sorted(set(tids)|{r[0] for r in db.execute('SELECT term_id FROM term_surface WHERE key=?',(d['key'],))})
            d.update(term_ids=tids,source_id=sid,document_name=doc['name'],source_artifact_sha256=s['source_artifact_sha256'],origin='existing_corpus_definition',match_kind='LABEL_CANDIDATE',verification='EXACT_BLOCK_AND_HASH')
            for k in ['scope_hint','location','reference_hints']:d[k]=json.loads(d[k])
            db.execute('INSERT INTO definition VALUES (?,?,?)',(d['id'],did,json.dumps(d,ensure_ascii=False)));definitions+=1
        docs+=1;db.commit()
        if docs%20==0:print('Indexed documents',docs,flush=True)
    from .term_references import compile_references
    references,unresolved=compile_references(db)
    dc.close();linkage=None
    if projector:
        try:linkage=projector.finish()
        finally:projector.close()
    db.execute('CREATE TABLE term_stats AS SELECT term_id,count(*) AS n FROM occurrence GROUP BY term_id');db.execute('CREATE UNIQUE INDEX term_stats_id ON term_stats(term_id)');db.commit()
    counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['term','edge','source','occurrence','definition','reference']}
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
    manifest={'schema_version':'term-navigation-index-v2','generation_id':store.manifest['generation_id'],'source_store_sha256':store.manifest['store_sha256'],'source_manifest_sha256':digest({k:v for k,v in store.manifest.items() if k!='navigation'}),'legal_sha256':sha(legal),'dictionary_sha256':sha(dictionary),'index_sha256':sha(output/'navigation.sqlite'),'counts':counts,'document_count':docs,'rejected_definitions':rejected_defs,'unresolved_references':unresolved,'quality_certified':False,'compiler_sha256':sha(__file__),'term_tools_sha256':sha(term_tools_module.__file__)}
    if linkage:manifest.update(schema_version='term-navigation-index-v3',linkage=linkage)
    write(output/'manifest.json',manifest);return manifest

class SourceMap(Mapping):
    def __init__(self,db,table='source'):self.db=db;self.table=table;self.cache={}
    def __getitem__(self,key):
        if key not in self.cache:
            r=self.db.execute('SELECT json FROM source WHERE id=?',(key,)).fetchone()
            if r is None:raise KeyError(key)
            self.cache[key]=json.loads(r[0])
        return self.cache[key]
    def __iter__(self):return (r[0] for r in self.db.execute('SELECT id FROM source'))
    def __len__(self):return self.db.execute('SELECT count(*) FROM source').fetchone()[0]

class OccurrenceMap:
    def __init__(self,db):self.db=db
    def __getitem__(self,key):return {r[0] for r in self.db.execute('SELECT term_id FROM occurrence WHERE source_id=?',(key,))}

class IndexTools(TermTools):
    def __init__(self,db,terms,relations,scope):
        super().__init__([],terms,relations)
        self.db=db;self.scope=set(scope);self.sources=SourceMap(db);self.source_terms=OccurrenceMap(db)
        self.df={r[0]:r[1] for r in db.execute('SELECT term_id,n FROM term_stats')}
        self.definitions={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,json FROM definition WHERE document_id IN ('+','.join('?' for _ in scope)+')',scope)} if scope else {}
        self.document_ids={r[0] for r in db.execute('SELECT DISTINCT document_id FROM source')}
        self.has_literal=bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='source_literal'").fetchone())
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='term_surface'").fetchone():
            for tid,key,value in db.execute('SELECT DISTINCT term_id,key,text FROM term_surface'):
                for label in dict.fromkeys((key,value)):
                    if tid not in self.labels[label]:self.labels[label].append(tid)
            self.prefix=defaultdict(list)
            for label in self.labels:self.prefix[label[:2]].append(label)
            for prefix in self.prefix:self.prefix[prefix].sort(key=lambda value:(-len(value),value))
    def validate_scope(self,scope):
        if not scope or not set(scope)<=self.scope or not set(scope)<=self.document_ids:raise ValueError('invalid source scope')
        return list(dict.fromkeys(scope))
    def search_labels(self,labels,scope,limit=3,exclude_ids=()):
        from .term_links import normalized
        scope=self.validate_scope(scope)
        labels=list(dict.fromkeys(normalized(x) for x in labels if 2<=len(normalized(x))<=80))[:8]
        if not labels:return []
        if type(limit) is not int or not 1<=limit<=8:raise ValueError('invalid source result limit')
        if not self.has_literal:
            # Older v2 remains readable; normalize each row lazily, without a second corpus in memory.
            self.db.create_function('normalize_source',1,normalized,deterministic=True)
            table="(SELECT id,document_id,normalize_source(json_extract(json,'$.text')) AS text FROM source)"
        else:table='source_literal'
        excluded=tuple(exclude_ids);exsql=' AND id NOT IN ('+','.join('?' for _ in excluded)+')' if excluded else ''
        scores='+'.join('(instr(text,?)>0)' for _ in labels)
        sql='SELECT id,text,('+scores+') AS score FROM '+table+' WHERE document_id IN ('+','.join('?' for _ in scope)+') AND ('+' OR '.join('instr(text,?)>0' for _ in labels)+')'+exsql+' ORDER BY score DESC,id LIMIT ?'
        deadline=time.monotonic()+3;self.db.set_progress_handler(lambda:int(time.monotonic()>deadline),10000)
        try:rows=self.db.execute(sql,(*labels,*scope,*labels,*excluded,limit)).fetchall()
        finally:self.db.set_progress_handler(None,0)
        return [{'id':r['id'],'score':r['score'],'matched_labels':[x for x in labels if x in r['text']]} for r in rows]
    def search(self,term_ids,scope,limit=3,exclude_ids=()):
        import math
        if not set(scope)<=self.scope or not set(term_ids)<=self.terms.keys():raise ValueError('term search scope/ID mismatch')
        if not term_ids or not scope:return []
        marks=lambda xs:','.join('?' for _ in xs)
        sql='SELECT o.source_id,o.term_id FROM occurrence o JOIN source s ON s.id=o.source_id WHERE o.term_id IN ('+marks(term_ids)+') AND s.document_id IN ('+marks(scope)+')'
        ranked={};excluded=set(exclude_ids);total=len(self.sources)
        for sid,tid in self.db.execute(sql,list(term_ids)+list(scope)):
            if sid in excluded:continue
            row=ranked.setdefault(sid,{'id':sid,'score':0,'matched_term_ids':[]});row['matched_term_ids'].append(tid);row['score']+=math.log((total+1)/(self.df.get(tid,0)+1))+1
        return sorted(ranked.values(),key=lambda x:(-x['score'],x['id']))[:limit]
    def navigation_menu(self,seen,searched,question,scope,*args,**kwargs):
        if not set(scope)<=self.scope:raise ValueError('navigation scope mismatch')
        if seen:
            query='SELECT DISTINCT r.id,r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id IN ('+','.join('?' for _ in seen)+')'
            self.references.update({r[0]:json.loads(r[1]) for r in self.db.execute(query,seen)})
        return super().navigation_menu(seen,searched,question,scope,*args,**kwargs)

class TermIndex:
    def __init__(self,path,store):
        path=Path(path);self.manifest=json.loads((path/'manifest.json').read_text())
        m=self.manifest
        if m.get('schema_version') not in {'term-navigation-index-v2','term-navigation-index-v3'}:raise ValueError('unsupported term index schema')
        if m['source_store_sha256']!=store.manifest['store_sha256'] or m['source_manifest_sha256']!=digest({k:v for k,v in store.manifest.items() if k!='navigation'}) or m['index_sha256']!=sha(path/'navigation.sqlite'):raise ValueError('term index generation/hash mismatch')
        self.path=path;db=ro(path/'navigation.sqlite');self.terms=[json.loads(r[0]) for r in db.execute('SELECT json FROM term')];self.relations=[json.loads(r[0]) for r in db.execute('SELECT json FROM edge')];db.close()
    def tools(self,scope):return IndexTools(ro(self.path/'navigation.sqlite'),self.terms,self.relations,list(scope))

def main():
    from .storage import Store
    p=argparse.ArgumentParser();p.add_argument('--generation',required=True,type=Path);p.add_argument('--legal',required=True,type=Path);p.add_argument('--dictionary',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--glossary',type=Path);p.add_argument('--linkage-report',type=Path);p.add_argument('--knowledge',type=Path)
    a=p.parse_args();store=Store(a.generation)
    try:print(json.dumps(compile_index(store,a.legal,a.dictionary,a.output,glossary=a.glossary,
        linkage_report=a.linkage_report,knowledge=a.knowledge),ensure_ascii=False,indent=2))
    finally:store.close()
if __name__=='__main__':main()
