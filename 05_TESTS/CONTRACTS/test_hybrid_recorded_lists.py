"""Hybrid search that reads nothing goes back to its own recorded lists (user 2026-11-11).

"하이브리드 해서 밀렸을수도 있을것 같아 … 읽을것 못찾앗다 그러면 vector,fulltext 검색했던거 기록 다시
들고와서(다시 쿼리 때리지마) 각각 줘서 선택하게해봐." The two lists stay unmerged, the model picks once, the
server reads what it picked, and no search runs again.
"""
import json
import types
import pytest
import test_guided_continue_bounds as bounds
from fastapi.testclient import TestClient
from semantic_runtime import vector_navigation as vn
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import guided_navigation as gn
from semantic_runtime.legal_agent.errors import ProposalError
from test_hybrid_initial_search import SOURCES, fake
from test_legal_agent_double_harness import ROOT, wire
from test_multiturn_structured_scope import tree
from test_vector_scope_respect import Retriever


def recorded(monkeypatch, vector, lexical):
    s, index, events = fake(monkeypatch, 'hybrid', vector, lexical)
    _, discovery = vn.discover(s, ['q'], ['의무인수'], 'x')
    return s, index, events, discovery['law_navigation']


def test_each_list_keeps_its_own_order_and_is_not_logged(monkeypatch):
    s, index, events, catalogue = recorded(monkeypatch, [('s1', 'd1'), ('s2', 'd1'), ('s3', 'd1')], ['s55', 's3'])
    lists = catalogue['search_lists']
    assert [r['source_id'] for r in lists['vector']] == ['s1', 's2', 's3']
    assert [r['source_id'] for r in lists['lexical']] == ['s55', 's3']
    assert lists['lexical'][0] == {'source_id': 's55', 'document_id': 'd2', 'document': '법', 'article': '제55조'}
    assert 'search_lists' not in catalogue['fusion']
    assert not any('search_lists' in json.dumps(p, ensure_ascii=False) for k, p in events)


def test_an_article_past_the_fused_page_is_still_listed_and_vector_mode_records_none(monkeypatch):
    vector = [(f's{i}', 'd1') for i in range(1, 41)]
    lexical = [f's{i}' for i in range(50, 60)]
    _, _, _, catalogue = recorded(monkeypatch, vector, lexical)
    assert len(catalogue['search_lists']['vector']) == vn.LIST_TOP and catalogue['search_lists']['lexical'][0]['source_id'] == 's50'
    s, _, _ = fake(monkeypatch, 'vector', vector, lexical)
    _, discovery = vn.discover(s, ['q'], ['의무인수'], 'x')
    assert 'search_lists' not in discovery['law_navigation']


def investigation(monkeypatch, lists, reply, *, selected=None, reserved=0, reads=('g1',)):
    calls, events, targets = [], [], []

    def invoke(system, payload, schema, phase, timeout):
        calls.append({'payload': payload, 'schema': schema, 'phase': phase})
        if isinstance(reply, Exception):
            raise reply
        return reply

    def preread(inv):
        targets.extend(inv.s.continuation_reads)
        return list(reads)

    monkeypatch.setattr(gn, 'enabled', lambda profile: True)
    monkeypatch.setattr(gn, 'preread', preread)
    repo = types.SimpleNamespace(event=lambda k, p: events.append((k, p)),
                                 budget=lambda: {'model_limit': 40, 'finalization_reserve': 2, 'model_reserved': reserved})
    s = types.SimpleNamespace(repo=repo, profile={'selection_time_reserve_seconds': 5}, continuation_reads=['held'])
    inv = types.SimpleNamespace(p={'initial_search_lists': lists, 'selected': selected or {}}, s=s, question='공매 절차는?',
                                invoke=invoke, left=lambda: 500, save=lambda: None)
    return inv, calls, events, targets


LISTS = {'vector': [{'source_id': 'a', 'document_id': 'd1', 'document': '담보관리준칙', 'article': '제3조'},
                    {'source_id': 'b', 'document_id': 'd1', 'document': '담보관리준칙', 'article': '제4조(공매)'}],
         'lexical': [{'source_id': 'b', 'document_id': 'd1', 'document': '담보관리준칙', 'article': '제4조(공매)'},
                     {'source_id': 'c', 'document_id': 'd2', 'document': '채권회수지침', 'article': '제9조'}]}


def test_the_model_sees_both_lists_unmerged_and_the_server_reads_its_pick(monkeypatch):
    inv, calls, events, targets = investigation(monkeypatch, LISTS, {'reason': '공매 조문', 'candidate_ids': ['C2', 'C3']})
    assert vn.read_recorded_lists(inv) is True
    payload = calls[0]['payload']
    assert [(r['id'], r['rank']) for r in payload['vector_search']] == [('C1', 1), ('C2', 2)]
    assert [(r['id'], r['rank']) for r in payload['fulltext_search']] == [('C2', 1), ('C3', 2)]
    assert payload['fulltext_search'][1]['document'] == '채권회수지침' and 'source_id' not in payload['vector_search'][0]
    assert calls[0]['phase'] == vn.LIST_PHASE
    assert [t['identity'] for t in targets] == [{'source_id': 'b', 'document_id': 'd1'}, {'source_id': 'c', 'document_id': 'd2'}]
    assert inv.s.continuation_reads == ['held']
    assert dict(events)['RECORDED_LIST_CHOICE']['chosen'] == ['b', 'c'] and dict(events)['RECORDED_LIST_CHOICE']['search_called'] is False
    assert vn.read_recorded_lists(inv) is False and len(calls) == 1, 'once per investigation'


