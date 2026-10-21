from copy import deepcopy
from types import SimpleNamespace as S
import json
import pytest
from jsonschema import ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import decision_projection as dp, output_contract as oc, law_navigation as nav, minimal_output
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from test_read_choice_input_preservation import unit
from test_output_contract_recovery import Journal


def choice(**extra):return dict(unit.choice(queries=['주체 행위']),intent='CONTINUE',**extra)
def finish(**extra):
    value={'intent':'FINALIZE','choice':'FINISH','basis_refs':['E1'],'issue_refs':['Q1'],'evidence_sufficient':False,'reason':'확인 범위와 남은 부족을 전달한다'}
    value.update(extra);return value

def fixture(monkeypatch,value):
    inv,data,actions,payloads,out=unit.fixture(monkeypatch,value)
    actions['T7']['identity']={'frame_id':'H1'}
    inv.p['action_chain']={'frames':{'H1':{'kind':'NAVIGATION','actions':{'work':actions['T2']}}},'steps':[]}
    return inv,data,actions,payloads,out

@pytest.mark.parametrize('value',[choice(),finish(),{**choice(),'choice':'READ','selections':[{'target':'T1','issue_id':'Q1','missing_need':'추가 원문','relation':'DIRECT','source_ref':None}]}])
def test_one_call_preserves_continuation_or_partial_finish(monkeypatch,value):
    if value['choice']=='READ':
        for k in ('queries','target','issue_id','missing_need','relation','source_ref'):value.pop(k,None)
    inv,d,a,shown,out=fixture(monkeypatch,value);result=dp.choose_read(inv,d,a,'intent')
    assert len(shown)==1 and result['evidence_sufficient'] is False
    assert result['next_action']=={'READ':'READ_ARTICLES'}.get(value['choice'],value['choice'])
    assert d['sources']==[{'id':'E1','text':'원문'}]

@pytest.mark.parametrize('value',[dict(choice(),intent='FINALIZE'),finish(intent='CONTINUE')])
def test_conflicting_intent_is_not_executed_or_inferred_from_reason(monkeypatch,value):
    inv,d,a,shown,out=fixture(monkeypatch,value)
    with pytest.raises(oc.OutputContractError) as e:dp.choose_read(inv,d,a,'conflict')
    assert e.value.issues[0]['code']=='NAVIGATION_INTENT_CONFLICT'
    assert out==[] and not inv.p.get('executed_compact_choices')

def test_reason_keywords_do_not_force_completion(monkeypatch):
    v=choice();v['missing_need']='답변 확정이라는 문구의 의미를 확인할 추가 원문'
    inv,d,a,_,_=fixture(monkeypatch,v);assert dp.choose_read(inv,d,a,'keyword')['next_action']=='RESEARCH'

@pytest.mark.parametrize('defect',['missing_intent','bad_target','missing_work','unavailable_work'])
def test_return_requires_real_offered_work(monkeypatch,defect):
    v=unit.choice('RETURN_TO','T7',intent='CONTINUE',resume_action='RESEARCH')
    if defect=='missing_intent':v.pop('intent')
    elif defect=='bad_target':v['target']='forged'
    elif defect=='missing_work':v.pop('resume_action')
    else:v['resume_action']='FINISH'
    inv,d,a,shown,out=fixture(monkeypatch,v)
    with pytest.raises((ValidationError,ProposalError)):dp.choose_read(inv,d,a,'return-invalid')
    assert not out

def test_valid_return_keeps_work_and_target_in_durable_choice(monkeypatch):
    v=unit.choice('RETURN_TO','T7',intent='CONTINUE',resume_action='RESEARCH')
    inv,d,a,shown,out=fixture(monkeypatch,v);result=dp.choose_read(inv,d,a,'return')
    assert result['targets']==['T7'] and inv.p['executed_compact_choices'][-1]==v
    assert next(x for x in shown[0]['tool_options'] if x['choice']=='RETURN_TO')['resume_actions']==['RESEARCH']


def receipt(state,status='APPLIED'):
    return {'action':'RETURN_TO','status':status,'return_intent_receipt':{'binding':digest(state['binding']),'epoch':state.get('investigation_epoch',0),'progress_facts':dp.return_progress_facts(state)}}

@pytest.mark.parametrize('mutation',['same','roundtrip','new_fact','new_epoch','failed'])
def test_return_receipt_survives_restart_and_only_new_progress_reopens(mutation):
    p={'binding':{'generation':'g','principal':'u'},'action_chain':{'steps':[]},'request_progress':['source:a']}
    p['action_chain']['steps'].append(receipt(p))
    p=json.loads(json.dumps(p))
    if mutation=='roundtrip':p.update(turn=99,state_version=91,window='different',focus='other')
    elif mutation=='new_fact':p['request_progress'].append('source:b')
    elif mutation=='new_epoch':p['investigation_epoch']=1
    elif mutation=='failed':p['action_chain']['steps'][0]['status']='INTERRUPTED'
    assert dp.return_repeat(p)==(mutation in ('same','roundtrip'))


