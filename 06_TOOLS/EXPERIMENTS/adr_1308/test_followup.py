from pathlib import Path
from types import SimpleNamespace as NS
from contextlib import contextmanager
import importlib.util,sys,json,sqlite3,os
import pytest

def test_recovery_only_current_open_need_actions(monkeypatch):
    from semantic_runtime.legal_agent import request_repair as rr,need_continuity,read_judgment
    needs={'n':{'status':'OPEN','text':'need','declarations':[{'proposed_actions':[{'target':'A'}]}]},
           'closed':{'status':'RESOLVED','text':'closed','declarations':[{'proposed_actions':[{'target':'B'}]}]}}
    state={'history':['old','latest'],'receipts':{'old':{'next_actions':[{'target':'OLD','missing_need':'need'}]},
        'latest':{'next_actions':[{'target':'C','missing_need':'need'},{'target':'D','missing_need':'closed'}]}}}
    monkeypatch.setattr(need_continuity,'known_needs',lambda *a:needs)
    monkeypatch.setattr(read_judgment,'state_for',lambda *a:state)
    inv=NS(policy={'read_judgment':True});data={'sources':[{'text':'verified'}]}
    assert rr.recovery_need_targets(inv,data)=={'A','C'}
    needs['n']['status']='RESOLVED';assert rr.recovery_need_targets(inv,data)==set()
    assert rr.recovery_need_targets(inv,{'sources':[]}) is None

def test_sqlite_navigation_cache_is_bound_and_copies():
    from test_queries import sqlite_index
    i,db=sqlite_index();statements=[];db.set_trace_callback(statements.append)
    first=i.search_metadata(db,['alpha'],{'s1'});calls=len(statements);first[0]['block_ids'].append('999')
    second=i.search_metadata(db,['alpha'],{'s1'});assert len(statements)==calls and '999' not in second[0]['block_ids']
    i.search_metadata(db,['alpha'],{'s2'});assert len(statements)>calls

@pytest.fixture
def loader(monkeypatch):
    import semantic_runtime
    root=Path(semantic_runtime.__file__).parents[2]
    package=Path(os.environ['R7_TEST_PACKAGE']) if os.environ.get('R7_TEST_PACKAGE') else root/'08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_seek_20261103_r7/package'
    monkeypatch.syspath_prepend(str(package))
    for p in package.glob('*.py'):monkeypatch.delitem(sys.modules,p.stem,raising=False)
    import reduced_export,fast_export,fast_loader,run_full
    return NS(asset=reduced_export,export=fast_export,load=fast_loader,base=run_full,root=root)

@pytest.fixture
def asset(tmp_path):
    p=tmp_path/'units.sqlite';db=sqlite3.connect(p)
    db.execute('CREATE TABLE unit(key TEXT PRIMARY KEY,document_id,source_id,json)')
    db.execute('CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body)')
    db.execute('CREATE TABLE label(source,node_id)');db.execute('CREATE VIRTUAL TABLE words USING fts5(body)')
    for n,body in enumerate(['alpha alpha beta','alpha beta gamma','delta']):
        db.execute('INSERT INTO unit VALUES(?,?,?,?)',(str(n),'D1','s'+str(n),json.dumps({'text':body})))
        db.execute('INSERT INTO unit_fts VALUES(?,?)',(str(n),body));db.execute('INSERT INTO label VALUES(?,?)',('test',str(n)))
        db.execute('INSERT INTO words VALUES(?)',(body,))
    for rowid in (-1,0):
        db.execute('INSERT INTO label(rowid,source,node_id) VALUES(?,?,?)',(rowid,'test',str(rowid)))
        db.execute('INSERT INTO words(rowid,body) VALUES(?,?)',(rowid,'edge alpha'))
    db.commit();db.close();return p

@pytest.mark.parametrize('excluded',[(),('label',)])
def test_producer_resume_every_boundary_preserves_payload_and_id(loader,asset,excluded):
    oldpath=loader.root/'08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_fast_20261103_r6/package/reduced_export.py'
    spec=importlib.util.spec_from_file_location('_old_export',oldpath);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    before=list(old.asset_rows(asset,'fts/units.sqlite',excluded_tables=excluded))
    after=list(loader.asset.asset_rows(asset,'fts/units.sqlite',excluded_tables=excluded))
    assert after==before
    for n,row in enumerate(after):
        resumed=list(loader.asset.asset_rows(asset,'fts/units.sqlite',excluded_tables=excluded,resume=row.producer_cursor))
        assert resumed==before[n+1:],row.producer_cursor

