from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
p=C/'02_BACKEND/semantic_runtime/legal_agent/evidence_inventory.py';t=p.read_text()
needle='\ndef check_presented_page(session, state, page):'
insert='''
def confirmed_pages(state):
    """Confirmed input and accepted decisions share a delivery ledger, not adoption."""
    pages = {}
    for page in state.get('delivery_history', {}).values():
        if page.get('delivery_contract') != DELIVERY or not page.get('spans'): continue
        prior = pages.get(page['id'])
        if prior and any(prior.get(k) != page.get(k) for k in ('branch_id','source_id','scope_id','spans')):
            raise ContractError('confirmed delivery identity changed')
        pages[page['id']] = page
    for page in state.get('basis_history', {}).values():
        if not page.get('accepted') or not page.get('spans'): continue
        prior = pages.get(page['id'])
        if prior and any(prior.get(k) != page.get(k) for k in ('branch_id','source_id','scope_id','spans')):
            raise ContractError('accepted and delivered source identity disagree')
        pages[page['id']] = page
    return pages

'''
assert needle in t;t=t.replace(needle,'\n'+insert+needle)
t=t.replace("saved=state.get('basis_history',{}).get(page['id'],{})","saved=confirmed_pages(state).get(page['id'],{})")
t=t.replace("if not saved.get('accepted') or any(saved.get(k)!=page.get(k) for k in fields):","if not saved or any(saved.get(k)!=page.get(k) for k in fields):")
t=t.replace("    for ref in dict.fromkeys(context_refs):\n        page=state['basis_history'].get(ref)\n        if not page or not page.get('accepted') or not page.get('spans'):","    confirmed=confirmed_pages(state)\n    for ref in dict.fromkeys(context_refs):\n        page=confirmed.get(ref)\n        if not page or not page.get('spans'):")
p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/decision_projection.py';t=p.read_text()
t=t.replace("    wanted=set(state.get('selected',{}))\n    return [ref for ref,b in state.get('basis_history',{}).items()\n        if b.get('branch_id') in wanted and b.get('accepted') and b.get('spans')", "    from .evidence_inventory import confirmed_pages\n    wanted=set(state.get('selected',{}))\n    return [ref for ref,b in confirmed_pages(state).items()\n        if b.get('branch_id') in wanted and b.get('spans')")
start=t.index('def bounded_original_refs(');end=t.index('\ndef shared_reference_decisions(',start)
segment=t[start:end].replace("    mandatory=list(dict.fromkeys(mandatory));available=requested_refs(state)","    from .evidence_inventory import confirmed_pages\n    pages=confirmed_pages(state)\n    mandatory=list(dict.fromkeys(mandatory));available=requested_refs(state)").replace("state['basis_history']","pages").replace("inv.p['basis_history'].items()","inventory.confirmed_pages(inv.p).items()")
t=t[:start]+segment+t[end:];p.write_text(t)
p=C/'05_TESTS/CONTRACTS/test_retained_partial_connections.py';t=p.read_text().replace("    scope=cs.candidates(inv,{'sources':[page]})[0][0]", "    from semantic_runtime.legal_agent import law_candidates\n    monkeypatch.setattr(law_candidates,'token',lambda *args:'follow')\n    scope=cs.candidates(inv,{'sources':[page]})[0][0]")
t+='''

def test_failed_choice_delivery_is_retained_on_the_next_view_without_adoption(session):
    from semantic_runtime.legal_agent import decision_projection as dp
    inv,data,page=adopted_and_delivered(session)
    next_view={'sources':[],'basis':[]}
    prior=deepcopy(inv.p['basis_history'])
    dp.retain_requested(inv,next_view)
    assert page['id'] in [p['id'] for p in next_view['sources']]
    assert inv.p['basis_history']==prior
    context=inventory.originals_for(inv.s,inv.p,context_refs=dp.requested_refs(inv.p))
    assert {p['block_id'] for p in page['spans']} <= {p['block_id'] for s in context for p in s['adopted_spans']}
''';p.write_text(t)
