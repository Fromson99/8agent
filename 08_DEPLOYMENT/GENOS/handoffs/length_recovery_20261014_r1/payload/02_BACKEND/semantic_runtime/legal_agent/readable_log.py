"""Plain text projections for request .log files; journals keep complete JSON."""
import json


ERROR_EVENTS = frozenset({'LAW_DECISION_REJECTED', 'LAW_DECISION_RETRY',
    'OUTPUT_SCHEMA_INVALID',
    'LAW_DECISION_PATCH_PROPOSED', 'COMPLETION_ASSESSMENT_REJECTED',
    'WORKFLOW_REPAIR', 'SEMANTIC_REPAIR', 'INVESTIGATION_BOUNDED_STOP'})


def is_error_event(kind):
    return kind in ERROR_EVENTS or kind.endswith(('_FAILED', '_REJECTED'))


DIAGNOSTIC_EVENTS = frozenset({'REFERENCE_NAVIGATION_STATUS', 'REFERENCE_NAVIGATION_FAILED', 'SOURCE_INVESTIGATION_INCOMPLETE',
    'UNIT_CANDIDATE_ACQUISITION_STOPPED', 'RUN_FAILED', 'UNASSESSED_AT_STOP', 'REFERENCE_GROUP_DECISION'}) | ERROR_EVENTS
CATEGORIES = {'DATA_REFERENCE':'데이터 참조 해석', 'MODEL_DECISION':'모델 결정',
    'UNPROCESSED_WORK':'미처리 작업', 'EXECUTION_LIMIT':'실행 한도',
    'SOURCE_SELECTION':'근거 선별', 'DIAGNOSTIC_GAP':'상세 사유 미기록','EXECUTION_FAILURE':'실행 예외'}


def diagnostic_rows(value, *, full=True):
    """Every cause has provenance; incomplete metadata is explicitly unknown."""
    if not isinstance(value, dict):
        return ['상세 진단 미기록 · 과거 로그만으로 데이터/모델/실행 원인을 판별할 수 없음']
    rows = ['진단 단계: '+str(value.get('stage') or '미기록')+
        ' · 자료 세대: '+str(value.get('generation_id') or '미기록')]
    counts = value.get('counts') or {}
    rows.append('중단 사유별 기록 수: '+(' / '.join(CATEGORIES.get(k,k)+': '+str(v) for k,v in counts.items()) or '0'))
    for name,label in (('blockers','중단 사유'), ('observations','비차단 관측')):
        for i,item in enumerate(objects(value.get(name)),1):
            origin=item.get('anchor') or {}; target=item.get('target') or {}
            refs=item.get('references') or []
            identity=' · '.join(str(v) for v in (
                item.get('document_name') or origin.get('document_name'),
                item.get('heading') or origin.get('heading'),
                '대상 '+str(target.get('document_name'))+' '+str(target.get('heading') or '') if target else None,
                '참조 '+str(item.get('reference_id')) if item.get('reference_id') else None,
                '참조 '+','.join(str(r.get('reference_id')) for r in refs) if refs else None) if v)
            rows.append(f'{label}[{i}] {CATEGORIES.get(item.get("category"),item.get("category"))} / {item.get("code")}'+
                        (' · '+identity if identity else ''))
            if full:
                # Literal newlines are escaped; no row/count-only replacement of nested causes.
                rows.append('  상세: '+json.dumps(item,ensure_ascii=False,sort_keys=True))
            else:
                decision=item.get('decision') or {}
                why=decision.get('reason') or item.get('stored_resolution_reason') or item.get('reason')
                if why:rows[-1]+=' · 이유: '+compact(why,100)
                if item.get('resolution') is not None:rows[-1]+=' · 저장된 해석 상태: '+str(item['resolution'])
    if value.get('pending') and not value.get('blockers'):
        rows.append('중단 사유 미기록 · pending만으로 원인을 추정하지 않음')
    return rows


