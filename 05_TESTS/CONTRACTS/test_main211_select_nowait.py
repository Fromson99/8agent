"""MAIN211: body-search group check goes through the read-only SQL gate; questions do not wait for preload.

Field 2026-11-11 (MAIN210): relax_groups sent 'WITH anchor_rows AS (...)' and oracle_dp_io.SQL.query
refused it before sending (READ_ONLY: query accepts SELECT only) - every Oracle question with a
multi-word search group failed. The startup preparation took about 5 minutes and the first question
waited 3 m 49 s for it.
"""
import asyncio
import threading
from types import SimpleNamespace

from semantic_runtime import oracle_dp_io as io
from semantic_runtime.oracle_query_fulltext import UnitIndex


class Client:
    SQL_PATH = '/sql'

    def __init__(self, groups):
        self.groups, self.sent = groups, []

    def request(self, method, path, json):
        self.sent.append(json['statementText'])
        return {'items': [{'resultSet': {'offset': 0, 'hasMore': False, 'items': [{'G': g} for g in self.groups]}}]}


def index(groups, tmp_path):
    idx = UnitIndex.__new__(UnitIndex)
    idx.request = SimpleNamespace(release_id='r', sources=SimpleNamespace(allowed=frozenset({'d1', 'd2'})))
    idx.kinds = {'unit': 'u', 'unit_fts_posting': 'p', 'unit_fts_length': 'l', 'unit_fts_stats': 's'}
    idx.statistics = {'documents': 100, 'tokens': 10000}
    idx.check_unchanged = lambda: None
    idx._frequencies = lambda words: {w: 5 for w in words}
    client = Client(groups)
    idx.sql = io.SQL(client, journal=tmp_path/'sql.jsonl', binding='contract')
    return idx, client


def test_group_check_passes_the_read_only_gate_and_keeps_the_answer(tmp_path):
    idx, client = index([0], tmp_path)
    terms, report = idx.relax_groups(None, ['승인 기준', '보고 원칙'])
    assert len(client.sent) == 1 and client.sent[0].startswith('SELECT x.G FROM (WITH anchor_rows AS (')
    # group 0 ('승인 기준') has a unit; group 1 had none and becomes its words
    assert terms[0] == '승인 기준' and [r['group'] for r in report] == ['보고 원칙']


def test_wait_preparation_does_not_wait_by_default(monkeypatch):
    import service
    from semantic_runtime import oracle_query_service
    monkeypatch.delenv('GENOS_PRELOAD_WAIT_SECONDS', raising=False)
    monkeypatch.setattr(oracle_query_service, 'preparing', lambda: True)
    events = []
    monkeypatch.setattr(service.obs, 'event', lambda log, name, **kw: events.append(name))
    asyncio.run(asyncio.wait_for(service._wait_preparation({'request_id': 'q'}, None), 1))
    assert events == ['request.preparation.running']


def test_wait_preparation_can_still_be_asked_to_wait(monkeypatch):
    import service
    from semantic_runtime import oracle_query_service
    monkeypatch.setenv('GENOS_PRELOAD_WAIT_SECONDS', '1')
    state = {'n': 0}
    def preparing():
        state['n'] += 1
        return state['n'] < 3
    monkeypatch.setattr(oracle_query_service, 'preparing', preparing)
    events = []
    monkeypatch.setattr(service.obs, 'event', lambda log, name, **kw: events.append(name))
    asyncio.run(service._wait_preparation({'request_id': 'q'}, None))
    assert events == ['request.preparation.waiting', 'request.preparation.done']


def test_glossary_spellings_do_not_block_a_question_while_loading():
    from semantic_runtime import oracle_query_index as oqi
    oqi._LABELS.clear()
    started, release = threading.Event(), threading.Event()

    class Records:
        release_id = 'r-labels'
        calls = 0
        def select(self, kind, condition, *a, **kw):
            Records.calls += 1
            if kind == 't':
                started.set(); assert release.wait(5)
                return [{'id': 'T1', 'label': '승인', 'document_id': None}]
            return []

    out = {}
    loader = threading.Thread(target=lambda: out.setdefault('held', oqi.held_labels(Records(), 't', 'srf')))
    loader.start()
    assert started.wait(5)
    # A question while the preparation is loading: not held yet, no wait (it reads Oracle itself).
    assert oqi.held_labels(Records(), 't', 'srf') is None
    release.set(); loader.join(5)
    assert out['held'][0] == (('T1', '승인', None),)
    calls = Records.calls
    assert oqi.held_labels(Records(), 't', 'srf') == out['held'] and Records.calls == calls
    oqi._LABELS.clear()
