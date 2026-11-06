import asyncio,json,logging,copy,io
import pytest
from semantic_runtime import chat_adapter as ca,observability as obs
from semantic_runtime.app import legal_error_payload
from semantic_runtime.progress import ProgressCapture
from semantic_runtime.legal_agent.errors import InvestigationPending
from semantic_runtime.request_report import _RequestCapture

TAIL='PRIVATE_CAUSE_TAIL_한글';LONG='중첩 원인\n'+'x'*45001+TAIL

def failure():return {'error_type':'InternalSecretError','detail':LONG,'request_id':'req-1','failure_diagnostics':{'traceback':LONG},'diagnostics':{'rejected_assessment':LONG}}

def test_api_logs_complete_scrubbed_causes_and_returns_reference(monkeypatch):
 monkeypatch.setenv('GENOS_LLM_KEY','synthetic-credential-only')
 capture=_RequestCapture('req-1');logger=obs.get_logger('app');logger.addHandler(capture)
 try:
  try:raise InvestigationPending(LONG+' synthetic-credential-only',diagnostics={'cause':LONG})
  except InvestigationPending as exc:r=legal_error_payload(exc,'req-1')
 finally:logger.removeHandler(capture)
 assert r['answer_status']=='failed' and r['request_id']=='req-1'
 assert TAIL not in json.dumps(r) and 'synthetic-credential-only' not in json.dumps(r)
 logged=json.dumps(capture.events,ensure_ascii=False)
 assert TAIL in logged and 'x'*45001 in logged and 'synthetic-credential-only' not in logged

@pytest.mark.parametrize('kind',['full_error','proposal'])
def test_progress_blocks_errors_and_unaccepted_judgments(tmp_path,kind):
 w=ca.views();events=[];collector=ProgressCapture('r',tmp_path,events.append)
 basis={'detail_mode':kind if kind=='full_error' else 'judgment','kind':'ATTEMPT_FINISHED','state':'PROPOSED'}
 collector.publish('decision','실행 오류',basis=basis,details=[LONG])
 assert events==[]
 display=w._ChatProgress({});display.enabled=False;display.show_progress=True
 asyncio.run(display.progress({'schema_version':'rag-progress-v1','kind':'decision','label':'error','basis':basis,'details':[LONG]}))
 assert not display.blocks and not display.flow_events


def test_accepted_judgment_and_normal_answer_remain():
 w=ca.views();display=w._ChatProgress({});display.enabled=False;display.show_progress=True
 e={'schema_version':'rag-progress-v1','kind':'decision','label':'승인 판단','basis':{'kind':'CASE_JUDGMENT_ACCEPTED','detail_mode':'judgment','state':'COMPLETED'},'details':['현재 판단: 모의 규정에 따른 답변']}
 asyncio.run(display.progress(e))
 card = json.loads(display.blocks[0]['data']['output']['content'])['visible_rationale']
 assert '승인 판단' in card and '현재 판단: 모의 규정에 따른 답변' in card
 assert '모의 규정' in json.dumps(display.flow_events,ensure_ascii=False)
 assert w.render({'answer':{'text':'정상 답변'}}).startswith('정상 답변')


def test_legacy_cached_error_is_not_reused():
 w=ca.views();b={'answer':{'text':'정상 답변'}}
 display=asyncio.run(w.workflow_display_result(b,[],request_id='r'))
 b['workflow_display']=display
 assert w._bound_workflow_display(b,'r')
 display.pop('display_policy_revision');display['text']=LONG
 display['content_sha256']=w._workflow_display_digest({k:v for k,v in display.items() if k!='content_sha256'})
 assert w._bound_workflow_display(b,'r') is None
 assert TAIL not in w.render(b)

@pytest.mark.parametrize('route',['/json','/stream'])
def test_workflow_raw_json_and_sse_failure_are_projected(monkeypatch,tmp_path,route):
 import main_workflow
 from fastapi.testclient import TestClient
 monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path))
 async def failed(config,data):return {'status':500,'body':failure()}
 monkeypatch.setattr(main_workflow.backend,'service',failed)
 r=TestClient(main_workflow.app).post(route,json={'API_TYPE':'LEGAL_AGENT','question':'모의','request_id':'req-1'})
 assert TAIL not in r.text and 'InternalSecretError' not in r.text
 if route=='/json':
  b=r.json();assert b['status']==500 and b['body']['answer_status']=='failed'
  assert '조회 번호' in b['body']['workflow_display']['text']
 else:assert '"failed"' in r.text


def test_native_chat_no_echo_or_exception_details(monkeypatch,tmp_path):
 monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path))
 async def failed(body):
  if body['API_TYPE']=='AD_PROBE':return {'status':200,'body':{'ad_handled':False}}
  raise ValueError(LONG)
 monkeypatch.setattr(ca,'call_service',failed)
 r=asyncio.run(ca.chat({'question':'모의','request_id':'req-1','debug':True,'diagnostics':LONG}))['data']
 assert r['answer_status']=='failed' and '조회 번호: req-1' in r['text']
 assert TAIL not in json.dumps(r) and 'error_type' not in r
