from copy import deepcopy
from types import SimpleNamespace as S
import json
import pytest
from jsonschema import ValidationError
from fastapi.testclient import TestClient
from test_main50_request_repair import tree,session,modern,GAP
from test_investigation_completion_adr0678 import decision,apply
from semantic_runtime.legal_agent import request_repair as rr,law_navigation as ln,evidence_inventory as inv
from semantic_runtime.legal_agent.errors import ProposalError,ContractError

@pytest.mark.parametrize('gap_form',['omit','empty','one'])
def test_valid_read_does_not_require_gap_bookkeeping(session,gap_form):
 native,_=session;i=modern(native)
 i.p['assessment_gaps']=[{**rr.bind_gap({**GAP,'missing_target':target},i.s),'gap_id':'gap-'+str(n),'gap_key':'key-'+str(n)} for n,target in enumerate(('모의승인규정 제1조','모의승인규정 제2조'))]
 i.open_gap_round();d,a=i.view();target=next(k for k,v in a.items() if v['action']=='READ_ARTICLES');v=decision(d,'READ_ARTICLES',target);v['branch_decisions']=[]
 if gap_form!='omit':v['gap_ids']=[] if gap_form=='empty' else ['gap-0']
 i.validate(v,d,a)
 bad=deepcopy(v);bad['gap_ids']=['unknown']
 with pytest.raises((ValidationError,ProposalError,ValueError)):i.validate(bad,d,a)

@pytest.mark.parametrize('resolution',['omit','empty','partial'])
def test_finish_selected_original_without_adopt_preserves_unresolved(session,resolution):
 native,_=session;i=modern(native);d,a=i.view();apply(i,decision(d,'READ_PARENT',d['articles'][0]['read_parent_action']),d,a)
 i.p['assessment_gaps']=[{**rr.bind_gap({**GAP,'missing_target':target},i.s),'gap_id':'gap-'+str(n),'gap_key':'key-'+str(n)} for n,target in enumerate(('모의승인규정 제1조','모의승인규정 제2조'))]
 i.open_gap_round();i.p['window']='sources';i.p['window_groups']=list(i.p['selected']);d,a=i.view();v=decision(d,'FINISH');v['branch_decisions']=[];v['evidence_sufficient']=False
 assert v['basis_refs']
 if resolution!='omit':v['gap_resolutions']=[] if resolution=='empty' else [{'gap_id':'gap-0','status':'UNRESOLVED','reason':'한계 유지'}]
 apply(i,v,d,a);out=i.result(v)
 assert out['selected_originals'] and out['final_evidence_ids'] and out['evidence_sufficient'] is False
 assert all(g['status']!='ACTIVE' for g in i.p['groups'].values())
 i.close_gap_round(v.get('gap_resolutions',[]),'FINISH partial')
 assert all(r['status']=='UNRESOLVED' for r in i.p['gap_rounds'][-1]['resolutions'])
 damaged=deepcopy(i.p);damaged['basis_history'].pop(v['basis_refs'][0])
 with pytest.raises(ContractError):inv.originals_for(i.s,damaged,v['basis_refs'])

@pytest.mark.parametrize('status',['PARTIAL','MISSING','CONFLICT','CONFIRMED'])
def test_selected_sources_compare_without_semantic_approval(monkeypatch,status):
 from workflow.risk_team_compare_workflow import basis
 from workflow import presentation
 es=[{'evidence_id':s,'side':s,'spans':[{'text':s}]} for s in ('internal','external')]
 monkeypatch.setattr(presentation,'evidence',lambda ctx,state,ids=None:es)
 item={s:{'status':status,'citations':[{'evidence':s,'quote':s}],'dependencies':[],'scope_sufficient':False,'missing':'추가 확인'} for s in ('internal','external')}
 state={'scope':{'issues':[{'id':'i'}]},'task_board':{'rows':{'i:a':{'issue_id':'i','field':'a','current':item}}}}
 ctx=S(request={'as_of':None},repo=S(save=lambda s:None));out=basis.from_items(ctx,state)
 assert len(out['pairs'])==1 and out['pairs'][0]['comparison_eligibility'] and len(out['gaps'])==2
 item['internal']['citations'][0]['quote']='invented'
 with pytest.raises(ValueError):basis.from_items(ctx,state)

# Existing API fixture runs the actual workflow with synthetic model responses.
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('direct_prior',Path(__file__).parents[1]/'adr_0838/test_workflow.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
@pytest.fixture
def workflow_tree(tmp_path,term_glossary):return prior.tree.__wrapped__(tmp_path,term_glossary)
def test_api_routes_items_directly_to_compare_and_saves(tmp_path,workflow_tree):
 app,t=prior.task_app(tmp_path,workflow_tree,'failed_followup')
 with TestClient(app) as c:
  r=c.post('/v1/rag/ask',json=prior.BODY);assert r.status_code==200,r.text
  v=r.json();stages=[s for s,_ in t.views]
  assert 'workflow-items' in stages and 'workflow-compare' in stages and 'workflow-basis' not in stages
  assert v['report']['rows'] and v['latest_rag_attempts']['internal']['status']=='failed'
  n=len(t.views);again=c.post('/v1/rag/ask',json=prior.BODY).json();saved=c.get('/v1/workflows/runs/'+v['run_id'],params={'session_id':'s'}).json()
  assert v['answer']==again['answer']==saved['answer'] and len(t.views)==n

def test_split_original_and_prior_observation_reach_direct_compare():
 from workflow.risk_team_compare_workflow import basis
 from workflow.contracts import WorkflowError
 data=[]
 for ident,side,text in [('i','internal','원칙과 예외'),('fragment','internal','원칙'),('e','external','원칙')]:
  data.append({'evidence_id':ident,'source_id':side,'side':side,'spans':[{'block_id':'0','start_cp':0,'end_cp':len(text),'text':text}],'text':text})
 native=type('Native',(),{'__module__':'semantic_runtime.workflow_bridge'})()
 port=S(services=native,session=S(tools=S(sources={s:{'id':s,'blocks':[{'block_id':'0','text':'원칙과 예외' if s=='internal' else '원칙'}]} for s in ('internal','external')})))
 ctx=S(rag=S(evidence=lambda:data,port=port),request={'as_of':None},repo=S(save=lambda s:None))
 row={s:{'status':'PARTIAL','citations':[{'evidence':ident,'quote':'원칙'}],'dependencies':[],'scope_sufficient':False,'missing':'판본 미확인'} for s,ident in [('internal','fragment'),('external','e')]}
 row['internal']['alternatives']=[{'text':'이전 확인','citations':row['internal']['citations'],'dependencies':[]}];row['internal']['citations']=[]
 state={'scope':{'issues':[{'id':'issue'}]},'packet_evidence':{'fragment':'i'},'rag_results':{'internal':{'evidence_ids':['i']},'external':{'evidence_ids':['e']}},'task_board':{'rows':{'issue:x':{'issue_id':'issue','field':'subject','current':row}}}}
 out=basis.from_items(ctx,state);assert out['pairs'][0]['internal']==['fragment'] and out['pairs'][0]['external']==['e']
 state['packet_evidence']['fragment']='missing'
 with pytest.raises(WorkflowError):basis.from_items(ctx,state)
