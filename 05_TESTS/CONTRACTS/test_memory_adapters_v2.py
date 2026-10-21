import importlib.util
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import memory_identity, corrected_memory as m
from test_memory_runtime_v2 import Fake,Wire,command
from test_bounded_source_main import generation,settings,Transport
from test_legal_agent_double_harness import ROOT
from test_structure_first_search import structured_generation

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);out=importlib.util.module_from_spec(spec);spec.loader.exec_module(out);return out

def test_workflow_unsigned_session_and_service_preservation(monkeypatch):
 workflow=module('memory_workflow',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
 service=module('memory_service',ROOT/'service.py')
 monkeypatch.setenv('GENOS_MEMORY_ENABLED','1');monkeypatch.delenv('GENOS_MEMORY_SIGNING_KEY',raising=False);monkeypatch.setenv('TEAM_ID','risk_team')
 raw=workflow._request_body('모의 요청',{'userInfo':{'userId':'u/one'},'chatId':'s/one','request_id':'r'})
 normalized=service._normalize(raw)['json']
 principal=memory_identity.validate_session(normalized)
 assert principal['team_id']=='risk_team' and principal['user_id'].startswith('session:')
 assert normalized['session_id']==raw['session_id']
 assert 'user_id' not in raw
 assert raw['session_id']!=workflow._request_body('모의 요청',{'userId':'u-one','chatId':'s-one'})['session_id']
 assert 'memory_authorization' not in raw
 changed={**normalized,'session_id':''}
 with pytest.raises(m.MemoryError):memory_identity.validate_session(changed)
 monkeypatch.setenv('GENOS_MEMORY_ENABLED','0')
 old=workflow._request_body('모의 요청',{'userId':'u','chatId':'s'})
 assert 'memory' not in old and service._normalize(old)['json']['session_id']=='s'

@pytest.mark.parametrize('data',[{}, {'userId':'u'}])
def test_anonymous_memory_is_rejected(monkeypatch,data):
 workflow=module('memory_workflow',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
 monkeypatch.setenv('GENOS_MEMORY_ENABLED','1');monkeypatch.delenv('GENOS_MEMORY_SIGNING_KEY',raising=False);monkeypatch.setenv('TEAM_ID','risk_team')
 with pytest.raises(ValueError,match='식별자'):workflow._request_body('모의 요청',data)

def test_api_multiturn_uses_authenticated_principal_and_safe_response(tmp_path,generation):
 wire=Wire();wire.command=command('CASE_START',task='보고 위임',facts=[])
 captured=[];principal={'user_id':'u','team_id':'risk_team','document_ids':['d']}
 def factory(p,runtime,body,identity):
  captured.append(body)
  return m.Memory(tmp_path/'memory.sqlite',Fake(),wire)
 app=create_app(tmp_path,generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-tools-v5',
                legal_agent_profile=settings(),legal_agent_transport=Transport(),memory_factory=factory,memory_identity=lambda req:principal)
 body={'memory':True,'question':'모의 요청','user_id':'u','team_id':'risk_team','session_id':'s','request_id':'r','memory_authorization':{'signature':'not persisted'}}
 with TestClient(app) as api:
  one=api.post('/v1/rag/ask',json=body);assert one.status_code==200,one.text
  result=one.json();assert result['response_schema']=='corrected-memory-response-v2'
  assert result['assembly']['context'][0]['id']=='cited'
  assert result['answer']['claims'][0]['source_ids']==['cited']
  assert 'memory_authorization' not in captured[0]
  wire.command=command('FACT_UPDATE',target=result['goal_id'],facts=[{'name':'대상','value':'A'}])
  two=api.post('/v1/rag/ask',json={**body,'request_id':'r2'});assert two.status_code==200,two.text
  assert two.json()['executed']==['ASSESS','COMPOSE']
  assert api.post('/v1/rag/ask',json={**body,'request_id':'r3','expected_revision':1}).status_code==409
  assert api.post('/v1/rag/ask',json={**body,'user_id':'other','request_id':'r4'}).status_code==200
  assert api.post('/v1/rag/ask',json={**body,'document_ids':['private'],'request_id':'r5'}).status_code==422

def test_unsigned_api_still_requires_selected_documents(tmp_path,generation,monkeypatch):
 from semantic_runtime import team_scope
 monkeypatch.setattr(team_scope,'select_documents',lambda store,team:[])
 monkeypatch.delenv('GENOS_MEMORY_SIGNING_KEY',raising=False)
 app=create_app(tmp_path,generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-tools-v5',legal_agent_profile=settings(),legal_agent_transport=Transport())
 with TestClient(app) as api:
  response=api.post('/v1/rag/ask',json={'memory':True,'question':'모의 요청','session_id':'s','request_id':'r','user_id':'u','team_id':'risk_team'})
  assert response.status_code==422 and response.json()['answer_status']=='failed'
  assert 'no documents authorized' not in response.text

def test_real_native_retrieval_read_selection_reentry_and_publication(tmp_path,structured_generation):
    generation=structured_generation
    from semantic_runtime.legal_agent.memory_rag import NativeRag
    from semantic_runtime.legal_agent import source_selection
    wire=Wire();wire.command=command('CASE_START',task='모의승인규정 제1조의 승인 대상은?',queries=['승인'],facts=[])
    phases=[];triages=0
    def invoke(system,data,schema,phase):
        nonlocal triages
        phases.append(phase)
        if phase.startswith('memory-resolve') or phase=='memory-command-check':return wire(system,data,schema,phase)
        if phase.endswith('check'):return {'valid':True,'reason':'모의 응답; 실제 모델 평가 아님'}
        if phase=='memory-intent':return {'purpose':'승인 대상 확인','concepts':['승인']}
        if phase.startswith('source-'):
            triages+=1
            labels=schema['properties']['choices']['items']['properties']['id']['enum']
            output={'issues':['승인'],'choices':[{'id':labels[0],'reason':'모의 원문 선별'}] if labels else []}
            if 'needs_fulltext' in schema['properties']:output['needs_fulltext']=True
            return output
        if phase.startswith('memory-assess'):
            source=data['sources'][0]
            return {'claims':[{'text':'제공된 승인 규정에 따른다.','source_id':source['source_id'],'quote':source['text'][:15]}],'limitations':[]}
        if phase.startswith('memory-compose'):
            return {'text':'제공된 승인 규정에 따른다.',**data['assessment']}
        raise AssertionError(phase)
    def factory(p,runtime,body,principal):return m.Memory(tmp_path/'native-memory.sqlite',NativeRag(p,runtime,invoke),invoke)
    app=create_app(tmp_path,generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-tools-v5',
                   legal_agent_profile=settings(),legal_agent_transport=Transport(),memory_factory=factory,
                   memory_identity=lambda req:{'user_id':'u','team_id':'risk_team','document_ids':['d']})
    with TestClient(app) as api:
        body={'memory':True,'session_id':'s','request_id':'native1','question':'모의승인규정 제1조의 승인 대상은?'}
        out=api.post('/v1/rag/ask',json=body)
        assert out.status_code==200,out.text
        result=out.json();assert result['status']=='READY'
        assert result['executed'].count('RECALL')==2 and result['executed'].count('READ')==2
        assert result['assembly']['context'] and 'source-triage' in phases
        gid=result['goal_id'];wire.command=command('EXPERIENCE_CONFIRM',target=gid)
        out=api.post('/v1/rag/ask',json={**body,'question':'최종 맞아. 저장해줘.','request_id':'native2'})
        assert out.status_code==200 and out.json()['status']=='STORED',out.text
