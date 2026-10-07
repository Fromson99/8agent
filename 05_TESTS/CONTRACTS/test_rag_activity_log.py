"""Actual journals/READ scopes to visible activity; synthetic sources only."""
import asyncio
import json
import pytest

from semantic_runtime.progress import ProgressCapture
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.readable_log import render_detail
from test_genos_chat_flow import journal, workflow, evidence, read
from test_genos_v6_progress import run_captured
from test_unified_legal_agent import unified, ok
from test_structure_first_search import structured_generation
from test_unit_fulltext_adaptive_read import session, tree, hit, record, us
from semantic_runtime.legal_agent import unit_reading as ur


@pytest.fixture
def native_journal(journal, tmp_path):
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    original, _, _ = journal
    repo = UnifiedRepository(tmp_path/'native/journal.sqlite', original.context,
        {'max_model_attempts': 10, 'finalization_reserve': 2, 'max_tool_actions': 10})
    events = []
    projection = ProgressCapture('fixture', tmp_path, events.append)
    projection.run_id = original.context.run_id
    projection.journal_path = repo.path
    yield repo, projection, events
    repo.close()


def test_fulltext_lists_all_locations_in_order_and_filters_scope(journal):
    repo, projection, events = journal
    rows = [{'document_id': 'allowed', 'document_name': '모의규정',
             'location': f'제1조 제2항 제{i}호'} for i in range(1, 22)]
    repo.event('SOURCE_FULLTEXT_RESULTS', {'query': '승인', 'locations': rows + [
        {'document_id': 'other', 'document_name': '다른 팀 비공개', 'location': '제99조'}]})
    projection.poll_journal()
    candidates = [e for e in events if e['kind'] == 'candidate']
    assert len(candidates) == 3 and all(e['count'] == 21 for e in candidates)
    locations = [d for e in candidates for d in e['details'] if '검색됨' in d]
    assert locations == [f'모의규정 · {r["location"]} · 검색됨' for r in rows]
    assert '비공개' not in json.dumps(events, ensure_ascii=False)
    before = len(events)
    projection.poll_journal()
    assert len(events) == before


def test_actual_expansion_and_reuse_report_the_read_range(session):
    s, _ = session
    rec = record(s)
    def invoke(system, data, schema, phase, timeout):
        return {'issues': [], 'choices': [{'id': 'U001', 'scope': 'subtree:1',
            'reason': '상위 항의 조건과 각 호 확인'}] if phase == 'source-unit-triage' else [],
            'needs_search': False}
    selected = us.select('긴급 승인', rec, invoke, session=s.sources,
                         remaining_seconds=120, max_fulltext_chars=80000)
    events = []
    projection = ProgressCapture('unit-test', s.work.path.parent, events.append)
    projection.run_id = s.context.run_id
    projection.journal_path = s.work.path
    projection.poll_journal()
    trace = [e for e in events if e.get('basis', {}).get('detail_mode') == 'activity']
    choice = next(e for e in trace if e['basis']['kind'] == 'UNIT_READ_CHOICE')
    assert '확장 읽기 선택' in choice['label'] and '상위 항' in ' '.join(choice['details'])
    assert '제1조 ①' in ' '.join(choice['details'])
    reads = [e for e in trace if e['basis']['kind'] == 'UNIT_READ_FINISHED']
    assert any('열람 완료' in ' '.join(e['details']) for e in reads)
    assert selected['final_ids']
    # READ is still only acquisition; it must not claim final adoption.
    assert not any('근거 채택함' in ' '.join(e['details']) for e in reads)