def test_repeated_return_removed_without_extra_model_or_forced_finish(monkeypatch):
    inv,d,a,shown,_=fixture(monkeypatch,choice())
    inv.p['action_chain']['steps'].append(receipt(inv.p));before=deepcopy(d)
    result=dp.choose_read(inv,d,a,'repeat')
    assert result['next_action']=='RESEARCH' and d==before
    assert shown[0]['navigation_feedback']['return_without_new_progress_blocked']
    assert not any(x['choice']=='RETURN_TO' for x in shown[0]['tool_options'])
    assert len(shown)==1

@pytest.mark.parametrize('second_valid',[True,False])
def test_real_decision_owner_repairs_once_and_restart_keeps_budget(tmp_path,monkeypatch,second_valid):
    original=oc.bounded_decision
    inv,d,a,_,_=fixture(monkeypatch,choice());monkeypatch.setattr(oc,'bounded_decision',original)
    repo=Journal(tmp_path/'decision.sqlite');repo.budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3)
    inv.s.repo=repo;inv.control=False;inv.left=lambda:120;calls=[]
    def invoke(system,payload,schema,phase,timeout):
        calls.append(deepcopy(payload));return choice() if len(calls)==2 and second_valid else dict(choice(),intent='FINALIZE')
    inv.invoke=invoke
    if second_valid:
        assert dp.choose_read(inv,d,a,'repair')['next_action']=='RESEARCH'
        assert dp.choose_read(inv,d,a,'repair')['next_action']=='RESEARCH'
    else:
        with pytest.raises(ProposalError):dp.choose_read(inv,d,a,'repair')
        inv.p=json.loads(json.dumps(inv.p))
        with pytest.raises(ProposalError):dp.choose_read(inv,d,a,'repair')
    assert len(calls)==2 and calls[0]['sources']==calls[1]['sources']
    assert calls[1]['repair_contract']['max_attempts']==1
    assert calls[1]['repair_contract']['validation']['issues'][0]['code']=='NAVIGATION_INTENT_CONFLICT'


def test_low_budget_does_not_start_extra_intent_review(monkeypatch):
    inv,d,a,shown,_=fixture(monkeypatch,choice());inv.s.repo.budget=lambda:dict(model_limit=40,model_reserved=35,finalization_reserve=3)
    assert dp.choose_read(inv,d,a,'budget') is None and not shown


def test_intent_is_generated_not_filled_as_a_branch_constant(monkeypatch):
    inv,d,a,_,_=fixture(monkeypatch,choice());schemas=[]
    def capture(repo,owner,payload,schema,invoke,expand,**kw):schemas.append(schema);expand(choice());return choice()
    monkeypatch.setattr(oc,'bounded_decision',capture);dp.choose_read(inv,d,a,'wire')
    codec=minimal_output._Node(schemas[0]);raw=codec.project(choice())
    assert raw['intent']=='CONTINUE'
    bad=dict(raw,intent='FINALIZE');assert codec.expand(bad)['intent']=='FINALIZE' # stage validator owns the conflict
    raw.pop('intent')
    with pytest.raises((ValidationError,ProposalError)):codec.expand(raw)


def test_actual_return_executor_records_and_rejects_unchanged_second_return(monkeypatch):
    from semantic_runtime.legal_agent import tool_availability
    inv=object.__new__(nav.Investigation);inv.modern=True;inv.completion=False;inv.control=False
    inv.s=S(repo=S(event=lambda *args:None));inv.p={'binding':{'generation':'g'},'catalogue':{'query_fingerprint':'q'},'action_chain':{'contract':'investigation-action-chain-v1','frames':{'H':{'id':'H','number':1,'kind':'NAVIGATION','location':{},'data':{}}},'steps':[{'id':'step1','action':'RETURN_TO','status':'ACCEPTED'}],'current_frame':'H'}}
    monkeypatch.setattr(tool_availability,'require_navigation',lambda *args:None)
    value={'next_action':'RETURN_TO','targets':['T'],'reason':'미완료 검색 계속','notes':'','law_decisions':[],'branch_decisions':[]}
    actions={'T':{'id':'T','action':'RETURN_TO','identity':{'frame_id':'H'}}}
    inv.execute_tool(value,{'sources':[]},actions)
    step=inv.p['action_chain']['steps'][0];assert step['return_intent_receipt']['frame_id']=='H';step['status']='APPLIED'
    inv.p['action_chain']['steps'].append({'id':'step2','action':'RETURN_TO','status':'ACCEPTED'})
    with pytest.raises(ProposalError,match='without new content'):inv.execute_tool(value,{'sources':[]},actions)
    inv.p['request_progress']=['new-source-span']
    inv.execute_tool(value,{'sources':[]},actions)
    assert 'return_intent_receipt' in inv.p['action_chain']['steps'][-1]
