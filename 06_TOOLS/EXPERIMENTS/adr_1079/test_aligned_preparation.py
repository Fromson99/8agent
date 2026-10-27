"""Tiny selected-directory composition checks; no real corpus or model."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as S
import pytest

from semantic_runtime.legal_agent import unit_relations as rel, connection_scope as cs
from semantic_runtime.legal_agent.errors import ContractError
from test_final_connection_selection import setup

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('adr1079_tiny_cache_fixture',ROOT/'06_TOOLS/EXPERIMENTS/adr_1076/finite_contract.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)


def test_reused_coverage_keeps_checks_and_cannot_be_poisoned():
    session,selected=fixtures.fixture(S(rel=rel),'multi_source')
    try:
        preparation=rel.CatalogReadPreparation()
        first,_=rel.acquired_blocks(session,selected,preparation=preparation)
        expected=deepcopy(first);reads=session.store.reads;checks=session.store.checks
        first['S1'].clear()
        second,_=rel.acquired_blocks(session,selected,preparation=preparation)
        assert second==expected and session.store.reads==reads and session.store.checks>checks
        session.store.generation+=1
        with pytest.raises(ValueError,match='immutable source changed'):
            rel.acquired_blocks(session,selected,preparation=preparation)
        assert preparation._key is None
    finally:session.store.close()


@pytest.mark.parametrize('change',['permission','span_type','span_text'])
def test_changed_authorization_or_span_revalidates_and_fails(change):
    session,selected=fixtures.fixture(S(rel=rel))
    try:
        preparation=rel.CatalogReadPreparation();rel.acquired_blocks(session,selected,preparation=preparation)
        if change=='permission':session.scope.remove('D1')
        if change=='span_type':selected['R1']['evidence'][0]['spans'][0]['start_cp']=False
        if change=='span_text':selected['R1']['evidence'][0]['spans'][0]['text']='변조'
        with pytest.raises(ContractError):rel.acquired_blocks(session,selected,preparation=preparation)
        assert preparation._key is None
    finally:session.store.close()


def test_directory_creation_and_saved_flags_share_only_supplied_preparation(monkeypatch):
    session,selected=fixtures.fixture(S(rel=rel),'multi_source')
    try:
        inv=S(s=session,p={'binding':{'generation':'tiny'},'turn':0},save=lambda:None,
              read_records=lambda:deepcopy(selected))
        inv.s.repo=S(event=lambda *_:None)
        scope={'id':'scope','label':'tiny','members':[{'source_id':'S1','document_id':'D1','spans':selected['R1']['evidence'][0]['spans']}]}
        calls=[]
        def preview(i,s,*,preparation=None):
            calls.append(preparation)
            rel.acquired_blocks(i.s,i.read_records(),preparation=preparation)
            return {'status':'COMPLETE','groups':[{'anchor':{'source_id':'S1','document_id':'D1'},
                'target':{'source_id':'S2','document_id':'D2'},'connections':[{'endpoint_block_ids':['1']}]}],
                'connection_count':1,'absence_proven':False}
        monkeypatch.setattr(cs,'preview',preview)
        prepared=rel.CatalogReadPreparation()
        first=cs.inspect_directory(inv,scope,preparation=prepared);reads=session.store.reads
        assert first['groups'][0]['connections'][0]['already_read'] is True and calls==[prepared]
        again=cs.inspect_directory(inv,scope,preparation=prepared)
        assert again==first and calls==[prepared] and session.store.reads==reads
        cs.inspect_directory(inv,scope,preparation=rel.CatalogReadPreparation())
        assert session.store.reads>reads and calls==[prepared]  # fresh-screen check, no directory requery
        session.scope.remove('D2')
        with pytest.raises(ContractError):cs.inspect_directory(inv,scope,preparation=prepared)
    finally:session.store.close()


def test_offer_owns_one_new_preparation_per_screen(monkeypatch):
    inv,data=setup(monkeypatch)
    chosen=next(scope for scope,_ in cs.candidates(inv,data)
        if scope['structural_selection'].get('unit_id')=='4')
    cs.accept(inv,chosen,data,'선택 범위')
    observed=[];original=cs.inspect_directory
    def inspect(i,s,*,preparation=None):
        observed.append(preparation);return original(i,s,preparation=preparation)
    monkeypatch.setattr(cs,'inspect_directory',inspect)
    monkeypatch.setattr(cs,'preview',lambda *a,**kw:{'status':'COMPLETE','groups':[],
        'connection_count':0,'absence_proven':False})
    cs.offer_choices(inv,deepcopy(data),{});first=list(observed);observed.clear()
    cs.offer_choices(inv,deepcopy(data),{});second=list(observed)
    assert first and second and all(isinstance(p,rel.CatalogReadPreparation) for p in first+second)
    assert len({id(p) for p in first})==len({id(p) for p in second})==1
    assert first[0] is not second[0]


def test_cache_helpers_and_visibility_code_match_performance_source():
    plan=json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-1079-ontology-departure-single-cell/artifacts/main105-alignment-plan.json').read_text())
    source=ROOT/plan['performance_code_root']
    def nodes(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body
        if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    current=nodes(Path(rel.__file__));expected=nodes(source/'02_BACKEND/semantic_runtime/legal_agent/unit_relations.py')
    for name in ('_UncacheablePreparation','_preparation_key','CatalogReadPreparation','acquired_blocks'):
        assert current[name]==expected[name]
    from semantic_runtime import search_selection
    assert Path(search_selection.__file__).read_bytes()==(source/'02_BACKEND/semantic_runtime/search_selection.py').read_bytes()
