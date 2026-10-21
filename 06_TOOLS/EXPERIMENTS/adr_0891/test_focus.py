from pathlib import Path
from copy import deepcopy
import importlib.util,json
import pytest
from semantic_runtime.legal_agent import definition_entry as de,completion_v6 as v6
from semantic_runtime.legal_agent.errors import ContractError,BudgetExhausted
from semantic_runtime.legal_agent.output_contract import DecisionConflict
from test_focused_input_modality import v6_proposal

P=Path(__file__).resolve().parents[1]/'adr_0810/test_retrieval_boundaries.py'
spec=importlib.util.spec_from_file_location('definition_receipt_fixture',P);prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)


def fixture(window='search',count=12):
    inv,calls,events=prior.seed_investigation(count);inv.modern=True
    origin={'window':window,'window_groups':['existing'],'focus':'existing',
            'structure_location':{'document_id':'law','unit_id':'old','offset':4}}
    inv.p.update(deepcopy(origin),no_progress=2,used_calls=9,deadline=12345)
    execute=inv.execute_tool
    def changing(decision,data,actions):
        inv.p.update(window='read',focus='new',structure_location={'document_id':'law','unit_id':'new'})
        return execute(decision,data,actions)
    inv.execute_tool=changing
    return inv,calls,events,origin


@pytest.mark.parametrize('window',['search','law','structure','read'])
def test_complete_auto_queue_preserves_focus_and_all_completed_original_receipts(window):
    inv,calls,events,origin=fixture(window,19);de.acquire_initial(inv)
    assert {k:inv.p[k] for k in origin}==origin
    seed=inv.p['system_definition_seed']
    assert seed['status']=='COMPLETE' and len(seed['completed'])==len(seed['acquired_groups'])==19
    assert len(inv.p['selected'])==19 and len(calls)==len(set(calls))==19
    assert inv.p['used_calls']==9 and inv.p['no_progress']==2 and inv.p['deadline']==12345
    assert events[-1][1]['adopted'] is False
    # A later explicit model choice must not be reset by an idempotent seed call.
    inv.p.update(window='read',focus='model-chosen',window_groups=['model-chosen'])
    de.acquire_initial(inv);assert inv.p['focus']=='model-chosen' and len(calls)==19


@pytest.mark.parametrize('error',[OSError,KeyboardInterrupt,BudgetExhausted])
def test_interrupted_queue_restores_focus_then_resumes_pending_without_reacquisition(error):
    inv,calls,_,origin=fixture(count=5);execute=inv.execute_tool
    def fail(decision,data,actions):
        if len(calls)==2:
            inv.p['window']='failed-read';inv.p['focus']='failed'
            raise error('bounded original failure')
        return execute(decision,data,actions)
    inv.execute_tool=fail
    if error is BudgetExhausted:de.acquire_initial(inv)
    else:
        with pytest.raises(error):de.acquire_initial(inv)
    assert {k:inv.p[k] for k in origin}==origin
    seed=inv.p['system_definition_seed'];assert len(seed['completed'])==2 and seed['pending_reasons']
    assert seed['status']==('PARTIAL' if error is BudgetExhausted else 'INTERRUPTED')
    inv.p=json.loads(json.dumps(inv.p));inv.execute_tool=execute;de.acquire_initial(inv)
    assert len(calls)==len(set(calls))==5 and {k:inv.p[k] for k in origin}==origin
    assert inv.p['system_definition_seed']['status']=='COMPLETE'


def test_deadline_pending_does_not_erase_reading_context_or_reset_budget():
    inv,calls,_,origin=fixture();inv.left=lambda:0;de.acquire_initial(inv)
    assert not calls and inv.p['system_definition_seed']['status']=='PARTIAL'
    assert {k:inv.p[k] for k in origin}==origin and inv.p['deadline']==12345


@pytest.mark.parametrize('tamper',['origin','hash','unknown_key','policy','scope','question','target'])
def test_seed_binding_and_navigation_origin_tampering_fail_closed(tamper):
    inv,calls,_,_=fixture();inv.left=lambda:0;de.acquire_initial(inv);seed=inv.p['system_definition_seed']
    if tamper=='origin':seed['navigation_origin']['window']='forged'
    if tamper=='hash':seed['navigation_origin_hash']='changed'
    if tamper=='unknown_key':seed['navigation_origin']['selected']={}
    if tamper=='policy':seed['navigation_policy']='unknown'
    if tamper=='scope':inv.s.scope=set()
    if tamper=='question':inv.s.context.request['question']='different'
    if tamper=='target':seed['actions'][seed['targets'][0]]['identity']['unit_id']='wrong'
    with pytest.raises(ContractError):de.acquire_initial(inv)
    assert not calls


@pytest.mark.parametrize('fault',['no_receipt','partial_original','unfinished_plan'])
def test_failed_original_is_not_marked_complete_and_focus_is_restored(fault):
    inv,calls,_,origin=fixture(count=1);execute=inv.execute_tool
    def fail(decision,data,actions):
        inv.p.update(window='read',focus='incomplete')
        if fault=='no_receipt':return
        execute(decision,data,actions)
        if fault=='partial_original':next(iter(inv.p['selected'].values()))['complete']=False
        if fault=='unfinished_plan':next(iter(inv.p['read_plans'].values()))['status']='INTERRUPTED'
    inv.execute_tool=fail
    with pytest.raises(ContractError):de.acquire_initial(inv)
    assert {k:inv.p[k] for k in origin}==origin
    assert not inv.p['system_definition_seed']['completed']


def test_absent_navigation_keys_remain_absent_and_legacy_seed_not_reinterpreted():
    inv,calls,_=prior.seed_investigation(2);inv.modern=True;de.acquire_initial(inv)
    assert all(k not in inv.p for k in de.NAVIGATION_KEYS) and len(inv.p['selected'])==2
    old,calls,_=prior.seed_investigation(2);de.acquire_initial(old)
    assert old.p['window_groups']==['0','1'];old.modern=True;old.p['window']='model-view'
    de.acquire_initial(old);assert old.p['window']=='model-view' and len(calls)==2


def test_error_related_path_exists_in_every_norm_contract():
    value=v6_proposal(quote='보고하여야 한다.',kind='OBLIGATION')
    value['claims'][0]['rule']['norms'][0]['text']='보고할 수 있다.'
    with pytest.raises(DecisionConflict) as error:v6.verify_modalities(value,[{'id':'S1','text':'보고하여야 한다.'}])
    for path in [error.value.issues[0]['path'],*error.value.issues[0]['related_paths']]:
        node=value
        for token in path.strip('/').split('/'):node=node[int(token)] if isinstance(node,list) else node[token]
        assert node

# Retain the legacy definition queue contracts without unrelated pre-MAIN attachment expectations.
test_definition_initial_acquisition_has_no_first_eight_cutoff_and_is_idempotent = prior.test_definition_initial_acquisition_has_no_first_eight_cutoff_and_is_idempotent
test_definition_interruption_preserves_completed_targets_and_resume = prior.test_definition_interruption_preserves_completed_targets_and_resume
test_definition_budget_and_deadline_preserve_pending_without_false_completion = prior.test_definition_budget_and_deadline_preserve_pending_without_false_completion
test_definition_return_without_completed_original_is_not_success = prior.test_definition_return_without_completed_original_is_not_success
test_definition_resume_rejects_changed_binding_or_false_completion = prior.test_definition_resume_rejects_changed_binding_or_false_completion
