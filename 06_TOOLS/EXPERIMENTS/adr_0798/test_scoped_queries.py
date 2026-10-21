from types import SimpleNamespace
import pytest
from workflow.risk_team_compare_workflow.retrieval import discover

@pytest.mark.parametrize('side',['internal','external'])
@pytest.mark.parametrize('count',[1,8,12])
def test_child_question_retains_user_and_only_own_hints(side,count):
    sent=[]
    def call(action,call_id):
        sent.append(action)
        return {'status':'partial','evidence_ids':[],'unresolved':[]}
    request={'question':'회사 A의 유동성 기준과 예외를 비교해 주세요.','as_of':'2026-10-15'}
    ctx=SimpleNamespace(request=request,rag=SimpleNamespace(call=call),repo=SimpleNamespace(save=lambda s:None))
    state={'scope':{'issues':[{'id':str(i),'label':'다른 쪽 상세 항목 '+str(i)} for i in range(count)],
        'internal_queries':['내부 기준','내부 예외'],'external_queries':['외부 기준','외부 예외']},'history':[],'gaps':[]}
    assert discover(ctx,state,side)
    q=sent[0]['args']['question'];other='external' if side=='internal' else 'internal'
    assert q.count(request['question'])==1 and '2026-10-15' in q
    assert all(h in q for h in state['scope'][side+'_queries'])
    assert all(h not in q for h in state['scope'][other+'_queries'])
    assert '다른 쪽 상세 항목' not in q and len(q)<300
    assert discover(ctx,state,side) is False and len(sent)==1
