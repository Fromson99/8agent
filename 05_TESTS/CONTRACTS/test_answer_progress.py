"""State, decision, and failure contracts; opinions never certify legal truth."""
from copy import deepcopy
from types import SimpleNamespace as S
import json
import pytest
from jsonschema import validate, ValidationError
from semantic_runtime.legal_agent import answer_progress as ap, decision_projection as dp, law_navigation as nav, output_contract as oc, investigation_scope as scope
from semantic_runtime.legal_agent.errors import ProposalError, ContractError


def fixture(monkeypatch, value, *, original=True):
    data={'issues':[{'id':'Q1','request_quote':'질문'}], 'sources':[{'id':'E1','document_id':'D1','source_id':'S1','text':'원문'}] if original else [], 'basis':[{'id':'E1','branch_id':'B1'}] if original else [], 'laws':[], 'branches':[], 'presentation_id':'P1','state_version':9,'control_contract':'control','completion_contract':nav.cc.V8,'read_batch_limit':8,'investigation_scope':{'request':'질문'}}
    actions={'T1':{'id':'T1','action':'READ_ARTICLES','identity':{'document_id':'D1'},'label':'필수 원문'}}
    events=[];payloads=[]
    def check(v,d,a):validate(v,nav.decision_schema(d,a,set()));scope.validate(v,d)
    inv=S(modern=True,control=False,policy={'answer_progress_control':True},p={'binding':{'hash':'fixed'}},s=S(repo=S(budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3),event=lambda *v:events.append(v))),question='질문',save=lambda:None,validate=check,left=lambda:180)
    def decide(*args,**kw):payloads.append(args[2]);args[5](value);return deepcopy(value)
    monkeypatch.setattr(oc,'bounded_decision',decide)
    return inv,data,actions,events,payloads


def review(effect='INITIAL',status='NEEDS_SOURCE'):
    return {'goals':[dict(issue_id='Q1',status=status,answer_so_far='현재 원문의 내용',basis_refs=['E1'],material_need='' if status=='ANSWERABLE' else '위임된 필수 항목',next_answer_change='' if status=='ANSWERABLE' else '필수 항목을 원문으로 확정',previous_effect=effect)]}


def read_choice(effect='INITIAL'):
    return {'choice':'READ','selections':[{'target':'T1','issue_id':'Q1','relation':'DEPENDENCY','source_ref':'E1'}], 'answer_progress':review(effect)}


def test_answerable_finishes_and_missing_keeps_reading(monkeypatch):
    for value in [read_choice(),dict(choice='FINISH',basis_refs=['E1'],issue_refs=['Q1'],evidence_sufficient=True,reason='충분',answer_progress=review(status='ANSWERABLE'))]:
        inv,d,a,events,p=fixture(monkeypatch,value)
        result=dp.choose_read(inv,d,a,'test')
        assert result['next_action']==('FINISH' if value['choice']=='FINISH' else 'READ_ARTICLES')
        assert len(p)==1 and events[-1][0]=='READ_CHOICE_SELECTED'
        assert events[0][1]['legal_claim_approved'] is False


def test_no_progress_finish_retains_uncertainty(monkeypatch):
    value=dict(choice='FINISH',basis_refs=['E1'],issue_refs=['Q1'],evidence_sufficient=False,reason='추가 원문 미확보',answer_progress=review(status='NO_PROGRESS'))
    inv,d,a,events,p=fixture(monkeypatch,value)
    result=dp.choose_read(inv,d,a,'test')
    assert result['next_action']=='FINISH' and not result['evidence_sufficient']
    assert d['sources'][0]['text']=='원문'


def test_receipts_idempotent_restart_and_presentation_do_not_reset(monkeypatch):
    value=read_choice();inv,d,a,events,p=fixture(monkeypatch,value)
    assert not ap.record(inv,d,value,'accepted1')
    value['answer_progress']['goals'][0]['previous_effect']='NO_CHANGE'
    assert not ap.record(inv,d,value,'accepted2')
    assert not ap.record(inv,d,value,'accepted2')
    assert ap.state_for(inv,d)['unchanged_steps_by_issue']['Q1']==1
    inv.p=json.loads(json.dumps(inv.p));d['presentation_id']='after-restart'
    assert ap.record(inv,d,value,'accepted3')
    assert ap.state_for(inv,d)['unchanged_steps_by_issue']['Q1']==2
    d['current_request']='다른 질문'
    assert ap.state_for(inv,d)=={}


