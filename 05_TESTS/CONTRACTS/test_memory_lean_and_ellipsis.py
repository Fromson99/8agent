"""2026-11-13 user: "메모리 부하 문제 수정 … 다하고 삼성으로". A request that read a big annex kept a 39,000-connection
list (80MB) in its saved investigation state and every local journal stayed in the process (~0.8GB per large
request); the GENOS memory budget counted a held record once although it keeps rows and a serialized copy; a first-step
quote shortened with an ellipsis stopped the question before any research (ADR-1522 RISK-EDGE-013)."""
import gc
import json

from semantic_runtime import memory_runtime as mr
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import chat_records as cr
from semantic_runtime.legal_agent import connection_scope as cs
from semantic_runtime.legal_agent import request_entry as re_
from test_final_connection_selection import setup

Q013 = ('단기자금 운용 목적으로 발행 당시 만기 2개월짜리 국내 PF 전자단기사채를 만기보유 목적으로 350억원 사려고 합니다. '
        '만기가 짧으니 현지실사를 생략해도 되나요? 280억원이면 어떻게 되나요?')


def test_ellipsis_quote_maps_to_the_questions_own_words():
    span = re_.exact_span('단기자금 운용 목적으로 ... 만기보유 목적으로', Q013)
    assert span == '단기자금 운용 목적으로 발행 당시 만기 2개월짜리 국내 PF 전자단기사채를 만기보유 목적으로'
    assert re_.exact_span('단기자금 운용 목적으로…만기보유 목적으로', Q013) == span
    assert re_.exact_span('만기보유 목적으로 ... 단기자금 운용 목적으로', Q013) is None   # out of order
    assert re_.exact_span('억원 ... 현지실사', Q013) is None                             # '억원' appears twice
    assert re_.exact_span('...', Q013) is None
    assert re_.exact_span('350억원', Q013) == '350억원'                                   # literal copy as before


def test_budget_counts_an_open_record_with_its_serialized_copy():
    assert mr.held_bytes({'records': object(), 'cache': (1, b'x' * 10), 'size': 10}) == 20
    assert mr.held_bytes({'records': None, 'raw': b'x' * 10, 'size': 10}) == 10
    assert mr.held_bytes({'records': object(), 'size': 0}) == 0


def scope_of(inv, data):
    rows = cs.candidates(inv, data)
    return next(s for s, _ in rows if s['structural_selection'].get('unit_id') == '6')


def group(n):
    return {'anchor': {'source_id': 'article92', 'document_id': 'd'}, 'target': {'source_id': 'article97', 'document_id': 'd'},
            'connections': [{'endpoint_block_ids': [str(i)], 'already_read': False} for i in range(n)]}


def test_large_directory_list_stays_in_request_memory(monkeypatch):
    from semantic_runtime.legal_agent import unit_relations as rel
    inv, data = setup(monkeypatch); a = scope_of(inv, data); calls = []; inv.read_records = lambda: {}
    monkeypatch.setattr(cs, 'EXTERNAL_DIRECTORY_CONNECTIONS', 2)
    monkeypatch.setattr(rel, 'acquired_blocks', lambda *a, **kw: ({}, {}))
    groups = [group(3)]
    monkeypatch.setattr(cs, 'preview', lambda *a, **kw: (calls.append(1) or dict(status='COMPLETE', groups=json.loads(json.dumps(groups)), connection_count=3)))
    cs.accept(inv, a, data, '연결 확인')
    assert len(cs.inspect_directory(inv, a)['groups'][0]['connections']) == 3
    stored = inv.p['connection_directories'][cs.directory_key(a)]['result']
    assert stored['groups'] == [] and stored['groups_external'] and stored['groups_sha256'] == digest(groups)
    assert len(cs.inspect_directory(inv, a)['groups'][0]['connections']) == 3 and calls == [1]   # same request: no lookup
    inv.p = json.loads(json.dumps(inv.p)); del inv.s._connection_directory_groups              # a later request
    assert len(cs.inspect_directory(inv, a)['groups'][0]['connections']) == 3 and calls == [1, 1]
    del inv.s._connection_directory_groups; groups[0] = group(4)                               # the list changed since
    assert len(cs.inspect_directory(inv, a)['groups'][0]['connections']) == 4
    assert inv.p['connection_directories'][cs.directory_key(a)]['result']['groups_sha256'] == digest(groups)


def test_small_directory_is_saved_as_before(monkeypatch):
    inv, data = setup(monkeypatch); a = scope_of(inv, data)
    monkeypatch.setattr(cs, 'preview', lambda *a, **kw: dict(status='COMPLETE', groups=[], connection_count=0))
    cs.accept(inv, a, data, '연결 확인'); cs.inspect_directory(inv, a)
    stored = inv.p['connection_directories'][cs.directory_key(a)]['result']
    assert 'groups_external' not in stored and stored['groups'] == []


def test_run_journal_leaves_memory_but_chat_record_stays(tmp_path):
    ddl = 'CREATE TABLE IF NOT EXISTS t(a TEXT)'
    journal = cr.open_records(str(tmp_path / 'journal.sqlite'), [ddl], snapshot=True)
    chat = cr.open_records(str(tmp_path / 'cases.sqlite'), [ddl])
    key_j, key_c = (str((tmp_path / n).resolve()) for n in ('journal.sqlite', 'cases.sqlite'))
    assert cr._LOCAL_JOURNALS.get(key_j) is journal and cr._LOCAL.get(key_c) is chat
    assert cr.open_records(str(tmp_path / 'journal.sqlite'), [ddl], snapshot=True) is journal   # one object while held
    del journal; gc.collect()
    assert cr._LOCAL_JOURNALS.get(key_j) is None and cr._LOCAL.get(key_c) is chat
