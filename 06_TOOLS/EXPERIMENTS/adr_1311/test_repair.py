from conftest import term_glossary
from copy import deepcopy
from types import SimpleNamespace as NS, MappingProxyType
from collections import defaultdict
from pathlib import Path
import importlib.util, json, sqlite3, threading, time
import pytest
from semantic_runtime.legal_agent import structure_selection as ss, structure_query as sq, query_scope as qs
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.multi_entry_navigation import freeze
from semantic_runtime.storage import Store
from semantic_runtime.term_index import SourceMap
from semantic_runtime.contracts import digest
from test_model_structure_selection import matcher, choose, interval, single
from test_structure_first_search import structured_generation


def prepared(m):
    m.units=freeze(m.units);coords=MappingProxyType(dict(m.stored_coordinates));m.stored_coordinates=coords
    groups=defaultdict(list)
    for key in m.units:groups[key[0]].append(key)
    m.prepared_structure={'units':m.units,'coordinates':coords,'unit_index':groups,'lock':threading.Lock()}
    m._structure_store=NS(check_unchanged=lambda:None)
    return m


def legacy():
    p=Path('/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/structure_selection.py')
    spec=importlib.util.spec_from_file_location('semantic_runtime.legal_agent.legacy_selection',p)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

@pytest.mark.parametrize('selection',[
    choose(),choose([single(1),single(3)]),choose([interval(2,6)],[single(4)]),
    choose([interval(3,None,False)]),choose([interval(None,5,True,False)]),
    choose([{'kind':'SINGLE','value':{'n':6,'dash':3}}],paragraph=None,unit='조',root=True),
    choose(exclude=[single(5)]),choose([{'kind':'BOUND','operator':'LTE','value':{'n':4}}])])
@pytest.mark.parametrize('immutable',[False,True])
def test_same_full_record_and_metadata_hash(selection,immutable):
    m=matcher();old=legacy().resolve(selection,m,'d',{'d'})
    if immutable:prepared(m)
    assert ss.resolve(selection,m,'d',{'d'})==old
    ss.verify(old,m,{'d'})


def test_parent_lookup_never_iterates_global_units(monkeypatch):
    m=prepared(matcher());sq.document_tree(m,'d')
    original=type(m.units).items
    def guarded(self):
        if self is m.units:raise AssertionError('whole corpus scan')
        return original(self)
    monkeypatch.setattr(type(m.units),'items',guarded)
    assert ss.resolve(choose(root=True,unit='호'),m,'d',{'d'})['unit_ids']==list('1234567')


def test_verified_reuse_is_copy_hash_acl_and_store_bound(monkeypatch):
    m=prepared(matcher());record=ss.resolve(choose(),m,'d',{'d'})
    def forbidden(*a,**k):raise AssertionError('successful selection resolved again')
    monkeypatch.setattr(ss.Nodes,'__init__',forbidden)
    ss.verify(record,m,{'d'});other=ss.resolve(choose(),m,'d',{'d'});other['unit_ids'].clear()
    ss.verify(record,m,{'d'})
    bad=deepcopy(record);bad['unit_ids'].clear()
    with pytest.raises(ContractError,match='hash'):ss.verify(bad,m,{'d'})
    with pytest.raises(ContractError,match='authorization'):ss.verify(record,m,{'other'})
    def stale():raise ValueError('source changed')
    m._structure_store.check_unchanged=stale
    with pytest.raises(ValueError,match='changed'):ss.verify(record,m,{'d'})


def test_mutable_metadata_and_coordinates_rechecked():
    m=matcher();record=ss.resolve(choose(),m,'d',{'d'})
    m.units[('d','5')]['span']=[90,91]
    with pytest.raises(ContractError,match='metadata'):ss.verify(record,m,{'d'})
    m=prepared(matcher());record=ss.resolve(choose(),m,'d',{'d'})
    m.units=deepcopy(m.units);m.units[('d','5')]['span']=[90,91]
    with pytest.raises(ContractError,match='metadata'):ss.verify(record,m,{'d'})


def test_failed_resolution_and_bounded_memo():
    m=prepared(matcher())
    for _ in range(2):
        with pytest.raises(ss.SelectionError):ss.resolve(choose([single(99)]),m,'d',{'d'})
    assert not m._selection_resolution_cache.values
    c=ss._ResolutionCache()
    for n in range(130):c.put(str(n),{'v':n})
    assert len(c.values)==128 and c.get('0')==(False,None)
    c.put('huge',{'v':'x'*(1024*1024)})
    assert not c.get('huge')[0] and c.bytes<=1024*1024