def failure_rows(value):
    if not isinstance(value,dict):return ['실패 상세 미기록']
    rows=['실패 코드: '+str(value.get('error_code') or '미기록'),
          '예외 종류: '+str(value.get('error_type') or '미기록'),
          '실패 단계: '+str(value.get('stage') or '미기록'),
          '오류 메시지: '+json.dumps(value.get('error_message'),ensure_ascii=False),
          '발생 위치: '+json.dumps(value.get('location'),ensure_ascii=False)]
    if isinstance(value.get('investigation'),dict):rows.extend(diagnostic_rows(value['investigation']))
    if isinstance(value.get('tool_outcome'),dict):
        outcome=value['tool_outcome']
        rows.append('도구 실패 상태: '+json.dumps({k:outcome.get(k) for k in
            ('failure_kind','cause_code','execution','effects','receipt_refs','remaining_target_refs','failure_ref')},ensure_ascii=False))
    if value.get('traceback'):rows.append('전체 traceback:\n'+str(value['traceback']))
    rows.append('전체 실패 상세:\n'+json.dumps(value,ensure_ascii=False,indent=2,default=str))
    return rows


PHASES = {
    'source-unit-triage': '최소 원문 선별·확장 범위 선택',
    'source-unit-review': '확장 원문 검토·근거 선별',
    'memory-intent': '조사 목적 확인', 'memory-assess': '원문 근거 판단',
    'memory-compose': '최종 답변 작성', 'memory-resolve': '요청 해석',
    'investigate': '근거 탐색', 'select_sources': '근거 선별',
    'compose': '답변 작성', 'review': '답변 검토', 'rebut': '반론 검토',
    'source-query-plan': '요청 분류·검색 계획', 'source-triage': '조문 원문 확인·선별',
    'source-omission-review': '누락 근거 확인', 'bounded-question-plan': '질문 요구 정리',
    'source-request-route': '대화 입력 분류',
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
         'case_evidence_rebind': '저장 근거를 현재 요청에 재결속',
         'follow_reference': '참조 확인', 'follow_relations': '연결 근거 확인',
         'inspect_relation': '연결 상세 확인', 'view_page': '다음 목록 확인'}


def compact(value, limit=180):
    """Flatten control characters so model text cannot forge extra log lines."""
    text = ' '.join(''.join(ch if ch.isprintable() else ' ' for ch in str(value or '')).split())
    return text if limit is None or len(text) <= limit else text[:limit-1] + '…'


