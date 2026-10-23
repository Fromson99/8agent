"""Surgical proposal edits; no production imports or writes."""
from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
def edit(name, old, new):
    p=C/'02_BACKEND'/name;t=p.read_text();assert old in t,(name,old[:100]);p.write_text(t.replace(old,new))
LA='semantic_runtime/legal_agent/'

# One entry decision supplies both the scope command and legacy search hint IDs.
edit(LA+'request_entry.py',"question_span, title_matches와 실제 title을 비교해 문맥에 맞는 후보만 search.title_hint_ids로 선택한다. 없거나 틀리면 빈 배열로 둔다.",
"question_span, title_matches와 실제 title을 비교한다. 법령 선택과 범위 설정은 search.scope_decision 하나로만 판단한다. title_hint_ids나 command.search_scope_change를 따로 출력하지 않는다.")
edit(LA+'request_entry.py','이 후보 외 문서도 조사할 수 있다.',
'''사용자가 검색 대상으로 지정한 법령/내규는 scope_decision.mode=NAMED_SCOPE, targets에 넣는다. 법령 전체면 structure=null, selection=null이다. 배경에 언급한 법령을 무조건 범위로 삼지 않는다.
최초 질문에 검색 대상 법령을 주지 않았을 때만 AUTHORIZED_SCOPE, targets=[], user_quote=""로 둔다. 두 모드 모두 reason에 사용자 요청에서 판단한 범위를 설명한다.
예: "상법에서 의결 요건을 설명해"는 상법을 NAMED_SCOPE로 지정한다. "어제 상법 교육을 받았는데 오늘은 계약 해지의 일반 기준이 궁금해"는 상법이 배경인지 판단한다.
구조 검색과 본문 검색은 이 동일한 범위를 사용한다. 법령 제목 후보를 택하고 범위를 비워두는 별도 선택은 없다.''')
edit(LA+'request_entry.py',"    return object_schema({'routing':case_routing_schema(),", "    result = object_schema({'routing':case_routing_schema(),")
needle="            'reason':{'type':'string','minLength':1}}),{'type':'null'}]}})"
edit(LA+'request_entry.py',needle,needle+'''
    if model:
        command['properties'].pop('search_scope_change')
        command['required'].remove('search_scope_change')
        search = result['properties']['search']['anyOf'][0]
        search['properties'].pop('title_hint_ids')
        search['required'].remove('title_hint_ids')
        search['properties']['scope_decision'] = object_schema({
            'mode': {'enum': ['NAMED_SCOPE', 'AUTHORIZED_SCOPE']},
            'targets': deepcopy(command_scope_targets()),
            'user_quote': {'type': 'string'},
            'reason': {'type': 'string', 'minLength': 1}})
        search['required'].append('scope_decision')
    return result


def command_scope_targets():
    from .query_scope import model_change_schema
    return model_change_schema()['properties']['targets']


def decode_scope(value, hints):
    """Mechanical projection of the sole model decision, never title inference."""
    out = deepcopy(value)
    search = out.get('search')
    if search is None:
        return out
    choice = search.pop('scope_decision')
    named = choice['mode'] == 'NAMED_SCOPE'
    if named != bool(choice['targets']):
        raise MemoryError('NAMED_SCOPE requires targets; AUTHORIZED_SCOPE must have no targets')
    if not named and choice['user_quote']:
        raise MemoryError('AUTHORIZED_SCOPE must have an empty scope quote')
    if not choice['reason'].strip():
        raise MemoryError('scope decision requires its request-specific reason')
    if out.get('command') is None or out['command']['method_id'] != 'CASE_START':
        raise MemoryError('scope decision requires a new case')
    out['command']['search_scope_change'] = {
        'operation': 'REPLACE' if named else 'KEEP',
        'targets': deepcopy(choice['targets']), 'user_quote': choice['user_quote']}
    from ..navigation_match import norm
    names = {norm(t['document']) for t in choice['targets'] if t['document']}
    search['title_hint_ids'] = [h['hint_id'] for h in hints['candidates']
        if norm(h['title']) in names or norm(h.get('matched_label') or '') in names][:3]
    return out
''')
edit(LA+'request_entry.py',"        value=deepcopy(raw);history_ids=value.pop('history_ids',[])\n        try:routing,command,intent=accept(repo,context,value,scoped=scoped,admit=False)",
"        value=deepcopy(raw);history_ids=value.pop('history_ids',[])\n        try:\n            if not from_host:value=decode_scope(value,repo._entry_title_hints)\n            routing,command,intent=accept(repo,context,value,scoped=scoped,admit=False)")
edit(LA+'request_entry.py',"prepared.update(value=value,history_ids=history_ids,routing=routing,command=command,intent=intent)",
"prepared.update(value=value,history_ids=history_ids,routing=routing,command=command,intent=intent,\n            scope_decision=deepcopy((raw.get('search') or {}).get('scope_decision')))")
edit(LA+'request_entry.py',"entry={'contract':POLICY,'request_hash'", "entry={'scope_decision':prepared.get('scope_decision'),'contract':POLICY,'request_hash'")

