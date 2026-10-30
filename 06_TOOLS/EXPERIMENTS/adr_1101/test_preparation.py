"""Prospectively fixed contracts, synthetic data and no model/network calls."""
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace as NS
import pytest
import jsonschema
from semantic_runtime.navigation_match import ReverseMatcher, SurfaceIndex
from semantic_runtime.storage import Store
from semantic_runtime import unit_fulltext as fts
from semantic_runtime.legal_agent import schema_preparation as sp
from semantic_runtime.legal_agent import unit_reading as ur, tool_availability as ta
from semantic_runtime.legal_agent import law_navigation as ln, law_candidates as lc
from semantic_runtime.legal_agent import decision_projection as dp


@pytest.mark.parametrize('question', ['모의법 제1조', '모의법 시행령과 모의법', '별칭법 규정', '없는 이름', '「모의법」', '모 의 법'])
@pytest.mark.parametrize('scope', [['a'], ['b'], ['a','b']])
def test_title_only_preserves_documents_without_glossary(question,scope):
    m=ReverseMatcher.__new__(ReverseMatcher)
    m.documents={'a':'모의법','b':'모의법 시행령'};m.document_context={}
    m.document_names=SurfaceIndex();m.structures=SurfaceIndex();m.body=SurfaceIndex()
    for did,name in m.documents.items():m.document_names.add(name,did)
    m.document_names.add('별칭법','a');m.tools=NS(validate_scope=lambda s:s)
    expected=m.starts(question,scope)['documents']
    m.body.match=lambda q:(_ for _ in ()).throw(AssertionError('glossary was called'))
    assert m.document_starts(question,scope)==expected


@pytest.mark.parametrize('schema', [
    {'type':'object','properties':{'b':{'type':'integer'},'a':{'type':'string'}},'required':['b','a']},
    {'anyOf':[{'type':'number'},{'type':'array','items':{'type':'boolean'}}]},
    {'$defs':{'value':{'enum':[1,2]}},'$ref':'#/$defs/value'},
    {'$schema':'http://json-schema.org/draft-07/schema#','type':'integer'},
])
def test_schema_reuse_preserves_best_match_and_mutation(schema,monkeypatch):
    cache=sp.OrderedSchemaValidators(max_entries=1)
    cls=jsonschema.validators.validator_for(schema);calls=[];original=cls.check_schema
    monkeypatch.setattr(cls,'check_schema',lambda s,*a,**k:(calls.append(deepcopy(s)),original(s,*a,**k))[1])
    def outcome(fn,value,schema):
        try:fn(value,schema);return None
        except jsonschema.ValidationError as e:return (e.message,list(e.absolute_path),list(e.absolute_schema_path))
    for value in ({'b':'bad','a':1},None,1,[],[False],{'b':1,'a':'ok'}):
        expected=outcome(jsonschema.validate,value,schema);before=len(calls)
        assert outcome(cache.validate,value,schema)==expected
        assert len(calls)-before <= 1
        before=len(calls);assert outcome(cache.validate,value,schema)==expected;assert len(calls)==before
    changed={**schema,'const':'changed'};before=len(calls)
    outcome(cache.validate,1,changed);assert len(calls)==before+1
    before=len(calls);outcome(cache.validate,1,schema);assert len(calls)==before+1


def test_schema_invalid_and_external_reference_not_cached(monkeypatch):
    cache=sp.OrderedSchemaValidators();bad={'type':123}
    for _ in range(2):
        with pytest.raises(jsonschema.SchemaError):cache.validate(1,bad)
    assert not cache._entries
    calls=[];monkeypatch.setattr(jsonschema,'validate',lambda v,s:calls.append((v,s)))
    schema={'$ref':'https://example.invalid/never-fetch'}
    cache.validate(1,schema);cache.validate(1,schema)
    assert len(calls)==2 and not cache._entries