def objects(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def reason_text(value):
    from .judgment_view import reason_text as clean
    return compact(clean(value))


def phase_label(value):
    phase = str(value or '')
    for prefix, label in (('source-unit-triage', '최소 원문 선별·확장 범위 선택'),
                          ('source-law-navigation-', '법령별 선택·부모 원문 조사'),
                          ('source-unit-review', '확장 원문 검토·근거 선별'),
                          ('source-unit-choice-repair', '읽기 범위 선택 재확인'),
                          ('source-reference', '연결 근거 조사'),
                          ('memory-assess', '원문 근거 판단'),
                          ('memory-compose', '최종 답변 작성'),
                          ('memory-resolve', '요청 해석')):
        if phase.startswith(prefix):
            return label
    return PHASES.get(phase, compact(phase, 70))


def input_rows(view):
    """Short explicit values and collection sizes, never complete prompts."""
    rows = []
    for key, label in (('question', '질문'), ('task', '요청 작업')):
        value = view.get(key)
        if isinstance(value, dict):
            value = value.get('task') or value.get('question')
        if isinstance(value, str) and value.strip():
            rows.append('입력 ' + label + ': ' + compact(value, 160))
    for key, label in (('units', '원문 단위'), ('sources', '원문 후보'),
                       ('evidence', '근거'), ('exact_evidence', '검증 원문'),
                       ('claims', '판단'), ('history', '대화 이력'),
                       ('facts', '현재 사실'), ('current_facts', '현재 사실')):
        value = view.get(key)
        if isinstance(value, (list, dict)):
            examples = []
            if key in ('units', 'sources', 'evidence', 'exact_evidence'):
                for item in objects(value)[:2]:
                    meta = item.get('metadata') or {}
                    meta = meta if isinstance(meta, dict) else {}
                    name = item.get('coordinate') or item.get('article') or item.get('heading') or meta.get('read_location') or meta.get('heading')
                    if name:
                        examples.append(compact(name, 90))
            rows.append(f'입력 {label}: {len(value)}개' +
                (' · '+ ' / '.join(examples) + (f' · 외 {len(value)-2}개 생략' if len(value)>2 else '')
                 if examples else ' · 상세 내용 생략'))
    return rows[:6] or ['입력: 현재 요청과 단계별 처리 맥락']


def wire_view(request):
    import json
    view = {}
    for message in objects(request.get('messages')):
        if message.get('role') != 'user':
            continue
        try:
            content = json.loads(message.get('content') or '{}')
            if isinstance(content, dict):
                candidate = content.get('view', content)
                if isinstance(candidate, dict):
                    view = candidate
        except (TypeError, ValueError):
            continue
    return view


def acquisition_summary(data):
    reason = data.get('stop_reason')
    label = {'EVIDENCE_SUFFICIENT':'답변 근거가 충분해 남은 검색 후보 열람을 멈춤',
        'REFERENCE_NAVIGATION_INCOMPLETE':'연결 조사 미완료 · 아래 사유별 기록 확인',
        'REQUIRED_CONNECTION_PENDING':'과거 연결 미완료 표시 · 상세 원인 구분 미기록',
        'NEW_SEARCH_REQUESTED':'새 검색어로 추가 검색 필요',
        'CANDIDATE_BATCH_LIMIT':'남은 후보 묶음이 있어 후속 조사 필요',
        'CANDIDATES_EXHAUSTED':'검색 후보 확인을 마침 · 근거 충분성 미확인'}.get(reason, '원문 조사 중단 코드: '+str(reason or '미기록'))
    unread = len(data.get('unread_candidate_keys') or [])
    details = [f'남은 후보: {unread}개 묶음' + (' · 읽지 않음' if reason=='EVIDENCE_SUFFICIENT' else '')]
    batches = objects(data.get('batches'))
    if batches:
        why = reason_text(batches[-1].get('sufficiency_reason'))
        if why:
            details.append('충분성 판단 이유: '+why)
    if reason in ('REFERENCE_NAVIGATION_INCOMPLETE','REQUIRED_CONNECTION_PENDING') or data.get('diagnostics',{}).get('pending'):
        details.extend(diagnostic_rows(data.get('diagnostics')))
    return label, details


def output_rows(value, view=None):
    """Received proposals do not establish executed READ or adopted evidence."""
    if not isinstance(value, dict):
        return ['출력: 구조화 응답 미확인']
    rows = []
    if isinstance(value.get('purpose'), str):
        rows.append('출력 조사 목적: '+compact(value['purpose'], 140))
    for key, label in (('mode', '요청 유형'), ('intent', '다음 행동'), ('next_action', '법령 조사 행동'),
                       ('needs_search', '추가 검색 필요'), ('evidence_sufficient', '근거 충분 판단')):
        if type(value.get(key)) in (str, bool):
            rendered = ('예' if value[key] else '아니오') if type(value[key]) is bool else compact(value[key], 80)
            rows.append('출력 ' + label + ': ' + rendered)
    if value.get('search_queries'):
        rows.append('출력 새 검색어: '+' / '.join(compact(q, 60) for q in value['search_queries'][:3] if isinstance(q, str)))
    if isinstance(view, dict) and objects(value.get('choices')):
        units = {r.get('id'):r for r in objects(view.get('units'))}
        choices = objects(value['choices'])
        names = [compact(units[c['id']].get('coordinate') or units[c['id']].get('article'), 100)
                 for c in choices[:2] if c.get('id') in units]
        if names:
            rows.append('출력 읽기 제안 위치: '+' / '.join(names)+
                        (f' · 외 {len(choices)-2}개 생략' if len(choices)>2 else ''))
    for key, label in (('choices', '읽기·선별 제안'), ('actions', '도구 행동 제안'),
                       ('claims', '판단'), ('paragraphs', '답변 문단'), ('checks', '검토 결과'),
                       ('plans', '검색 계획')):
        if isinstance(value.get(key), list):
            rows.append(f'출력 {label}: {len(value[key])}개')
    reason = reason_text(value.get('reason') or value.get('sufficiency_reason'))
    if reason:
        rows.append('출력 이유: ' + reason)
    return rows[:6] or ['출력: 단계 처리 응답 수신 · 상세 내용 생략']


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
    def add(judgment, finding='', reason='', *, full=False):
        from .judgment_view import reason_text as clean
        rows.append({'judgment': compact(judgment, 60), 'finding': compact(finding, None if full else 180),
                     'reason': compact(clean(reason), None) if full else reason_text(reason)})

    if not isinstance(value, dict): return rows
    # Native v6 replies use claims/issues rather than the legacy assessments
    # envelope. These are explicit output fields, never hidden model reasoning.
    if value.get('purpose'):
        add('조사 목적', value['purpose'], value.get('reason'), full=True)
    for issue in objects(value.get('issues')):
        add('확인할 쟁점', issue.get('question'), issue.get('reason'), full=True)
    for claim in objects(value.get('claims')):
        if claim.get('text'):
            add('현재 판단 후보', claim['text'], claim.get('reason'), full=True)
    for issue in objects(value.get('issue_assessments')):
        add('쟁점 판단', {'COVERED':'근거 확인 완료','PARTIAL':'일부 미확인','INSUFFICIENT':'근거 부족'}.get(issue.get('status'), issue.get('conclusion')),
            issue.get('reason'), full=True)
    for gap in objects(value.get('gaps')):
        add('추가 확인 필요', gap.get('reason'), full=True)
    for limitation in value.get('limitations', []) if isinstance(value.get('limitations'), list) else []:
        if isinstance(limitation, str): add('미확인 사항', limitation, full=True)
    laws={law.get('id'):law for law in objects(view.get('laws'))}
    branches={branch.get('id'):branch for branch in objects(view.get('articles'))}
    for choice in objects(value.get('law_decisions')):
        add('법령 조사 선택' if choice.get('status')=='INVESTIGATE' else '법령 조사 보류',
            laws.get(choice.get('law_id'),{}).get('name','제시된 법령'),choice.get('reason'))
    for choice in objects(value.get('branch_decisions')):
        add({'KEEP':'원문 묶음 유지','EXCLUDE':'읽은 원문 묶음 제외','DEFER':'원문 묶음 보류'}.get(choice.get('status'),'원문 묶음 판단'),
            branches.get(choice.get('branch_id'),{}).get('article','제시된 원문 묶음'),choice.get('reason'))
    if value.get('next_action'):add('법령 조사 다음 행동',value['next_action'],value.get('reason'))
    if value.get('mode') in ('CASE','DIRECT') and 'answer' in value:
        add('안내 답변' if value['mode']=='DIRECT' else '법률·문서 요청 처리',
            value.get('answer') or '기존 사건 처리로 연결',value.get('reason'))
    for plan in objects(value.get('plans')):
        if plan.get('agent_required') is False:
            add('안내 답변', '원문 검색 없이 응답', plan.get('reason'))
        else:
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
    lines = [f'판단: {row["judgment"]} → 찾은 것: {row["finding"] or "처리 결과 기록"}'
             + (f' → 이유: {row["reason"]}' if row.get('reason') else '')
             for row in rows]
    return '\n'.join(lines)


def render_detail(label, value):
    """Return plain agent/tool text, or None for unaffected report sections."""
    if not (label.startswith('AGENT ') or label in {
            'MODEL CALL', 'MODEL RESPONSE / LLM ANSWER', 'QUESTION PLAN',
            'WORKFLOW REPAIR', 'SEMANTIC REPAIR', 'TOOL RESULT'}):
        return None
    data = value if isinstance(value, dict) else {}
    kind = label.removeprefix('AGENT ').replace(' ', '_')
    if is_error_event(kind) or kind in {'WORKFLOW_REPAIR', 'SEMANTIC_REPAIR'}:
        # Error context must precede the generic decision projection: otherwise
        # a rejected decision renders as an ordinary successful decision.
        return '전체 오류·복구 기록 (생략 없음)\n'+json.dumps(value,ensure_ascii=False,indent=2,default=str)
    if label == 'AGENT STAGE RESULT':
        return compact(data.get('label'), 120)+'\n'+'\n'.join(
            compact(row, None) for row in data.get('details', []) if isinstance(row, str))
    if label == 'AGENT LAW SELECTION DECISION':
        law = data.get('law') or {}
        return render_rows([{'judgment':'법령 조사 선택' if data.get('status')=='INVESTIGATE' else '법령 조사 보류',
            'finding': compact(law.get('name'), None), 'reason': compact(data.get('reason'), None)}])
    if label == 'AGENT LAW BRANCH DECISION':
        branch = data.get('branch') or {}
        return render_rows([{'judgment': {'KEEP':'원문 묶음 채택','EXCLUDE':'원문 묶음 제외','DEFER':'원문 묶음 보류'}.get(data.get('status'), '원문 묶음 판단'),
            'finding': compact(branch.get('article') or branch.get('name') or data.get('article') or data.get('document_name'), None),
            'reason': compact(data.get('reason'), None)}])
    if label == 'AGENT UNIT CANDIDATE ACQUISITION STOPPED':
        heading, rows = acquisition_summary(data)
        return heading+'\n'+'\n'.join(rows)
    if label in {'AGENT REFERENCE NAVIGATION STATUS','AGENT SOURCE INVESTIGATION INCOMPLETE'}:
        return '\n'.join(diagnostic_rows(data))
    if label=='AGENT REFERENCE NAVIGATION FAILED':
        return '\n'.join(failure_rows(data))
    if label in {'AGENT RUN FAILED','AGENT UNASSESSED AT STOP'}:
        rows=[('실패 코드: ' if label=='AGENT RUN FAILED' else '종료 사유: ')+str(data.get('code') or data.get('reason') or '미기록')]
        if label=='AGENT RUN FAILED' or data.get('diagnostics') is not None:
            rows.extend(failure_rows(data.get('diagnostics')))
        if label=='AGENT UNASSESSED AT STOP':
            from collections import Counter
            counts=Counter(r.get('last_state') or 'STATE_NOT_RECORDED' for r in objects(data.get('coverage')))
            rows.append('미평가 근거 현황(중단 원인이 아닌 처리 상태): '+json.dumps(dict(counts),ensure_ascii=False))
            rows.append('근거별 상태: '+json.dumps([{k:r.get(k) for k in
                ('evidence','status','last_state','presented')} for r in objects(data.get('coverage'))],ensure_ascii=False))
        return '\n'.join(rows)
    if label=='AGENT REFERENCE GROUP DECISION':
        return '결정 출처: '+str(data.get('decision_origin') or '과거 기록 · 미기록')+'\n'+json.dumps(data,ensure_ascii=False,sort_keys=True)
    if label == 'AGENT SOURCE FULLTEXT RESULTS':
        lines = ['행동: Fulltext 검색 · 입력: ' + compact(data.get('query'), 120)]
        locations = objects(data.get('locations'))
        lines.append(f'출력: 검색된 위치 {len(locations)}개')
        lines.extend('  ' + compact(r.get('document_name'), 100) + ' · ' + compact(r.get('location'), 160)
                     for r in locations)
        return '\n'.join(lines)
    if label in {'AGENT UNIT READ CHOICE', 'AGENT UNIT READ STARTED', 'AGENT UNIT READ FINISHED'}:
        name = compact(data.get('document_name'), 100) + ' · ' + compact(data.get('location'), 160)
        if label.endswith('CHOICE'):
            return '입력: ' + compact(data.get('document_name'), 100) + ' · ' + compact(data.get('input_location') or data.get('location'), 160) + '\n행동: ' + compact(data.get('read_location'), 160) + (' · 확장 읽기 선택' if data.get('expanded') else ' · 선택 범위 확인') + '\n선택 이유: ' + reason_text(data.get('reason'))
        if label.endswith('STARTED'):
            status = ' · 원문 읽기 진행'; prefix = '행동: '
        else:
            prefix = '출력: '
            status = (' · 열람 완료' if data.get('complete') else ' · 일부 열람, 나머지 확인 필요') + (' · 검증 원문 재사용' if data.get('reused') else '')
        locations = data.get('locations') or [data.get('location')]
        return '\n'.join(prefix + compact(data.get('document_name'), 100) + ' · ' + compact(loc, 160) + status
                         for loc in locations if isinstance(loc, str))
    if label == 'MODEL CALL':
        return f'단계: {phase_label(data.get("phase"))} · LLM 호출 {data.get("attempt", "")} · 시작' + '\n' + '\n'.join(input_rows(data.get('view') or {}))
    if label == 'MODEL RESPONSE / LLM ANSWER':
        phase = data.get('source_stage') or data.get('phase')
        heading = f'단계: {phase_label(phase)} · 응답 상태: {compact(data.get("status"))} · 모델 제안 (채택은 후속 검증)'
        reply = data.get('reply')
        if not isinstance(reply, dict):
            return heading + '\n모델 응답 수신' + (' · ' + compact(reply) if reply else '')
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
        reason = reason_text(reason)
        if not reason and query: reason = '검색어: ' + compact(query)
        return f'판단: {TOOLS.get(str(data.get("tool", "")).lower(), "도구 실행")} · 상태 {compact(data.get("status"))} → 찾은 것: {finding}' + (' → 이유: ' + reason if reason else '')
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
