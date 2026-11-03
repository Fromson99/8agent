from types import SimpleNamespace as NS
from copy import deepcopy
import json,sqlite3,time
import pytest
from semantic_runtime.oracle_query_cache import for_request
from semantic_runtime.oracle_dp_io import DPError,BudgetPause
from semantic_runtime.oracle_query_fulltext import UnitIndex
from semantic_runtime.unit_fulltext import UnitFulltextIndex
from semantic_runtime.oracle_query_db import Connection

def request():
    return NS(release_id='a'*64,sources=NS(allowed=frozenset({'D1'})),sql=NS(deadline=time.monotonic()+60),snapshot=NS(binding_hash='pin'),records=NS(manifest={}))

def test_cache_is_bound_and_returns_copies():
    r=request();c=for_request(r);assert c.put('k',[{'x':1}]);a=c.get('k')[1];a[0]['x']=9
    assert c.get('k')[1]==[{'x':1}]
    r.sources.allowed={'D2'}
    with pytest.raises(DPError,match='BINDING'):c.get('k')

@pytest.mark.parametrize('change',['manifest','release','snapshot','deadline'])
def test_cache_rejects_changed_binding(change):
    r=request();c=for_request(r);c.put('x',[])
    if change=='manifest':r.records.manifest['x']=1
    if change=='release':r.release_id='b'*64
    if change=='snapshot':r.snapshot.binding_hash='other'
    if change=='deadline':r.sql.deadline=0
    with pytest.raises((DPError,BudgetPause)):c.get('x')

def test_cache_bounded_eviction(monkeypatch):
    from semantic_runtime import oracle_query_cache as m
    monkeypatch.setattr(m,'MAX_ENTRIES',2);monkeypatch.setattr(m,'MAX_ENTRY_BYTES',100)
    c=for_request(request());c.put('a',1);c.put('b',2);c.get('a');c.put('c',3)
    assert c.get('b')==(False,None) and c.get('a')==(True,1)
    assert not c.put('large','x'*101)

def test_navigation_only_complete_verified_pages_are_cached():
    from semantic_runtime.oracle_query_matcher import pages
    r=request();calls=[]
    def fetch(kind,**kwargs):calls.append(kwargs);return {'rows':[{'id':'a'}],'next':None}
    r.records.page=fetch
    g=pages(r,'native.unit',document_id='D1');next(g);g.close()
    assert list(pages(r,'native.unit',document_id='D1'))==[{'id':'a'}] and len(calls)==2
    assert list(pages(r,'native.unit',document_id='D1'))==[{'id':'a'}] and len(calls)==2

def index():
    i=UnitIndex.__new__(UnitIndex);i.request=request();i.sql=i.request.sql;i.records=i.request.records
    i.kinds={'unit_fts_posting':'post','unit_fts_length':'length','unit':'unit'}
    i.statistics={'documents':100,'tokens':1000};i.check_unchanged=lambda:None
    return i

@pytest.mark.parametrize('terms,positions',[(['alpha'],False),(['alpha','beta'],False),(['alpha alpha'],True),(['alpha','beta gamma'],True)])
def test_single_token_tf_and_phrase_adjacency(terms,positions):
    i=index();sql,binds=i._matches(terms,NS(document_ids={'D1'}))
    assert ('positions AS' in sql)==positions
    assert "'$.tf'" in sql
    if positions:assert 'JOIN positions' in sql
    assert 'q_sources' not in {n for n,v,t in binds}
    assert ('df AS (SELECT phrase,COUNT(*) AS n FROM frequencies' in sql) if positions else ('COUNT(DISTINCT k) AS n FROM postings' in sql)

def test_source_predicate_uses_physical_owner():
    sql,binds=index()._matches(['alpha'],{'S1'})
    assert 'r.OWNER_ID IN' in sql and 'l.sid IN' not in sql

def test_projection_reused_between_groups_and_hits():
    i=index();calls=[]
    rows=[['k1','D1','s1',-2.0],['k2','D1','s1',-1.0],['k3','D1','s2',-1.0]]
    i.sql.query=lambda sql,binds,limit:(calls.append(sql) or [{'N':3,'ITEMS':json.dumps(rows)}])
    bodies={k:{'key':k,'document_id':d,'source_id':s,'unit_id':k,'block_ids':['1'],'text':'text'} for k,d,s,_ in rows}
    loaded=[]
    i.records.page=lambda kind,lookup_ids,limit:(loaded.extend(lookup_ids) or {'rows':[{'key':k,'json':json.dumps(bodies[k])} for k in lookup_ids]})
    scope=NS(document_ids={'D1'})
    assert i.law_groups_page(i,['alpha'],scope)['items']==[{'document_id':'D1','article_count':2,'unit_count':3}]
    assert i.article_groups_page(i,['alpha'],'D1',scope)['total']==2
    result=i.hit_page(i,['alpha'],'s1',scope,limit=1)
    assert result['total']==2 and loaded==['k1'] and len(calls)==1
    assert i.hit_page(i,['alpha'],'s1',scope,cursor=result['next_cursor'],limit=1)['items'][0]['key']=='k2'
    assert len(calls)==1
    with pytest.raises(DPError,match='CURSOR'):i.hit_page(i,['beta'],'s1',scope,cursor=result['next_cursor'])