def test_native_selection_does_not_display_unselected_read_ranges(native_journal):
    repo, projection, events = native_journal
    item = evidence(); excluded = evidence(suffix='2')
    excluded['source_id'] = item['source_id']
    item['metadata']['read_location'] = '제1조 제1항 제1호'
    excluded['metadata']['read_location'] = '제1조 제2항'
    read(repo, item); read(repo, excluded)
    payload = {'final_ids': [item['source_id']], 'selected_originals': [{
        'source_id': item['source_id'], 'evidence_ids': [item['evidence_id']]}]}
    with repo.transaction():
        seq = repo.event('CASE_JUDGMENT_ACCEPTED', {'stage': 'SELECT', 'payload_hash': digest(payload)})
        repo.put('case_stage', 'case:SELECT', payload, seq)
    projection.poll_journal()
    selected = [e for e in events if e['kind'] == 'selected']
    text = json.dumps(selected, ensure_ascii=False)
    assert '제1조 제1항 제1호' in text and '근거 채택' in text
    assert '제1조 제2항' not in text


def test_model_wire_inputs_and_outputs_reach_live_progress(unified):
    _, send, _, _, runtime = unified
    response, events = run_captured(runtime, send)
    result = ok(response)
    inputs = [e for e in events if e.get('basis', {}).get('kind') == 'ATTEMPT_SENT']
    outputs = [e for e in events if e.get('basis', {}).get('kind') == 'ATTEMPT_FINISHED']
    assert inputs and outputs
    assert any('모의승인규정' in ' '.join(e['details']) for e in inputs)
    assert any('SUCCEEDED' in ' '.join(e['details']) for e in outputs)
    assert all('후속 검증' in e['label'] for e in outputs)
    assert result['answer']['text'] not in json.dumps(events, ensure_ascii=False)


