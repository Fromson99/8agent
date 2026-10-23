from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
p=C/'02_BACKEND/semantic_runtime/legal_agent/decision_projection.py';t=p.read_text().replace("and state['groups'][b['branch_id']]['status'] != 'EXCLUDED']","and state['groups'][b['branch_id']]['status'] != 'EXCLUDED'\n        and (b.get('accepted') or state['groups'][b['branch_id']]['status'] != 'DEFERRED')]");p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/unit_relations.py';t=p.read_text();needle='def _navigate('
assert needle in t
pos=t.index(needle)
helper='''def fit_context(data, offered, limit):
    """Page a verified menu and whole originals; never truncate a source body."""
    data = deepcopy(data); offered = dict(offered)
    omitted = []
    def size(): return len(json.dumps(data, ensure_ascii=False))
    while size() > limit:
        anchors = {g['anchor']['source_id'] for g in offered.values()}
        removable = [s for s in data.get('sources', []) if s['source_id'] not in anchors]
        if removable:
            source = max(removable, key=lambda s: len(json.dumps(s, ensure_ascii=False)))
            data['sources'].remove(source); omitted.append(source['source_id'])
            data['original_context_omissions'] = {'source_ids': omitted,
                'reason': 'CONTEXT_LIMIT', 'still_acquired': True, 'source_absence_proven': False}
            continue
        if len(offered) <= 1: break
        label = next(reversed(offered)); del offered[label]
        data['groups'] = [r for r in data['groups'] if r['id'] != label]
        data['omitted_groups'] += 1
        data['all_group_summaries'] = [{'anchor_source_id':g['anchor']['source_id'],
            'target':g['target'], 'direction':g['direction'], 'connections':len(g['connections']),
            'read_options_presented':True} for g in offered.values()]
    return data, offered


'''
t=t[:pos]+helper+t[pos:]
needle="        hook=getattr(session,'investigation_menu_hook',None)\n        if hook:data=hook(data,offered)"
replacement="""        data, offered = fit_context(data, offered, max_context_chars)
        hook=getattr(session,'investigation_menu_hook',None)
        if hook:data=hook(data,offered)"""
assert needle in t;t=t.replace(needle,replacement);p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';t=p.read_text()
needle="        if selected:data={**data,'selected_connection_scope':deepcopy(selected['scope'])}\n        f=trail.capture"
replacement="""        if selected:data={**data,'selected_connection_scope':deepcopy(selected['scope'])}
        # Account for the request/scope wrapper before persisting the exact menu.
        data, bounded = rel.fit_context(data,offered,max(1,self.s.profile['max_context_chars']-2000))
        offered.clear();offered.update(bounded)
        f=trail.capture"""
assert needle in t;t=t.replace(needle,replacement)
needle="                self.s.repo.event('CONNECTION_SCOPE_RESULT',{'scope_id':scope_choice['scope']['id'],"
replacement="""                context_limit = next((x for x in nav['limits'] if x['kind'] in
                    ('reference_context_limit','reference_item_context_limit')),None)
                if context_limit:
                    self.p.setdefault('connection_context_blocks',{})[scope_choice['scope']['id']] = {
                        'acquired_signature':cs.acquired_signature(self), 'reason':context_limit['kind'],
                        'absence_proven':False, 'fallback':'SEARCH_STRUCTURE'}
                self.s.repo.event('CONNECTION_SCOPE_RESULT',{'scope_id':scope_choice['scope']['id'],"""
assert needle in t;t=t.replace(needle,replacement);p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/connection_scope.py';t=p.read_text()
needle="        if not inline and result['status'] != 'FAILED':\n            actions[target] = action"
replacement="""        blocked = inv.p.get('connection_context_blocks',{}).get(scope['id'])
        if blocked and blocked['acquired_signature'] != acquired_signature(inv):blocked=None
        if not inline and result['status'] != 'FAILED' and not blocked:
            actions[target] = action"""
assert needle in t;t=t.replace(needle,replacement).replace("if card.get('requires_scope_menu'):","if card.get('requires_scope_menu') and not blocked:")
t=t.replace("'connections_complete': inline,","'connections_complete': inline,\n                        'menu_unavailable': deepcopy(blocked),")
p.write_text(t)
p=C/'05_TESTS/CONTRACTS/test_retained_partial_connections.py';t=p.read_text();t+='''

def test_reference_menu_pages_whole_sources_and_keeps_anchor_bytes():
    from semantic_runtime.legal_agent import unit_relations as rel
    groups={str(i):{'anchor':{'source_id':'anchor'},'target':{'source_id':str(i)},'direction':'OUTGOING','connections':[]} for i in range(3)}
    data={'groups':[{'id':str(i),'text':'x'*400} for i in range(3)],'omitted_groups':0,
          'all_group_summaries':[], 'sources':[{'source_id':'anchor','text':'필수 원문'}, {'source_id':'other','text':'a'*6000}]}
    before=deepcopy(data)
    shown,offered=rel.fit_context(data,groups,1200)
    import json
    assert len(json.dumps(shown,ensure_ascii=False))<=1200
    assert shown['sources']==[data['sources'][0]] and shown['original_context_omissions']['still_acquired']
    assert shown['omitted_groups']==3-len(offered) and len(offered)>=1
    assert data==before and len(groups)==3


def test_oversized_anchor_is_never_silently_truncated():
    from semantic_runtime.legal_agent import unit_relations as rel
    g={'x':{'anchor':{'source_id':'anchor'},'target':{},'connections':[]}}
    d={'groups':[{'id':'x'}],'sources':[{'source_id':'anchor','text':'원문'*4000}], 'omitted_groups':0}
    shown,offered=rel.fit_context(d,g,1000)
    assert shown==d and offered==g
''';p.write_text(t)