def test_scoped_sql_ids_without_source_json(structured_generation):
    from contextlib import closing
    with closing(sqlite3.connect(structured_generation/'navigation/navigation.sqlite')) as db:
        sources=SourceMap(db);calls=[];db.set_trace_callback(calls.append)
        s=NS(scope={'d','other'},tools=NS(sources=sources),direct_search_scope={'targets':[{'document_id':'d','unit_id':None}]})
        ids=qs.search_sources(s)
        assert ids and not sources.cache and not any(sql.startswith('SELECT json') for sql in calls)
        s.scope={'other'};assert not qs.search_sources(s)


def test_oracle_scope_stays_lazy_and_rebinds():
    from semantic_runtime.oracle_query_index import Sources,SourceScope
    class DB:
        tables={'source':('kind','value')}
        def execute(self,*a):raise AssertionError('scope must not enumerate')
    req=NS(release_id='v1',sources=NS(allowed={'d','other'}));sources=Sources(req,DB())
    s=NS(scope={'d','other'},tools=NS(sources=sources),direct_search_scope={'targets':[{'document_id':'d','unit_id':None}]})
    a=qs.search_sources(s);assert isinstance(a,SourceScope) and a.document_ids=={'d'}
    assert qs.search_sources(s) is a
    s.direct_search_scope={'targets':[{'document_id':'other','unit_id':None}]}
    assert qs.search_sources(s).document_ids=={'other'}
    req.sources.allowed={'d'}
    from semantic_runtime.oracle_dp_io import DPError
    with pytest.raises(DPError):qs.search_sources(s)


def test_oracle_success_memo_keeps_request_deadline_and_scope():
    from semantic_runtime.oracle_query_matcher import Units,Coordinates
    from semantic_runtime.oracle_dp_io import BudgetPause,DPError
    m=matcher();rows=[{'document_id':did,'unit_id':uid,'unit':deepcopy(u),'coordinate':m.stored_coordinates[(did,uid)].as_dict()} for (did,uid),u in m.units.items()]
    calls=[]
    def page(kind,**kw):
        calls.append((kind,kw));values=[r for r in rows if r['document_id']==kw.get('document_id','d')]
        if 'owner_id' in kw:values=[r for r in values if r['unit']['parent']==kw['owner_id']]
        if 'lookup_id' in kw:values=[r for r in values if digest([r['document_id'],r['unit_id']])==kw['lookup_id']]
        return {'rows':values,'next':None}
    req=NS(release_id='v1',sources=NS(allowed={'d'}),sql=NS(deadline=time.monotonic()+60),snapshot=NS(binding_hash='p'),records=NS(manifest={},page=page))
    m.coordinate_index={(did,c.canonical_surface()):[uid] for (did,uid),c in m.stored_coordinates.items()}
    m.units=Units(req);m.stored_coordinates=Coordinates(m.units)
    record=ss.resolve(choose(),m,'d',{'d'});count=len(calls)
    ss.verify(record,m,{'d'});assert len(calls)==count
    req.sql.deadline=0
    with pytest.raises(BudgetPause):ss.verify(record,m,{'d'})
    req.sql.deadline=time.monotonic()+60;req.sources.allowed={'other'}
    with pytest.raises(DPError):ss.verify(record,m,{'d'})


def test_block_reuse_copy_stale_and_missing(structured_generation):
    store=Store(structured_generation);traced=[];store.db.set_trace_callback(traced.append)
    try:
        first=dict(store.db.execute("SELECT * FROM source_block WHERE document_id='d' LIMIT 1").fetchone());key=first['block_id']
        a=store.source('d',key);a['text']='changed'
        assert store.source('d',key)==first
        reads=[s for s in traced if s.startswith('SELECT * FROM source_block WHERE document_id=') and 'LIMIT' not in s]
        assert len(reads)==1
        for _ in range(2):
            with pytest.raises(KeyError):store.source('d','missing')
        assert ('d','missing') not in store._source_cache
        with (structured_generation/'store.sqlite').open('ab') as f:f.write(b'changed')
        with pytest.raises(ValueError,match='changed'):store.source('d',key)
    finally:store.close()
