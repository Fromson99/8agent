"""UI mode contracts with synthetic sources; no live model or legal scoring."""
import copy,json
import pytest
from fastapi.testclient import TestClient
from semantic_runtime import chat_adapter as adapter
from semantic_runtime.pipeline import route_question
from semantic_runtime.app import create_app
from test_source_prefix_routing import mixed_generation
from test_legal_agent_v5 import app_for
from test_unified_legal_agent import ScriptedTransport,ROOT,settings
from test_memory_runtime_v2 import command
import main

@pytest.fixture(autouse=True)
def environment(monkeypatch,tmp_path):
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path/'runtime'))
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','0')
    monkeypatch.delenv('TEAM_ID',raising=False)
    monkeypatch.delenv('GENOS_CHAT_TRUST_PLATFORM_IDENTITY',raising=False)

@pytest.mark.parametrize('value,label',[('전체 법령','전체 법령'),('전체','전체 법령'),('all','전체 법령'),('내규','내규'),('internal','내규'),('외규','외규'),('external','외규'),('대사','대사'),('compare','대사')])
@pytest.mark.parametrize('stream',[False,True])
def test_native_chat_modes(monkeypatch,value,label,stream):
    calls=[]
    async def fake(body):
        calls.append(body);return {'status':200,'body':{'answer':{'text':'모의 응답'},'assembly':{}}}
    monkeypatch.setattr(adapter,'call_service',fake)
    data={'question':'승인 기준은?','request_id':'r','chatId':'s','team_id':'risk_team','applied_fields':{'mode':value},'stream':stream,'document_ids':['internal']}
    before=copy.deepcopy(data)
    response=TestClient(main.app).post('/chat',json=data)
    result=next(json.loads(x[6:])['data'] for x in response.text.splitlines() if x.startswith('data: ') and json.loads(x[6:])['event']=='result') if stream else response.json()['data']
    assert result['answer_status']=='answered',result
    assert len(calls)==1 and calls[0]['question']==label+': 승인 기준은?'
    assert calls[0]['team_id']=='risk_team' and calls[0]['document_ids']==['internal']
    assert data==before and calls[0]['request_id']=='r'
    assert adapter.views()._request_body(data['question'],data)['question']==calls[0]['question']

@pytest.mark.parametrize('fields',[None,{}, {'mode':None},{'mode':''},{'mode':'  '},{'other':'x'}])
def test_missing_is_legacy(fields):
    data={'request_id':'r','applied_fields':fields}
    assert adapter.request_body(data,'질문')['question']=='질문'

@pytest.mark.parametrize('fields',[[], '전체 법령', {'mode':[]},{'mode':False},{'mode':42},{'mode':'오타'}])
def test_invalid_no_execution(monkeypatch,fields):
    async def no(body):pytest.fail('invalid form executed')
    monkeypatch.setattr(adapter,'call_service',no)
    result=TestClient(main.app).post('/chat',json={'question':'질문','applied_fields':fields}).json()['data']
    assert result['answer_status']=='invalid_input' and '조회 방식' in result['text']

@pytest.mark.parametrize('mode,question',[('전체 법령','내규: 질문'),('외규','내규: 질문'),('내규','대사: 질문'),('대사','외규: 질문')])
def test_conflicting_marker(mode,question):
    with pytest.raises(adapter.views().QueryModeError):adapter.request_body({'request_id':'r','chatId':'s','team_id':'risk_team','applied_fields':{'mode':mode}},question)

@pytest.mark.parametrize('mode,marker',[('전체 법령','전체'),('내규','내규'),('외규','외규'),('대사','대사')])
def test_idempotent(mode,marker):
    data={'request_id':'r','chatId':'s','team_id':'risk_team','applied_fields':{'mode':mode}}
    first=adapter.request_body(data,marker+'： 질문');second=adapter.request_body(data,first['question'])
    assert first==second and first['question']==mode+': 질문'

@pytest.mark.parametrize('extra',[{}, {'chatId':'s'}, {'team_id':'risk_team'}])
def test_compare_needs_session_and_team(extra):
    with pytest.raises(adapter.views().QueryModeError):adapter.request_body({'request_id':'r','applied_fields':{'mode':'대사'},**extra},'질문')

@pytest.mark.parametrize('question',['__verify__','SSE_CHECK'])
def test_diagnostics_ignore_selector(monkeypatch,question):
    async def no(body):pytest.fail('diagnostic called RAG')
    monkeypatch.setattr(adapter,'call_service',no)
    out=TestClient(main.app).post('/chat',json={'question':question,'applied_fields':{'mode':42}}).json()
    assert out['code']==0 and out['data'].get('answer_status')!='invalid_input'

