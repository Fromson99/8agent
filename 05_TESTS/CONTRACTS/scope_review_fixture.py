"""Explicit synthetic model proposals, never used by product code."""
def scope_rows(value,ctx,review):
    if ctx.get("need_continuity",{}).get("version") != "declared-need-continuity-v2": return
    rows=[]
    for target in ctx['need_continuity']['targets']:
        groups=[]
        for ref in target['available_evidence_refs']:
            claims=[c for c in value['claims'] if ref in c['evidence_refs']]
            groups.append({'basis_refs':[ref],'disposition':'USE' if claims else 'EXCLUDE',
                'claim_refs':[c['claim_id'] for c in claims],'issue_refs':sorted({i for c in claims for i in c['issue_refs']}) or target['issue_refs'],
                'gap_indices':[],'scope_quote':'','reason':'해당 원문을 실제 주장에 사용' if claims else '질문이 요청한 적용 기준과 별도인 범위로 검토하여 제외'})
        rows.append({'target_id':target['id'],'groups':groups})
    review['scope_reviews']=rows
    targets={r['target_id']:r for r in rows}
    for row,need in zip(review['needs'],ctx['needs']):
        if need.get('origin') in ('SOURCE_GOAL','STRUCTURE_SELECTION') and row['status']=='RESOLVED':
            row['claim_refs']=sorted({c for tid in need.get('target_refs',[]) for g in targets[tid]['groups'] for c in g['claim_refs']})
