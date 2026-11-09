"""Definition priority (2026-11-09, ADR-1461 diagnosis): rule questions should not start from definitions.

1) request-entry asks the model whether the question asks what a term means (search.asks_definition).
2) A rule question does not pre-read definitions before the model's first choice; definitions stay offered.
3) Definitions of laws outside the vector top documents / named scope are neither pre-read nor offered.
4) The answer stage reads unread vector top-5 articles whose title holds a question word.
"""
from types import SimpleNamespace as S
import pytest

from semantic_runtime.legal_agent import request_entry, definition_entry as de, guided_answer as g, guided_navigation as gn


def test_entry_schema_asks_definition_required_for_the_model_optional_in_stored_entries():
    model = request_entry.schema(False, model=True)['properties']['search']['anyOf'][0]
    stored = request_entry.schema(False)['properties']['search']['anyOf'][0]
    assert 'asks_definition' in model['required'] and model['properties']['asks_definition'] == {'type': 'boolean'}
    assert 'asks_definition' in stored['properties'] and 'asks_definition' not in stored['required']
    assert 'search.asks_definition' in request_entry.SYSTEM


class Repo:
    def __init__(self):
        self.events = []
    def event(self, kind, payload):
        self.events.append((kind, payload))


def inv_for(asks, *, vector=None, definitions=None, active=False):
    s = S(entry_search={'mode': 'FULLTEXT', 'reason': 'r', **({'asks_definition': asks} if asks is not None else {})},
          repo=Repo(), tools=S(definitions=definitions or {}), scope={'law', 'other'},
          context=S(request={'question': '상장주선인의 의무인수 수량은?'}))
    inv = S(s=s, policy={'definition_entry': True}, p={'catalogue': {'vector_candidates': vector or []}}, saved=0)
    inv.save = lambda: setattr(inv, 'saved', inv.saved + 1)
    return inv


def test_rule_question_defers_definition_preread_and_definition_question_keeps_it(monkeypatch):
    called = []
    monkeypatch.setattr(de, 'matches', lambda session: called.append(1) or [])
    inv = inv_for(False)
    de.acquire_initial(inv)
    assert inv.p['definition_entry_deferred'] is True and called == []
    assert [k for k, _ in inv.s.repo.events] == ['DEFINITION_ENTRY_DEFERRED']
    de.acquire_initial(inv)  # once per request
    assert [k for k, _ in inv.s.repo.events] == ['DEFINITION_ENTRY_DEFERRED']
    assert de.question_asks_definition(inv.s) is False
    for asks in (True, None):  # definition question, or an entry without a question type: old behaviour
        inv = inv_for(asks)
        de.acquire_initial(inv)
        assert 'definition_entry_deferred' not in inv.p and called and inv.p['system_definition_seed']['targets'] == []


def test_definitions_of_laws_outside_the_vector_top_documents_are_dropped(monkeypatch):
    rows = [{'definition_id': 'd1', 'question_span': {}}, {'definition_id': 'd2', 'question_span': {}}]
    monkeypatch.setattr(de, 'matches', lambda session: list(rows))
    from semantic_runtime.legal_agent import query_scope as qs
    monkeypatch.setattr(qs, 'active', lambda s: False)
    defs = {'d1': {'document_id': 'law'}, 'd2': {'document_id': 'other'}}
    inv = inv_for(True, vector=[{'document_id': 'law', 'source_id': 's1', 'rank': 1}], definitions=defs)
    assert de.scoped_matches(inv) == [rows[0]]
    assert inv.s.repo.events[-1][0] == 'DEFINITION_ENTRY_SCOPED' and inv.s.repo.events[-1][1]['dropped'] == 1
    # No vector catalogue (keyword initial search): unchanged.
    assert de.scoped_matches(inv_for(True, definitions=defs)) == rows
    # The user's named scope also counts as the question's law.
    monkeypatch.setattr(qs, 'active', lambda s: True); monkeypatch.setattr(qs, 'documents', lambda s: {'other'})
    assert de.scoped_matches(inv) == rows


