from types import SimpleNamespace
from copy import deepcopy
import pytest
from workflow.risk_team_compare_workflow.retrieval import discover
from workflow.risk_team_compare_workflow.compare import validate
from semantic_runtime.legal_agent.workflow_execution import task_context,child_execution

@pytest.mark.parametrize('side',['internal','external'])
@pytest.mark.parametrize('count',[1,8,12])
def test_original_question_separate_from_scope_hints(side,count):
    sent=[]
    def call(action,call_id):
        sent.append(action);return {'status':'partial','evidence_ids':[],'unresolved':[]}
    q='회사 A의 유동성 기준과 예외를 비교해 주세요.\n기준 자산은 별도 제공하지 않았습니다.'
    ctx=SimpleNamespace(request={'question':q,'as_of':None},rag=SimpleNamespace(call=call),repo=SimpleNamespace(save=lambda s:None))
    state={'scope':{'issues':[{'id':str(i),'label':'다른 쪽 상세 항목 '+str(i)} for i in range(count)],
        'internal_queries':['내부 기준','내부 예외'],'external_queries':['외부 기준','외부 예외']},'history':[],'gaps':[]}
    assert discover(ctx,state,side)
    args=sent[0]['args'];assert args['question']==q
    assert args['task']=={'source_category':side,'search_hints':state['scope'][side+'_queries']}
    assert discover(ctx,state,side) is False and len(sent)==1

def test_task_context_is_copy_and_does_not_leak_after_failure():
    task={'source_category':'internal','search_hints':['승인']}
    assert task_context() is None
    with pytest.raises(RuntimeError):
        with child_execution(None,None,'call',['inside'],task=task):
            value=task_context();value['search_hints'].append('조작')
            assert task_context()==task
            raise RuntimeError('synthetic interruption')
    assert task_context() is None and task['search_hints']==['승인']

@pytest.mark.parametrize('verdict',['CONFORMS','ADDITIONAL_INTERNAL','CONFLICT','POSSIBLE_GAP'])
@pytest.mark.parametrize('fault',['partial','version','intermediate'])
def test_substantive_comparison_rechecks_presented_pair(verdict,fault):
    sources=[{'evidence_id':k,'source_complete':True,'version_verified':True,'spans':[{'text':'원칙'}]} for k in ('I','E','M')]
    pair={'pair_id':'p','issue_id':'i','internal':['I'],'external':['E'],'comparison_eligibility':True,'basis_relation':'DIRECT','basis_path':[]}
    if fault=='partial':sources[0]['source_complete']=False
    if fault=='version':sources[1]['version_verified']=False
    if fault=='intermediate':
        pair['basis_path']=[{'from_evidence':'I','to_evidence':'M'},{'from_evidence':'M','to_evidence':'E'}]
        sources[2]['source_complete']=False
    row={'pair_id':'p','verdict':verdict,'citations':[{'evidence':k,'quote':'원칙'} for k in ('I','E')],'numeric':False,'unresolved':['한계']}
    with pytest.raises(ValueError,match='complete verified'):
        validate({'rows':[row]},sources,{'pairs':[pair]},[{'id':'i','numeric':False}])
    row['verdict']='DEFERRED'
    validate({'rows':[row]},sources,{'pairs':[pair]},[{'id':'i','numeric':False}])
