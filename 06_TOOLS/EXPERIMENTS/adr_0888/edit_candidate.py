from pathlib import Path
R=Path(__file__).resolve().parents[3];p=R/'02_BACKEND/lawrag/research/candidates/adr_0888/historical/snapshot/02_BACKEND/semantic_runtime/legal_agent/evidence_inventory.py'
s=p.read_text();marker='\ndef reconcile_delivery(session, state, data, phase):';assert marker in s
helper='''\ndef check_presented_page(session, state, page):
    """Historical scope is valid only when identical to an accepted delivery."""
    record=state['selected'].get(page['branch_id'])
    if not record:
        check_page(session,state,page)
        return
    current=digest(record['offer'])
    if page.get('scope_id',current)==current:
        check_page(session,state,page)
        return
    saved=state.get('basis_history',{}).get(page['id'],{})
    fields=('id','branch_id','source_id','page','total_pages','scope_id','spans')
    if not saved.get('accepted') or any(saved.get(k)!=page.get(k) for k in fields):
        raise ContractError('historical presentation lacks identical accepted delivery')
    # Do not trust a client historical flag. Receipt equality permits the old
    # scope; current ACL, source identity and original bytes must still match.
    check_page(session,state,page,current_scope=False)

'''
s=s.replace(marker,'\n'+helper+marker)
s=s.replace("for page in data['sources']: check_page(session, state, page)","for page in data['sources']: check_presented_page(session, state, page)")
s=s.replace('def acknowledge(session, state, page, presentation_id):\n    check_page(session, state, page)','def acknowledge(session, state, page, presentation_id):\n    check_presented_page(session, state, page)')
p.write_text(s)
