"""Public failure boundaries: status, privacy, one dispatch and no false success."""
import asyncio,json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from semantic_runtime import chat_adapter as adapter
from semantic_runtime.legal_agent.errors import BudgetExhausted

@pytest.mark.parametrize('status',[401,403,409,413,429,500,502,503,504])
def test_status_guidance_is_stable_and_private(status):
 v=adapter.views();raw={'error':'private','_gateway_status':status,'request_id':'case-1'}
 text=v.render(v.public_response(raw))
 assert f'({status})' in text and 'private' not in text
 assert text.startswith('현재 충분한 법률 검토를 하지 못했습니다.')
 if status in (401,403):assert '권한' in text
 if status==409:assert '처리 중' in text
 if status==413:assert '분량' in text

def test_budget_notice_preserves_failed_state():
 v=adapter.views();out=v.public_failure('case-1',exc=BudgetExhausted('private budget'))
 assert out['answer_status']=='failed' and out['error_code']=='limit'
 assert '법률 쟁점을 나누어' in out['message'] and '(limit)' in out['message']
 assert v.public_response(v.public_response(out))==out

@pytest.mark.parametrize('failure',['raise','envelope','malformed'])
def test_native_preflight_failure_never_calls_rag(monkeypatch,failure):
 monkeypatch.delenv('GENOS_RUNTIME_DIR',raising=False);monkeypatch.delenv('GENOS_DATA_ROOT',raising=False)
 calls=[]
 async def service(data):
  calls.append(data['API_TYPE'])
  if failure=='raise':raise TimeoutError('private timeout')
  if failure=='malformed':return {'status':200,'body':[]}
  return {'status':503,'body':{'error':'private failure'}}
 monkeypatch.setattr(adapter,'call_service',service)
 out=asyncio.run(adapter.chat({'question':'모의 질문','request_id':'case-1'}))['data']
 assert out['answer_status']=='failed' and 'private' not in out['text']
 assert calls==['AD_PROBE']
 assert {'raise':'(timeout)','envelope':'(503)','malformed':'(502)'}[failure] in out['text']

@pytest.mark.parametrize('route',['/chat','/json','/stream'])
@pytest.mark.parametrize('malformed',[True,False])
def test_http_validation_and_invalid_json_have_safe_notices(monkeypatch,tmp_path,route,malformed):
 import main_workflow,main
 monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path));client=TestClient(main.app if route=='/chat' else main_workflow.app)
 response=client.post(route,content='{' if malformed else '[]',headers={'Content-Type':'application/json','X-Request-ID':'case-1'})
 assert response.status_code in (400,422,500)
 body=response.json();safe=body['data'] if route=='/chat' else body['body']
 assert safe['answer_status']=='failed'
 assert '현재 충분한 법률 검토를 하지 못했습니다.' in (safe.get('text') or safe.get('message'))
 assert 'Traceback' not in response.text

def test_bad_native_transport_configuration_is_503(monkeypatch):
 import main
 monkeypatch.setenv('GENOS_CHAT_TRANSPORT','invalid-private-setting')
 response=TestClient(main.app).post('/chat',json={'question':'모의'})
 assert response.status_code==503 and '(503)' in response.json()['data']['text']
 assert 'invalid-private-setting' not in response.text

@pytest.mark.parametrize('native',[False,True])
def test_duplicate_active_request_is_409_without_dispatch(native):
 import stream_app
 calls=[]
 async def service(*args):calls.append(1)
 stream_app._ACTIVE_REQUESTS.add('case-1')
 try:
  response=asyncio.run(stream_app.stream_response({'request_id':'case-1'},service,
   display=adapter.stream_display() if native else None))
 finally:stream_app._ACTIVE_REQUESTS.discard('case-1')
 assert response.status_code==409 and not calls
 assert '(409)' in response.body.decode() and '현재 충분한 법률 검토' in response.body.decode()

@pytest.mark.parametrize('phase',['preflight','display'])
def test_workflow_envelope_and_display_failures_finish_once(monkeypatch,phase):
 v=adapter.views();monkeypatch.setenv('GENOS_RAG_PROGRESS_UI','off');calls=[];finished=[]
 monkeypatch.setattr(v,'_post_code_serving',lambda data: {'status':503,'body':{'error':'private'}} if phase=='preflight' else {'status':200,'body':{'ad_handled':False}})
 async def stream(*args):calls.append(1);return {'answer':{'text':'normal'}}
 async def finish(self,text):finished.append(text)
 monkeypatch.setattr(v,'_stream_code_serving',stream);monkeypatch.setattr(v._ChatProgress,'finish',finish)
 if phase=='display':monkeypatch.setattr(v,'_judgment_flow',lambda *args: (_ for _ in ()).throw(ValueError('private display failure')))
 out=asyncio.run(v.run({'question':'모의','request_id':'case-1'}))
 assert out['answer_status']=='failed' and len(finished)==1 and 'private' not in out['text']
 assert len(calls)==(0 if phase=='preflight' else 1)

@pytest.mark.parametrize('payload',[None,[],{'status':200,'body':[]},'bad private JSON'])
def test_invalid_backend_envelope_is_failed_not_no_sources(payload):
 v=adapter.views();out=v.unwrap(payload)
 assert out['answer_status']=='failed' and out['error_code']=='502'
 assert '(502)' in v.render(out)

def test_ad_failure_is_sanitized_but_normal_admin_table_is_preserved():
 v=adapter.views();out=v._ad_result({'response_schema':'ad-mode-v1','answer_status':'error','text':'private','error':{'type':'TimeoutError','message':'private'}})
 assert out['answer_status']=='failed' and '(timeout)' in out['text'] and 'private' not in json.dumps(out)
 assert v._ad_result({'response_schema':'ad-mode-v1','answer_status':'administration','text':'관리 목록'})['text']=='관리 목록'
