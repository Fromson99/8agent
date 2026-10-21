from copy import deepcopy
import json
import pytest
from semantic_runtime.legal_agent import research_continuity as rc, request_repair as rr
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.workflow_execution import validate_task
from workflow.risk_team_compare_workflow import task_board as tb


def span(lo, hi):return {'block_id':'b','start_cp':lo,'end_cp':hi}
def acquired(lo,hi):return {'document_id':'d','evidence':[{'spans':[span(lo,hi)]}]}


@pytest.mark.parametrize('kind',['law','candidate','location','definition','term'])
def test_discovery_is_recorded_but_is_not_new_original(kind):
    state={'groups':{},'basis_history':{},'selected':{}}
    assert not rr.record_progress(state)
    if kind=='law':state['laws']={'L':{'document_id':'d'}}
    if kind=='candidate':state['groups']={'G':{'hit':{'document_id':'d','source_id':'s'}}}
    if kind=='location':state['structure_page']={'items':[{'document_id':'d','unit_id':'u'}]}
    if kind=='definition':state['definition_visible_ids']=['definition']
    if kind=='term':state['document_term_exploration']={'documents':{'d':{'status':'READY','binding':'fixed','items':[{'source_id':'s'}]}}}
    assert not rr.record_progress(state)
    assert state['discovery_changed'] and state['request_progress']
    assert not rc.progress_view(state)['new_original']


def test_original_progress_is_union_preserved_across_restart_and_page_eviction():
    state={'selected':{'a':acquired(0,10)}}
    assert rr.record_progress(state)
    saved=json.loads(json.dumps(state))
    saved['selected']={'different-label':acquired(2,8)}
    assert not rr.record_progress(saved)
    saved['selected']={'different-label':acquired(8,15)}
    assert rr.record_progress(saved)
    assert saved['original_progress']['ranges']=={'d':{'b':[[0,15]]}}
    assert saved['original_progress']['revision']==2
    saved['selected']={};assert not rr.record_progress(saved)
    saved['selected']={'a':acquired(0,10)};assert not rr.record_progress(saved)


def task(query='허용 조건',operation='search_text'):
    return {'schema_version':'comparison-research-v1','task_id':'unassigned','issue_id':'i',
        'target_side':'external','requested_fields':['condition'],'missing_target':query,
        'target_locator':None,'anchor_refs':[],'operation':operation,'allowed_operations':[operation],
        'completion_conditions':['Read originals'],'binding_hash':'bound'}


def setup():
    board={'tasks':{},'round':0};issue={'id':'i','external_task':'허용 조건 조사'}
    row={'status':'PARTIAL','text':'확인한 내용','missing':'추가 조건 미확인',
         'citations':[{'evidence':'old','quote':'원문'}]}
    def compile(proposal):
        t=task(proposal['query'],proposal['operation']);t['target_locator']=proposal.get('target')
        return tb.register_task(board,t,proposal,True)
    return board,issue,row,compile


@pytest.mark.parametrize('status',['COMPLETE','PARTIAL','FAILED'])
def test_reworded_missing_never_restarts_automatic_exhausted_route(status):
    board,issue,row,compile=setup()
    tb.reconcile_need(board,issue,'condition','external',row,'first',[],compile)
    need=next(iter(board['research_needs'].values()));record=next(iter(board['tasks'].values()))
    record.update(status=status,result_request_id='child',need_basis={need['need_id']:need['basis_hash']})
    board=json.loads(json.dumps(board));row['missing']='같은 조건을 다른 표현으로 다시 확인'
    before=len(board['tasks'])
    def forbidden(_):pytest.fail('rewritten missing must retain old attempt')
    tb.reconcile_need(board,issue,'condition','external',row,'second',[],forbidden)
    assert len(board['tasks'])==before and board['round']==0
    need=next(iter(board['research_needs'].values()))
    assert need['status']=='OPEN' and need['continuation_reason']=='SAME_EVIDENCE_ATTEMPT_RECORDED'
    assert tb.research_need_view(board)[0]['execution_state']=='ATTEMPT_RECORDED'


def test_explicit_alternative_and_new_cited_original_can_continue():
    board,issue,row,compile=setup();tb.reconcile_need(board,issue,'condition','external',row,'first',[],compile)
    need=next(iter(board['research_needs'].values()));record=next(iter(board['tasks'].values()))
    record.update(status='PARTIAL',need_basis={need['need_id']:need['basis_hash']})
    proposal={'side':'external','operation':'search_text','query':'다른 원문 표현',
              'priority':'CORE','priority_reason':'다른 경로','reason':'첫 검색에서 확보하지 못한 직접 근거 탐색'}
    alternate=compile(proposal)
    tb.reconcile_need(board,issue,'condition','external',row,'second',[alternate],compile)
    assert board['tasks'][alternate]['status']=='PENDING'
    board['tasks'][alternate].update(status='PARTIAL',need_basis={need['need_id']:need['basis_hash']})
    row['citations']=[{'evidence':'new','quote':'새 원문 조건'}];row['missing']='새 원문의 예외 미확인'
    tb.reconcile_need(board,issue,'condition','external',row,'third',[],compile)
    assert any(r['status']=='PENDING' for r in board['tasks'].values())
    assert len(board['tasks'])==3 and need['status']=='OPEN'


