"""Exercise real saved inspection and action-coupled correction at SELECT boundaries."""
from copy import deepcopy
import pytest
from jsonschema import validate, ValidationError
from test_unit_fulltext_adaptive_read import tree, session
from test_investigation_control_adr0674 import investigation, read_parent, value, apply, adopt
from semantic_runtime.legal_agent import law_navigation as ln
from semantic_runtime.legal_agent.errors import ProposalError


def defer(data,gid):
    return {'branch_id':gid,'status':'DEFER','reason':'원문 재열람 후 채택 재판단',
            'issue_refs':['Q1'],'basis_refs':[]}


def test_deferred_saved_original_can_be_inspected_without_acquisition_or_adoption(session):
    native,_=session;inv=investigation(native);gid=read_parent(inv)
    data,actions=inv.view();out=value(data);out['branch_decisions']=[defer(data,gid)]
    apply(inv,out,data,actions)
    data,actions=inv.view();assert not data['sources']
    count=inv.p['read_state']['count']
    target=next(a['id'] for a in actions.values() if a['action']=='VIEW_SAVED_SOURCE')
    out=value(data,'VIEW_SAVED_SOURCE',target);out['branch_decisions']=[defer(data,gid)]
    apply(inv,out,data,actions)
    data,actions=inv.view();assert data['sources'] and inv.p['read_state']['count']==count
    assert inv.p['groups'][gid]['issue_decisions']['Q1']['status']=='DEFER'
    done=adopt(inv,gid);assert inv.result(done)['selected_originals']


def test_new_original_read_still_rejects_same_branch_defer(session):
    native,_=session;inv=investigation(native);data,actions=inv.view();card=data['articles'][0]
    out=value(data,'READ_PARENT',card['read_parent_action'],card)
    out['branch_decisions']=[defer(data,card['id'])]
    with pytest.raises(ProposalError,match='cannot read'):inv.validate(out,data,actions)
    strong,instructions=ln.repair_contract(data,actions,set(inv.p['groups']),out,ProposalError('conflict'))
    assert instructions['conflicts'][0]['status']=='DEFER'
    with pytest.raises(ValidationError):validate(out,strong)
    corrected=deepcopy(out);corrected['branch_decisions']=[]
    validate(corrected,strong);assert not inv.p['selected']


def test_control_correction_rebinds_original_basis_when_action_changes(session):
    native,_=session;inv=investigation(native);gid=read_parent(inv);data,actions=inv.view()
    previews=[b['id'] for b in data['basis'] if not b.get('branch_id')]
    assert previews
    target=next(a['id'] for a in actions.values() if a['action']=='VIEW_SAVED_SOURCE')
    rejected=value(data,'VIEW_SAVED_SOURCE',target);rejected['basis_refs']=[previews[0]]
    schema,is_patch=ln.correction_schema(data,actions,set(inv.p['groups']),rejected)
    assert not is_patch
    with pytest.raises(ValidationError):validate({'next_action':'FINISH'},schema)
    wrong=deepcopy(rejected);wrong.update(next_action='FINISH',targets=[],sufficiency_reason='종료')
    with pytest.raises(ValidationError):validate(wrong,schema)
    right=deepcopy(wrong);right['basis_refs']=[p['id'] for p in data['sources']]
    validate(right,schema);assert ln.corrected_decision(rejected,right,is_patch)==right