@pytest.mark.parametrize('bad',[[['k','D2','s',-1]],[['k','D1','s',-1],['k','D1','s',-2]]])
def test_projection_scope_and_duplicate_rejected(bad):
    i=index();i.sql.query=lambda *a,**k:[{'N':len(bad),'ITEMS':json.dumps(bad)}]
    with pytest.raises(DPError,match='PROJECTION'):i._projection(['alpha'],None)

def sqlite_index():
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE unit(key TEXT PRIMARY KEY,source_id,document_id,json)')
    db.execute('CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body)')
    values=[('k1','s1','u1',['1'],'alpha alpha alpha'),('k2','s1','u2',['2'],'alpha'),('k3','s2',None,['3'],'alpha'),('k4','s2',None,['4'],'alpha beta')]
    for key,sid,uid,blocks,body in values:
        row={'key':key,'source_id':sid,'document_id':'D1','unit_id':uid,'block_ids':blocks,'text':body}
        db.execute('INSERT INTO unit VALUES(?,?,?,?)',(key,sid,'D1',json.dumps(row)));db.execute('INSERT INTO unit_fts VALUES(?,?)',(key,body))
    i=UnitFulltextIndex.__new__(UnitFulltextIndex);i.check_unchanged=lambda:None;i.source_ids=frozenset({'s1','s2'});i.manifest={'index_sha256':'a'*64}
    return i,db

def test_sqlite_article_limit_does_not_limit_units():
    i,db=sqlite_index()
    expected=list(dict.fromkeys(r['source_id'] for r in i.rank_units(db,['alpha'])))
    assert i.rank(db,['alpha'],limit=2)==expected[:2]
    assert i.rank(db,['alpha'],limit=1)==expected[:1]
    assert i.rank(db,['alpha'],limit=0)==[]

@pytest.mark.parametrize('bounds',[None,(2,4),(99,100)])
def test_search_page_preserves_duplicate_nodes_bounds_total_and_only_loads_page(bounds):
    i,db=sqlite_index();old=i.rank_units(db,['alpha'])
    expected={}
    for r in old:
        if bounds and not any(bounds[0]<=int(b)<bounds[1] for b in r['block_ids']):continue
        expected[(r['document_id'],r['unit_id'],r['source_id'] if r['unit_id'] is None else None)]=r
    seen=[];original=i.search_bodies
    i.search_bodies=lambda db,keys:(seen.extend(keys) or original(db,keys))
    first=i.search_page(db,['alpha'],bounds=bounds,limit=1)
    assert first['total']==len(expected) and len(seen)<=1
    actual=list(first['items']);offset=first['next_offset']
    while offset is not None:
        page=i.search_page(db,['alpha'],bounds=bounds,offset=offset,limit=1);actual.extend(page['items']);offset=page['next_offset']
    assert actual==list(expected.values())

@pytest.mark.parametrize('predicate,params,expected',[
    ('id=?',['one'],True),('id IN (?,?)',['one','two'],True),
    ('id=? OR source_id=?',['one','source'],True),
    ('id=? OR document_id IS NULL',['one'],False),
    ('id IN (SELECT value FROM json_each(?))',['["one","two"]'],True),
    ('id IN (?,?)',['one',None],False),('id=?',[''],False)])
def test_key_predicate_pushdown_preserves_boolean_semantics(predicate,params,expected):
    r=request();columns={k:{'type':'text','max_bytes':512,'has_null':False,'has_empty':False} for k in ('id','source_id','document_id')}
    r.records.manifest={'tables':{'sample':{'asset':'sample.sqlite','table':'sample','columns':columns}}}
    c=Connection(r,'sample.sqlite');seen=[];c._pages=lambda sql,binds:(seen.append((sql,binds)) or iter([]))
    list(c.execute('SELECT id FROM sample WHERE '+predicate,params))
    assert bool('AND (r.LOOKUP_ID' in seen[0][0] or 'AND ((r.LOOKUP_ID' in seen[0][0])==expected
    list(c.execute('SELECT id FROM sample WHERE '+predicate,params));assert len(seen)==1

def test_oracle_literal_empty_result_no_args_overwrite():
    from semantic_runtime.legal_agent.exploration_tools import ExplorationTools
    stub=NS(docs_bounds=lambda t:(['D1'],None),handle=lambda *a:'L',store=NS(is_oracle_query=True,db=NS(execute=lambda *a:[])),page=lambda rows,offset:(rows,None))
    result=ExplorationTools.search(stub,{'target':'D1','query':'alpha','mode':'literal'},0)
    assert result[3]['search_receipt']['searched_target']=='D1'


def test_document_scope_never_reuses_equal_named_source_scope():
    i=index();calls=[]
    def query(sql,binds,limit):
        calls.append(sql)
        values=[] if any(n=='q_sources' for n,v,t in binds) else [['k1','D1','s1',-1],['k2','D1','s2',-1]]
        return [{'N':len(values),'ITEMS':json.dumps(values)}]
    i.sql.query=query
    page=i._page(['alpha'],NS(document_ids={'D1'}),'rank_keys',limit=1)
    assert page['total']==2
    assert i._page(['alpha'],{'D1'},'rank_keys',limit=1)['total']==0
    assert len(calls)==2
    with pytest.raises(DPError,match='CURSOR'):
        i._page(['alpha'],{'D1'},'rank_keys',limit=1,cursor=page['next_cursor'])
