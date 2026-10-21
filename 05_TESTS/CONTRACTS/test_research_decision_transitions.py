"""Explicit need decisions and bounded recovery without legal keyword rules."""
from copy import deepcopy
import json
from types import SimpleNamespace as S

import pytest
import jsonschema
from semantic_runtime.research_state import ResearchLedger
from semantic_runtime.legal_agent import request_repair as rr
from semantic_runtime.legal_agent.errors import ContractError
from workflow.adapters import projection
from workflow.risk_team_compare_workflow import task_board as tb
import test_research_state_owner as owners


@pytest.mark.parametrize('status', ['PARTIAL', 'CONFIRMED'])
@pytest.mark.parametrize('shape', ['flat', 'nested'])
def test_explicit_resolution_is_grounded_and_field_side_bound(status, shape):
    ledger, task = owners.ledger_with_need()
    source = {'evidence_id':'E1','side':'external','spans':[{'text':'원문'}]}
    row = {'status':status,'text':'기존 조건 미확보를 원문에서 확인함',
           'citations':['C1'],'missing':'','need_resolution':'RESOLVED'}
    item = {'field':'condition', 'side':'external', **row} if shape=='flat' else {'field':'condition','external':row}
    data = {'sources':[source], 'fields':{'condition':'조건'}, 'locators':{},
            'review_mode':'UPDATE','previous':[], 'unresolved_research':ledger.needs()}
    schema = tb.review_contract(['condition'], [], True)
    _, _, expand, _ = projection.prepare('ITEMS',data,schema)
    value = expand({'evidence_updates':[], 'items':[item]})
    jsonschema.validate(value,schema)
    tb.checked_update(value,[source],['condition'],{},[],True)
    tb.checked_needs(value,ledger.board,'i')
    canonical = value['items'][0]['external']
    assert canonical['need_resolution']=='RESOLVED'
    ledger.reconcile({'id':'i'},'condition','external',canonical,'r2',[],lambda _:pytest.fail())
    assert ledger.needs()[0]['status']=='RESOLVED'
    assert ledger.needs()[0]['resolution']['missing']=='조건 원문 미확보'
    assert task['status']=='RESOLVED'
    restored=ResearchLedger(json.loads(json.dumps(ledger.board)))
    assert restored.needs()==ledger.needs()


@pytest.mark.parametrize('defect', ['unknown_need','missing','no_citation','no_reason','wrong_side','false_quote'])
def test_invalid_resolution_cannot_mutate_need_or_cancel_work(defect):
    ledger, task = owners.ledger_with_need()
    source = {'evidence_id':'E1','side':'external','spans':[{'text':'원문'}]}
    row = {'status':'PARTIAL','text':'해소 이유','citations':[{'evidence':'E1','quote':'원문'}],
           'dependencies':[],'scope_sufficient':False,'missing':'','need_resolution':'RESOLVED'}
    item = {'field':'condition','external':row,'content_status':'UNKNOWN','difference':'','next_tasks':[]}
    if defect=='unknown_need':item['field']='obligation'
    if defect=='missing':row['missing']='아직 원문 미확보'
    if defect=='no_citation':row['citations']=[]
    if defect=='no_reason':row['text']=' '
    if defect=='wrong_side':source['side']='internal'
    if defect=='false_quote':row['citations'][0]['quote']='다른 내용'
    before=deepcopy(ledger.board)
    value={'items':[item],'evidence_updates':[]}
    with pytest.raises(ValueError):
        tb.checked_update(value,[source],['condition','obligation'],{},[],True)
        tb.checked_needs(value,ledger.board,'i')
    assert ledger.board==before and task['status']=='PENDING'


@pytest.mark.parametrize('disposition', [None,'OPEN'])
def test_empty_missing_does_not_erase_original_need(disposition):
    ledger, task = owners.ledger_with_need()
    before=ledger.needs()[0]
    row={'status':'CONFIRMED','text':'다른 부분만 확인함','citations':[{'evidence':'E1','quote':'원문'}],
         'dependencies':[],'scope_sufficient':True,'missing':''}
    if disposition:row['need_resolution']=disposition
    ledger.reconcile({'id':'i'},'condition','external',row,'r2',[],lambda _:pytest.fail())
    after=ledger.needs()[0]
    assert after['status']=='OPEN' and after['missing']==before['missing']
    assert task['status']=='PENDING' and not after.get('resolution')


def investigation():
    state={'binding':{'generation':'fixed'},'state_version':1,'investigation_epoch':0,
           'turn':3,'no_progress':3,'discovery_changed':True}
    menu={'open':{'action':'OPEN_LAW','identity':{'document':'first'}}}
    events=[]
    budget={'model_reserved':5,'model_limit':40}
    inv=S(modern=True,p=state,view=lambda:({'page':'p'},deepcopy(menu)),
          s=S(repo=S(event=lambda *a:events.append(a),budget=lambda:deepcopy(budget))),save=lambda:None)
    return inv,menu,events,budget


def test_recovery_is_at_most_three_changed_menus_and_restores_same_reservation():
    inv,menu,events,budget=investigation()
    before=deepcopy(budget)
    for count in range(1,4):
        snapshot=rr.no_progress_recovery(inv)
        assert snapshot and inv.p['no_progress_recovery']['selection_count']==count
        inv.p=json.loads(json.dumps(inv.p))
        assert rr.no_progress_recovery(inv)==snapshot and len(events)==count
        rr.finish_no_progress_recovery(inv.p,snapshot[2])
        inv.p['turn']+=1
        menu.clear();menu[str(count)]={'action':'READ_ARTICLES','identity':{'unit':str(count)}}
    assert rr.no_progress_recovery(inv) is None
    assert budget==before and inv.p['no_progress']==3
    assert len(inv.p['no_progress_recovery']['history'])==2