def test_activity_read_rows_are_not_collapsed_or_hidden(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-inline')
    display = workflow()._ChatProgress({'socketIOClientId': 'fixture'})
    sent = []
    async def emit(name, value, room): sent.append((name, value))
    display.emit = emit
    async def render():
        for i in range(1, 12):
            await display.progress({'schema_version': 'rag-progress-v1', 'kind': 'reading',
                'label': '선택 범위 원문 읽기 진행', 'details': [f'모의규정 · 제1조 제{i}항'],
                'basis': {'detail_mode': 'activity'}})
        await display.finish('최종 답변 원문')
    asyncio.run(render())
    text = ''.join(v for name, v in sent if name == 'token')
    assert all(f'제1조 제{i}항' in text for i in range(1, 12))
    assert text.split('**최종 답변**\n\n')[1] == '최종 답변 원문'


def test_saved_text_log_keeps_all_search_coordinates_and_short_input():
    rows = [{'document_name': '모의규정', 'location': f'제1조 제2항 제{i}호'} for i in range(1, 24)]
    text = render_detail('AGENT SOURCE FULLTEXT RESULTS', {'query': '승인', 'locations': rows})
    assert all(r['location'] in text for r in rows)
    text = render_detail('MODEL CALL', {'phase': 'source-unit-triage', 'attempt': 1,
        'view': {'question': '승인' * 200, 'units': [{}] * 20, 'hidden_reasoning': 'DO NOT DUMP'}})
    assert '입력 원문 단위: 20개' in text and '…' in text and 'DO NOT DUMP' not in text


@pytest.mark.parametrize('reason, expected', [
    ('EVIDENCE_SUFFICIENT', '근거가 충분'),
    ('REQUIRED_CONNECTION_PENDING', '미완료'),
    ('NEW_SEARCH_REQUESTED', '새 검색어'),
    ('CANDIDATE_BATCH_LIMIT', '후속 조사'),
    ('CANDIDATES_EXHAUSTED', '충분성 미확인')])
def test_cursor_stop_states_never_invent_completed_research(journal, reason, expected):
    repo, projection, events = journal
    payload = {'stop_reason': reason, 'unread_candidate_keys': ['group1'],
        'batches': [{'sufficiency_reason': '현재 원문의 조건 검토'}], 'read_groups': 1}
    repo.event('UNIT_CANDIDATE_ACQUISITION_STOPPED', payload)
    projection.poll_journal()
    event = next(e for e in events if e['basis']['kind'] == 'UNIT_CANDIDATE_ACQUISITION_STOPPED')
    assert expected in event['label']
    assert '현재 원문의 조건 검토' in ' '.join(event['details'])
    saved = render_detail('AGENT UNIT CANDIDATE ACQUISITION STOPPED', payload)
    assert expected in saved
    if reason != 'EVIDENCE_SUFFICIENT':
        assert '충분해' not in event['label'] and event['kind'] != 'selected'


def test_grouped_read_activity_lists_each_hit_and_actual_reused_segments(session):
    s, _ = session
    group = ur.group_hits(s.sources, [hit(s, '3'), hit(s, '4')])[0]
    own = next(o for o in ur.offers(s.sources, group) if o['extent'] == 'exact')
    state = {'count': 0, 'chars': 0}
    first = ur.read(s.sources, group, own, action_state=state)
    reused = ur.read(s.sources, group, own, action_state=state)
    assert first['complete'] and reused['complete'] and not reused['actions']
    events = []
    projection = ProgressCapture('group', s.work.path.parent, events.append)
    projection.run_id = s.context.run_id; projection.journal_path = s.work.path
    projection.poll_journal()
    finished = [e for e in events if e['basis']['kind'] == 'UNIT_READ_FINISHED']
    text = json.dumps(finished, ensure_ascii=False)
    assert '제1조 ① 1. 가.' in text and '제1조 ① 2.' in text
    assert '기존 검증 원문 재사용' in text
    assert any('미확보 구간' in ' '.join(e['details']) for e in finished)


def test_saved_native_stage_log_uses_the_same_verified_adoption(native_journal):
    import io
    from semantic_runtime.request_report import _LiveLog
    repo, _, _ = native_journal
    item = evidence(); item['metadata']['read_location'] = '제1조 제2항 제3호'
    read(repo, item)
    payload = {'final_ids': [item['source_id']], 'selected_originals': [{
        'source_id': item['source_id'], 'evidence_ids': [item['evidence_id']]}]}
    with repo.transaction():
        seq = repo.event('CASE_JUDGMENT_ACCEPTED', {'stage': 'SELECT', 'payload_hash': digest(payload)})
        repo.put('case_stage', 'case:SELECT', payload, seq)
    stream = io.StringIO(); handler = _LiveLog('fixture', stream, repo.path.parent)
    handler.journal_path = repo.path; handler.run_id = repo.context.run_id
    try:
        handler.poll_journal()
        saved = stream.getvalue()
        assert '제1조 제2항 제3호' in saved and '근거 채택' in saved
        assert 'DO NOT SEND ORIGINAL TEXT' not in saved
    finally:
        handler.close()


def test_adoption_of_grouped_hits_keeps_every_coordinate(native_journal):
    repo, projection, events = native_journal
    item = evidence()
    coords = [f'제1조 제2항 제{i}호' for i in range(1, 20)]
    item['metadata']['read_location'] = ' / '.join(coords)
    read(repo, item)
    payload = {'final_ids': [item['source_id']], 'selected_originals': [{
        'source_id': item['source_id'], 'evidence_ids': [item['evidence_id']]}]}
    with repo.transaction():
        seq = repo.event('CASE_JUDGMENT_ACCEPTED', {'stage': 'SELECT', 'payload_hash': digest(payload)})
        repo.put('case_stage', 'case:SELECT', payload, seq)
    projection.poll_journal()
    adopted = [d for e in events if e['kind'] == 'selected' for d in e['details']]
    assert len(adopted) == len(coords)
    assert all('모의규정 · '+coord+' · 답변 근거로 선택' in row for coord, row in zip(coords, adopted))


def test_negative_output_decisions_remain_visible():
    from semantic_runtime.legal_agent.readable_log import output_rows, input_rows
    assert '출력 근거 충분 판단: 아니오' in output_rows({'evidence_sufficient':False})
    rows = input_rows({'units':[{'coordinate':f'제1조 제{i}항'} for i in range(1,5)]})
    assert '제1조 제1항' in rows[0] and '제1조 제2항' in rows[0] and '외 2개 생략' in rows[0]
