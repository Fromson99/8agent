"""Plain text projections for request .log files; journals keep complete JSON."""


PHASES = {
    'investigate': '근거 탐색', 'select_sources': '근거 선별',
    'compose': '답변 작성', 'review': '답변 검토', 'rebut': '반론 검토',
    'source-query-plan': '검색 계획', 'source-triage': '읽을 조문 선별',
    'source-omission-review': '누락 근거 확인', 'bounded-question-plan': '질문 요구 정리',
}
DECISIONS = {
    'CONTINUE': '추가 탐색', 'DRAFT': '답변 작성', 'CLARIFY': '추가 사실 확인',
    'KEEP_CORE': '핵심 근거 채택', 'KEEP_SUPPLEMENTAL': '보완 근거 채택',
    'DEFER': '판단 보류', 'REJECT': '근거 제외', 'SUPPORTED': '원문 부합',
    'NEEDS_RESEARCH': '추가 근거 필요', 'NEEDS_REWRITE': '수정 필요',
    'ANSWERED': '답변 요구 충족', 'CONDITIONAL': '조건부 답변',
    'MISSING_FACT': '사실 확인 필요', 'RESOLVED': '검토 완료', 'PARTIAL': '일부 미확인',
    'NOT_RELEVANT': '관련성 없음', 'RELEVANT': '관련성 있음',
    'ADOPT': '근거 채택', 'UNCERTAIN': '판단 미확인',
}
TOOLS = {'search': '검색', 'read': '원문 읽기', 'browse': '목차 확인',
         'follow_reference': '참조 확인', 'follow_relations': '연결 근거 확인',
         'inspect_relation': '연결 상세 확인', 'view_page': '다음 목록 확인'}


def compact(value, limit=180):
    """Flatten control characters so model text cannot forge extra log lines."""
    text = ' '.join(''.join(ch if ch.isprintable() else ' ' for ch in str(value or '')).split())
    return text if len(text) <= limit else text[:limit-1] + '…'


