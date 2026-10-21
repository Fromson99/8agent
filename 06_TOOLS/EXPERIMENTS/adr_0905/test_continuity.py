"""Finite reference state/consumer contracts; no live model or legal scoring."""
from copy import deepcopy
import json
import pytest
from test_batch_reference_navigation import connected,initial,decision
from test_investigation_chain_adr0671 import execute,back
from test_law_grouped_navigation import decide,cards,prepared
from test_read_choice_input_preservation import wire,capture
from semantic_runtime.legal_agent import law_navigation as ln,unit_relations as rel,investigation_chain as chain
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.contracts import digest

Q='긴급 승인 예외'

def start(s,action='SKIP'):
    menus=[]
    def invoke(system,data,schema,phase,timeout):
        assert phase.startswith('source-reference-')
        menus.append(deepcopy(data));return decision(data,action)
    inv=ln.Investigation(s,Q,prepared(s),invoke,120,None,None)
    data,actions=inv.view();card=next(c for c in cards(data) if s.tools.sources[inv.p['groups'][c['id']]['source_id']]['document_id']=='d')
    execute(inv,data,actions,decide(data,'READ_PARENT',card['read_parent_action'],card))
    data,actions=inv.view();a=next(a for a in actions.values() if a['action']=='FOLLOW_CONNECTION')
    execute(inv,data,actions,decide(data,'FOLLOW_CONNECTION',a['id']))
    assert len(menus)==1
    return inv,menus


def overview(inv):
    # Exercise the modern dependency consumer without replacing the reader's
    # legacy synthetic fixture with a different legal/model policy.
    prior=inv.control;inv.control=True;inv.p.setdefault('issues',[{'id':'Q1','question':Q}])
    try:return inv.reference_overview()
    finally:inv.control=prior


def test_closed_skip_reaches_next_wire_and_completion_inspection(connected,monkeypatch):
    inv,menus=start(connected[0]);before=deepcopy(inv.p['reference_states'])
    refs=overview(inv);assert refs['pending'] is False and refs['closed_connection_groups']==1
    card=refs['dependency_cards'][0];d=menus[0]['groups'][0]
    assert card['applicability']=='DOES_NOT_APPLY' and card['decision']['action']=='SKIP'
    assert card['decision']['reason']==decision(menus[0])['decisions'][0]['reason']
    def change(data,actions):data['references']=refs
    projected=capture(monkeypatch,change);assert wire(projected)['references']==refs
    assert inv.inspect_references()['pending'] is False
    assert inv.p['reference_states']==before
    _,actions=inv.view();assert not any(a['action']=='FOLLOW_CONNECTION' for a in actions.values())


@pytest.mark.parametrize('resume',[False,True])
def test_return_closed_skip_has_no_extra_model_call_and_keeps_frame(connected,resume):
    inv,menus=start(connected[0]);fid=menus[0]['chain_frame_id'];frame=deepcopy(chain.frame(inv.p,fid))
    states=deepcopy(inv.p['reference_states']);budget=deepcopy(inv.p['read_state'])
    if resume:
        saved=json.loads(json.dumps(inv.p,ensure_ascii=False))
        inv=ln.Investigation(inv.s,Q,inv.record,inv.invoke,120,saved,None)
    restored,_=back(inv,fid,'기존 판단 내용을 확인한다')
    assert len(menus)==1 and json.loads(json.dumps(chain.frame(inv.p,fid)))==json.loads(json.dumps(frame))
    assert inv.p['read_state']==budget
    assert inv.p['reference_state']['decisions']==next(iter(states.values()))['decisions']
    assert any(s['action']=='RETURN_TO' for s in chain.context(inv.p)['steps'])
    assert any(s['reference_decisions'] for s in chain.context(inv.p)['steps'])
    assert restored['references']['pending'] is False


def test_defer_stays_pending_and_explicit_return_can_finish_it(connected):
    inv,menus=start(connected[0],'DEFER');assert overview(inv)['pending'] is True
    assert not overview(inv)['dependency_cards'][0].get('decision')
    fid=menus[0]['chain_frame_id'];back(inv,fid,'미완료 판단을 계속한다')
    assert len(menus)==2 and inv.p['reference_state']['deferred']