# Rank titles rather than deciding legal relevance by lexical overlap thresholds.
edit(LA+'structure_query.py',"if len(hit['key']) < 4 or any(","if any(")
edit(LA+'structure_query.py',"    if not matches or any(len(keys) != 1 for keys in matches.values()):", "    ambiguous = [label for label, keys in matches.items() if len(keys) != 1]\n    matches = {label: keys for label, keys in matches.items() if len(keys) == 1}\n    if not matches:")
edit(LA+'structure_query.py',"'reason': 'EXACT_DOCUMENT_HEADING'}", "'reason': 'EXACT_DOCUMENT_HEADING', 'ambiguous_headings': ambiguous}")
edit(LA+'structure_query.py',"        if len(matched) >= 2 and len(matched) * 3 >= len(title_terms) * 2:\n            found[key] = (len(matched), len(matched) / len(title_terms))", "        found[key] = (len(matched), len(matched) / max(1, len(title_terms)))")
edit(LA+'law_title_hints.py','def hints(question, matcher, scope, *, limit=6):','def hints(question, matcher, scope, *, limit=None):')
edit(LA+'law_title_hints.py',"'omitted_candidates': max(0, len(ranked)-limit)","'omitted_candidates': max(0, len(ranked)-limit) if limit is not None else 0")
edit(LA+'law_title_hints.py','if fragments and matched >= 3:', 'if fragments:')
edit(LA+'law_title_hints.py',"if len(short) < 4 or not title.startswith(short[0]) or not title.endswith('법'):","if len(short) < 3 or not title.endswith('법'):")

# Nested lexical terms remain candidates. Document routing retains longest names.
edit('semantic_runtime/navigation_match.py','    def match(self, text):\n        """Longest match, left to right, no overlap, anchored at word starts."""',
'''    def match(self, text, *, include_nested=False):
        """Word-boundary matches; optionally retain all nested lexical clues."""''')
edit('semantic_runtime/navigation_match.py','                hit = (key, end)\n                break',
'''                if include_nested:
                    start_raw, end_raw = offsets[i], offsets[end-1]+1
                    result.append({'key': key, 'start': start_raw, 'end': end_raw,
                                   'text': text[start_raw:end_raw], 'values': self.values[key]})
                    continue
                hit = (key, end)
                break''')
edit('semantic_runtime/navigation_match.py',"getattr(self, 'short', set()).__contains__)]", "getattr(self, 'short', set()).__contains__, include_nested=True)]")
edit('semantic_runtime/term_morph.py','def longest(text, has_key, key_of, short=None):','def longest(text, has_key, key_of, short=None, *, include_nested=False):')
edit('semantic_runtime/term_morph.py','                        hit = (j, start, end, key)\n                        break',
'''                        if include_nested:
                            row = (start, end, key)
                            if row not in found: found.append(row)
                            continue
                        hit = (j, start, end, key)
                        break''')
