"""Actual native loop, index/menu and source reads with scripted decisions."""
from semantic_runtime.legal_agent import request_repair as rr
from semantic_runtime.legal_agent import comparison_research, source_investigation, definition_entry
from test_main50_request_repair import tree, session, modern
from test_investigation_completion_adr0678 import decision


def test_actual_native_discovery_recovery_can_reach_read_and_finish(session,monkeypatch):
    inv=modern(session[0])
    from semantic_runtime.basis_links import resolver
    for module,name in [(resolver,'acquire'),(comparison_research,'acquire'),
                        (source_investigation,'acquire_preferred'),(definition_entry,'acquire_initial')]:
        monkeypatch.setattr(module,name,lambda _:None)
    data,initial_actions=inv.view()
    rr.record_progress(inv.p)
    inv.p['no_progress']=inv.s.profile['max_no_progress']
    initially_offered={rr.operation_key({'next_action':a['action'],'targets':[target]},initial_actions)
                       for target,a in initial_actions.items() if a['action']=='READ_ARTICLES'}
    calls=[]
    def choose(data,actions,phase):
        calls.append(phase)
        if len(calls)==1:
            target=next(t for t,a in actions.items() if a['action']=='OPEN_LAW')
            return decision(data,'OPEN_LAW',target)
        if len(calls)==2:
            target=next(t for t,a in actions.items() if a['action']=='READ_ARTICLES'
                        and rr.operation_key({'next_action':'READ_ARTICLES','targets':[t]},actions) not in initially_offered)
            return decision(data,'READ_ARTICLES',target)
        return decision(data,'FINISH')
    inv.request_decision=choose
    result=inv.run()
    assert len(calls)==3
    assert inv.p['no_progress_recovery']['selection_count']==2
    assert inv.p['no_progress_recovery']['status']=='COMPLETED'
    assert inv.p['original_progress']['revision']>=2
    assert result['next_action']=='DONE'
    assert inv.p['completion_basis_refs']
