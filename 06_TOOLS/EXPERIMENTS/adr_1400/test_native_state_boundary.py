"""Actual API false PASS -> primary repair -> persisted state -> real RAG entry.
Intentional failure at INTENT isolates this contract from unrelated source fixtures.
"""
from copy import deepcopy
import json,sqlite3
from fastapi.testclient import TestClient
from test_multiturn_structured_scope import tree,change
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT,wire
from test_memory_runtime_v2 import command
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import memory_rag,errors
from semantic_runtime.legal_agent.shortcut_store import selected_store


def test_native_api_repairs_before_persisting_and_enters_current_task(tree,tmp_path,monkeypatch):
 gen,idx=tree;old='모의승인규정 제1조제1항에서 승인 예외를 찾아줘.';new='같은 규정 제1조제2항에서 보고 의무를 찾아줘.'
 class Transport:
  binding=settings()['model_binding']
  def __init__(self):self.target=None;self.checks=0;self.repairs=[]
  def validate_model(self):return {'verified':True,'synthetic':True}
  def send_once(self,*,body,ticket):
   from api_fixture_integrated import decode
   v=decode(json.loads(body['messages'][1]['content'])['view']);phase=v.get('source_stage') or v.get('phase')
   if phase=='request-entry':
    return wire({'routing':{'mode':'CASE','answer':'','reason':'원문 조사'},'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],'queries':['승인 예외'],'format':'prose','reason':'명시 조항'},'intent':{'purpose':'승인 예외 조사','concepts':['승인'],'issues':[{'id':'Q1','question':old,'subject':'승인','kind':'OTHER','request_quote':old}]},'context_quotes':[],'search':{'mode':'FULLTEXT','scope_decision':{'mode':'NAMED_SCOPE','targets':[{'document':'모의승인규정','structure':'제1조제1항','selection':None}],'user_quote':old,'reason':'명시 범위'},'reason':'범위 조회'}})
   if phase=='source-request-route':return wire({'mode':'CASE','answer':'','reason':'현재 후속 질문 조사'})
   if phase=='memory-resolve':return wire(command('RESEARCH_REENTER',target=self.target,stage='SELECT'))
   if phase=='memory-resolve-repair':
    self.repairs.append(deepcopy(v));return wire(command('RESEARCH_REPLAN',target=self.target,task=new,queries=['보고 의무'],search_scope_change=change(structure='제1조제2항',quote=new)))
   if phase=='memory-reason-decision-review':return wire({'decision':'PASS'})
   if phase=='memory-command-check':
    self.checks+=1;return wire({'valid':True,'reason':'현재 요청 목적을 독립 제시한 합성 검토','request_relation':'FOLLOWUP','requested_task':new})
   raise AssertionError(phase)
 transport=Transport();entries=[]
 def entry(self,stage,state,parts,utterance,format):
  entries.append({'stage':stage,'state':deepcopy(state),'effective_question':self.host.retrieval_question(state),'utterance':utterance})
  raise errors.ContractError('INTENTIONAL_NATIVE_BOUNDARY_STOP')
 monkeypatch.setattr(memory_rag.NativeExecution,'stage',entry)
 profile={**settings(),'max_model_attempts':40,'request_entry_policy':'fused-title-v1','candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'compact_input':True,'minimal_input':True,'supervisor_mode':'enforce','structure_first':True,'completion_contract':True,'completion_policy_version':'investigation-completion-v8'}}
 runtime=tmp_path/'runtime'
 app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=runtime,memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d','other']})
 app.state.pipeline.term_agent.unit_fulltext=idx
 with TestClient(app) as api:
  first=api.post('/v1/rag/ask',json={'session_id':'native-delta','request_id':'r1','question':old})
  assert first.status_code>=400
  with sqlite3.connect(selected_store(runtime)) as db:
   gid,encoded=db.execute('SELECT id,state FROM goal').fetchone();before=json.loads(encoded)
  transport.target=gid
  second=api.post('/v1/rag/ask',json={'session_id':'native-delta','request_id':'r2','question':new})
  assert second.status_code>=400
 with sqlite3.connect(selected_store(runtime)) as db:
  after=json.loads(db.execute('SELECT state FROM goal WHERE id=?',(gid,)).fetchone()[0])
  events=[json.loads(x[0]) for x in db.execute('SELECT command FROM event WHERE after_state IS NOT NULL')]
 assert transport.checks==2 and len(transport.repairs)==1
 assert transport.repairs[0]['rejected_decision']['command']['method_id']=='RESEARCH_REENTER'
 assert before['task']==old and after['task']==new
 assert before['search_scope']['targets'][0]['unit_id']=='1' and after['search_scope']['targets'][0]['unit_id']=='5'
 assert events[-1]['method_id']=='RESEARCH_REPLAN' and events[-1]['task']==new
 assert entries[-1]['stage']=='INTENT' and entries[-1]['effective_question']==new
 assert entries[-1]['state']['task']==new
