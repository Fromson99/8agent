import json,os,time,threading,sqlite3
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from types import SimpleNamespace as NS
import httpx,pytest
from lawrag.core import request_deadline as rd
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
from semantic_runtime.legal_agent.errors import TransportError
from test_serving_provider import work,gateway,run,completed_app,tree,term_glossary,CFG,HASH,routing

@pytest.fixture
def endpoint():
 seen=[]
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   seen.append({'path':self.path,'body':json.loads(self.rfile.read(int(self.headers['Content-Length'])))})
   try:
    if self.path=='/headers':time.sleep(1.1)
    code=429 if self.path=='/429' or (self.path=='/switch/chat/completions' and len(seen)==1) else 500 if self.path=='/500' else 200
    self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('X-Request-ID','synthetic-request');self.end_headers()
    if self.path in ('/drip','/chat/completions') or (self.path=='/switch/chat/completions' and code==200):
     for _ in range(30):self.wfile.write(b' ');self.wfile.flush();time.sleep(.04)
    if self.path in ('/stall','/slow'):
     self.wfile.write(b' ');self.wfile.flush();time.sleep(.75)
    self.wfile.write(b'{"ok":true}');self.wfile.flush()
   except (BrokenPipeError,ConnectionResetError):pass
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
 thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.03),daemon=True);thread.start()
 yield 'http://127.0.0.1:'+str(server.server_port),seen
 server.shutdown();server.server_close();thread.join(1)

@pytest.mark.parametrize('mode',['headers','drip','stall','slow'])
def test_absolute_deadline_with_real_partial_socket(endpoint,mode):
 url,seen=endpoint;start=time.monotonic()
 with pytest.raises(rd.AbsoluteDeadlineExceeded) as got:
  rd.post_json(url+'/'+mode,headers={'Authorization':'Bearer never-log-this-secret'},json_body={'original':'그대로'},deadline=start+.45)
 elapsed=time.monotonic()-start;e=got.value
 assert .4 <= elapsed < 1.2 and len(seen)==1
 assert e.diagnostics['worker_reaped'] and e.diagnostics['worker_returncode'] is not None
 with pytest.raises(ProcessLookupError):os.kill(e.diagnostics['worker_pid'],0)
 if mode!='headers':
  assert e.diagnostics['headers_received'] and e.diagnostics['received_bytes']>0
  assert e.diagnostics['whitespace_only'] and e.partial_body.strip()==b''
 assert 'never-log-this-secret' not in json.dumps(e.diagnostics)

@pytest.mark.parametrize('mode,status',[('ok',200),('429',429),('500',500)])
def test_normal_and_complete_errors_preserved(endpoint,mode,status):
 url,seen=endpoint;r=rd.post_json(url+'/'+mode,headers={},json_body={'text':'한글'},deadline=time.monotonic()+2)
 assert r.status_code==status and r.json()=={'ok':True}
 assert seen[0]['body']=={'text':'한글'} and r.extensions['absolute_deadline']['complete']
 assert r.extensions['absolute_deadline']['worker_reaped']

def test_expired_never_starts_request(endpoint):
 url,seen=endpoint
 with pytest.raises(rd.AbsoluteDeadlineExceeded) as got:rd.post_json(url,headers={},json_body={},deadline=time.monotonic()-1)
 assert got.value.diagnostics['sent'] is False and seen==[]

def test_reproduces_old_idle_timeout_overrun(endpoint):
 url,seen=endpoint;start=time.monotonic()
 with httpx.Client(timeout=.2,trust_env=False) as client:r=client.post(url+'/drip',json={})
 assert r.json()=={'ok':True} and time.monotonic()-start>1.0

def test_native_transport_absolute_timeout_is_unknown(endpoint):
 url,seen=endpoint;t=LocalQwen38Transport.__new__(LocalQwen38Transport)
 t.binding={'model':'synthetic'};t.policy={'max_output_tokens':None,'provider_routing':{},'reasoning':{},'endpoint':url};t.provider_policy=None;t._key='synthetic-secret'
 with pytest.raises(TransportError) as got:t.send_once(body={'model':'synthetic','stream':False},ticket={'remaining_seconds':.45})
 assert got.value.unknown and not got.value.retryable and got.value.http_status==504
 assert got.value.response['transport_diagnostics']['worker_reaped'] and len(seen)==1

