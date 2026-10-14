"""Review counterexamples plus negative provenance and historical-render contracts."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from semantic_runtime.legal_agent import completion_contracts as cc, law_navigation as ln
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from test_judgment_loop_recovery import GAP, completion, read_and_adopt, reopened_with_gap, value, apply
from test_unit_fulltext_adaptive_read import tree, session

def test_distinct_unlocated_source_gaps_do_not_collapse():
 a={k:v for k,v in GAP.items() if k!='missing_target'}
 b={**a,'reason':'별표의 산식 원문이 없다'}
 assert cc.gap_key(a)!=cc.gap_key(b)
 assert cc.gap_key(a)==cc.gap_key({**a,'reason':'  '+a['reason']+'  '})

def test_known_target_is_stable_across_reason_changes():
 assert cc.gap_key(GAP)==cc.gap_key({**GAP,'reason':'같은 원문을 다시 요구한다'})

@pytest.mark.parametrize('layout',[None,'table'])
def test_shared_claim_support_is_shown_without_duplicating_claim(layout):
 issues=[{'id':'Q1','question':'승인권자'},{'id':'Q2','question':'보고 상대'},{'id':'Q3','question':'기한'}]
 claims=[{'claim_id':'C1','issue_refs':['Q1','Q2'],'text':'승인권자는 A, 보고 상대는 B다.'}]
 assessment={'claims':claims,'completion_contract':cc.CONTRACT,'limitations':[], 'limitation_items':[],'stop_reason':None}
 answer=cc.compose(assessment,cc.default_plan(assessment,layout,issues))
 cc.verify_composition(assessment,answer)
 assert answer['text'].count(claims[0]['text'])==1
 assert '공통 판단에 함께 설명' in answer['text']
 assert answer['text'].count(cc.NO_ISSUE_EVIDENCE)==1
 assert len(answer['claims'])==1

def test_forged_shared_issue_links_are_rejected():
 issues=[{'id':'Q1','question':'첫째'},{'id':'Q2','question':'둘째'}]
 a={'claims':[{'claim_id':'C1','issue_refs':['Q1'],'text':'판단'}], 'completion_contract':cc.CONTRACT,
    'limitations':[],'limitation_items':[],'stop_reason':None}
 plan=cc.default_plan(a,None,issues);plan['issue_sections'][1]['shared_claim_ids']=['C1']
 with pytest.raises(ContractError,match='shared issue'):cc.compose(a,plan)

@pytest.mark.parametrize('contract',[cc.V1,cc.V2])
def test_historical_contract_rendering_is_preserved(contract):
 issues=[{'id':'Q1','question':'첫째'},{'id':'Q2','question':'둘째'}]
 a={'claims':[{'claim_id':'C1','issue_refs':['Q1','Q2'],'text':'과거 판단'}], 'completion_contract':contract,
    'limitations':[],'limitation_items':[],'stop_reason':None}
 answer=cc.compose(a,cc.default_plan(a,None,issues));cc.verify_composition(a,answer)
 assert '공통 판단에 함께 설명' not in answer['text']
 assert (cc.NO_ISSUE_EVIDENCE in answer['text'])==(contract==cc.V2)

def gap_validator(receipts=(),groups=None):
 gaps=[dict(GAP,gap_id='G1'),dict(GAP,gap_id='G2',issue_id='Q2',missing_target='다른 법 제2조')]
 inv=object.__new__(ln.Investigation)
 inv.p={'groups':groups or {}}
 inv.current_gap_round=lambda:{'adopted_at_open':[], 'actions':10,'action_receipts':list(receipts)}
 inv.adopted_basis=lambda decision:{'B1'}
 return inv,{'assessment_gaps':gaps}

def resolutions(status='NOT_AVAILABLE'):
 return {'gap_resolutions':[{'gap_id':g,'status':status,'reason':'조사 결과','action_refs':['S1'],'basis_refs':[]}
                            for g in ['G1','G2']]}

def test_round_global_action_count_cannot_close_gaps():
 inv,data=gap_validator()
 with pytest.raises(ProposalError,match='completed'):inv.validate_gap_resolutions(resolutions(),data)

@pytest.mark.parametrize('status',['INTERRUPTED','STARTED','AWAITING_RESULT'])
def test_unfinished_actions_cannot_close_gaps(status):
 inv,data=gap_validator([{'id':'S1','gap_ids':['G1','G2'],'status':status}])
 with pytest.raises(ProposalError,match='completed'):inv.validate_gap_resolutions(resolutions(),data)

def test_action_for_one_gap_cannot_close_another():
 inv,data=gap_validator([{'id':'S1','gap_ids':['G1'],'status':'COMPLETED'}])
 with pytest.raises(ProposalError,match='G2'):inv.validate_gap_resolutions(resolutions(),data)

def test_resolution_requires_evidence_adopted_for_same_issue():
 groups={'b':{'status':'ACTIVE','issue_decisions':{'Q1':{'status':'ADOPT','basis_refs':['B1']}}}}
 inv,data=gap_validator([{'id':'S1','gap_ids':['G1','G2'],'status':'COMPLETED'}],groups)
 out=resolutions('RESOLVED')
 for row in out['gap_resolutions']:row['basis_refs']=['B1']
 with pytest.raises(ProposalError,match='G2'):inv.validate_gap_resolutions(out,data)

def test_explicit_completed_actions_close_their_own_gaps():
 inv,data=gap_validator([{'id':'S1','gap_ids':['G1'],'status':'COMPLETED'},
                         {'id':'S2','gap_ids':['G2'],'status':'COMPLETED'}])
 out=resolutions();out['gap_resolutions'][1]['action_refs']=['S2']
 inv.validate_gap_resolutions(out,data)

def test_multigap_action_requires_explicit_target_and_persists_receipt(session):
 native,_=session;inv,_=completion(native);read_and_adopt(inv)
 state=deepcopy(inv.p);state['assessment_gaps']=[deepcopy(GAP),dict(GAP,missing_target='모의 시행령 제9조')]
 again,_=completion(native,checkpoint=state);data,actions=again.view()
 target=next(k for k,a in actions.items() if a['action']=='OPEN_LAW')
 decision=value(data,'OPEN_LAW',target)
 with pytest.raises(Exception):again.validate(decision,data,actions)
 decision['gap_ids']=[data['assessment_gaps'][0]['gap_id']]
 apply(again,decision,data,actions)
 receipt=again.p['gap_rounds'][-1]['action_receipts'][0]
 assert receipt['gap_ids']==decision['gap_ids'] and receipt['status']=='COMPLETED'
 resumed=ln.Investigation(again.s,again.question,again.record,None,120,deepcopy(again.p),None)
 assert resumed.p['gap_rounds'][-1]['action_receipts']==again.p['gap_rounds'][-1]['action_receipts']
