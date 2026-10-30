from copy import deepcopy
from pathlib import Path
import json,hashlib,sqlite3
from types import SimpleNamespace as NS
import pytest,httpx
from test_legal_agent_double_harness import work,PROFILE,wire
from semantic_runtime.legal_agent import provider_routing as routing
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.bounded_source_session import _Protocol
from semantic_runtime.legal_agent.errors import TransportError,ContractError,ProposalError,BudgetExhausted
from semantic_runtime.legal_agent.repository import WorkRepository
R=Path(__file__).resolve().parents[3]
CFG=json.loads((R/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json').read_text())
HASH=hashlib.sha256(json.dumps(CFG).encode()).hexdigest()
SCHEMA={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}

def gateway(work,sequence):
 class Transport:
  binding=PROFILE['model_binding'];provider_policy=CFG;routing_hash=HASH
  def __init__(self):self.sent=[]
  def send_once(self,*,body,ticket):
   self.sent.append((deepcopy(body),dict(ticket)))
   value=sequence.pop(0)
   if isinstance(value,Exception):raise value
   return wire(value)
 t=Transport();p={**PROFILE,'max_transport_retries':0,'max_schema_repairs':0,'max_output_tokens':None}
 g=ModelGateway(work,work.context,p,{},t,message_protocol=_Protocol(SCHEMA),system='synthetic')
 return g,t

def error(status=429,unknown=False):
 return TransportError('synthetic',retryable=True,unknown=unknown,response={'status_code':status,'acceptance':'UNKNOWN' if unknown else 'KNOWN_REJECTED','body_sha256':'a'*64})

def run(g,work):
 return g.generate('investigate',work.save_view('investigate',{'synthetic':True},[]),'BoundedSourceDecision')

def test_native_gateway_two_physical_attempts_and_resume_shared_one_switch(work):
 g,t=gateway(work,[error(),{'ok':True}]);assert run(g,work)=={'ok':True}
 assert work.budget()['model_reserved']==2
 assert [b['provider']['only'] for b,_ in t.sent]==[['chutes/fp8'],['near-ai/fp8']]
 assert [tk['provider_index'] for _,tk in t.sent]==[0,1]
 assert all('max_tokens' not in b for b,_ in t.sent)
 # Another gateway object on the SAME journal does not reset the switch allowance.
 g2,t2=gateway(work,[error()])
 with pytest.raises(TransportError):g2.generate('investigate',work.save_view('investigate',{'synthetic':'next'},[]),'BoundedSourceDecision')
 assert len(t2.sent)==1 and t2.sent[0][0]['provider']['only']==['near-ai/fp8']
 assert work.budget()['model_reserved']==3
 state,_=routing.current(work,CFG,HASH,work.context.binding_hash);assert state['switches']==1
 assert work.db.execute("select count(*) from model_attempt").fetchone()[0]==3

@pytest.mark.parametrize('status,unknown',[(429,True),(400,False),(403,False),(408,False),(500,True),(502,True)])
def test_unknown_and_non429_never_switch(work,status,unknown):
 g,t=gateway(work,[error(status,unknown)])
 with pytest.raises(TransportError):run(g,work)
 assert len(t.sent)==1 and work.budget()['model_reserved']==1
 assert routing.current(work,CFG,HASH,work.context.binding_hash)[0]['index']==0

def test_last_physical_budget_does_not_switch(work):
 work.db.execute('UPDATE budget SET model_limit=finalization_reserve+1')
 g,t=gateway(work,[error()])
 with pytest.raises(TransportError):run(g,work)
 assert len(t.sent)==1 and routing.current(work,CFG,HASH,work.context.binding_hash)[0]['switches']==0

@pytest.mark.parametrize('damage',['hash','binding','policy'])
def test_tamper_blocks_resume(work,damage):
 g,t=gateway(work,[error(),{'ok':True}]);run(g,work)
 if damage=='hash':
  with pytest.raises(sqlite3.IntegrityError):work.db.execute("UPDATE event SET payload_hash='wrong' WHERE kind=?",(routing.EVENT,))
  rows=work.db.execute('SELECT kind,payload_json,payload_hash FROM event WHERE kind=?',(routing.EVENT,)).fetchall()
  broken=NS(db=NS(execute=lambda *a:[(r[0],r[1],'wrong') for r in rows]))
  with pytest.raises(ContractError):routing.current(broken,CFG,HASH,work.context.binding_hash)
  return
 with pytest.raises(ContractError):routing.current(work,CFG,'wrong' if damage=='policy' else HASH,'wrong' if damage=='binding' else work.context.binding_hash)

def test_separate_requests_start_at_primary(work,tmp_path):
 g,t=gateway(work,[error(),{'ok':True}]);run(g,work)
 other=WorkRepository(tmp_path/'other.sqlite',work.context,PROFILE)
 try:assert routing.current(other,CFG,HASH,other.context.binding_hash)[0]['index']==0
 finally:other.close()

@pytest.mark.parametrize('damage',['provider','model','reasoning'])
def test_shared_response_policy_rejects_mismatch(damage):
 b={'provider':'Chutes','model':CFG['model'],'choices':[]}
 if damage=='provider':b['provider']='Parasail'
 if damage=='model':b['model']='other'
 if damage=='reasoning':b['usage']={'completion_tokens_details':{'reasoning_tokens':1}}
 with pytest.raises(ValueError):routing.validate_response(b,CFG['providers'][0],CFG['model'])

from test_investigation_completion_adr0678 import completed_app,tree
from conftest import term_glossary

def test_actual_http_new_run_retains_switch_and_physical_budget(completed_app,monkeypatch):
 api,t,runtime=completed_app;sent=[]
 t.provider_policy=CFG;t.routing_hash=HASH
 def fail(*,body,ticket):
  sent.append(body['provider']['only']);raise error()
 monkeypatch.setattr(t,'send_once',fail)
 body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'s','request_id':'r1'}
 for expected in (503,500):
  result=api.post('/v1/rag/ask',json=body);assert result.status_code==expected,result.text
 # Outer decision remains reserved after failure: resume must not replay it.
 assert sent==[['chutes/fp8'],['near-ai/fp8']]
 values=[]
 for p in (runtime/'legal-agent/runs').glob('*/*/journal.sqlite'):
  with sqlite3.connect(p) as db:
   values.append(db.execute('SELECT model_reserved FROM budget').fetchone()[0])
   binding=db.execute('SELECT binding_hash FROM run').fetchone()[0]
   state,_=routing.current(NS(db=db),CFG,HASH,binding);assert state['index']==1 and state['switches']==1
 assert sorted(values)==[2,2]
 assert api.post('/v1/rag/ask',json={**body,'request_id':'r2'}).status_code==503
 assert sent[-2:]==[['chutes/fp8'],['near-ai/fp8']]

@pytest.fixture
def completed_app(tmp_path,tree):
 import os
 from test_investigation_completion_adr0678 import CompletionTransport,settings
 from semantic_runtime.app import create_app
 from fastapi.testclient import TestClient
 gen,idx=tree;t=CompletionTransport()
 profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,'max_transport_retries':0,
  'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True}}
 principal={'user_id':'synthetic','team_id':'risk_team','document_ids':['d']}
 app=create_app(tmp_path,gen,contracts_root=Path(os.environ['WORKFLOW_TEST_CODE_ROOT']),provider=object(),implementation='legal-agent-unified-v6',
  legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:principal)
 app.state.pipeline.term_agent.unit_fulltext=idx
 with TestClient(app) as api:yield api,t,tmp_path/'90_RUNTIME/semantic'
