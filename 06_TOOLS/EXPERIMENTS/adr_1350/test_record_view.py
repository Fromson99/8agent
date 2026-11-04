from copy import deepcopy
import pytest
from test_wiki_workspace import env,ws
from semantic_runtime.legal_agent.errors import ContractError

@pytest.mark.parametrize('payload',[
    '원기록의 판단을 그대로 보존😀',
    {'status':'업무 승인 대기','acl_ref':'업무상 접근권 설명','work_hash':'업무 데이터 이름',
     'index':[{'raw':{'payload':'원문 내부 중첩'}}],'reviewer':'업무 담당자'},
    [None,True,42,{'payload':['보존','같음','같음']}],
])
def test_model_sees_exact_payload_once_and_separate_immutable_bindings(env,ws,payload):
    raw=ws.import_payload(payload,event_id='projection',run_id='synthetic',format_description='형식 설명')
    before=deepcopy(ws.load(raw['bundle_id']));seen=[]
    def generate(prompt,context,schema):
        seen.append(deepcopy(context));r=context['raw_records'][raw['bundle_id']]
        assert set(r)=={'payload','format_description','origin'} and r['payload']==payload
        assert context['raw_record_bindings'][raw['bundle_id']]=={k:before[k] for k in ('revision','work_hash')}
        assert '최대 개수를 채우지 않는다' in prompt
        assert ws.load(raw['bundle_id'])==before
        return {'operations':[{'op':'ADD_STATEMENT','target':'@s','value':{'text':'원기록 의견 보존','origin_refs':[raw['bundle_id']]}}]},{}
    ws.generate=generate;args=dict(change_id='projection',raw_ids=[raw['bundle_id']])
    proposal=ws.propose(**args);assert ws.propose(**args)==proposal and len(seen)==1
    ws.apply(**proposal);assert ws.load(raw['bundle_id'])==before

def test_raw_binding_drift_after_response_blocks_commit_without_repair(env,ws,monkeypatch):
    raw=ws.import_payload('보존',event_id='drift',run_id='synthetic');real=ws.load;calls=[];changed=[False]
    def load(bid):
        result=real(bid)
        if bid==raw['bundle_id'] and changed[0]:result=deepcopy(result);result['revision']+=1
        return result
    monkeypatch.setattr(ws,'load',load)
    def generate(*args):
        calls.append(1);changed[0]=True
        return {'operations':[{'op':'CREATE_ENTRY','target':'@e','value':{'title':'미반영'}}]},{}
    ws.generate=generate
    with pytest.raises(ContractError,match='raw record changed'):ws.propose(change_id='drift',raw_ids=[raw['bundle_id']])
    assert len(calls)==1 and ws.list_items()['items']==[]