def test_gateway_rejects_late_adapter_result_and_charges_once(work,monkeypatch):
 from test_legal_agent_double_harness import wire
 g,t=gateway(work,[]);g.context=replace(g.context,deadline=time.monotonic()+.15)
 def late(**kwargs):time.sleep(.2);return wire({'ok':True})
 monkeypatch.setattr(t,'send_once',late)
 with pytest.raises(TransportError) as got:run(g,work)
 assert got.value.unknown and got.value.code=='MODEL_DEADLINE_EXCEEDED'
 assert work.budget()['model_reserved']==1
 assert work.db.execute('select status from model_attempt').fetchone()[0]=='UNKNOWN'
 assert routing.current(work,CFG,HASH,work.context.binding_hash)[0]['switches']==0

def test_actual_native_http_timeout_saved_no_retry(completed_app,endpoint,monkeypatch):
 api,t,runtime=completed_app;url,seen=endpoint
 t.provider_policy=CFG;t.routing_hash=HASH
 def expired(*,body,ticket):
  try:rd.post_json(url+'/drip',headers={},json_body=body,deadline=min(ticket['deadline'],time.monotonic()+.45))
  except rd.AbsoluteDeadlineExceeded as e:
   err=TransportError('absolute deadline',unknown=True,response={'transport_diagnostics':e.diagnostics});err.code='MODEL_DEADLINE_EXCEEDED';err.http_status=504;raise err
 monkeypatch.setattr(t,'send_once',expired)
 start=time.monotonic();response=api.post('/v1/rag/ask',json={'question':'모의승인규정 제1조 승인 기준은?','session_id':'s','request_id':'timeout'})
 assert response.status_code==504,response.text
 assert time.monotonic()-start<8 and len(seen)==1
 journals=list((runtime/'legal-agent/runs').glob('*/*/journal.sqlite'));assert journals
 for p in journals:
  with sqlite3.connect(p) as db:
   assert db.execute('select model_reserved from budget').fetchone()[0]==1
   assert db.execute('select status from model_attempt').fetchone()[0]=='UNKNOWN'
 # Resuming the same request cannot send an uncertain operation again.
 api.post('/v1/rag/ask',json={'question':'모의승인규정 제1조 승인 기준은?','session_id':'s','request_id':'timeout'})
 assert len(seen)==1

def test_common_client_uses_real_deadline_no_switch(endpoint,tmp_path,monkeypatch):
 import test_provider as p
 url,seen=endpoint;monkeypatch.setenv('OPEN_ROUTER','test-key');monkeypatch.setattr(p.mod,'PROXY_ENDPOINT',url)
 c=p.mod.ExperimentClient(p.R,tmp_path/'raw',provider_policy=p.policy(tmp_path),max_calls=4,max_repairs=0)
 with pytest.raises(p.mod.ExperimentTransportError) as got:c.chat_completions(p.BODY,timeout_seconds=.45)
 assert got.value.unknown and not got.value.retryable and c.calls==1 and len(seen)==1
 assert seen[0]['body']['provider']['only']==['chutes/fp8']

def test_common_client_preparation_uses_existing_deadline(endpoint,tmp_path,monkeypatch):
 import test_provider as p
 url,seen=endpoint;monkeypatch.setenv('OPEN_ROUTER','test-key');monkeypatch.setattr(p.mod,'PROXY_ENDPOINT',url)
 c=p.mod.ExperimentClient(p.R,tmp_path/'raw',provider_policy=p.policy(tmp_path),max_calls=4,max_repairs=0)
 old=c._write
 def slow(path,value):
  old(path,value)
  if path.name=='request.json':time.sleep(.1)
 monkeypatch.setattr(c,'_write',slow)
 with pytest.raises(p.mod.ExperimentTransportError):c.chat_completions(p.BODY,timeout_seconds=.04)
 assert seen==[]

def test_real_429_switch_shares_absolute_budget(endpoint,tmp_path,monkeypatch):
 import test_provider as p
 url,seen=endpoint;monkeypatch.setenv('OPEN_ROUTER','test-key');monkeypatch.setattr(p.mod,'PROXY_ENDPOINT',url+'/switch')
 c=p.mod.ExperimentClient(p.R,tmp_path/'raw',provider_policy=p.policy(tmp_path),max_calls=4,max_repairs=0)
 start=time.monotonic()
 with pytest.raises(p.mod.ExperimentTransportError) as got:c.chat_completions(p.BODY,timeout_seconds=.65)
 assert got.value.unknown and not got.value.retryable and .6<time.monotonic()-start<1.4
 assert c.calls==2 and [x['body']['provider']['only'] for x in seen]==[['chutes/fp8'],['near-ai/fp8']]
