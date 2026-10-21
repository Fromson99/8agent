from copy import deepcopy
import pytest
from semantic_runtime.legal_agent.completion_execution import intent_input,INTENT_PROVENANCE_PROMPT
from semantic_runtime.legal_agent import completion_v5 as v5
from semantic_runtime.legal_agent.errors import ProposalError

@pytest.mark.parametrize('current',['그럼 제외되는 경우는?','그럼 예외는?\n업무배경: 분기보고','추가 조건 😀 e\u0301도 알려줘','아예 다른 제도의 제출기한은?'])
@pytest.mark.parametrize('prior',['이전 규정 10% 기준 (업무 문맥: 기존 규정)',''])
def test_current_quotes_remain_distinct_from_resolved_goal(current,prior):
    original={'question':prior or current,'investigation_chain':{'steps':['prior read']},'current_facts':[]}
    before=deepcopy(original);view=intent_input(original,current)
    assert view['question']==view['current_request']==current and original==before
    assert view['investigation_chain']==before['investigation_chain']
    value={'background_quotes':[],'issues':[{'request_quote':current}]}
    v5.verify_intent(value,current)
    if prior:
        assert view['resolved_goal_context']['text']==prior and view['resolved_goal_context']['quote_source'] is False
        value['background_quotes']=[prior]
        with pytest.raises(ProposalError,match='background quote'):v5.verify_intent(value,current)
        value['background_quotes']=[];value['issues'][0]['request_quote']=prior
        with pytest.raises(ProposalError,match='request quote'):v5.verify_intent(value,current)
    else:assert 'resolved_goal_context' not in view
