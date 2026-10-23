from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
p=C/'02_BACKEND/semantic_runtime/legal_agent/connection_scope.py';t=p.read_text()
t=t.replace("        if inline:\n            shown = inline_cards(inv, scope, refs, result['groups'], actions)","""        # A partial catalog still contains verified links. Keep a bounded page
        # visible and retain FOLLOW_CONNECTION for the remaining frontier.
        visible = []; remaining = INLINE_CONNECTION_LIMIT
        for group in result['groups'] if result['status'] != 'FAILED' else []:
            connections = group['connections'][:remaining]
            if connections:
                visible.append({**group, 'connections': connections})
                remaining -= len(connections)
            if not remaining:
                break
        if visible:
            shown = inline_cards(inv, scope, refs, visible, actions)""")
t=t.replace("'connections_presented_inline': inline})", "'connections_presented_inline': bool(visible),\n                        'connections_complete': inline,\n                        'connections_presented_count': sum(len(g['connections']) for g in visible)})")
t=t.replace("    references['omitted_dependency_cards'] = sum(\n        p['connection_count'] or 0 for p in previews.values()\n        if p['status']!='COMPLETE' or (p['connection_count'] or 0)>INLINE_CONNECTION_LIMIT)","    references['omitted_dependency_cards'] = sum(max(0, (p['connection_count'] or 0) - INLINE_CONNECTION_LIMIT)\n        for p in previews.values())")
t=t.replace("'연결이 5개 이하인 정확한 원문 범위는 dependency_cards에 바로 제시했다. '","'각 원문 범위에서 확인한 연결을 최대 5개씩 dependency_cards에 바로 제시했다. '")
t=t.replace("'더 많은 연결은 해당 범위의 연결 메뉴로 확인한다.'","'일부만 제시된 범위는 연결 메뉴에서 나머지를 확인할 수 있다. 제시된 대상은 바로 READ할 수 있다.'")
t=t.replace("'읽은 원문 중 현재 요청에 쓸 범위를 판단한다. 연결이 5개 이하이면 '","'읽은 원문 중 현재 요청에 쓸 범위를 판단한다. 목록이 일부여도 '")
p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/evidence_inventory.py';t=p.read_text().replace('explicit_sources=set(sources)','explicit_sources=set(gathered)')
needle='\ndef acquired_originals_for(session, state, limit, *, include_deferred=True):'
insert='''
def merge_delivered_originals(session, state, originals, limit):
    """Merge confirmed delivery into assessment context, without adopting it.

    Mandatory originals survive the limit. Additional source bundles are kept
    whole; omission is explicit and never reclassified as unread or absent.
    """
    current = {o['source_id']: deepcopy(o) for o in originals}
    used = sum(sum(hi-lo for ranges in intervals(o['adopted_spans']).values()
                   for lo,hi in ranges) for o in current.values())
    omitted = []; added = []
    for extra in reversed(delivered_originals_for(session, state)):
        sid = extra['source_id']; previous = current.get(sid)
        spans = (previous['adopted_spans'] if previous else []) + extra['adopted_spans']
        unique = list({digest(p): p for p in spans}.values())
        size = sum(hi-lo for ranges in intervals(unique).values() for lo,hi in ranges)
        old_size = sum(hi-lo for ranges in intervals(previous['adopted_spans']).values()
                       for lo,hi in ranges) if previous else 0
        if used + size - old_size > limit:
            omitted.append(sid)
            continue
        record = next(r for r in state['selected'].values() if r['source_id'] == sid)
        merged = _pack(session, state, {sid:record}, {sid:unique})[0]
        merged['delivered_context_only'] = previous.get('delivered_context_only', False) if previous else True
        current[sid] = merged; used += size-old_size
        if size > old_size: added.append(sid)
    return list(current.values()), {'confirmed_delivery_merged': added,
        'omitted_delivered_source_ids': omitted, 'character_limit': limit,
        'omission_reason': 'CONTEXT_LIMIT' if omitted else None,
        'automatic_adoption': False, 'source_absence_proven': False}

'''
assert needle in t;t=t.replace(needle,'\n'+insert+needle);p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';t=p.read_text()
needle="            if self.modern and current and sufficient:\n"
insert="""            if self.modern and sufficient and self.p.get('delivery_handoff'):
                current, delivery_merge = inventory.merge_delivered_originals(self.s,self.p,current,limit)
                result['original_delivery_context'] = {**result.get('original_delivery_context',{}), **delivery_merge}
                if self.p.get('adoption_fallback'):
                    result['adoption_fallback'] = deepcopy(self.p['adoption_fallback'])
"""
assert needle in t;t=t.replace(needle,insert+needle)
# All bounded exits use the same handoff consumer, not just the special progress exit.
needle="        self.p['stop_reason']=reason\n        current=inventory.originals_for(self.s,self.p)"
assert needle in t;t=t.replace(needle,"        self.p['stop_reason']=reason\n        if self.modern:self.p['delivery_handoff']=True\n        current=inventory.originals_for(self.s,self.p)")
# Do not restore an obsolete delivery ledger on accepted-action replay.
t=t.replace("'basis_history','material_history','window','window_groups','focus',", "'basis_history','delivery_history','answer_progress_reviews','material_history','window','window_groups','focus',")
p.write_text(t)