edit(LA+'law_title_hints.py','for hit in index.match(question):','for hit in index.match(question, include_nested=True):')
edit(LA+'structure_query.py','matcher.structures.match(question)','matcher.structures.match(question, include_nested=True)')
edit(LA+'structure_query.py','matcher.structures.match(query)','matcher.structures.match(query, include_nested=True)')
edit('semantic_runtime/fulltext.py','return list(dict.fromkeys(forms(tokens)))[:MAX_TERMS]','return list(dict.fromkeys(forms(tokens)))')
edit('semantic_runtime/fulltext.py',"    return ' OR '.join('\"'+t.replace('\"', '')+'\"' for t in terms)",
'''    chunks = [' OR '.join('"'+t.replace('"', '')+'"' for t in terms[i:i+MAX_TERMS])
              for i in range(0, len(terms), MAX_TERMS)]
    return ' OR '.join('('+chunk+')' for chunk in chunks) if len(chunks)>1 else (chunks[0] if chunks else '')''')

# Full document body search stays inside explicit user scope, independent of cursor.
edit(LA+'law_navigation.py',"                law['body_search_action']=offer('SEARCH_BODY',location,law['name']+' 현재 구조 범위 안에서 본문 표현 검색')", "                law['body_search_action']=offer('SEARCH_BODY',location,law['name']+' 현재 구조 범위 안에서 본문 표현 검색')\n                law['document_body_search_action']=offer('SEARCH_BODY',{'document_id':did,'unit_id':None},\n                    law['name']+'의 사용자 지정 범위 전체에서 본문 표현 검색')")

# Semantic assessments remain model proposals; deterministic provenance is retained.
edit(LA+'completion_execution.py',"    row['properties'].pop('reason');row['required'].remove('reason')", "    # Retain the model's issue-specific sufficiency reason.")
old='''        for row in value['issue_assessments']:
            claims=sum(row['issue_id'] in c['issue_refs'] for c in value['claims'])
            gaps=sum(g['issue_id']==row['issue_id'] for g in value['gaps'])
            row['reason']=f"판단 상태 {row['status']}; 근거 주장 {claims}개, 미확인 {gaps}개."
'''
edit(LA+'completion_execution.py',old,'')
edit(LA+'completion_execution.py',"        defer_to_user = modern and answer_first(self.s.sources.profile) and bool(result['claims'])", "        defer_to_user = False  # Materiality is the model's assessment; a claim is not completion.")
edit(LA+'completion_v6.py',"    for gap in out['gaps']:\n        if gap['kind']!='UNRESOLVED_REFERENCE':gap['material']=True\n", "    # Preserve submitted materiality; missing-source type is not importance.\n")
edit(LA+'completion_v6.py',"model={'disposition':value['disposition'],'issue_assessments':deepcopy(value['issue_assessments'])}", "model={'disposition':value['disposition'],'issue_assessments':deepcopy(value['issue_assessments']),\n        'gaps':deepcopy(value['gaps'])}")
edit(LA+'completion_v8.py',"            if key in seen:\n                raise ProposalError('Repeated source clause, effect and context: merge identical facts and issue_refs')\n            seen.add(key)", "            # Reusing a verified norm across issues is not a source/meaning error.\n            seen.add(key)")
edit(LA+'completion_v8.py','요청한 범위의 실제 부족은 material=true로 보존하고 적절한 원문 탐색 행동을 고른다.', '요청한 답변에 필요한 핵심 부족은 material=true로 보존하고 적절한 원문 탐색 행동을 고른다. 답변을 막지 않는 미확인을 함께 설명할 필요가 있으면 material=false와 구체 이유를 기록한다. 중요도는 원문과 요청을 보고 판단하며 종류만으로 결정하지 않는다.')
edit(LA+'completion_execution.py','질문과 무관한 미해결 참조만 material=false로 둘 수 있다.', '답변을 막지 않는 미확인은 material=false와 구체 이유를 기록할 수 있다. 중요도는 질문과 원문으로 판단한다.')
edit(LA+'relation_read_policy.py',"'obligation': RULES[kind][direction == 'INCOMING'],", "'obligation': 'OPTIONAL',\n            'lexical_reading_hint': RULES[kind][direction == 'INCOMING'],\n            'necessity_judgment': 'MODEL',")
edit(LA+'relation_read_policy.py','CHECK_APPLICABILITY를 SKIP하려면 applicability=DOES_NOT_APPLY와 구체적 사유를 기록한다.\n적용 여부가 불명확하면 DEFER 또는 FOLLOW다. REQUIRED도 문언상 읽기 단서이며 질문에 대한 적용 결론은 아니다. 질문과 무관하다고 판단하면 DOES_NOT_APPLY와 구체적 사유를 기록하여 SKIP할 수 있다. 필요한 준용·정의의 범위를 임의로 줄이지 않는다.',
'''lexical_reading_hint는 문언 단서이며 읽기 의무나 적용 결론이 아니다. 필요한 조사인지 원문·질문으로 판단한다.
적용 여부가 불명확하더라도 현재 답변에 필요 없다고 판단하면 SKIP과 구체 사유를 기록할 수 있다. 미확인을 법률상 적용 불가로 바꾸지 않는다. 필요한 준용·정의 범위는 FOLLOW로 읽는다.''')
start="        if decision['action'] == 'SKIP':\n"
p=C/'02_BACKEND'/LA/'relation_read_policy.py';t=p.read_text();a=t.index(start);b=t.index("        if decision['action'] == 'FOLLOW':",a);t=t[:a]+t[b:];p.write_text(t)