def test_conflicting_replayed_proposal_and_binding_are_not_ignored(monkeypatch):
    value=read_choice();inv,d,a,events,p=fixture(monkeypatch,value)
    ap.record(inv,d,value,'accepted')
    value['answer_progress']['goals'][0]['answer_so_far']='변조'
    with pytest.raises(ContractError):ap.record(inv,d,value,'accepted')
    inv.p['binding']['hash']='another-verified-binding'
    assert ap.state_for(inv,d)=={}


@pytest.mark.parametrize('effect',['ANSWER_CHANGED','NEED_NARROWED'])
def test_narrowing_chain_resets_streak_even_without_new_original(monkeypatch,effect):
    value=read_choice();inv,d,a,*_=fixture(monkeypatch,value)
    ap.record(inv,d,value,'1')
    value['answer_progress']['goals'][0]['previous_effect']='NO_CHANGE';ap.record(inv,d,value,'2')
    value['answer_progress']['goals'][0]['previous_effect']=effect
    assert not ap.record(inv,d,value,'3') and ap.state_for(inv,d)['unchanged_steps_by_issue']['Q1']==0


@pytest.mark.parametrize('effect',['NO_CHANGE','TOOL_FAILED'])
def test_two_unchanged_reviews_handoff_without_executing_proposed_tool(monkeypatch,effect):
    value=read_choice();inv,d,a,events,p=fixture(monkeypatch,value)
    dp.choose_read(inv,d,a,'t')
    value['answer_progress']['goals'][0]['previous_effect']=effect;d['presentation_id']='P2'
    dp.choose_read(inv,d,a,'t')
    d['presentation_id']='P3'
    with pytest.raises(ap.ProgressHandoff):dp.choose_read(inv,d,a,'t')
    assert len(inv.p['executed_compact_choices'])==2
    assert events[-1][0]=='ANSWER_PROGRESS_HANDOFF' and events[-1][1]['originals_preserved']


@pytest.mark.parametrize('mutation',[
    lambda v:v['answer_progress']['goals'][0].update(status='ANSWERABLE'),
    lambda v:v['answer_progress']['goals'][0].update(material_need=' '),
    lambda v:v['answer_progress']['goals'][0].update(next_answer_change=''),
    lambda v:v['answer_progress']['goals'][0].update(basis_refs=['UNAUTHORIZED']),
    lambda v:v['answer_progress']['goals'][0].update(previous_effect='NO_CHANGE'),
])
def test_invalid_review_is_not_committed(monkeypatch,mutation):
    value=read_choice();mutation(value);inv,d,a,events,p=fixture(monkeypatch,value)
    with pytest.raises((ProposalError,ContractError,ValidationError)):dp.choose_read(inv,d,a,'t')
    assert 'answer_progress_reviews' not in inv.p and not events


def test_no_original_never_manufactures_evidence_handoff(monkeypatch):
    value=read_choice();inv,d,a,*_=fixture(monkeypatch,value,original=False)
    ap.record(inv,d,value,'1');value['answer_progress']['goals'][0]['previous_effect']='NO_CHANGE'
    assert not ap.record(inv,d,value,'2') and not ap.record(inv,d,value,'3')


def test_budget_reserve_skips_extra_review_call(monkeypatch):
    inv,d,a,events,p=fixture(monkeypatch,read_choice())
    inv.s.repo.budget=lambda:dict(model_limit=40,model_reserved=36,finalization_reserve=3)
    assert dp.choose_read(inv,d,a,'t') is None and not p and not events


def test_progress_context_and_nested_source_ids_roundtrip_wire(monkeypatch):
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    inv,d,a,*_=fixture(monkeypatch,read_choice());ap.record(inv,d,read_choice(),'1')
    context=ap.context(inv,d)
    payload={'sources':d['sources'],'answer_progress_context':context}
    codec=NavigationReferences(payload)
    # Actual API contracts additionally pass the dynamic enum and model reply through the gateway.
    assert context['previous_model_opinions'][0]['review']['goals'][0]['basis_refs']==['E1']
    assert context['meaning'] and context['unchanged_steps_by_issue']['Q1']==0