@pytest.mark.parametrize('label,expected',[('전체 법령',{'internal','external','unknown'}),('내규',{'internal'}),('외규',{'external'})])
def test_all_and_category_plan(tmp_path,mixed_generation,label,expected):
    app=app_for(tmp_path,mixed_generation);p=app.state.pipeline
    try:
        assert set(p.plan(label+': 승인')['scope']['document_version_ids'])==expected
        subset=['internal','external']
        assert set(p.plan(label+': 승인',subset)['scope']['document_version_ids'])==expected&set(subset)
    finally:p.store.close()

@pytest.mark.parametrize('label,included,excluded',[('전체 법령',['모의내규','모의외규','출처미확인'],[]),('내규',['모의내규'],['모의외규','출처미확인']),('외규',['모의외규'],['모의내규','출처미확인'])])
def test_real_chat_service_scope(tmp_path,mixed_generation,monkeypatch,label,included,excluded):
    import service
    app=app_for(tmp_path,mixed_generation)
    monkeypatch.setattr(service,'_bootstrap_application',lambda:app)
    with TestClient(main.app) as client:
        response=client.post('/chat',json={'question':'전체 문서 목록','use_llm':False,'applied_fields':{'mode':label}}).json()['data']
        assert response['answer_status']=='answered',response
        assert all(x in response['text'] for x in included)
        assert all(x not in response['text'] for x in excluded)
    app.state.pipeline.store.close()


def test_session_switch_overrides_model_and_dedup(tmp_path,mixed_generation,monkeypatch):
    import service
    t=ScriptedTransport()
    principal={'user_id':'u','team_id':'risk_team','document_ids':['internal','external']}
    app=create_app(tmp_path,mixed_generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=t,memory_identity=lambda req:principal)
    monkeypatch.setattr(service,'_bootstrap_application',lambda:app)
    base={'question':'승인 절차는?','session_id':'s','team_id':'risk_team','memory':True}
    async def post(body):return await service.service({},body)
    # Direct ingress plus actual dispatch; inspect structured result before presentation.
    import asyncio
    from semantic_runtime.legal_agent.unified_rag import UnifiedRag
    original_open=UnifiedRag.open;opened=[]
    def observe_open(self,state,principal,body):
        opened.append({'category':state['source_category'],'documents':set(self.documents(state,principal))})
        return original_open(self,state,principal,body)
    monkeypatch.setattr(UnifiedRag,'open',observe_open)
    gid=None
    for n,(mode,expected) in enumerate([('내규',{'internal'}),('외규',{'external'}),('전체 법령',{'internal','external'})]):
        t.command=command('CASE_START',document_scope_mode='AUTHORIZED',task='승인 절차는?',queries=['승인'],facts=[],source_category='external') if gid is None else command('RESEARCH_REPLAN',target=gid,source_category='KEEP')
        data={**base,'request_id':str(n),'applied_fields':{'mode':mode}}
        body=adapter.request_body(data,base['question'])
        result=asyncio.run(post(body));assert result['status']==200,result
        answer=result['body'];gid=answer['question_id']
        assert opened[-1]['documents']==expected,opened
        assert opened[-1]['category']==['internal','external','ALL'][n]
        assert set() < {x['document_id'] for x in answer['assembly']['context']} <= expected,answer
        assert 'unknown' not in {x['document_id'] for x in answer['assembly']['context']}
        if n:
            assert 'PLAN' in answer['executed'],answer
        count=len(t.phases);retry=asyncio.run(post(body));assert retry['status']==200 and len(t.phases)==count
    changed=adapter.request_body({**data,'applied_fields':{'mode':'내규'}},base['question'])
    assert asyncio.run(post(changed))['status']==409
    app.state.pipeline.store.close()


def test_compare_reaches_registered_workflow(tmp_path,mixed_generation,monkeypatch):
    import service,asyncio
    principal={'user_id':'u','team_id':'risk_team','document_ids':['internal','external']}
    app=create_app(tmp_path,mixed_generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=ScriptedTransport(),memory_identity=lambda req:principal)
    monkeypatch.setattr(service,'_bootstrap_application',lambda:app)
    seen=[]
    def intercept(body,who):
        seen.append((body,who));return {'response_schema':'workflow-result-v1','status':'completed','answer':{'text':'모의 대사'}}
    monkeypatch.setattr(app.state.workflow_runtime,'execute',intercept)
    body=adapter.request_body({'question':'승인','request_id':'r','chatId':'s','team_id':'risk_team','applied_fields':{'mode':'대사'}},'승인')
    result=asyncio.run(service.service({},body))
    assert result['status']==200 and len(seen)==1,result
    assert seen[0][0]['workflow_id']=='risk_team_compare_workflow'
    assert set(seen[0][1]['document_ids'])=={'internal','external'}
    assert result['body']['response_schema']=='workflow-result-v1'
    app.state.pipeline.store.close()