@pytest.mark.parametrize('case', ['already_read', 'no_budget', 'no_lists'])
def test_no_model_call_when_something_was_read_or_nothing_can_be_asked(monkeypatch, case):
    inv, calls, _, _ = investigation(monkeypatch, None if case == 'no_lists' else LISTS, {'reason': 'x', 'candidate_ids': []},
                                     selected={'g': {}} if case == 'already_read' else None, reserved=38 if case == 'no_budget' else 0)
    assert vn.read_recorded_lists(inv) is False and calls == []


@pytest.mark.parametrize('reply', [{'reason': '관련 없음', 'candidate_ids': []}, {'reason': 'x', 'candidate_ids': ['C9']}, ProposalError('bad')])
def test_no_pick_or_an_invalid_one_keeps_the_stop_and_reads_nothing(monkeypatch, reply):
    inv, calls, _, targets = investigation(monkeypatch, LISTS, reply)
    assert vn.read_recorded_lists(inv) is False and targets == [] and len(calls) == 1


def test_a_pick_that_cannot_be_read_keeps_the_stop(monkeypatch):
    inv, _, _, targets = investigation(monkeypatch, LISTS, {'reason': 'x', 'candidate_ids': ['C1']}, reads=())
    assert vn.read_recorded_lists(inv) is False and len(targets) == 1


class Listing(bounds.Transport):
    def __init__(self, plan, choose):
        super().__init__(bounds.BROAD, 'authorized', plan)
        self.choose = choose; self.lists = []; self.answered = []

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        if phase == vn.LIST_PHASE:
            self.lists.append(view)
            ids = [r['id'] for r in view['vector_search']][:1] if self.choose else []
            return wire({'reason': '목록에서 고름', 'candidate_ids': ids})
        if phase == 'memory-guided-answer' and view.get('originals'):
            schema = body['response_format']['json_schema']['schema']
            self.answered.append(view)
            point = {'issue_refs': bounds.find(schema, 'issue_refs')['items']['enum'][:1], 'text': '고른 조문이 승인 기준을 정합니다.',
                     'evidence_refs': bounds.find(schema, 'evidence_refs')['items']['enum'][:1]}
            return wire({**{key: [] for key in schema['required']}, 'answer_points': [point]})
        return super().send_once(body=body, ticket=ticket)


def serve(tree, tmp_path, monkeypatch, plan, *, choose=True):
    gen, idx = tree
    retrievers, lexical_calls = [], []
    real = vn.discover

    def discover(session, queries, terms, origin):
        retriever = Retriever([(sid, session.tools.sources[sid]['document_id']) for sid in sorted(session.tools.sources)[:2]])
        retrievers.append(retriever)
        session.matcher.initial_vector = retriever
        return real(session, queries, terms, origin)

    def lexical(session, terms):
        lexical_calls.append(list(terms))
        return sorted(session.tools.sources)[-1:]

    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'hybrid')
    monkeypatch.setattr(vn, 'discover', discover)
    monkeypatch.setattr(vn, 'lexical_articles', lexical)
    transport = Listing(plan, choose)
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=tmp_path / 'runtime',
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app, raise_server_exceptions=False) as api:
        response = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': bounds.BROAD})
    return transport, response, retrievers, lexical_calls


@pytest.mark.parametrize('plan', [{'ask': True, 'reads': 0}, {'reads': 0}])
def test_stopping_without_reading_goes_back_to_the_lists_and_answers_from_the_pick(tree, tmp_path, monkeypatch, plan):
    transport, response, retrievers, lexical_calls = serve(tree, tmp_path, monkeypatch, plan)
    assert response.status_code == 200, response.text
    assert len(transport.lists) == 1
    assert len(retrievers) == 1 and len(retrievers[0].calls) == 1 and len(lexical_calls) == 1, 'no search runs again'
    assert response.json()['answer']['claims'], 'the answer is written from the original the model picked'
    assert len(transport.answered) == 1 and transport.answered[0]['originals']


def test_when_the_model_picks_nothing_the_question_stands(tree, tmp_path, monkeypatch):
    transport, response, retrievers, _ = serve(tree, tmp_path, monkeypatch, {'ask': True, 'reads': 0}, choose=False)
    assert response.status_code == 200, response.text
    assert len(transport.lists) == 1 and len(retrievers) == 1
    assert response.json()['answer']['claims'] == [] and bounds.OFFER['question'] in response.json()['answer']['text']