# Recovery queues every failed query independently; no successful sibling suppresses it.
edit(LA+'law_name_recovery.py','def candidates(matcher, scope, name, limit=8):','def candidates(matcher, scope, name, limit=None):')
edit(LA+'law_name_recovery.py','def attach(page, matcher, scope):','def _attach_one(page, matcher, scope):')
edit(LA+'law_name_recovery.py',"    if any(r.get('status') == 'MATCH' for r in page.get('resolutions', [])):\n        return page\n",'')
insert='''def attach(page, matcher, scope):
    """Keep a recovery for each failed request, alongside successful siblings."""
    if page.get('offset') or page.get('name_retry'):
        return page
    recoveries = []
    queries = list(page.get('queries') or [])
    attempts = [page] if page.get('structure_filter') or len(queries)<=1 else [
        {**page, 'queries':[q], 'failure':None,
         'resolutions':[r for r in page.get('resolutions',[]) if r.get('query')==q]}
        for q in queries]
    for attempt in attempts:
        result = _attach_one(attempt, matcher, scope).get('law_name_recovery')
        if result and result['recovery_id'] not in {r['recovery_id'] for r in recoveries}:
            recoveries.append(result)
    if not recoveries:
        return page
    return {**page, 'law_name_recovery':recoveries[0], 'law_name_recoveries':recoveries}


'''
edit(LA+'law_name_recovery.py','def retry_key(recovery, did):',insert+'def retry_key(recovery, did):')
edit(LA+'law_name_recovery.py',"    recovery = inv.p['structure_page'].get('law_name_recovery')", "    page = inv.p['structure_page']\n    records = page.get('law_name_recoveries') or [page.get('law_name_recovery')]\n    recovery = next((r for r in records if r and r['recovery_id']==identity['recovery_id']),None)")
edit(LA+'law_navigation.py',"        name_recovery = deepcopy(structure_page.get('law_name_recovery'))\n        if name_recovery:\n", "        name_recoveries = deepcopy(structure_page.get('law_name_recoveries') or\n            ([structure_page['law_name_recovery']] if structure_page.get('law_name_recovery') else []))\n        for name_recovery in name_recoveries:\n")
edit(LA+'law_navigation.py',"            'law_name_recovery': name_recovery,", "            'law_name_recovery': name_recoveries[0] if name_recoveries else None,\n            'law_name_recoveries': name_recoveries,")
edit(LA+'decision_projection.py',"        'law_name_recovery':deepcopy(data.get('law_name_recovery')),", "        'law_name_recovery':deepcopy(data.get('law_name_recovery')),\n        'law_name_recoveries':deepcopy(data.get('law_name_recoveries',[])),")

print('Proposed scope, search and assessment changes written only in snapshot')