def source_store():
    s=Store.__new__(Store);s.db=sqlite3.connect(':memory:');s.db.row_factory=sqlite3.Row
    s.db.execute('CREATE TABLE source_block(document_id,block_id,unit_id,text,PRIMARY KEY(document_id,block_id))')
    texts=[' 가\n나🙂 ', '', 'a\0b', 'e\u0301', '끝']
    s.db.executemany('INSERT INTO source_block VALUES(?,?,?,?)',[('d',str(i),'u',t) for i,t in enumerate(texts)])
    s._binding_state=('generation','rights');s.check_unchanged=lambda:None
    return s,texts


def test_source_batch_order_duplicates_nul_and_missing():
    store,texts=source_store();sql=[];store.db.set_trace_callback(sql.append)
    ids=['3','2','0','2'];got=store.sources('d',ids)
    assert [r['text'] for r in got]==[texts[int(b)] for b in ids]
    got[1]['text']='mutated';assert got[3]['text']==texts[2]
    assert store.source_lengths('d',ids)=={b:len(texts[int(b)]) for b in ids}
    assert len([q for q in sql if q.startswith('SELECT')])==2
    for fn in (store.sources,store.source_lengths):
        with pytest.raises(KeyError):fn('d',['0','missing'])
        with pytest.raises(KeyError):fn('other',['0'])
        assert not fn('d',[])


@pytest.mark.parametrize('count',[1,799,800,801,1601])
def test_source_batches_scale_with_unique_ids(count):
    store,_=source_store();store.db.execute('DELETE FROM source_block')
    store.db.executemany('INSERT INTO source_block VALUES(?,?,?,?)',[('d',str(i),'u','原文') for i in range(count)])
    sql=[];store.db.set_trace_callback(sql.append);ids=[str(i) for i in range(count)]*2
    assert len(store.sources('d',ids))==count*2
    assert len(sql)==(count+799)//800


def test_metadata_cost_matches_original_ranges_and_invalidates():
    store,texts=source_store();s=NS(store=store,scope=['d'],profile={'max_read_chars':3,'page_size':2})
    hit={'document_id':'d','source_id':'s'};offer={'block_ids':['0','2','3']}
    evidence=[{'source_id':'s','spans':[{'block_id':'0','start_cp':0,'end_cp':2}]}]
    cost=ta.read_cost(s,hit,offer,evidence)
    assert cost[0]==sum(len(texts[i]) for i in (0,2,3))-2
    before=deepcopy(evidence);assert ta.sequence_cost(s,[(hit,offer),(hit,offer)],evidence)==cost
    assert evidence==before
    def fail(*a):raise ValueError('generation changed')
    store.check_unchanged=fail
    with pytest.raises(ValueError,match='generation changed'):ta.read_cost(s,hit,offer,evidence)
    new,_=source_store();s.store=new;assert ta.read_cost(s,hit,offer,evidence)==cost


def test_changed_batch_rejected_at_end():
    store,_=source_store();calls=[]
    def check():
        calls.append(1)
        if len(calls)==2:raise ValueError('changed during read')
    store.check_unchanged=check
    with pytest.raises(ValueError,match='during read'):store.sources('d',['0'])


class CountConnection(fts._SearchConnection):
    queries=[]
    def execute(self,sql,*args,**kwargs):
        self.queries.append(sql)
        return super().execute(sql,*args,**kwargs)