@pytest.mark.parametrize('repair_succeeds',[True,False])
def test_real_decision_journal_repairs_once_and_restart_never_repeats(tmp_path,monkeypatch,repair_succeeds):
    from test_output_contract_recovery import Journal
    real=oc.bounded_decision
    value=read_choice();inv,d,a,*_=fixture(monkeypatch,value)
    monkeypatch.setattr(oc,'bounded_decision',real)
    path=tmp_path/'journal.sqlite';repo=Journal(path)
    repo.budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3)
    inv.s.repo=repo;inv.s.profile={'selection_time_reserve_seconds':20}
    calls=[]
    def invoke(system,payload,schema,phase,timeout):
        calls.append(deepcopy(payload))
        if len(calls)==2:
            assert payload['repair_contract']['same_evidence_scope']
            assert payload['sources']==calls[0]['sources'] and payload['contract_error']
        result=read_choice()
        if len(calls)==1 or not repair_succeeds:result['answer_progress']['goals'][0]['next_answer_change']=''
        return result
    inv.invoke=invoke
    if repair_succeeds:
        first=dp.choose_read(inv,d,a,'t');assert first['next_action']=='READ_ARTICLES'
    else:
        with pytest.raises((ProposalError,ValidationError)):dp.choose_read(inv,d,a,'t')
    repo.db.commit();repo.db.close()
    inv.p=json.loads(json.dumps(inv.p));repo=Journal(path);repo.budget=lambda:dict(model_limit=40,model_reserved=2,finalization_reserve=3);inv.s.repo=repo
    if repair_succeeds:assert dp.choose_read(inv,d,a,'t')==first
    else:
        with pytest.raises(oc.OutputContractError):dp.choose_read(inv,d,a,'t')
    assert len(calls)==2
    repo.db.close()


@pytest.mark.parametrize('choice,status,sufficient', [('READ','ANSWERABLE',None),('READ','NO_PROGRESS',None),('FINISH','NEEDS_SOURCE',False),('FINISH','NO_PROGRESS',True)])
def test_wire_schema_itself_disallows_inconsistent_stop_and_action(monkeypatch,choice,status,sufficient):
    value=read_choice() if choice=='READ' else dict(choice='FINISH',basis_refs=['E1'],issue_refs=['Q1'],reason='확인한 범위',evidence_sufficient=sufficient,answer_progress=review())
    value['answer_progress']['goals'][0]['status']=status
    inv,d,a,*_=fixture(monkeypatch,value)
    from semantic_runtime.legal_agent.local_gemma import provider_request
    def decide(repo,owner,payload,schema,*args,**kw):
        body=provider_request({'response_format':{'type':'json_schema','json_schema':{'schema':schema}}})
        with pytest.raises((ValidationError,ProposalError)):
            validate(value,body['response_format']['json_schema']['schema'])
            ap.validate_review(value,{r['id']:r for r in d['sources']},d['issues'])
        raise ValueError('expected wire rejection')
    monkeypatch.setattr(oc,'bounded_decision',decide)
    with pytest.raises(ValueError,match='expected wire rejection'):dp.choose_read(inv,d,a,'t')


@pytest.mark.parametrize('status',['NEEDS_SOURCE','ANSWERABLE','NO_PROGRESS'])
def test_actual_choice_schema_roundtrips_minimal_and_provider_wire(monkeypatch,status):
    from semantic_runtime.legal_agent.minimal_output import Projection
    from semantic_runtime.legal_agent.local_gemma import provider_request
    value=read_choice() if status=='NEEDS_SOURCE' else dict(choice='FINISH',basis_refs=['E1'],issue_refs=['Q1'],reason='원문 검토',evidence_sufficient=status=='ANSWERABLE',answer_progress=review(status=status))
    inv,d,a,*_=fixture(monkeypatch,value)
    def decide(repo,owner,payload,schema,invoke,check,**kw):
        projection=Projection(schema)
        raw=projection.project(value)
        external=provider_request({'response_format':{'type':'json_schema','json_schema':{'schema':projection.wire}}})
        validate(raw,external['response_format']['json_schema']['schema'])
        expanded=projection.expand(raw)
        assert expanded==value
        check(expanded)
        return expanded
    monkeypatch.setattr(oc,'bounded_decision',decide)
    result=dp.choose_read(inv,d,a,'t')
    assert result['next_action']==('READ_ARTICLES' if status=='NEEDS_SOURCE' else 'FINISH')
