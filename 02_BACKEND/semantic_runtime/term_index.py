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
from .contracts import sha, write, digest
from .term_tools import TermTools

ARTICLE = re.compile(r'제\d+(?:-\d+)?조(?:의\d+)?')

def ro(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,check_same_thread=False)
    db.row_factory=sqlite3.Row
    return db

def text_sha(text):return hashlib.sha256(text.encode()).hexdigest()

def compile_index(store, legal, dictionary, output):
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
    ''')
    lg=ro(legal);terms=[]
    columns={r['name'] for r in lg.execute('PRAGMA table_info(entry)')}
    query=("SELECT id,label,homonym FROM entry WHERE id LIKE 'moleg:knowledge_terms:%' AND length(label)>=2 ORDER BY id"
           if 'homonym' in columns else "SELECT id,label,NULL AS homonym FROM entry WHERE length(label)>=2 ORDER BY id")
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
        groups=defaultdict(list);block_sources={}
        for b in store.db.execute('SELECT * FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)',(did,)):
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
        for row in dc.execute('SELECT * FROM corpus_definition WHERE document_id=?',(did,)):
            d=dict(row);sid=block_sources.get(d['block_id']);s=byid.get(sid)
            if not s or not any(b['block_id']==d['block_id'] and b['text']==d['source_text'] for b in s['blocks']) or text_sha(d['source_text'])!=d['source_text_sha256']:
                rejected_defs+=1;continue
            d.update(term_ids=matcher.labels.get(d['key'],[]),source_id=sid,document_name=doc['name'],source_artifact_sha256=s['source_artifact_sha256'],origin='existing_corpus_definition',match_kind='LABEL_CANDIDATE',verification='EXACT_BLOCK_AND_HASH')
            for k in ['scope_hint','location','reference_hints']:d[k]=json.loads(d[k])
            db.execute('INSERT INTO definition VALUES (?,?,?)',(d['id'],did,json.dumps(d,ensure_ascii=False)));definitions+=1
        for sid,s in byid.items():
            for b in s['blocks']:
                text=b['text']
                if text==s['blocks'][0]['text'] and len(text)<100 and text.startswith('제') and text.endswith(')'):continue
                for m in ARTICLE.finditer(text):
                    loc=m.group()
                    foreign=bool(re.search(r'「|(?:법|시행령|세칙)\s*제\d',text))
                    targets=heads.get(loc,[]) if not foreign and '부터' not in text and '내지' not in text else []
                    targets=[x for x in targets if x!=sid]
                    if len(targets)!=1:targets=[]
                    ident='ref:'+text_sha(sid+'|'+b['block_id']+'|'+loc)[:20]
                    r={'id':ident,'source_id':sid,'document_id':did,'block_id':b['block_id'],'source_text':text,'source_text_sha256':text_sha(text),'locator':loc,'mention_start':m.start(),'mention_end':m.end(),'target_source_ids':targets,'resolution':'EXACT_SAME_DOCUMENT_ARTICLE' if targets else 'UNRESOLVED','reason':None if targets else 'external/range/self/ambiguous/missing target','navigation_hint':'준용 단서' if '준용' in text else '인용 단서','origins':['raw_explicit_article_hint']}
                    inserted=db.execute('INSERT OR IGNORE INTO reference VALUES (?,?,?)',(ident,did,json.dumps(r,ensure_ascii=False))).rowcount
                    if inserted:
                        references+=1;unresolved+=not bool(targets)
                        db.executemany('INSERT INTO reference_end VALUES (?,?)',[(x,ident) for x in [sid]+targets])
        docs+=1;db.commit()
        if docs%20==0:print('Indexed documents',docs,flush=True)
    dc.close();db.execute('CREATE TABLE term_stats AS SELECT term_id,count(*) AS n FROM occurrence GROUP BY term_id');db.execute('CREATE UNIQUE INDEX term_stats_id ON term_stats(term_id)');db.commit()
    counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['term','edge','source','occurrence','definition','reference']}
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
    manifest={'schema_version':'term-navigation-index-v2','generation_id':store.manifest['generation_id'],'source_store_sha256':store.manifest['store_sha256'],'source_manifest_sha256':digest({k:v for k,v in store.manifest.items() if k!='navigation'}),'legal_sha256':sha(legal),'dictionary_sha256':sha(dictionary),'index_sha256':sha(output/'navigation.sqlite'),'counts':counts,'document_count':docs,'rejected_definitions':rejected_defs,'unresolved_references':unresolved,'quality_certified':False,'compiler_sha256':sha(__file__),'term_tools_sha256':sha(Path(__file__).with_name('term_tools.py'))}
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
        if m['source_store_sha256']!=store.manifest['store_sha256'] or m['source_manifest_sha256']!=digest({k:v for k,v in store.manifest.items() if k!='navigation'}) or m['index_sha256']!=sha(path/'navigation.sqlite'):raise ValueError('term index generation/hash mismatch')
        self.path=path;db=ro(path/'navigation.sqlite');self.terms=[json.loads(r[0]) for r in db.execute('SELECT json FROM term')];self.relations=[json.loads(r[0]) for r in db.execute('SELECT json FROM edge')];db.close()
    def tools(self,scope):return IndexTools(ro(self.path/'navigation.sqlite'),self.terms,self.relations,list(scope))

def main():
    from .storage import Store
    p=argparse.ArgumentParser();p.add_argument('--generation',required=True,type=Path);p.add_argument('--legal',required=True,type=Path);p.add_argument('--dictionary',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();store=Store(a.generation)
    try:print(json.dumps(compile_index(store,a.legal,a.dictionary,a.output),ensure_ascii=False,indent=2))
    finally:store.close()
if __name__=='__main__':main()