def test_exact_operation_identity_ignores_display_and_origin_but_keeps_binding():
    a=task(operation='read_node');a['target_locator']={'document_id':'d','unit_id':'u','source_id':'s','reference_id':None,
        'origin_evidence_id':'old','document_name':'첫 이름','coordinate':'제1조'}
    b=deepcopy(a);b.update(task_id='other',issue_id='j',requested_fields=['obligation'],missing_target='다른 설명')
    b['target_locator'].update(origin_evidence_id='new',document_name='다른 표시',lead_ref='new-label')
    assert tb.acquisition_key(a)==tb.acquisition_key(b)
    for key in ('binding_hash','target_side','operation'):
        c=deepcopy(b);c[key]='different';assert tb.acquisition_key(a)!=tb.acquisition_key(c)
    for key in ('document_id','unit_id','source_id','reference_id'):
        c=deepcopy(b);c['target_locator'][key]='different';assert tb.acquisition_key(a)!=tb.acquisition_key(c)
    assert tb.acquisition_key(task('첫 검색'))!=tb.acquisition_key(task('둘째 검색'))
    assert tb.acquisition_key(task('첫  검색'))==tb.acquisition_key(task('첫 검색'))


def scoped_context():
    board,issue,row,compile=setup();tb.reconcile_need(board,issue,'condition','external',row,'first',[],compile)
    t=next(iter(board['tasks'].values()))['task']
    request={'source_category':'external','search_hints':[],'issues':[{'id':'i','question':'조건 확인','numeric':False}],
             'facts':[],'research_task':t,'research_continuity':rc.child_context(board,'external','bound',t)}
    return board,request


@pytest.mark.parametrize('tamper',['side','binding','task','issue','need','status','extra'])
def test_scoped_child_rejects_tampered_continuity(tamper):
    board,request=scoped_context();validate_task(request,'조건 확인')
    c=request['research_continuity']
    if tamper=='side':c['side']='internal'
    if tamper=='binding':c['binding_hash']='stale'
    if tamper=='task':c['current_task_id']='other'
    if tamper=='issue':c['needs'][0]['issue_id']='other'
    if tamper=='need':c['needs'][0]['need_id']='other'
    if tamper=='status':c['needs'][0]['status']='ABSENCE_PROVEN'
    if tamper=='extra':c['unsupported']='value'
    with pytest.raises(ContractError):validate_task(request,'조건 확인')


def test_child_context_carries_attempt_result_and_parent_review_without_source_copy():
    board,request=scoped_context();record=next(iter(board['tasks'].values()))
    record.update(status='PARTIAL',result_request_id='child-1',new_evidence=['E1'])
    board['evidence_updates']=[{'issue_id':'i','evidence_id':'E1','disposition':'UNRELATED','fields':[], 'reason':'다른 적용 대상'}]
    c=rc.child_context(board,'external','bound',record['task'])
    assert c['attempts'][0]['new_evidence_ids']==['E1']
    assert c['attempts'][0]['evidence_review'][0]['disposition']=='UNRELATED'
    request['research_continuity']=json.loads(json.dumps(c));validate_task(request,'조건 확인')
    assert c['attempts'][0]['result_request_id']=='child-1'
    assert rc.child_context(board,'internal','bound')['attempts']==[]


def test_no_progress_state_survives_epoch_without_resetting_budget():
    state={'no_progress':3,'read_state':{'count':7},'original_progress':{'ranges':{'d':{'b':[[0,10]]}},'revision':2},
           'reentry_counters':{'ASSESS_GAP_REENTRY':1},'request_progress':['candidate:x']}
    again=rr.new_epoch(state,reason='ASSESS_GAP_REENTRY')
    for key in state:assert again[key]==state[key]


def test_actual_api_child_receives_continuity_and_duplicate_reuses_answer(tmp_path,tree):
    from fastapi.testclient import TestClient
    from test_generalized import General,prior
    from test_legal_agent_double_harness import wire
    class Continuation(General):
        def send_once(self,*,body,ticket):
            result=super().send_once(body=body,ticket=ticket)
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage')=='workflow-items':
                value=json.loads(result['body_json']['choices'][0]['message']['content'])
                if view['review_mode']=='INITIAL':
                    value['items'][0]['external']['missing']='적용 조건 원문 추가 조사'
                    value['items'][0]['next_tasks']=[]
                return wire(value)
            return result
    app,_=prior.app_for(tmp_path,tree);transport=Continuation();app.state.pipeline.term_agent.transport=transport
    with TestClient(app) as client:
        r=client.post('/v1/rag/ask',json=prior.BODY);assert r.status_code==200,r.text
        result=r.json()
        seen=[v for v in transport.views if v.get('research_continuity')]
        assert seen, [v.get('source_stage',v.get('phase')) for v in transport.views]
        c=seen[0]['research_continuity'];assert c['needs'] and c['attempts'] and c['current_task_id']
        assert all(r['side']=='external' for r in c['attempts'])
        count=len(transport.views)
        same=client.post('/v1/rag/ask',json=prior.BODY)
        assert same.json()['answer']==result['answer'] and len(transport.views)==count
        stored=client.get('/v1/workflows/runs/'+result['run_id'],params={'session_id':'s'})
        assert stored.json()['answer']==result['answer']


from test_generalized import tree
