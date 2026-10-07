"""Synthetic clock and original-source contracts; no model calls or benchmarks."""
from types import SimpleNamespace
import time

import pytest

from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.errors import DeadlineExceeded
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.source_recall_global import SourceRecall as GlobalRecall
from test_bounded_source_main import settings
from test_legal_agent_double_harness import generation
from test_legal_agent_v5 import app_for
from test_unit_fulltext_adaptive_read import tree, session, hit


@pytest.mark.parametrize('recall_class', [SourceRecall, GlobalRecall])
def test_recall_exceeds_old_timers_but_honors_request_deadline(monkeypatch, recall_class):
    clock = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    context = RequestContext.create({'question': '모의 원문'}, {}, {}, 1800)
    recall = recall_class.__new__(recall_class)
    recall.s = SimpleNamespace(context=context)
    recall.start = clock[0]
    clock[0] += 600
    recall.check_time()
    clock[0] += 1201
    with pytest.raises(DeadlineExceeded, match='request deadline exceeded'):
        recall.check_time()


def test_unit_original_read_completes_after_old_recall_timer(session):
    native, _ = session
    candidate = hit(native)
    recall = SourceRecall(native.sources)
    recall.start -= 7200
    recall.discover = lambda: ([candidate['source_id']], {
        'discovery_mode': 'fulltext', 'routes': {}, 'unit_hits': [candidate]})
    record = recall.prepare()
    assert record['unit_reads'][0]['complete']
    assert record['unit_reads'][0]['text'] == '가. 긴급 승인 예외는 허용한다.'
    assert record['selection_complete'] == [candidate['source_id']]


def test_legacy_original_read_completes_after_old_recall_timer(tmp_path, generation):
    app = app_for(tmp_path, generation, profile=settings())
    pipeline = app.state.pipeline
    request = {'question': '모의승인규정 승인 대상', 'document_ids': ['d'], 'use_llm': False}
    try:
        with pipeline.term_agent.open_session(request, query=pipeline.plan(request['question'], ['d']),
                                             runtime=tmp_path/'runtime') as native:
            recall = SourceRecall(native.sources)
            recall.start -= 7200
            record = recall.prepare()
            assert record['read_complete']
            assert all(e['document_id'] == 'd' for e in native.work.evidence())
    finally:
        pipeline.store.close()
