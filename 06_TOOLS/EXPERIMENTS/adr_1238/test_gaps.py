from copy import deepcopy
from types import SimpleNamespace as S
import importlib.util,json
from pathlib import Path
import pytest
from semantic_runtime.legal_agent import investigation_supervisor as su,read_judgment_final as final,read_judgment as rj
from semantic_runtime.legal_agent.errors import TransportError,ContractError
from semantic_runtime.legal_agent.law_navigation import Investigation
from test_read_judgment import conflict_setup,setup,options,ISSUES
R=Path('/home/jin/8-AGENT')
spec=importlib.util.spec_from_file_location('supervisor_fixture_1238',R/'06_TOOLS/EXPERIMENTS/adr_1199/test_supervisor.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def test_incomplete_conflict_only_preserves_both_opinions_and_limits():
 inv,data,page=conflict_setup();ctx=final.context(inv.p,inv.question,ISSUES,options(data),{'d'})
 assert ctx['conflicts'] and not ctx['needs'];prior=deepcopy(inv.p)
 result={'limitation_items':[],'disposition':'ANSWER'};final.incomplete(result,ctx)
 assert final.limitations(result) and result['disposition']=='LIMITED_ANSWER'
 assert {x['id'] for x in result['limitation_items']}=={'L-'+r['id'] for r in ctx['conflicts']+ctx['judgments']}
 assert any('충돌' in x for x in result['limitations'])
 assert result[final.FIELD]['prior_conflicts']==ctx['conflicts'] and inv.p==prior
 before=deepcopy(result);final.limitations(result);assert before==result

def test_incomplete_new_source_judgment_is_visible():
 inv,data,*_=setup();ctx=final.context(inv.p,inv.question,ISSUES,options(data),{'d'})
 assert ctx['judgments'][0]['version']==0 and not ctx['needs'] and not ctx['conflicts']
 result={'limitation_items':[],'disposition':'ANSWER'};final.incomplete(result,ctx)
 assert final.limitations(result) and '최종 검토 미완료 판단' in result['limitations'][0]
 assert result[final.FIELD]['review'] is None

def test_reviewed_open_conflict_already_limits_and_now_idempotent():
 result={'disposition':'ANSWER','limitation_items':[],final.FIELD:{'status':'REVIEWED','review':{
  'needs':[],'judgments':[],'conflicts':[{'id':'CF1','status':'OPEN','material':True,'reason':'양쪽 근거 충돌'}]}}}
 assert final.limitations(result);before=deepcopy(result);final.limitations(result);assert result==before

@pytest.mark.parametrize('deadline',[False,True])
def test_unknown_stops_not_handoffs_and_preserves_receipt(deadline):
 inv,d,v,p,s,x=f.fixture();f.seed(inv,d);calls=[]
 exc=TransportError('supervisor unknown',unknown=True,response={'partial':'preserved'})
 if deadline:exc.code='MODEL_DEADLINE_EXCEEDED';exc.http_status=504
 def invoke(*args):calls.append(args);raise exc
 inv.invoke=invoke
 with pytest.raises(TransportError) as got:f.call(inv,d,v,p,s,x)
 assert got.value is exc and got.value.response=={'partial':'preserved'}
 st=su.state_for(inv,d);assert st['pending'] and not st['halt'] and st['calls']==1
 assert not any(k=='SUPERVISOR_HANDOFF' for k,_ in inv.s.repo.events)
 saved=deepcopy(inv.p);inv.p=json.loads(json.dumps(inv.p))
 with pytest.raises(TransportError) as got:f.call(inv,d,v,p,s,x)
 assert got.value.unknown and got.value.http_status==exc.http_status and len(calls)==1 and inv.p==saved
 with pytest.raises(ContractError):su.before_execute(inv,d,x(v))

@pytest.mark.parametrize('saved_failure',[False,True])
def test_resume_guard_before_native_primary_call_or_goal_preselect(monkeypatch,saved_failure):
 inv,d,*_=f.fixture();st=su.state_for(inv,d);st['pending']={'key':'crash-after-dispatch'}
 if saved_failure:st['failure']={'reason':'deadline','code':'MODEL_DEADLINE_EXCEEDED','http_status':504}
 su.save(inv,st)
 from semantic_runtime.legal_agent import source_goal_control as goals
 monkeypatch.setattr(goals,'preselect',lambda *a:pytest.fail('no target after unknown'))
 inv._request_decision=lambda *a:pytest.fail('no model call after unknown')
 with pytest.raises(TransportError) as got:Investigation.request_decision(inv,d,{},'read-choice')
 assert got.value.unknown and (not saved_failure or got.value.http_status==504)

@pytest.mark.parametrize('directive',['CONTINUE_TARGETED','REDIRECT','ASSESS_NOW','STOP_UNRESOLVED'])
def test_valid_supervisor_directives_remain_supported(directive):f.test_gates_before_actual_execution(directive)
@pytest.mark.parametrize('failure',['malformed','429'])
def test_known_failure_retains_bounded_handoff(failure):f.test_failed_supervisor_no_retry_or_original_execution(failure)
@pytest.mark.parametrize('reason',['limit','reserve','deadline'])
def test_known_limits_do_not_add_calls(reason):f.test_no_call_after_limits_and_resume(reason)

def test_native_api_unknown_stops_final_and_duplicate(tmp_path,term_glossary,monkeypatch):
 monkeypatch.syspath_prepend(str(R/'06_TOOLS/EXPERIMENTS/adr_1188'))
 from api_unknown_fixture import run_api
 result=run_api(tmp_path,term_glossary,'goal_control',monkeypatch,coverage_fault='unknown')
 assert result['status']==504 and result['final_calls']==0