def test_navigation_prompt_marks_definitions_as_background_for_rule_questions():
    from semantic_runtime.legal_agent import law_navigation as ln
    assert 'definition_role이 PRIMARY' in ln.COMPACT_SYSTEM and 'BACKGROUND' in ln.COMPACT_SYSTEM
    assert '질문의 정의·기준을 찾을 때 해당 정의와 연결 조문의 read_action을 함께 우선 검토한다' not in ln.COMPACT_SYSTEM


def test_vector_top_title_matches_are_read_before_the_answer():
    reads = [{'id': 'L1', 'origin': 'LOCATION', 'label': '코스닥시장 상장규정 · 제26조(신규상장 의무보유)', 'identity': {}},
             {'id': 'L2', 'origin': 'LOCATION', 'label': '코스닥시장 상장규정 · 제13조(상장주선인의 의무)', 'identity': {},
              'vector_rank': 3, 'matched_terms': ['상장주선인']},
             {'id': 'L3', 'origin': 'LOCATION', 'label': '유가증권시장 상장규정 · 제13조(상장주선인의 의무)', 'identity': {},
              'vector_rank': 2, 'matched_terms': ['상장주선인']},
             {'id': 'L4', 'origin': 'LOCATION', 'label': '정의', 'identity': {}, 'vector_rank': 1, 'matched_terms': []},
             {'id': 'L5', 'origin': 'LOCATION', 'label': 'x', 'identity': {}, 'vector_rank': 4, 'matched_terms': ['상장주선인']}]
    assert [r['id'] for r in g.vector_title_reads({'next_reads': []}, reads)] == ['L3', 'L2']
    assert [r['id'] for r in g.vector_title_reads({'next_reads': ['L3']}, reads)] == ['L2', 'L5']
    assert 'vector_rank' in g.PROMPT


def test_assess_adds_vector_reads_to_the_answer_round():
    from test_guided_answer import ISSUES, SOURCES, execution, value
    e, calls = execution({**value(open=False), 'next_reads': []})
    loc = {'identity': {'document_id': 'd', 'source_id': 's13', 'unit_id': '175'}, 'label': '코스닥시장 상장규정 · 제13조(상장주선인의 의무)',
           'vector_rank': 3, 'matched_terms': ['상장주선인']}
    result = g.assess(e, SOURCES, ISSUES, '상장주선인의 의무인수 수량은?', [], selection={'issues': ISSUES, 'unread_locations': [loc]})
    reads = result['guided_reply']['proposed_reads']
    assert [r['identity']['source_id'] for r in reads] == ['s13']
    assert any(k == 'GUIDED_ANSWER_VECTOR_READS' and p['model_called'] is False for k, p in e.s.work.events)
    assert calls[0][1]['readable_locations'][0]['vector_rank'] == 3


def test_vector_top_locations_offer_unread_nearest_candidates(monkeypatch):
    from semantic_runtime.legal_agent import unit_reading as ur
    monkeypatch.setattr(ur, 'blocks', lambda s, did, uid, extent: ['b1', 'b2'])
    s = S(scope={'d'}, tools=S(sources={'s13': {'document_id': 'd', 'unit_id': '175'}, 's2': {'document_id': 'd', 'unit_id': '3'}}),
          matcher=S(units={}, documents={'d': 'external > t > krx > 코스닥시장 상장규정'}, stored_coordinates={}))
    inv = S(s=s, p={'catalogue': {'vector_candidates': [{'source_id': 's13', 'unit_id': '175', 'rank': 1},
                                                       {'source_id': 's2', 'unit_id': '3', 'rank': 2}]}})
    rows = gn.vector_top_locations(inv, [{'identity': {'source_id': 's2'}}], {}, {('d', '175'): {}})
    assert [r['identity']['source_id'] for r in rows] == ['s13'] and rows[0]['from_vector']
    assert gn.vector_top_locations(inv, [], {'s13': {'b1', 'b2'}, 's2': {'b1', 'b2'}}, {('d', '175'): {}, ('d', '3'): {}}) == []