@pytest.mark.parametrize('units',[None,[],['k1'],['k1','k4','k7','k10'],[f'k{i}' for i in range(15)]])
@pytest.mark.parametrize('scope',[None,['s0'],['s0','s2']])
@pytest.mark.parametrize('overflow',[False,True])
def test_scoped_fts_counts_order_pages_acl_and_overflow(units,scope,overflow,monkeypatch):
    monkeypatch.setattr(fts,'expression',lambda terms:' OR '.join('"'+t+'"' for t in terms))
    monkeypatch.setattr(fts,'MATCH_CACHE_ROWS',3 if overflow else 50000)
    db=sqlite3.connect(':memory:',factory=CountConnection);db.queries=[]
    db.executescript('CREATE TABLE unit(key PRIMARY KEY,source_id,document_id,json);CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body);')
    for i in range(15):
        sid='s'+str(i%3);did='d'+str(i%2);key='k'+str(i)
        row={'key':key,'source_id':sid,'document_id':did,'text':'alpha beta' if i%2 else 'alpha','unit_id':str(i)}
        db.execute('INSERT INTO unit VALUES(?,?,?,?)',(key,sid,did,json.dumps(row)))
        db.execute('INSERT INTO unit_fts VALUES(?,?)',(key,row['text']))
    db.commit();db.execute('PRAGMA query_only=ON')
    idx=fts.UnitFulltextIndex.__new__(fts.UnitFulltextIndex);idx.source_ids=frozenset(['s0','s1','s2'])
    idx.manifest={'index_sha256':'test'};idx.check_unchanged=lambda:None;idx.cache_namespace=lambda:('fixture',id(db))
    fts.CACHE.clear()
    real=idx._projection
    def pages():
        calls=[(idx.law_groups_page,()),(idx.article_groups_page,('d0',)),(idx.article_groups_page,('d1',)),*( (idx.hit_page,('s'+str(i),)) for i in range(3))]
        result=[]
        for fn,args in calls:
            page=fn(db,['alpha'],*args,allowed=scope,unit_keys=units,limit=2);group=[page]
            while page['next_cursor']:
                page=fn(db,['alpha'],*args,allowed=scope,unit_keys=units,limit=2,cursor=page['next_cursor']);group.append(page)
            result.append(group)
        return result
    idx._projection=lambda *a,**k:None;expected=pages();idx._projection=real;db.queries=[]
    actual=pages();assert actual==expected
    if not overflow and units!=[]:
        assert len([q for q in db.queries if 'SELECT u.key,u.document_id,u.source_id,unit_fts.rank' in q])==1
    assert pages()==expected
    with pytest.raises(ValueError):idx.law_groups_page(db,['alpha'],['forbidden'])
    db.close();fts.CACHE.clear()


def test_only_visible_details_prepared_and_resume_reuses(monkeypatch):
    calls=[];allowed=['s'+str(i) for i in range(45)]
    monkeypatch.setattr(lc,'allowed',lambda s:allowed)
    idx=NS(manifest={'index_sha256':'index'},check_unchanged=lambda:None)
    def hit_page(db,terms,sid,scope,**kwargs):
        calls.append(sid);return {'items':[{'unit_id':'child','article_unit_id':'root','text':'preview '+sid}]}
    idx.hit_page=hit_page
    inv=NS(s=NS(store=NS(check_unchanged=lambda:None)),idx=idx,db=None,save=lambda:None,
           p={'binding':'request','candidate_preview_queries':{'q':{'terms':['alpha'],'allowed':allowed,'args':{},'document_id':'d','index_sha256':'index'}}})
    candidates={'T'+str(i):{'identity':{'source_id':s}} for i,s in enumerate(allowed)}
    data={'laws':[{'document_id':'d','name':'법','article_matches':[{'source_id':s,'read_action':'T'+str(i),'article':str(i),'deferred_preview':{'query':'q','source_id':s}} for i,s in enumerate(allowed)]}]}
    original=deepcopy(data);first=list(candidates)[:20]
    got=ln.Investigation.prepare_read_details(inv,data,candidates,first)
    rows=dp.read_candidate_rows(got,{t:candidates[t] for t in first})
    assert len(calls)==20 and len(rows)==20 and all(r['preview'].startswith('preview') for r in rows)
    inv.p=deepcopy(inv.p);ln.Investigation.prepare_read_details(inv,data,candidates,first);assert len(calls)==20
    ln.Investigation.prepare_read_details(inv,data,candidates,list(candidates)[20:40]);assert len(calls)==40
    assert data==original
    idx.manifest['index_sha256']='changed'
    with pytest.raises(ln.ContractError):ln.Investigation.prepare_read_details(inv,data,candidates,first)
