"""Current research continuity: explicit plans and preserved unresolved observations."""
from copy import deepcopy
from itertools import permutations
from types import SimpleNamespace as S
import json
import pytest
from semantic_runtime.legal_agent import research_continuity as rc, request_repair as rr
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime import workflow_rag
from workflow.risk_team_compare_workflow import task_board as tb


@pytest.mark.parametrize('side',['internal','external'])
@pytest.mark.parametrize('field',['condition','exceptions','obligation'])
@pytest.mark.parametrize('status',sorted(rc.TERMINAL))
@pytest.mark.parametrize('new_source',[False,True])
def test_need_attempt_state_matrix(side,field,status,new_source):
    issue={'id':'issue',side+'_task':'적용 범위 확인'}
    row={'status':'PARTIAL','missing':'조건 원문 미확보','text':'현재 확인한 내용',
         'citations':[{'evidence':'E1','quote':'처음 원문'}],'dependencies':[]}
    board={'tasks':{},'round':1}
    def compile(proposal):
        task={'issue_id':issue['id'],'requested_fields':[field],'target_side':side,
              'operation':proposal['operation'],'missing_target':proposal['query'],
              'target_locator':None,'anchor_refs':[],'binding_hash':'bound'}
        return tb.register_task(board,task,proposal,True)
    proposal={'operation':'search_text','query':'적용 범위 확인 / 조건 원문 미확보',
              'priority':'CORE','priority_reason':'명시적 원문 조사','reason':'조건 확인'}
    task_id=compile(proposal)
    tb.reconcile_need(board,issue,field,side,row,'first',[task_id],compile)
    need_id=rc.need_id(issue['id'],field,side);record=next(iter(board['tasks'].values()))
    record.update(status=status,need_basis={need_id:board['research_needs'][need_id]['basis_hash']},
                  result_request_id='saved-result',new_evidence=['E1'])
    board=json.loads(json.dumps(board));before=deepcopy(board['tasks'])
    row['missing']='같은 미확보 상태를 바꾸어 쓴 설명'
    if new_source:row['citations'].append({'evidence':'E2','quote':'추가 확보한 원문'})
    tb.reconcile_need(board,issue,field,side,row,'second',[],compile)
    assert board['round']==1 and board['research_needs'][need_id]['status']=='OPEN'
    assert all(board['tasks'][key]['status']==old['status'] and board['tasks'][key]['result_request_id']=='saved-result' for key,old in before.items())
    assert len(board['tasks'])==1
    assert not any(r['status']=='PENDING' for r in board['tasks'].values())
    visible=rc.child_context(board,side,'bound')
    assert visible['used_followups']==1 and visible['needs'][0]['need_id']==need_id
    assert visible['attempts'][0]['result_request_id']=='saved-result'
    assert not rc.child_context(board,'internal' if side=='external' else 'external','bound')['attempts']


@pytest.mark.parametrize('order',list(permutations([(0,4),(3,7),(1,2)])))
def test_progress_union_is_order_independent_and_survives_empty_pages(order):
    state={}
    expected=set()
    for index,(lo,hi) in enumerate(order):
        old=set(expected);expected.update(range(lo,hi))
        state['selected']={str(index):{'document_id':'d','evidence':[{'spans':[{'block_id':'b','start_cp':lo,'end_cp':hi}]}]}}
        assert rr.record_progress(state)==(old!=expected)
        state=json.loads(json.dumps(state));state['selected']={}
        assert not rr.record_progress(state)
    assert state['original_progress']['ranges']=={'d':{'b':[[0,7]]}}
    state['selected']={'new':{'document_id':'other','evidence':[{'spans':[{'block_id':'b','start_cp':0,'end_cp':7}]}]}}
    assert rr.record_progress(state)


@pytest.mark.parametrize('stale',[False,True])
def test_workflow_ingress_checks_parent_binding_before_child_dispatch(stale):
    context=S(binding_hash='current',run_id='parent',request={'question':'조건 확인'})
    port=S(services=S(),session=S(context=context),all_scope=[],categories={})
    task={'source_category':'external','search_hints':[],
          'research_continuity':rc.child_context({'tasks':{},'round':0},'external','stale' if stale else 'current')}
    action={'side':'external','operation':'ask_rag','args':{'question':'조건 확인','previous':None,'task':task}}
    if stale:
        with pytest.raises(ContractError,match='parent binding changed'):workflow_rag.execute(port,action,'call')
    else:
        result=workflow_rag.execute(port,action,'call')
        assert result['status']=='not_registered' and not result['evidence_ids']