def test_posting_resume_does_not_rebuild_completed_lengths(loader,asset,monkeypatch):
    rows=list(loader.asset.asset_rows(asset,'fts/units.sqlite'))
    cursor=next(r.producer_cursor for r in rows if r.producer_cursor['section']=='posting')
    phases=[];monkeypatch.setattr(loader.asset,'report',lambda phase,**kw:phases.append(phase))
    list(loader.asset.asset_rows(asset,'fts/units.sqlite',resume=cursor))
    # A later, different FTS table still needs its own lengths.
    assert phases.count('FTS_LENGTH_AGGREGATE')==1

def test_loader_ack_resume_and_legacy_checkpoint(loader,asset,monkeypatch):
    from itertools import islice
    monkeypatch.setattr(loader.load,'mapped_query',lambda release,row:dict(row))
    def grouped(rows):
        it=iter(rows)
        while batch:=list(islice(it,3)):yield batch
    monkeypatch.setattr(loader.base,'grouped',grouped)
    source={'source_manifest':{}};expected=list(loader.export.projected_rows(asset,'units.sqlite',source,mode='full'))
    class Job:
        def __init__(self,state):self.state={'query':{'units.sqlite':state}};self.rows=[];self.progress=NS(emit=lambda *a,**k:None)
        def guard(self):pass
        def save(self):pass
        def batch(self,key,rows,**kw):self.rows.extend(rows);self.state[kw['section']][kw['slot']]=kw['next_progress']
    for state in ({'rows':6},{'rows':6,'producer_cursor':expected[5].producer_cursor}):
        job=Job(state);loader.load.load_query(job,asset.parent,source,{},['units.sqlite'],'full')
        assert job.rows==expected[6:] and job.state['query']['units.sqlite']=={'rows':len(expected),'complete':True}

def test_package_manifest_and_r6_resume_parent(loader):
    from gold_io import digest
    assert loader.base.verify_code()
    p=loader.root/'08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_fast_20261103_r6/package/CODE_MANIFEST.json'
    parent=digest(json.loads(p.read_text()));rows=json.loads((loader.base.HERE/'RESUME_PARENTS.json').read_text())['parents']
    assert {r['mode'] for r in rows if r['code_binding']==parent}=={'full','reduced'}

def test_current_publications_batch_rechecks_authority():
    from semantic_runtime.ontology_work.wiki_repository import WorkspaceTransactions
    refs=[{'publication_id':'p1','bundle_id':'b1','package_sha256':'h1'},{'publication_id':'p2','bundle_id':'b2','package_sha256':'h2'}]
    class Repo(WorkspaceTransactions):
        tables={'publication':'PUB','head':'HEAD','anchor':'ANCHOR'}
        rows=[('p1','b1','h1','D1'),('p2','b2','h2','D2')]
        calls=0
        @contextmanager
        def session(self):yield None
        def execute(self,c,sql,binds):
            self.calls+=1;assert len(binds)==4
            return NS(fetchmany=lambda limit:self.rows[:limit])
    r=Repo();assert r.current_publications(refs,{'D1'})=={'p1':True,'p2':False} and r.calls==1
    r.rows=[];assert r.current_publications(refs,{'D1','D2'})=={'p1':False,'p2':False} and r.calls==2


def test_literal_search_constructs_only_selected_cards():
    from semantic_runtime.legal_agent.exploration_tools import ExplorationTools
    rows=[{'document_id':'D1','block_id':str(n),'unit_id':str(n//2)} for n in range(8)]
    built=[]
    stub=NS(docs_bounds=lambda t:(['D1'],None),handle=lambda *a:'L',store=NS(is_oracle_query=True,db=NS(execute=lambda *a:rows)),
        page=lambda rows,offset:(rows[offset:offset+1],offset+1 if offset+1<len(rows) else None),
        node_card=lambda did,uid,**kw:(built.append((did,uid)) or {'target':uid}))
    result=ExplorationTools.search(stub,{'target':'D1','query':'alpha','mode':'literal'},0)
    assert result[0]==[{'target':'0'}] and result[1]==1 and result[3]['search_receipt']['total']==4
    assert built==[('D1','0')]


def test_glossary_page_reuse_never_crosses_acl():
    from semantic_runtime.oracle_query_glossary import Glossary
    from semantic_runtime.oracle_dp_io import DPError
    from test_queries import request
    g=Glossary.__new__(Glossary);g.request=request();g.binding={};g.check_unchanged=lambda:None
    calls=[];g._lookup=lambda *a,**k:(calls.append(k) or {'concepts':[{'id':'a'}]})
    first=g.lookup('test');first['concepts'][0]['id']='changed'
    assert g.lookup('test')=={'concepts':[{'id':'a'}]} and len(calls)==1
    g.request.sources.allowed={'D2'}
    with pytest.raises(DPError,match='BINDING'):g.lookup('test')
