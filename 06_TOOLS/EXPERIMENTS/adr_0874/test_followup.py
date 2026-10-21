from copy import deepcopy
from types import SimpleNamespace
import pytest
from workflow.risk_team_compare_workflow import task_board as board
from semantic_runtime.contracts import digest


def task(ident,side='internal',field='subject',query='missing original'):
    return {'schema_version':'comparison-research-v1','task_id':ident,'issue_id':'issue-1',
        'target_side':side,'requested_fields':[field],'missing_target':query,'operation':'search_text',
        'allowed_operations':['search_text'],'anchor_refs':[],'target_locator':None,
        'binding_hash':'bound','completion_conditions':['Read target originals']}


def harness(tasks,monkeypatch,outcomes,crash=False):
    state={'task_board':{'round':0,'tasks':{t['task_id']:{'task':t,'status':'PENDING'} for t in tasks}},
        'rag_results':{s:{'request_id':s+'-old','continuation':{'goal_id':'g'},'evidence_ids':[s+'-old']} for s in ('internal','external')},'rag_attempts':{}}
    results={v['request_id']:v for v in state['rag_results'].values()};calls=[];receipts={};saved=[]
    ctx=SimpleNamespace(definition=SimpleNamespace(manifest={'max_recoveries':2}),
        repo=SimpleNamespace(call=lambda key:{'result':results[key]},save=lambda s:saved.append(deepcopy(s))))
    def discover(ctx,state,side,*,question,research_task,previous_result):
        key=research_task['task_id']
        if key not in receipts:
            calls.append(key);mode=outcomes[key];old=state['rag_results'][side]
            receipt={'task_hash':digest(research_task),'status':mode[0]}
            result={'request_id':key+'-result','status':'failed' if mode[0]=='FAILED' else 'completed',
                'continuation':{'goal_id':'g'},'evidence_ids':old['evidence_ids']+mode[1],
                'investigation_return':{'research_tasks':{key:receipt}}}
            receipts[key]=result;results[result['request_id']]=result
        result=receipts[key];state['rag_attempts'][side]=result;state['rag_results'][side]=result
        if crash and not saved[-1].get('crashed'):
            saved[-1]['crashed']=True
            # Simulate interruption after durable child result and updated
            # latest result, before parent marks the research task complete.
            nonlocal_crashed[0]+=1
            if nonlocal_crashed[0]==1:raise KeyboardInterrupt()
        return result['status']!='failed'
    nonlocal_crashed=[0]
    monkeypatch.setattr(board.retrieval,'discover',discover)
    return ctx,state,calls,results


def test_empty_target_does_not_starve_distinct_target_and_duplicate_fields_share_receipt(monkeypatch):
    tasks=[task('missing'),task('same',field='obligation'),task('useful','external',query='specific article'),task('later',query='later target')]
    ctx,state,calls,_=harness(tasks,monkeypatch,{'missing':('PARTIAL',[]),'useful':('COMPLETE',['external-new'])})
    assert board.research(ctx,state)
    assert calls==['missing','useful'] and state['task_board']['round']==2
    records=state['task_board']['tasks']
    assert records['missing']['status']==records['same']['status']=='PARTIAL'
    assert records['same']['reused_acquisition'] and records['same']['result_request_id']==records['missing']['result_request_id']
    assert records['useful']['status']=='COMPLETE' and records['later']['status']=='PENDING'
    assert not board.research(ctx,state) and len(calls)==2


def test_all_empty_respects_existing_two_attempt_limit(monkeypatch):
    tasks=[task(str(n),query='different '+str(n)) for n in range(3)]
    ctx,state,calls,_=harness(tasks,monkeypatch,{'0':('PARTIAL',[]),'1':('PARTIAL',[])})
    assert not board.research(ctx,state)
    assert calls==['0','1'] and state['task_board']['round']==2
    assert state['task_board']['tasks']['2']['status']=='PENDING'


@pytest.mark.parametrize('status,ok,hash_ok,expected',[
    ('COMPLETE',True,True,'COMPLETE'),('PARTIAL',True,True,'PARTIAL'),
    ('FAILED',True,True,'FAILED'),('STARTED',True,True,'PARTIAL'),
    ('COMPLETE',False,True,'FAILED'),('COMPLETE',True,False,'PARTIAL')])
def test_old_readable_sources_do_not_certify_requested_task(status,ok,hash_ok,expected):
    t=task('target');latest={'evidence_ids':['old'],'investigation_return':{'research_tasks':{
        'target':{'status':status,'task_hash':digest(t) if hash_ok else 'wrong'}}}}
    assert board.acquisition_status(latest,t,ok)==expected
    assert board.acquisition_status({'evidence_ids':['old']},t,True)=='PARTIAL'


def test_resume_keeps_pre_attempt_evidence_and_no_extra_physical_acquisition(monkeypatch):
    ctx,state,calls,_=harness([task('target')],monkeypatch,{'target':('COMPLETE',['new'])},crash=True)
    with pytest.raises(KeyboardInterrupt):board.research(ctx,state)
    assert state['task_board']['tasks']['target']['status']=='RUNNING'
    assert board.research(ctx,state)
    assert calls==['target'] and state['task_board']['round']==1
    assert state['task_board']['tasks']['target']['new_evidence']==['new']
    assert not board.research(ctx,state) and calls==['target']


def test_exact_target_identity_keeps_side_binding_and_locator_distinct():
    t=task('a');same={**t,'task_id':'b','issue_id':'issue-2','requested_fields':['date']}
    assert board.acquisition_key(t)==board.acquisition_key(same)
    for change in ({'target_side':'external'},{'binding_hash':'changed'},{'missing_target':'another original'},
                   {'anchor_refs':[{'evidence_id':'different'}]}):
        assert board.acquisition_key(t)!=board.acquisition_key({**same,**change})