@pytest.mark.parametrize('changed',['question','scope','generation'])
def test_replay_never_reuses_foreign_binding(connected,changed):
    inv,menus=start(connected[0]);fid=menus[0]['chain_frame_id'];frame=chain.frame(inv.p,fid)
    if changed=='question':q=Q+' 변경'
    else:q=Q
    if changed=='scope':inv.s.scope=['d']
    if changed=='generation':inv.s.context.query['generation_id']='different-generation'
    with pytest.raises(ContractError,match='binding changed'):
        rel.navigate(q,inv.s,inv.read_records(),inv.invoke,read_state=inv.p['read_state'],seconds_left=lambda:120,max_context_chars=80000,
            state=inv.p['reference_state'],replay_menu={'data':frame['data'],'offered':frame['offered']})
    assert len(menus)==1


def test_replay_refreshes_changed_witness_and_retains_prior_receipt(connected,monkeypatch):
    inv,menus=start(connected[0]);fid=menus[0]['chain_frame_id'];old=deepcopy(inv.p['reference_state']['decisions'])
    catalog=rel.catalog
    def revised(*args,**kwargs):
        groups,statuses,limits,unresolved=catalog(*args,**kwargs)
        # Catalog-boundary unit mutation represents an authorized new witness;
        # separate hash/ACL tests exercise rejection in the real catalog.
        for g in groups:
            for c in g['connections']:c['witness_sha256']='new-verified-witness';c['witness']='새로 검증된 참조 문구'
        return groups,statuses,limits,unresolved
    monkeypatch.setattr(rel,'catalog',revised)
    assert overview(inv)['pending'] is True
    back(inv,fid,'새 참조 원문을 확인한다');assert len(menus)==2
    assert menus[1]['groups'][0]['connections'][0]['witness']=='새로 검증된 참조 문구'
    assert old.items()<=inv.p['reference_state']['decisions'].items()
    assert len(inv.p['reference_state']['decisions'])==2


def test_replay_missing_authorized_group_fails_without_model_call(connected,monkeypatch):
    inv,menus=start(connected[0]);fid=menus[0]['chain_frame_id'];frame=chain.frame(inv.p,fid)
    monkeypatch.setattr(rel,'catalog',lambda *a,**kw:([],[],[],[]))
    with pytest.raises(ContractError,match='stale reference replay group'):
        rel.navigate(Q,inv.s,inv.read_records(),inv.invoke,read_state=inv.p['read_state'],seconds_left=lambda:120,max_context_chars=80000,
            state=inv.p['reference_state'],replay_menu={'data':frame['data'],'offered':frame['offered']})
    assert len(menus)==1


@pytest.mark.parametrize('defect',['missing_reason','bad_scope','defer','incomplete_follow','foreign_binding','conflict'])
def test_uncertain_or_invalid_receipts_do_not_close_overview(connected,defect):
    inv,menus=start(connected[0]);state=inv.p['reference_state'];key=next(iter(state['decisions']));d=state['decisions'][key]
    if defect=='missing_reason':d.pop('reason')
    elif defect=='bad_scope':d['scopes']=['forged']
    elif defect=='defer':d.update(action='DEFER',applicability='UNDETERMINED')
    elif defect=='incomplete_follow':d.update(action='FOLLOW',applicability='APPLIES',scopes=['subtree:1'])
    elif defect=='foreign_binding':
        inv.p['reference_states']={'other':{**state,'binding':'foreign'}}
    else:
        other=deepcopy(state);other['decisions'][key]['reason']='서로 다른 판단 이유'
        inv.p['reference_states']={'a':state,'b':other}
    refs=overview(inv);assert refs['pending'] is True and refs['closed_connection_groups']==0
    assert all('decision' not in c for c in refs['dependency_cards'])


def test_follow_replay_reuses_completed_scopes_without_read_or_model(connected):
    s,_=connected;rec,sid=initial(s);selected={'U1':rec['unit_reads'][0]};groups,*_=rel.catalog(s,[sid],selected,set())
    g=groups[0];data={'question':Q,'groups':[rel.menu(g,'R1')]};calls=[];state={};read_state={'count':0,'chars':0}
    def invoke(system,data,schema,phase,timeout):
        calls.append(data);d=decision(data)
        
        if len(calls)==1:d['decisions'][0].update(action='FOLLOW',applicability='APPLIES',scopes=['subtree:1'])
        return d
    args=dict(read_state=read_state,seconds_left=lambda:120,max_context_chars=80000,state=state)
    rel.navigate(Q,s,selected,invoke,**args)
    assert calls and len(selected)>1
    prior_calls=len(calls)
    before=deepcopy((selected,read_state,state['decisions']))
    rel.navigate(Q,s,selected,invoke,replay_menu={'data':data,'offered':{'R1':g}},**args)
    assert len(calls)==prior_calls and (selected,read_state,state['decisions'])==before