def objects(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def decision_rows(value, view):
    """Use explicit fields only; never dump prompts, original text or arbitrary JSON."""
    labels = {'sources': {}, 'claims': {}, 'targets': {}}
    for key in ('exact_evidence', 'evidence', 'claims', 'current_claims'):
        kind = 'claims' if 'claim' in key else 'sources'
        for i, row in enumerate(objects(view.get(key)), 1):
            ident = row.get('evidence') or row.get('evidence_id') or row.get('claim') or row.get('entity_id')
            metadata = row.get('metadata') or {}
            if not isinstance(metadata, dict): metadata = {}
            parts = [row.get('document_name') or metadata.get('document_name'),
                     row.get('heading') or metadata.get('heading')]
            if isinstance(ident, (str, int)):
                labels[kind][ident] = ' '.join(str(part) for part in parts if part) or ('주장' if kind == 'claims' else '근거') + f' {i}'
    for key in ('candidates', 'deferred_candidates'):
        inventory = view.get(key) or {}
        if isinstance(inventory, dict):
            laws = inventory.get('laws') or {}
            for row in inventory.get('rows', []):
                if isinstance(row, list) and len(row) >= 3:
                    labels['sources'][row[0]] = compact(f'{laws.get(row[1], "")} {row[2]}')
        else:
            for row in objects(inventory):
                labels['sources'][row.get('id')] = compact(f'{row.get("law", "")} {row.get("article", "")}')

    for result in objects(view.get('last_action_results')):
        for row in objects(result.get('items')):
            target = row.get('target')
            if isinstance(target, (str, int)):
                labels['targets'][target] = ' '.join(compact(row.get(key)) for key in
                    ('document_name', 'name', 'heading', 'title', 'label') if row.get(key)) or '제시된 위치'

    def found(refs, kind='sources'):
        if not isinstance(refs, list): refs = [refs]
        names = list(dict.fromkeys(labels[kind].get(ref, '제시된 근거' if kind == 'sources' else '제시된 주장' if kind == 'claims' else '제시된 위치')
                                  for ref in refs if isinstance(ref, (str, int))))
        return ' / '.join(names[:3]) + (f' 외 {len(names)-3}건' if len(names) > 3 else '')

    rows = []
    def add(judgment, finding='', reason=''):
        rows.append({'judgment': compact(judgment, 60), 'finding': compact(finding),
                     'reason': compact(reason or '모델이 별도 이유를 제공하지 않음')})

    if not isinstance(value, dict): return rows
    for plan in objects(value.get('plans')):
        add('검색 계획', ' / '.join(plan.get('law_names', [])),
            '검색어: ' + ' / '.join(plan.get('queries', [])))
    plan = value.get('question_plan') or (value if 'demands' in value else {})
    if isinstance(plan, dict):
        for demand in objects(plan.get('demands')):
            add('답변 요구 정리', demand.get('requirement'), demand.get('missing_fact') or plan.get('change_reason'))
    if value.get('intent'):
        add(DECISIONS.get(value['intent'], value['intent']), found([e.get('evidence') for e in objects(view.get('exact_evidence'))]), value.get('reason'))
    for action in objects(value.get('actions')):
        args = action.get('args') or {}
        if not isinstance(args, dict): args = {}
        add(TOOLS.get(str(action.get('tool', '')).lower(), '추가 확인'), args.get('query') or found(args.get('target'), 'targets'), action.get('reason'))
    selections = [value]
    if isinstance(value.get('source_selection'), dict): selections.append(value['source_selection'])
    for selection in selections:
        for choice in objects(selection.get('choices')):
            add(DECISIONS.get(choice.get('decision'), '읽을 근거 선택'),
                found(choice.get('source') or choice.get('id')), choice.get('reason'))
        for item in objects(selection.get('selections')):
            add('핵심 근거 채택' if item.get('tier') == 'CORE' else '보완 근거 채택',
                found(item.get('evidence_id')), item.get('relevance_reason'))
    for item in objects(value.get('assessments')):
        add(DECISIONS.get(item.get('disposition'), item.get('disposition') or '근거 평가'),
            found(item.get('evidence')), item.get('reason'))
    for item in objects(value.get('checks')):
        add(DECISIONS.get(item.get('verdict'), item.get('verdict') or '주장 검토'),
            found(item.get('evidence')) if item.get('evidence') else found(item.get('claim'), 'claims'), item.get('reason'))
    for item in objects(value.get('obligation_checks')):
        add(DECISIONS.get(item.get('status'), item.get('status') or '요구 검토'),
            found(item.get('claims'), 'claims'), item.get('reason'))
    for item in objects(value.get('paragraphs')):
        add('답변 초안 작성', item.get('text'),
            '근거: ' + found(item.get('evidence') or item.get('evidence_ids')))
    question = value.get('question') or {}
    if isinstance(question, dict) and question.get('status'):
        add(DECISIONS.get(question['status'], question['status']), '질문 전체', question.get('reason'))
    if not rows: add('판단 결과 수신', '표시할 선택 항목 없음', value.get('reason'))
    return rows


def render_rows(rows):
    lines = [f'판단: {row["judgment"]} → 찾은 것: {row["finding"] or "표시 항목 없음"} → 이유: {row["reason"]}'
             for row in rows[:6]]
    if len(rows) > 6:
        lines.append(f'외 {len(rows)-6}건 · 전체 내용은 요청 JSON 보고서와 journal에 보존')
    return '\n'.join(lines)


def render_detail(label, value):
    """Return plain agent/tool text, or None for unaffected report sections."""
    if not (label.startswith('AGENT ') or label in {
            'MODEL CALL', 'MODEL RESPONSE / LLM ANSWER', 'QUESTION PLAN',
            'WORKFLOW REPAIR', 'SEMANTIC REPAIR', 'TOOL RESULT'}):
        return None
    data = value if isinstance(value, dict) else {}
    if label == 'MODEL CALL':
        return f'단계: {PHASES.get(data.get("phase"), compact(data.get("phase")))} · LLM 호출 {data.get("attempt", "")} · 시작'
    if label == 'MODEL RESPONSE / LLM ANSWER':
        phase = data.get('source_stage') or data.get('phase')
        heading = f'단계: {PHASES.get(phase, compact(phase))} · 응답 상태: {compact(data.get("status"))}'
        reply = data.get('reply')
        if not isinstance(reply, dict):
            return heading + '\n판단: 구조화된 판단 없음 → 찾은 것: 표시 항목 없음 → 이유: ' + compact(reply)
        return heading + '\n' + render_rows(decision_rows(reply, data.get('view') or {}))
    if label == 'QUESTION PLAN':
        return render_rows(decision_rows(data.get('plan') or data, {}))
    if label == 'AGENT DECISION' or isinstance(data.get('decision'), dict):
        return render_rows(decision_rows(data.get('decision') or data, {}))
    if isinstance(data.get('review'), dict):
        return render_rows(decision_rows(data['review'], {}))
    if label == 'TOOL RESULT':
        examples = [' '.join(compact(row.get(key)) for key in ('name', 'title', 'heading', 'label') if row.get(key))
                    if isinstance(row, dict) else compact(row) for row in data.get('examples', [])]
        names = ' / '.join(name for name in examples if name)
        count = data.get('returned_count', data.get('count', data.get('total')))
        finding = (f'{count}건' if count is not None else '결과 수 미기록') + (' · ' + names if names else '')
        reason = data.get('server_reason') or data.get('reason') or data.get('message')
        query = (data.get('input') or {}).get('query')
        if not reason: reason = '검색어: ' + compact(query) if query else '별도 이유 없음'
        return f'판단: {TOOLS.get(str(data.get("tool", "")).lower(), "도구 실행")} · 상태 {compact(data.get("status"))} → 찾은 것: {finding} → 이유: {compact(reason)}'
    # Less common audit/control events keep their status and reason as plain fields.
    details = []
    for key, item in data.items():
        if key.endswith(('_id', '_ids', '_hash', '_sha256')) or key in {'id', 'hash', 'seq', 'number_to_id'}:
            continue
        if isinstance(item, (str, int, float, bool)) and item is not None:
            details.append(f'{key}: {compact(item)}')
        elif isinstance(item, list):
            details.append(f'{key}: {len(item)}건')
            for row in objects(item)[:3]:
                reason = row.get('reason') or row.get('message') or row.get('issue')
                if reason: details.append('  이유: ' + compact(reason))
    return '\n'.join(details) or '처리 기록 저장 · 상세 내용은 요청 JSON 보고서와 journal에 보존'
