from copy import deepcopy
import json
import pytest
from test_batch_reference_navigation import connected,initial
from test_law_grouped_navigation import enable
from test_structure_reading import value
from semantic_runtime.legal_agent import law_navigation as ln,law_candidates as lc,connected_exploration as ce
from semantic_runtime.legal_agent.errors import ContractError,BudgetExhausted
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime import comparison_research_bridge as bridge

def new_document(connected,monkeypatch):
    s=connected[0]
    enable(s,structure_first=True,investigation_control=True,completion_contract=True,batch_selected_pages=True,
           completion_policy_version='investigation-completion-v8')
    s.profile.update(max_read_chars=8000,max_context_chars=80000)
    s.context.request['question']='모의승인규정'
    rec=SourceRecall(s).prepare()
    inv=ln.Investigation(s,'긴급 승인 예외',rec,None,120,None,None)
    monkeypatch.setattr(ce,'term_keys',lambda _:[])
    data,actions=inv.view()
    assert {r['document_id'] for r in inv.p['laws'].values()}=={'d'}
    source=next(r for r in s.tools.sources.values() if r['document_id']=='d')
    anchor={'id':'anchor','action':'READ_ARTICLES','identity':{'source_id':source['id'],'document_id':'d','unit_id':source['unit_id']},'label':'원칙 원문'}
    inv.execute_tool(value(data,'READ_ARTICLES','anchor'),data,{'anchor':anchor})
    data,actions=inv.view()
    assert {r['document_id'] for r in inv.p['laws'].values()}=={'d'}
    card=next(c for c in data['references']['dependency_cards'] if c['target']['document_id']=='detail')
    assert card['read_action'] in actions
    return inv,data,actions,card['read_action']

def test_new_connected_document_read_registers_before_decision_and_preserves_prior(connected,monkeypatch):
    inv,data,actions,target=new_document(connected,monkeypatch)
    before=deepcopy(inv.s.repo.evidence())
    inv.execute_tool(value(data,'READ_ARTICLES',target),data,actions)
    law=lc.token(inv.s,'L','detail')
    assert inv.p['laws'][law]['document_id']=='detail'
    assert inv.p['law_reasons'][law]['status']=='INVESTIGATE'
    evidence=inv.s.repo.evidence()
    assert all(e in evidence for e in before)
    assert any(e['document_id']=='detail' for e in evidence)
    assert any('책임자 확인' in e['text'] for e in evidence)
    assert not inv.active_records()
    count=deepcopy(inv.p['read_state']);state=deepcopy(inv.p)
    inv=ln.Investigation(inv.s,inv.question,inv.record,None,120,state,None)
    inv.execute_tool(value(data,'READ_ARTICLES',target),data,actions)
    assert inv.p['read_state']==count and inv.s.repo.evidence()==evidence

@pytest.mark.parametrize('defect',['scope','document','missing_target','budget'])
def test_invalid_new_document_never_registers_or_reads(connected,monkeypatch,defect):
    inv,data,actions,target=new_document(connected,monkeypatch)
    if defect=='scope':inv.s.scope=['d']
    elif defect=='document':actions[target]['identity']['document_id']='d'
    elif defect=='missing_target':actions={}
    else:inv.p['read_state']['chars']=10**9
    before=deepcopy(inv.p);evidence=deepcopy(inv.s.repo.evidence())
    with pytest.raises((ContractError,BudgetExhausted)):
        inv.execute_tool(value(data,'READ_ARTICLES',target),data,actions)
    assert inv.p==before and inv.s.repo.evidence()==evidence

def test_locator_projection_preserves_all_choices_and_full_provenance():
    offered={f'L{i}':{'side':'external','document_id':'doc','document_name':'동일한 긴 문서명 '*10,
        'source_id':'source','unit_id':str(i),'coordinate':f'제{i}조',
        'origin_evidence_id':'e','reference_id':('ref' if i%2 else None),
        'lead_ref':{'lead_id':f'lead{i}','bundle_hash':'h'*64}} for i in range(100)}
    before=deepcopy(offered);view=bridge.locator_view(offered)
    rows=[dict(zip(view['columns'],r)) for r in view['rows']]
    assert {r['locator_id'] for r in rows}==set(offered)
    assert all(r['coordinate']==offered[r['locator_id']]['coordinate'] for r in rows)
    assert all(r['lead_id']==offered[r['locator_id']]['lead_ref']['lead_id'] for r in rows)
    assert offered==before
    assert len(json.dumps(view,ensure_ascii=False))<len(json.dumps(offered,ensure_ascii=False))*0.5
    assert bridge.locator_view({})['rows']==[]
