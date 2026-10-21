from copy import deepcopy
from types import SimpleNamespace as S
import json,sqlite3,importlib.util
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.legal_agent import request_repair as rr
from semantic_runtime.legal_agent.errors import ContractError,InvestigationPending,BudgetExhausted
from test_main50_request_repair import GAP,tree as gap_tree,session
from test_main50_request_repair import tree

@pytest.mark.parametrize('target',['모의승인규정 제1조 이후','모의승인규정 제2조','모의승인규정 승인 세부사항'])
def test_refined_gap_keeps_allowance_and_new_target(session,target):
 native,_=session;prior=rr.bind_gap(GAP,native.sources);prior['gap_key']=prior['identity_key']
 proposal={'gaps':[{**GAP,'missing_target':target,'previous_gap_key':prior['gap_key']}]};before=deepcopy(proposal)
 result=rr.bind_gaps(proposal,native.sources,[{'gaps':[prior]}])['gaps'][0]
 assert result['identity_key']==prior['identity_key'] and result['missing_target']==target
 assert result['target_binding']==rr.bind_gap({**GAP,'missing_target':target},native.sources)['target_binding']
 assert proposal==before
 state={'gap_rounds':[{'gaps':[prior],'target_evidence_at_close':{prior['gap_key']:rr.target_evidence_signature(result,{})}}]}
 assert not rr.may_reopen(result,state)

@pytest.mark.parametrize('mutation',['binding','issue','unknown'])
def test_invalid_previous_gap_still_rejected(session,mutation):
 native,_=session;prior=rr.bind_gap(GAP,native.sources);prior['gap_key']=prior['identity_key']
 new={**GAP,'previous_gap_key':prior['gap_key']}
 if mutation=='binding':prior['target_binding_hash']='changed'
 elif mutation=='issue':new['issue_id']='Q2'
 else:new['previous_gap_key']='unknown'
 with pytest.raises((ContractError,rr.ProposalError)):rr.bind_gaps({'gaps':[new]},native.sources,[{'gaps':[prior]}])

spec=importlib.util.spec_from_file_location('prior_workflow',Path(__file__).parents[1]/'adr_0838/test_workflow.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
@pytest.fixture
def workflow_tree(tmp_path,term_glossary):return prior.tree.__wrapped__(tmp_path,term_glossary)

@pytest.mark.parametrize('failure',[InvestigationPending,BudgetExhausted])
def test_read_sources_survive_incomplete_assessment_and_saved_consumer(tmp_path,workflow_tree,monkeypatch,failure):
 from semantic_runtime.legal_agent.completion_execution import CompletionExecution
 from semantic_runtime.legal_agent.workflow_execution import task_context
 original=CompletionExecution.completion_stage
 def incomplete(self,stage,*args):
  if stage=='ASSESS' and (task_context() or {}).get('source_category')=='internal':raise failure('synthetic incomplete assessment')
  return original(self,stage,*args)
 monkeypatch.setattr(CompletionExecution,'completion_stage',incomplete)
 app,t=prior.task_app(tmp_path,workflow_tree)
 with TestClient(app) as client:
  response=client.post('/v1/rag/ask',json=prior.BODY);assert response.status_code==200,response.text
  out=response.json();inside=out['rag_results']['internal']
  assert inside['status']=='failed' and inside['bundle']['export_mode']=='READ_ORIGINALS'
  assert inside['evidence_ids'] and not inside['bundle']['claims'] and inside['answer'] is None
  assert any(stage=='workflow-compare' for stage,_ in t.views),out
  assert all(i['internal']['citations'] for i in out['comparison_items']['items'])
  count=len(t.views)
  saved=client.get('/v1/workflows/runs/'+out['run_id'],params={'session_id':'s'})
  again=client.post('/v1/rag/ask',json=prior.BODY)
  assert saved.status_code==again.status_code==200
  assert saved.json()['answer']==again.json()['answer']==out['answer'] and len(t.views)==count
  path=app.state.workflow_runtime.root/out['run_id']/'journal.sqlite'
  with sqlite3.connect(path) as db:db.execute("UPDATE workflow_child_export SET bundle_json='{}' WHERE envelope_json='null'")
  bad=client.post('/v1/rag/ask',json=prior.BODY)
  assert bad.status_code>=400 and len(t.views)==count

@pytest.mark.parametrize('new',[False,True])
def test_research_yields_after_one_task_and_no_new_evidence_stops(monkeypatch,new):
 from workflow.risk_team_compare_workflow import task_board as tb
 calls=[];old={'request_id':'old','status':'partial','evidence_ids':['old-e'],'continuation':{'goal_id':'g'}}
 state={'scope':{'issues':[{'id':'i'}]},'rag_results':{'internal':old},'rag_attempts':{},'task_board':{'round':0,'tasks':{str(i):{'status':'PENDING','task':{'target_side':'internal','missing_target':str(i)}} for i in range(3)}}}
 ctx=S(definition=S(manifest={'max_recoveries':2}),repo=S(save=lambda s:None,call=lambda k:{'result':old}))
 def discover(ctx,s,side,**kw):
  calls.append(kw);s['rag_attempts'][side]={'request_id':'new','status':'partial','evidence_ids':['old-e']+(['new-e'] if new else [])};return True
 monkeypatch.setattr(tb.retrieval,'discover',discover)
 assert tb.research(ctx,state)==new and len(calls)==1 and state['task_board']['round']==1
 assert sum(v['status']=='PENDING' for v in state['task_board']['tasks'].values())==2
