"""Separated finite need-state coverage; no model or legal quality evaluation."""
from copy import deepcopy
import json
import pytest
from semantic_runtime.research_state import ResearchLedger, need_id
from workflow.risk_team_compare_workflow import task_board as tb
from test_transitions import owners


@pytest.mark.parametrize('field', list(tb.CONFIG['fields']))
@pytest.mark.parametrize('side', ['internal','external'])
@pytest.mark.parametrize('disposition', [None,'OPEN','RESOLVED'])
@pytest.mark.parametrize('cited', [False,True])
@pytest.mark.parametrize('missing', ['', '미확보 유지'])
def test_all_need_fields_sides_and_resolution_guards(field,side,disposition,cited,missing):
    ledger=ResearchLedger({'tasks':{},'round':0,'rows':{},'reviewed':[]})
    issue={'id':'i',side+'_task':'조건 원문 확인'}
    def compile(proposal):
        task,_=owners.setup_task(field,side,proposal['query'])
        return ledger.register(task,proposal,True)
    initial={'status':'PARTIAL','text':'일부 확인','missing':'미확보 유지',
             'citations':[{'evidence':'E1','quote':'원문'}],'dependencies':[]}
    ledger.reconcile(issue,field,side,initial,'initial',[],compile)
    ledger=ResearchLedger(json.loads(json.dumps(ledger.board)))
    row={**deepcopy(initial),'missing':missing,'scope_sufficient':False,
         'citations':[{'evidence':'E1','quote':'원문'}] if cited else []}
    if disposition:row['need_resolution']=disposition
    item={'field':field,side:row,'content_status':'UNKNOWN','difference':'','next_tasks':[]}
    value={'items':[item],'evidence_updates':[]}
    before=deepcopy(ledger.board)
    rejected=disposition=='RESOLVED' and (bool(missing) or not cited)
    if rejected:
        with pytest.raises(ValueError):tb.checked_needs(value,ledger.board,'i')
        assert ledger.board==before
        return
    tb.checked_needs(value,ledger.board,'i')
    ledger.reconcile(issue,field,side,row,'updated',[],lambda _:pytest.fail('Pending work exists'))
    expected='RESOLVED' if disposition=='RESOLVED' else 'OPEN'
    need=ledger.needs()[0]
    assert need['need_id']==need_id('i',field,side) and need['status']==expected
    assert need['missing']=='미확보 유지'
    assert ledger.used_followups==0
    task=next(iter(ledger.board['tasks'].values()))
    assert task['status']==('RESOLVED' if expected=='RESOLVED' else 'PENDING')


@pytest.mark.parametrize('change', ['lead','attempt','source','none'])
@pytest.mark.parametrize('side', ['internal','external'])
@pytest.mark.parametrize('status', ['COMPLETE','PARTIAL','FAILED','BLOCKED'])
def test_review_input_identity_after_serialization(change,side,status):
    ledger,task=owners.ledger_with_need()
    task['task']['target_side']=side
    sources=[{'evidence_id':'E1','side':side}]
    attempts={side:'completed'};leads={'items':[]}
    initial=ledger.review_input('i',sources,attempts,leads)
    ledger.commit_review('i',sources,'first',accepted=True,general=True,updates=[],input_key=initial)
    ledger=ResearchLedger(json.loads(json.dumps(ledger.board)))
    if change=='lead':leads['items'].append({'lead_id':'new','acquisition':'NOT_READ'})
    if change=='attempt':
        record=next(iter(ledger.board['tasks'].values()))
        record.update(status=status,result_request_id='attempt2')
    if change=='source':sources.append({'evidence_id':'E2','side':side})
    key=ledger.review_input('i',sources,attempts,leads)
    assert ledger.review_allowed(incremental=True,new_ids=[],input_key=key)==(change!='none')
    if change!='none':
        ledger.commit_review('i',sources,'second',accepted=True,general=True,updates=[],input_key=key)
    assert not ledger.review_allowed(incremental=True,new_ids=[],input_key=key)
