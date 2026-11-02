import importlib,sys,json
from pathlib import Path
import httpx,pytest
from test_legal_agent_double_harness import work
from test_serving_provider import gateway,run,error,CFG,HASH
from semantic_runtime.legal_agent import provider_routing
from semantic_runtime.legal_agent.errors import TransportError,ProposalError,ContractError

@pytest.mark.parametrize('kind',[TypeError,ValueError,RuntimeError])
def test_untyped_failure_preserves_unknown_cause_and_no_retry(work,kind):
 original=kind('injected adapter failure');g,t=gateway(work,[original])
 with pytest.raises(TransportError) as caught:run(g,work)
 assert caught.value.unknown and caught.value.__cause__ is original
 assert len(t.sent)==work.budget()['model_reserved']==1
 assert work.db.execute('select status from model_attempt').fetchone()[0]=='UNKNOWN'
 assert provider_routing.current(work,CFG,HASH,work.context.binding_hash)[0]['switches']==0
 assert not work.heads('finding')

@pytest.mark.parametrize('kind',[ProposalError,ContractError])
def test_typed_failure_preserves_original_failed_and_no_switch(work,kind):
 original=kind('injected invalid output');g,t=gateway(work,[original])
 with pytest.raises(kind) as caught:run(g,work)
 assert caught.value is original
 assert len(t.sent)==work.budget()['model_reserved']==1
 assert work.db.execute('select status from model_attempt').fetchone()[0]=='FAILED'
 assert provider_routing.current(work,CFG,HASH,work.context.binding_hash)[0]['switches']==0

def test_confirmed_429_only_switch_once_and_normal_success(work):
 g,t=gateway(work,[error(),{'ok':True}]);assert run(g,work)=={'ok':True}
 assert len(t.sent)==2 and work.budget()['model_reserved']==2
 assert provider_routing.current(work,CFG,HASH,work.context.binding_hash)[0]['switches']==1

@pytest.mark.parametrize('status,unknown',[(429,True),(500,True),(400,False)])
def test_other_rejections_and_unknown_never_switch(work,status,unknown):
 g,t=gateway(work,[error(status,unknown)])
 with pytest.raises(TransportError):run(g,work)
 assert len(t.sent)==1
 assert provider_routing.current(work,CFG,HASH,work.context.binding_hash)[0]['switches']==0

@pytest.mark.parametrize('failure',['deadline','connect','read','format','policy','429','500','success'])
def test_reserved_adapter_preserves_failures_without_hidden_sends(tmp_path,monkeypatch,failure):
 import time,os
 from lawrag.research.experiment_client import ExperimentClient
 from lawrag.research.openrouter_legal_adapter import send_reserved
 from lawrag.core import request_deadline as rd
 from semantic_runtime.legal_agent import errors
 C=Path(os.environ['WORKFLOW_TEST_CODE_ROOT']);monkeypatch.setenv('OPEN_ROUTER','synthetic-key')
 original=rd.AbsoluteDeadlineExceeded({'received_bytes':660,'whitespace_only':True},b' '*660) if failure=='deadline' else httpx.ConnectError('offline') if failure=='connect' else httpx.ReadError('disconnected')
 sent=[]
 def post(url,**kwargs):
  sent.append(kwargs['json_body'])
  if failure in ('deadline','connect','read'):raise original
  if failure in ('429','500'):return httpx.Response(int(failure),json={'error':{'code':int(failure)}},request=httpx.Request('POST',url))
  return httpx.Response(200,json={'model':'qwen/qwen3.8-27b','provider':'unexpected' if failure=='policy' else 'Parasail','choices':[{'finish_reason':'length' if failure=='format' else 'stop','message':{'content':'{"ok":true}'}}],'usage':{'prompt_tokens':1,'completion_tokens':1}},request=httpx.Request('POST',url))
 monkeypatch.setattr(rd,'post_json',post)
 client=ExperimentClient(C,tmp_path/'raw',max_calls=4,max_repairs=0)
 body={'model':client.model,'messages':[{'role':'user','content':'synthetic public fixture'}],'stream':False}
 ticket={'provider_index':0,'remaining_seconds':30,'deadline':time.monotonic()+30}
 def call():return send_reserved(client,body=body,ticket=ticket,phase='synthetic',error_module=errors,request_encoder=lambda x:x)
 if failure=='success':assert call()['status_code']==200
 else:
  expected=ProposalError if failure=='format' else ContractError if failure=='policy' else TransportError
  with pytest.raises(expected) as caught:call()
  if failure=='deadline':
   assert caught.value.http_status==504 and caught.value.code=='MODEL_DEADLINE_EXCEEDED'
   assert caught.value.unknown and not caught.value.retryable
   assert caught.value.__cause__.__cause__ is original
   assert caught.value.response['transport_diagnostics']['received_bytes']==660
  if failure in ('connect','read'):assert caught.value.unknown==(failure=='read')
  if failure=='429':assert caught.value.response['acceptance']=='KNOWN_REJECTED'
  if failure=='500':assert caught.value.unknown
 assert len(sent)==client.calls==1 and client.provider_index==0 and not client.provider_switches


def test_expired_reserved_ticket_never_dispatches(tmp_path,monkeypatch):
 import os,time
 from lawrag.research.experiment_client import ExperimentClient
 from lawrag.research.openrouter_legal_adapter import send_reserved
 from semantic_runtime.legal_agent import errors
 monkeypatch.setenv('OPEN_ROUTER','synthetic-key');client=ExperimentClient(Path(os.environ['WORKFLOW_TEST_CODE_ROOT']),tmp_path/'raw',max_calls=4)
 with pytest.raises(ContractError):send_reserved(client,body={},ticket={'provider_index':0,'remaining_seconds':1,'deadline':time.monotonic()-1},phase='synthetic',error_module=errors,request_encoder=lambda x:x)
 assert client.calls==0
