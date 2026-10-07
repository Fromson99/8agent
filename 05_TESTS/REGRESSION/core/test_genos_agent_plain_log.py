"""Read the actual live .log projection of recorded model responses, without LLM calls."""
import json
import sqlite3

from semantic_runtime.request_report import live_log


def recorded_attempts(runtime, run_id, attempts):
    path = runtime / 'legal-agent' / 'runs' / '20260928' / run_id / 'journal.sqlite'
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE event(seq INTEGER,kind TEXT,payload_json TEXT,created_at TEXT);
            CREATE TABLE model_view(view_id TEXT,phase TEXT);
            CREATE TABLE model_attempt(attempt_id TEXT,view_id TEXT,attempt_no INTEGER,
                created_seq INTEGER,request_json TEXT,response_json TEXT,status TEXT);
        ''')
        for i, (phase, view, reply, tool_call) in enumerate(attempts, 1):
            message = {'content': json.dumps(reply, ensure_ascii=False)}
            if tool_call:
                message = {'tool_calls': [{'function': {'arguments': message['content']}}]}
            request = {'messages': [{'role': 'system', 'content': 'hidden system prompt'},
                                   {'role': 'user', 'content': json.dumps({'view': view}, ensure_ascii=False)}]}
            response = {'body_json': {'choices': [{'message': message}]}}
            db.execute('INSERT INTO model_view VALUES(?,?)', (f'V{i}', phase))
            db.execute('INSERT INTO model_attempt VALUES(?,?,?,?,?,?,?)',
                       (f'M{i}', f'V{i}', 1, i, json.dumps(request), json.dumps(response), 'SUCCEEDED'))
            db.execute('INSERT INTO event VALUES(?,?,?,?)',
                       (i, 'ATTEMPT_FINISHED', json.dumps({'attempt_id': f'M{i}'}), '2026-09-28T00:00:00+00:00'))
    return path


def test_live_log_shows_bounded_and_numbered_selection_with_document_names(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_LLM_KEY', 'fixture-secret-token')
    run_id = 'a' * 32
    runtime = tmp_path / 'runtime'
    triage = {'source_stage': 'source-triage', 'candidates': {
        'laws': {'D1': '모의승인규정'}, 'rows': [['C001', 'D1', '제2조(승인 예외)']]}}
    # Source 1 and claim 1 are independent reference namespaces.
    numbered = {'exact_evidence': [{'evidence': 1, 'document_name': '모의승인규정',
                                  'heading': '제2조(승인 예외)', 'text': 'hidden original source'}],
                'claims': [{'claim': 1, 'text': 'hidden draft'}], 'original_question': 'hidden question'}
    replies = [
        ('investigate', triage, {'issues': [], 'choices': [{'id': 'C001', 'reason': '승인 예외 요건 확인'}]}, False),
        ('select_sources', numbered, {'choices': [{'source': 1, 'decision': 'KEEP_CORE',
                                                  'reason': '직접 적용 근거 fixture-secret-token'}]}, False),
        ('review', numbered, {'checks': [{'claim': 1, 'evidence': [1], 'verdict': 'NEEDS_REWRITE',
                                        'reason': '예외 요건을 다시 확인해야 합니다.'}]}, True),
    ]
    journal = recorded_attempts(runtime, run_id, replies)
    before = journal.read_bytes()
    with live_log(tmp_path / 'shared', 'req-plain', runtime) as (path, handler):
        handler.run_id = run_id
        handler.poll_journal()
        first = path.read_text()
        handler.poll_journal()
        assert path.read_text() == first  # Polling must not duplicate decisions.
    assert '단계: 조문 원문 확인·선별' in first
    assert '판단: 읽을 근거 선택 → 찾은 것: 모의승인규정 제2조(승인 예외) → 이유: 승인 예외 요건 확인' in first
    assert '판단: 핵심 근거 채택 → 찾은 것: 모의승인규정 제2조(승인 예외) → 이유: 직접 적용 근거 [REDACTED]' in first
    assert '판단: 수정 필요 → 찾은 것: 모의승인규정 제2조(승인 예외) → 이유: 예외 요건을 다시 확인해야 합니다.' in first
    assert 'MODEL RAW RESPONSE' in first
    assert '"choices"' in first and '"checks"' in first
    assert 'hidden' not in first and 'fixture-secret-token' not in first
    assert journal.read_bytes() == before  # Display projection does not rewrite audit state.


def test_live_agent_blocks_bound_long_output_and_keep_repair_and_tool_reason(tmp_path):
    with live_log(tmp_path, 'req-compact') as (path, handler):
        handler.write_detail('MODEL RESPONSE / LLM ANSWER', {
            'phase': 'select_sources', 'status': 'SUCCEEDED',
            'reply': {'choices': [{'source': f'E{i}', 'decision': 'KEEP_CORE',
                                  'reason': '확인 이유\n\x1b[31m' + '가' * 400} for i in range(10)]}})
        handler.write_detail('QUESTION PLAN', {'plan': {'demands': [
            {'requirement': '승인 요건을 설명한다.', 'missing_fact': None}],
            'change_reason': '원질문의 답변 요구를 확인했습니다.'}})
        handler.write_detail('WORKFLOW REPAIR', {'errors': [{'message': '원문을 먼저 읽어야 합니다.'}]})
        handler.write_detail('TOOL RESULT', {'tool': 'search', 'status': 'ERROR',
                                          'server_reason': '원문 검색 중 조회가 중단되었습니다.'})
        handler.write_detail('TOOL RESULT', {'tool': 'search', 'status': 'OK',
            'returned_count': 2, 'input': {'query': '승인'},
            'examples': [{'title': '모의승인규정', 'heading': '제1조'}]})
        handler.write_detail('REQUEST / QUESTION', {'question': '원래 기록 형식 유지'})
        output = path.read_text()
    assert output.count('판단: 핵심 근거 채택') == 6
    assert '외 4건' in output and '\x1b' not in output
    assert '승인 요건을 설명한다.' in output
    assert '원문을 먼저 읽어야 합니다.' in output
    assert '원문 검색 중 조회가 중단되었습니다.' in output
    assert '찾은 것: 2건 · 모의승인규정 제1조 → 이유: 검색어: 승인' in output
    assert '"question": "원래 기록 형식 유지"' in output


def test_unexpected_model_shape_does_not_stop_later_live_blocks(tmp_path):
    with live_log(tmp_path, 'req-invalid') as (path, handler):
        handler.write_detail('MODEL RESPONSE / LLM ANSWER', {
            'phase': 'investigate', 'reply': {'plans': [{'law_names': [None]}]}})
        handler.write_detail('AGENT DECISION', {'intent': 'DRAFT', 'reason': '확보한 원문으로 답변합니다.'})
        output = path.read_text()
    assert '판단 요약 미완료' in output
    assert '판단: 답변 작성' in output and '확보한 원문으로 답변합니다.' in output
