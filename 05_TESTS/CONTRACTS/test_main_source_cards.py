import asyncio
from contextlib import contextmanager
import json
import sqlite3

from semantic_runtime import chat_adapter as ca
from semantic_runtime.progress import ProgressCapture


def test_journal_source_paths_stay_scoped_through_default_main_projection(tmp_path):
    events = []
    c = ProgressCapture('r', tmp_path, events.append)
    c.admitted = {'allowed'}
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE event(seq INTEGER,payload_json TEXT)')
        payload = {'laws': [{'document_id': 'allowed', 'name': f'허용 모의법{i}'} for i in range(19)]
                   + [{'document_id': 'denied', 'name': 'PRIVATE DOCUMENT'}]}
        db.execute('INSERT INTO event VALUES(1,?)', (json.dumps(payload),))
        c._activity(db, 1, 'LAW_FULLTEXT_DIRECTORY')
    assert len(events) == 3
    details = [row for e in events for row in e['details']]
    assert len(details) == 19 and 'PRIVATE DOCUMENT' not in json.dumps(events)
    w = ca.views()
    result = asyncio.run(w.workflow_display_result({'answer': {'text': '정상 답변'}}, events, request_id='r'))
    cards = json.dumps(result['agentFlowExecutedData'], ensure_ascii=False)
    assert all(row in cards for row in details)


def test_read_scope_is_enforced_before_grouping(tmp_path):
    events = []
    c = ProgressCapture('r', tmp_path, events.append)
    c.admitted = {'allowed'}
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE event(seq INTEGER,payload_json TEXT)')
        for seq, did in enumerate(['denied', 'allowed'], 1):
            db.execute('INSERT INTO event VALUES(?,?)', (seq, json.dumps(
                {'document_id': did, 'document_name': did, 'location': '제1조'})))
            c._activity(db, seq, 'UNIT_READ_STARTED')
    assert len(events) == 1 and events[0]['details'] == ['allowed · 제1조']


def test_private_model_outputs_remain_absent(tmp_path):
    events = []
    c = ProgressCapture('r', tmp_path, events.append)
    c.publish('decision', 'internal', details=['PRIVATE MODEL OUTPUT'],
              basis={'kind': 'ATTEMPT_FINISHED', 'detail_mode': 'activity'})
    c.publish('decision', 'internal', details=['PRIVATE ERROR'],
              basis={'kind': 'OBS_EVENT', 'detail_mode': 'full_error'})
    assert events == []


def test_native_chat_flushes_trailing_read_card_without_finished_event(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path))
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'final-cards')
    @contextmanager
    def capture(request_id, runtime, sink):
        sink({'schema_version': 'rag-progress-v1', 'request_id': request_id,
              'kind': 'reading', 'label': '원문 확인', 'details': ['모의법 · 제3조'],
              'basis': {'kind': 'UNIT_READ_STARTED', 'detail_mode': 'activity'}})
        yield
    monkeypatch.setattr(ca.progress, 'capture', capture)
    async def service(body):
        return {'status': 200, 'body': {'answer': {'text': '완료'}}}
    monkeypatch.setattr(ca, 'call_service', service)
    result = asyncio.run(ca.chat({'question': '모의', 'request_id': 'r'}))['data']
    assert result['text'] == '완료'
    assert '모의법' in json.dumps(result['agentFlowExecutedData'], ensure_ascii=False)


def test_off_mode_preserves_graph_inputs_but_no_progress_cards(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'off')
    w = ca.views(); d = w._ChatProgress({})
    event = {'schema_version': 'rag-progress-v1', 'kind': 'candidate', 'label': '검색',
             'details': ['모의법'], 'basis': {'kind': 'LAW_FULLTEXT_DIRECTORY', 'detail_mode': 'activity'}}
    asyncio.run(d.progress(event))
    assert d.flow_events and not d.blocks
