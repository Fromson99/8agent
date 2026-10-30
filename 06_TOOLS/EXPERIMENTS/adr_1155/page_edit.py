from pathlib import Path
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_1155/focused-r1/snapshot/02_BACKEND/semantic_runtime/legal_agent';p=B/'read_candidate_pages.py';s=p.read_text();start=s.index('    rows = data.get(\'read_candidates\', [])');end=s.index('    moves = []',start)
s=s[:start]+'''    if type(page_size) is not int or page_size < 1:
        raise ContractError('candidate page size must be positive')
    rows = data.get('read_candidates', [])
    groups = {}
    for row in data.get('tool_options', []):
        groups.setdefault(row['choice'], []).append(row)
    count = max([1, (len(rows) + page_size - 1) // page_size] +
                [(len(items) + page_size - 1) // page_size for items in groups.values()])
    if type(page) is not int or not 0 <= page < count:
        raise ContractError('read candidate page is outside the bound menu')
    # Small tool families remain visible on every page; large families have
    # explicit continuation. No hidden target remains valid in the wire schema.
    shown_tools = [r for items in groups.values() for r in
                   (items if len(items) <= page_size else items[page*page_size:(page+1)*page_size])]
    view = {**data, 'read_candidates': rows[page * page_size:(page + 1) * page_size],
            'tool_options': shown_tools,
            'tool_candidate_page': {'families': {kind: {'total': len(items),
                'shown': sum(r['choice'] == kind for r in shown_tools)} for kind, items in groups.items()},
                'meaning': '읽기 후보와 도구 대상의 페이지; 작은 도구 목록은 매 페이지 유지'},
            'read_candidate_page': {'page': page + 1, 'pages': count, 'total': len(rows),
                                    'shown': min(page_size, max(0, len(rows) - page * page_size)),
                                    'more_available': page + 1 < count}}
    wire = deepcopy(schema)
    visible = [row['target'] for row in view['read_candidates']]
    branches = []
    for branch in wire['anyOf']:
        props = branch['properties']; kind = props['choice'].get('const')
        if kind == 'READ':
            if not visible:
                continue
            props['selections']['items']['properties']['target']['enum'] = visible
        elif 'target' in props and kind in groups:
            targets = [r['target'] for r in shown_tools if r['choice'] == kind]
            props['target']['enum'] = [t for t in props['target']['enum'] if t in targets]
            if not props['target']['enum']:
                continue
        branches.append(branch)
    wire['anyOf'] = branches
    # Scope detail is redundant with a hidden FOLLOW_CONNECTION menu. Preserve
    # exact details for offered scopes; other pages retain the full server data.
    choices = data.get('connection_scope_choices')
    if isinstance(choices, list):
        targets = {r['target'] for r in shown_tools}
        kept = [r for r in choices if r.get('action') in targets or r.get('target') in targets
                or r.get('follow_action') in targets]
        # Unknown legacy shape is kept rather than silently dropping context.
        if choices and all(any(k in r for k in ('action','target','follow_action')) for r in choices):
            view['connection_scope_choices'] = kept
            view['connection_scope_choices_on_other_pages'] = len(choices)-len(kept)
''' +s[end:];s=s.replace("VERSION = 'read-candidate-pages-v2'","VERSION = 'read-candidate-pages-v3'");s=s.replace("data['read_candidates'], schema, page_size]","data['read_candidates'], data.get('tool_options', []), schema, page_size]");p.write_text(s)
# Round-robin prior search and current connection rows, keeping both reachable.
p=B/'decision_projection.py';s=p.read_text();s=s.replace('    return list(rows.values())\n','''    prior = [r for r in rows.values() if r.get('origin') == 'PREVIOUS_SEARCH_UNREAD']
    current = [r for r in rows.values() if r.get('origin') != 'PREVIOUS_SEARCH_UNREAD']
    result = []
    for i in range(max(len(prior), len(current))):
        if i < len(prior): result.append(prior[i])
        if i < len(current): result.append(current[i])
    return result
''',1);p.write_text(s)
