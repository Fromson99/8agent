from common import *
S=ROOT/read(DES/'candidate.json')['root']/'snapshot'
b=S/'02_BACKEND/semantic_runtime/legal_agent'
p=b/'source_goal_control.py';s=p.read_text();s=s.replace("'origin_gap_id':gap['gap_id'],'expected':deepcopy(binding.get('expected',[]))", "'origin_gap_id':gap['gap_id'],'expected':pair_expected(inv.s,binding,pair)")
s+='''

def pair_expected(session,binding,pair):
    from .unit_reading import blocks
    wanted=set(map(str,blocks(session,pair['document_id'],str(pair['unit_id']),'subtree')))
    return [deepcopy(x) for x in binding.get('expected',[]) if x['document_id']==pair['document_id'] and str(x['block_id']) in wanted]


def grant_required_targets(session,checkpoint,*,restore=False):
    """A verified reference endpoint may supply its required enclosing unit.

    This never adds a searchable document, crosses a canonical source, overrides
    explicit exclusions, or treats the model's locator as an ACL grant.
    """
    from . import query_scope as qs,request_repair as rr
    if not qs.active(session):return
    gaps=list(checkpoint.get('assessment_gaps',[]))
    if restore:
        gaps.extend(g for r in checkpoint.get('gap_rounds',[]) for g in r['gaps'])
    saved=checkpoint.get('scope_read_grants',{})
    for gap in gaps:
        binding=gap.get('target_binding',{})
        if not gap.get('material') or gap.get('kind')=='MISSING_FACT' or binding.get('status')!='EXACT':continue
        witness_hash=digest(gap)
        if restore and not any(w.get('kind')=='REQUIRED_CONNECTED_TARGET' and w.get('gap_hash')==witness_hash for rows in saved.values() for w in rows.values()):continue
        # Rebind against the request's current authorized generation and index.
        current=rr.bind_gap(gap,session)
        if current['target_binding_hash']!=gap['target_binding_hash'] or current['target_binding']!=binding:
            raise ContractError('required target binding changed')
        for pair in binding['pairs']:
            did=pair['document_id'];uid=pair['unit_id']
            if uid is None or qs.direct(session,did,uid):continue
            try:qs.check_selection_exclusions(session.matcher,[{'document_id':did,'unit_id':uid}],qs.active(session).get('selections',[]))
            except qs.UnresolvedScope:continue
            expected=pair_expected(session,binding,pair);ids={str(x['block_id']) for x in expected}
            sources=[sid for sid in binding['source_ids'] if session.tools.sources[sid]['document_id']==did and ids <= {str(b['block_id']) for b in session.tools.sources[sid]['blocks']}]
            if len(sources)!=1 or not ids:continue
            sid=sources[0];grants=session.scope_read_grants.get(sid,{})
            anchors={bid:w for bid,w in grants.items() if bid in ids and w.get('reference_id')}
            if not anchors:continue
            fresh=ids-qs.permitted_blocks(session,sid)
            if fresh:qs.grant(session,sid,fresh,witness={'kind':'REQUIRED_CONNECTED_TARGET','gap_hash':witness_hash,
                'gap_id':gap['gap_id'],'target_unit_id':uid,'binding_hash':gap['target_binding_hash'],
                'reference_ids':sorted({w['reference_id'] for w in anchors.values()})})
'''
p.write_text(s)
p=b/'request_repair.py';s=p.read_text().replace("    result = []\n    for gap in investigation.p.get('assessment_gaps', []):", "    if investigation.policy.get('source_goal_control'):\n        from .source_goal_control import grant_required_targets\n        grant_required_targets(investigation.s,investigation.p)\n    result = []\n    for gap in investigation.p.get('assessment_gaps', []):");p.write_text(s)
p=b/'query_scope.py';s=p.read_text().replace("    if any(not set(rows) <= permitted_blocks(session,sid) for sid,rows in saved.items()):", "    if any(w.get('kind')=='REQUIRED_CONNECTED_TARGET' for rows in saved.values() for w in rows.values()):\n        from .source_goal_control import grant_required_targets\n        grant_required_targets(session,checkpoint,restore=True)\n    if any(not set(rows) <= permitted_blocks(session,sid) for sid,rows in saved.items()):");p.write_text(s)