@pytest.mark.parametrize('change', ['same_physical','tamper','binding','epoch'])
def test_recovery_cannot_be_refreshed_by_menu_labels_or_stale_state(change):
    inv,menu,events,budget=investigation()
    snapshot=rr.no_progress_recovery(inv)
    rr.finish_no_progress_recovery(inv.p,snapshot[2])
    inv.p['turn']+=1
    original=menu.pop('open')
    menu['new-display-label']=original
    if change=='no_discovery':
        menu['read']={'action':'READ_ARTICLES','identity':{'unit':'new'}}
        inv.p['discovery_changed']=False
    if change=='tamper':inv.p['no_progress_recovery']['snapshot'][0]['page']='forged'
    if change=='binding':inv.p['binding']['generation']='other'
    if change=='epoch':inv.p['investigation_epoch']=1
    if change in ('tamper','binding'):
        with pytest.raises(ContractError):rr.no_progress_recovery(inv)
    else:assert rr.no_progress_recovery(inv) is None
    assert len(events)==1 and inv.p['no_progress']==3


@pytest.mark.parametrize('status', ['COMPLETE','PARTIAL','FAILED','BLOCKED'])
def test_outcome_admission_is_durable_and_review_does_not_trigger_itself(status):
    ledger,task=owners.ledger_with_need()
    source=[{'evidence_id':'E1','side':'external'}]
    old=ledger.review_input('i',source,{}, {})
    ledger.commit_review('i',source,'first',accepted=True,general=True,updates=[],input_key=old)
    task.update(status=status,result_request_id='attempt',reason='bounded result')
    new=ledger.review_input('i',source,{}, {})
    assert old!=new
    assert ledger.review_allowed(incremental=True,new_ids=[],input_key=new)
    ledger.commit_review('i',source,'second',accepted=True,general=True,updates=[],input_key=new)
    # The model's own pending plan and evidence judgments cannot manufacture progress.
    other=deepcopy(task);other['status']='PENDING'
    ledger.board['tasks']['new-plan']=other
    ledger.board['evidence_updates'].append({'issue_id':'i','reason':'new wording'})
    assert ledger.review_input('i',source,{}, {})==new
    restored=ResearchLedger(json.loads(json.dumps(ledger.board)))
    assert not restored.review_allowed(incremental=True,new_ids=[],input_key=new)


def test_pending_task_is_not_cancelled_when_other_need_shares_it():
    ledger,task=owners.ledger_with_need()
    task['need_ids'].append('another-unresolved-need')
    row={'status':'PARTIAL','text':'해소 이유','citations':[{'evidence':'E1','quote':'원문'}],
         'dependencies':[],'missing':'','need_resolution':'RESOLVED'}
    ledger.reconcile({'id':'i'},'condition','external',row,'r2',[],lambda _:pytest.fail())
    assert ledger.needs()[0]['status']=='RESOLVED'
    assert task['status']=='PENDING'


def test_new_physical_read_target_is_not_vetoed_by_coarse_discovery_flag():
    inv,menu,events,budget=investigation()
    view=rr.no_progress_recovery(inv)
    rr.finish_no_progress_recovery(inv.p,view[2])
    inv.p['turn']+=1
    inv.p['discovery_changed']=False
    menu['new-read']={'action':'READ_SCOPE','identity':{'unit':'new'}}
    assert rr.no_progress_recovery(inv)
    assert inv.p['no_progress_recovery']['selection_count']==2
    assert inv.p['no_progress']==3


def completed():
    inv,menu,events,budget=investigation()
    snapshot=rr.no_progress_recovery(inv)
    inv.p['state_version']+=1
    inv.p['turn']+=1
    rr.finish_no_progress_recovery(inv.p,snapshot[2])
    inv.p=json.loads(json.dumps(inv.p))
    menu['read']={'action':'READ_ARTICLES','identity':{'unit':'new'}}
    return inv,menu,events,budget


def test_completed_tool_version_survives_restart_and_allows_next_new_read():
    inv,menu,events,budget=completed()
    before=deepcopy(budget)
    assert inv.p['no_progress_recovery']['completed_state_version']==2
    next_view=rr.no_progress_recovery(inv)
    assert next_view and inv.p['no_progress_recovery']['state_version']==2
    assert inv.p['no_progress_recovery']['selection_count']==2
    assert rr.no_progress_recovery(inv)==next_view
    assert len(events)==2 and budget==before


@pytest.mark.parametrize('kind',['reserved_stale','completion_rollback','forged_completion','newer_work','legacy'])
def test_revision_mismatch_never_refreshes_recovery_allowance(kind):
    inv,menu,events,budget=completed()
    if kind=='reserved_stale':
        rr.no_progress_recovery(inv)
        inv.p['state_version']+=1
    elif kind=='completion_rollback':
        inv.p['state_version']-=1
    elif kind=='forged_completion':
        inv.p['no_progress_recovery']['completed_state_version']=0
    elif kind=='newer_work':
        inv.p['state_version']+=1
    else:
        inv.p['no_progress_recovery'].pop('completed_state_version')
    before=deepcopy(inv.p)
    if kind in ('newer_work','legacy'):
        assert rr.no_progress_recovery(inv) is None
    else:
        with pytest.raises(ContractError,match='state version'):
            rr.no_progress_recovery(inv)
    assert inv.p==before
