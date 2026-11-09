"""The request path never lists every in-scope source (field 2026-11-06, MAIN166 dev silver).

The Oracle port pages a result with a 10,000-row budget, so enumerating a large scope's
sources stopped the question with QUERY_SQL_RESULT_BUDGET at RECALL (`corpus_ids`).
The annex-file index had the same full scan. Real-Oracle reproduction with 10,203
originals: 09_ARTIFACTS/AUDITS/20261106-recall-source-budget.
"""
import json
import sqlite3
from types import SimpleNamespace

import pytest

from semantic_runtime import annex_files as af
from semantic_runtime.legal_agent import unit_relations as rel
from test_detached_annex_reference import SOURCES, bind
from test_unified_legal_agent import unified, ok, wire  # noqa: F401  (fixture)
from test_compact_v2_rag import structured_generation  # noqa: F401  (fixture)


class BoundedSources:
    """Oracle-shaped source port: point lookups and one-document ID streams only."""
    cache_binding = staticmethod(lambda: ('release', 'scope'))

    def __init__(self, rows):
        self.rows, self.streamed = rows, []

    def __iter__(self):
        raise AssertionError('QUERY_SQL_RESULT_BUDGET: full source scan')

    def items(self):
        raise AssertionError('QUERY_SQL_RESULT_BUDGET: full source scan')

    def ids_for_documents(self, ids):
        did, = ids
        self.streamed.append(did)
        return iter(sorted(sid for sid, d, _ in self.rows if d == did))


def bounded_index(rows):
    sources = BoundedSources(rows)
    session = SimpleNamespace(scope=sorted({did for _, did, _ in rows}), tools=SimpleNamespace(sources=sources),
                              matcher=SimpleNamespace(documents={did: name for _, did, name in rows}))
    return rel.detached_annex_files(session), sources


@pytest.mark.parametrize('origin,text,mention,hint', [
    ('body', '신청은 별지 제9호서식에 따른다.', '별지 제9호', None),
    ('body', '산출은 별표 3-2에 따른다.', '별표 3-2', None),
    ('t3-2', '세부는 별표 3의2에 따른다.', '별표 3의2', None),
    ('f11', '관련 서식은 별지 제9호서식이다.', '별지 제9호', None),
    ('body', '「다른법 시행규칙」 별지 제9호서식을 쓴다.', '별지 제9호', '다른법 시행규칙'),
    ('body', '별지 제12호서식에 따른다.', '별지 제12호', None),
])
def test_annex_index_from_document_names_binds_like_the_source_scan(origin, text, mention, hint):
    index, sources = bounded_index(SOURCES)
    assert bind(origin, text, mention, hint, index=index) == bind(origin, text, mention, hint, index=af.index(sorted(SOURCES)))
    assert len(sources.streamed) <= 1  # only the resolved file's source IDs are read


def test_annex_binding_keeps_every_source_of_the_resolved_file_in_port_order():
    rows = SOURCES + [('s-f9-b', 'f9', SOURCES[2][2]), ('s-f9-a', 'f9', SOURCES[2][2])]
    index, _ = bounded_index(rows)
    ref = {'source_text': '별지 제9호서식', 'mention_start': 0, 'mention_end': 6, 'mention_text': '별지 제9호',
           'locator': '별지 제9호', 'document_name_hint': None}
    out = rel.detached_annex(ref, {'document_id': 'body', 'document_name': SOURCES[0][2]}, index)
    assert out['target_source_ids'] == ['s-f9', 's-f9-a', 's-f9-b']
    assert out['detached_annex']['document_id'] == 'f9'


def test_two_files_with_one_label_stay_ambiguous_without_reading_sources():
    rows = SOURCES + [('s-f9b', 'f9b', SOURCES[0][2] + ' > 별표서식 > [별지 제9호서식] 신청서(구)')]
    index, sources = bounded_index(rows)
    assert bind('body', '별지 제9호서식에 따른다.', '별지 제9호', index=index) == 'DETACHED_ANNEX_AMBIGUOUS'
    assert sources.streamed == []


def test_recall_payload_has_no_full_source_list(unified):
    _, send, transport, _, runtime = unified
    original = transport.send_once

    def send_once(*, body, ticket):  # current-request review fields (MAIN148+), as test_guided_answer
        view = json.loads(body['messages'][1]['content'])['view']
        if view.get('source_stage', view['phase']) == 'memory-command-check':
            transport.phases.append('memory-command-check')
            after = (view.get('transition') or {}).get('after') or {}
            return wire({'valid': True, 'reason': '모의 현재 명령 대조', 'request_relation': 'NEW_TOPIC',
                         'requested_task': after.get('task')})
        return original(body=body, ticket=ticket)
    transport.send_once = send_once
    assert ok(send())['answer']['claims']
    with sqlite3.connect(runtime/'case-memory'/'cases-v3.sqlite') as db:
        recall = [json.loads(p) for (p,) in db.execute("SELECT payload FROM node WHERE stage='RECALL'")]
    assert recall and all(set(p) == {'selected_for_read', 'discovery', 'binding'} for p in recall)
