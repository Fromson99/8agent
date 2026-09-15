"""Serving wiring contracts with deterministic provider doubles; no quality eval."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.contracts import sha
from semantic_runtime.pipeline import Pipeline
from semantic_runtime.provider import Haiku
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())
GENERATION=ROOT/'01_DATA/SEMANTIC/GENERATIONS/term-source-20260915-v1'
INDEX=ROOT/'01_DATA/SEMANTIC/TERM_INDEX/term-source-navigation-20260915-v1'
DID='3521c3aaa5a735fd'

class FixtureProvider(Haiku):
    def __init__(self,path,bad=False):super().__init__(ROOT,path,False,backend='fixture',trust_zone='internal');self.calls=[];self.bad=bad
    def call(self,role,task,context,schema):
        self.calls.append((role,context))
        assert not {'rules','clauses','provisos','glue','role_bindings','canonical_bundle'}&context.keys()
        if role.endswith('plan') or role.endswith('replan'):value={'questions_to_check':['용어 정의 확인'],'seed_labels':['영업일']}
        else:
            d=next(x for x in context['scoped_definition_results'] if x['key']=='영업일');sid=d['source_id']
            value={'findings':[{'text':d['source_text'],'source_ids':['invented'] if self.bad else [sid]}],'open_questions':[],'evidence_ids':[sid],'next_action':'FINISH','next_term_ids':[],'next_navigation_ids':[],'reason':'deterministic wiring fixture','question_for_user':'','answer':'THIS_UNCITED_DRAFT_MUST_NOT_REACH_OUTPUT'}
        return value,self.record_local(value)

@pytest.fixture(scope='module')
def store():
    s=Store(GENERATION);yield s;s.close()

def test_source_only_uses_terms_definitions_and_generation_scope(store,tmp_path):
    p=Pipeline(ROOT,store,FixtureProvider(tmp_path/'provider'));r=p.run('영업일은 토요일을 포함하나요?',[DID],False)
    assert r['selection']['method']=='term-agent'
    state=r['retrieval']['term_agent'];assert state['status']=='SOURCE_ONLY' and state['calls']==0
    assert all(x['document_id']==DID for x in r['assembly']['context'])
    assert any(x['action']=='LOOKUP_DEFINITION' for x in state['trace'][0]['bounded_prefetch']['results'])
    assert 'condition_assessments' not in r['assembly']
    p.contracts.validate(r,'urn:8-agent:term-runtime-v1','Result')

def test_llm_provider_and_grounded_answer_contract(store,tmp_path):
    provider=FixtureProvider(tmp_path/'provider');p=Pipeline(ROOT,store,provider);r=p.run('영업일의 정의',[DID],True)
    assert len(provider.calls)>=3 and r['answer']['claims']
    assert 'THIS_UNCITED' not in r['answer']['text']
    assert r['retrieval']['term_agent']['status']=='FINISH'
    for c in r['answer']['claims']:assert c['text'] in next(s['text'] for s in r['assembly']['context'] if s['id'] in c['source_ids'])
    p.contracts.validate(r,'urn:8-agent:term-runtime-v1','Result')

def test_invalid_model_ids_fail_closed_without_stale_answer(store,tmp_path):
    p=Pipeline(ROOT,store,FixtureProvider(tmp_path/'provider',True));r=p.run('영업일의 정의',[DID],True)
    assert r['retrieval']['term_agent']['status']=='EXECUTION_FAILURE'
    assert not r['answer']['claims'] and not r['assembly']['context']
    assert r['answer']['unresolved'] and 'THIS_UNCITED' not in r['answer']['text']

def test_index_generation_drift_is_rejected(store):
    original=store.manifest['store_sha256'];store.manifest['store_sha256']='0'*64
    try:
        with pytest.raises(ValueError,match='generation/hash'):TermIndex(INDEX,store)
    finally:store.manifest['store_sha256']=original

def test_bidirectional_reference_reads_original_source(store):
    index=TermIndex(INDEX,store);tools=index.tools([DID])
    try:
        row=tools.db.execute("SELECT id FROM source WHERE document_id=? AND article='제46조'",(DID,)).fetchone();seen=[row[0]]
        menu=tools.navigation_menu(seen,[],'종류주식 상장의 유예',[DID],reference_limit=100)
        c=next(c for c in menu if c.get('direction')=='INCOMING' and '제80조' in c['target_headings'][0])
        opened,out=tools.navigate([c['id']],menu,seen,[DID]);assert '제80조' in tools.sources[opened[0]]['heading'];assert out[0]['direction']=='INCOMING'
        with pytest.raises(ValueError):tools.navigate([c['id']],menu,[],[DID])
    finally:tools.db.close()

def test_existing_ask_endpoint_scope_status_feedback_and_legacy_fact_guard(tmp_path):
    app=create_app(tmp_path,GENERATION,contracts_root=ROOT,provider=FixtureProvider(tmp_path/'provider'),vector=False)
    with TestClient(app) as client:
        health=client.get('/health').json();assert health['rag_mode']=='term-agent' and not health['quality_certified']
        q={'question':'영업일의 정의','document_ids':[DID],'use_llm':True};response=client.post('/v1/rag/ask',json=q);assert response.status_code==200,response.text
        r=response.json();assert r['answer']['claims'] and r['selection']['method']=='term-agent'
        assert client.post('/v1/rag/feedback',json={'run_id':r['run_id'],'signal':'MISSING_EVIDENCE','reason':'wiring fixture'}).status_code==200
        assert client.post('/v1/rag/ask',json={**q,'document_ids':['bad']}).status_code==422
        assert client.post('/v1/rag/ask',json={**q,'clause_values':{'old/clause':True}}).status_code==422

def test_no_runtime_import_of_research_candidate():
    for name in ['term_tools.py','term_index.py','term_agent.py']:
        text=(ROOT/'02_BACKEND/semantic_runtime'/name).read_text()
        assert 'from lawrag.research' not in text and 'import lawrag.research' not in text
