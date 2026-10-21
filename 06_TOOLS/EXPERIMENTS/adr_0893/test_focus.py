from copy import deepcopy
import json
import pytest
from semantic_runtime.legal_agent import unit_relations as rel,completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError,ProposalError,TransportError,BudgetExhausted
from test_batch_reference_navigation import connected,initial,decision

def modern(s):
    s.profile.setdefault('candidate_navigation',{}).update(investigation_control=True,completion_contract=True,completion_policy_version=cc.V8)

def cross_window(s):
    modern(s);record,sid=initial(s);selected={'initial':record['unit_reads'][0]}
    g=next(g for g in rel.catalog(s,[sid],selected,set())[0] if g['target']['document_id']=='detail')
    hit,offer=g['offers']['subtree:0'];r=rel.read(s,hit,offer,action_state={'count':0,'chars':0})
    spans=[deepcopy(p) for e in r['evidence'] for p in e['spans']]
    return sid,selected,g['target']['source_id'],spans

@pytest.mark.parametrize('mode',['whole','split_union','partial','acquired_only'])
def test_native_reference_target_coverage_survives_focus_change(connected,mode):
    s,_=connected;sid,selected,target,spans=cross_window(s)
    # The target was acquired through the native reader but is outside focused selected.
    assert all(r['source_id']!=target for r in selected.values())
    if mode=='partial':
        for p in spans:
            p['end_cp']=p['start_cp'];p['text']='';p.pop('span_hash',None)
    if mode=='split_union':
        split=[]
        for p in spans:
            at=p['start_cp']+len(p['text'])//2
            a={**p,'end_cp':at,'text':p['text'][:at-p['start_cp']]}
            b={**p,'start_cp':at,'text':p['text'][at-p['start_cp']:]}
            a.pop('span_hash',None);b.pop('span_hash',None);split.extend([a,b])
        spans=split
    s.investigation_delivered_spans={} if mode=='acquired_only' else {target:spans}
    g=next(g for g in rel.catalog(s,[sid],selected,set())[0] if g['target']['source_id']==target)
    assert all(c['already_read'] for c in g['connections'])==(mode in ('whole','split_union'))
    if mode in ('whole','split_union'):
        calls=[]
        def invoke(*args):calls.append(args);raise AssertionError('verified full target needs no extra model selection')
        out=rel.navigate('긴급 승인 예외',s,selected,invoke,read_state={'count':0,'chars':0},seconds_left=lambda:120,max_context_chars=100000,state={})
        assert not calls and not out['actions']

@pytest.mark.parametrize('fault',['scope','source','block','text','offset','block_hash','span_hash'])
def test_delivered_target_integrity_remains_strict(connected,fault):
    s,_=connected;_,_,target,spans=cross_window(s)
    if fault=='scope':s.scope=['d']
    elif fault=='source':target='unknown'
    elif fault=='block':spans[0]['block_id']='unrelated'
    elif fault=='text':spans[0]['text']+='forged'
    elif fault=='offset':spans[0]['start_cp']=True
    else:spans[0][fault]='forged'
    with pytest.raises(ContractError):rel.delivered_blocks(s,{target:spans})

def navigate(s,selected,invoke,state):
    return rel.navigate('긴급 승인 예외',s,selected,invoke,read_state={'count':0,'chars':0},seconds_left=lambda:120,max_context_chars=100000,state=state,max_model_batches=1)

@pytest.mark.parametrize('fault',['policy_conflict','invalid_shape','proposal_error'])
def test_exhausted_model_reference_decision_preserves_originals_and_resume_budget(connected,fault):
    s,_=connected;modern(s);r,_=initial(s);selected={'initial':r['unit_reads'][0]};before=deepcopy(selected);state={};calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if fault=='proposal_error':raise ProposalError('synthetic invalid proposal')
        if fault=='invalid_shape':return {'needs_more':False,'decisions':[]}
        from semantic_runtime.legal_agent.output_contract import DecisionConflict
        raise DecisionConflict('conditional relation skip requires inapplicability reason')
    out=navigate(s,selected,invoke,state)
    assert len(calls)==2 and out['pending'] and out['pending_group_keys']
    assert not out['actions'] and not state['accepted'] and not state['decisions']
    assert any(l['kind']=='reference_decision_unresolved' for l in out['limits'])
    assert selected==before and state['unresolved_decision_menus']
    resumed=json.loads(json.dumps(state));again=navigate(s,selected,invoke,resumed)
    assert len(calls)==2 and again['pending'] and selected==before
    failed=next(iter(resumed['unresolved_decision_menus'].values()));failed['failure']['category']='forged'
    with pytest.raises(ContractError,match='unresolved reference decision changed'):navigate(s,selected,invoke,resumed)

def test_successful_single_repair_has_no_unresolved_marker(connected):
    s,_=connected;modern(s);r,_=initial(s);state={};calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if len(calls)==1:raise ProposalError('one correction')
        return decision(data)
    out=navigate(s,{'initial':r['unit_reads'][0]},invoke,state)
    assert len(calls)==2 and not state.get('unresolved_decision_menus')
    assert all(a['source_id']==r['unit_reads'][0]['source_id'] for a in out['actions'])

@pytest.mark.parametrize('error',[ContractError,TransportError,BudgetExhausted])
def test_nonproposal_failure_is_not_converted_to_reference_success(connected,error):
    s,_=connected;modern(s);r,_=initial(s);state={}
    def invoke(*args):raise error('strict synthetic error')
    with pytest.raises(error):navigate(s,{'initial':r['unit_reads'][0]},invoke,state)
    assert not state.get('unresolved_decision_menus') and not state['decisions']

def test_legacy_reference_consumer_keeps_its_existing_failure_contract(connected):
    s,_=connected;r,_=initial(s);state={};calls=[]
    def invoke(*args):calls.append(1);raise ProposalError('legacy invalid')
    with pytest.raises(ProposalError):navigate(s,{'initial':r['unit_reads'][0]},invoke,state)
    assert len(calls)==2 and not state.get('unresolved_decision_menus')
