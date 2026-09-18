"""Work-loop contracts on the small serving fixture: budget, rejected actions, oversized articles."""
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.work_navigation import maximal_spans
from lawrag.pipeline.term_generation import build_generation

ROOT = Path(__file__).resolve().parents[2]


def generation_with(tmp_path, term_glossary, documents):
    source = tmp_path/'source.sqlite'
    with sqlite3.connect(source) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
        CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        for did, name, articles in documents:
            artifact = 'art-'+did
            db.execute('INSERT INTO document VALUES (?,?,?,?)', (did, name, artifact, '{}'))
            block = 0
            for i, blocks in enumerate(articles):
                unit = {'family': 'kr_article', 'surface': f'제{i+1}조', 'title': '절차', 'span': [block, block+len(blocks)],
                        'coordinate_scope': 'body', 'coordinate_key': f'body:제{i+1}조'}
                db.execute('INSERT INTO source_unit VALUES (?,?,?,?)', (did, str(i), None, json.dumps(unit)))
                for text in blocks:
                    db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)', (did, str(block), str(i), text, artifact, '{}'))
                    block += 1
    build_generation(source, term_glossary, tmp_path/'built', serving=True)
    return tmp_path/'built/generation'


class Provider:
    """Scripted model: one content question, actions supplied by the test."""
    def __init__(self, actions):
        self.actions = list(actions); self.roles = []; self.reviews = []
    def record_local(self, value): return {'kind': 'scripted-local'}
    def call(self, role, system, data, schema):
        self.roles.append(role)
        if role == 'structured_navigation' and 'work_state' not in data:
            return {'action': {'tool': 'INTERPRET_QUERY', 'args': {'intent': 'content', 'scope': 'current', 'bindings': [],
                    'title_query': '', 'clarification': ''}, 'reason': 'fixture'}}, {'kind': 'scripted', 'role': role}
        if role == 'navigation_requirements':
            span = '영업일' if '영업일' in data['question'] else data['question'][:4]
            return {'requirements': [{'id': 'Q1', 'text': '확인 항목', 'question_span': span}]}, {'kind': 'scripted', 'role': role}
        if role == 'structured_navigation':
            action = self.actions.pop(0) if self.actions else {'tool': 'STOP', 'args': {'reason': 'script exhausted'}}
            if callable(action): action = action(data)
            return {'action': {**action, 'reason': action.get('reason', 'fixture')}}, {'kind': 'scripted', 'role': role}
        if role == 'navigation_review':
            reviews = [{'segment_id': x['id'], 'status': 'adopted', 'requirement_ids': ['Q1'],
                        'quote_ref': x['quote_refs'][0]['id'], 'claim': x['text'][:40]} for x in data['pending_review']]
            self.reviews.append(reviews)
            return {'reviews': reviews}, {'kind': 'scripted', 'role': role}
        if role == 'navigation_synthesis':
            ids = [x['id'] for x in data['sources']]
            return {'findings': [{'text': '읽은 원문에 영업일 절차가 있다.', 'source_ids': ids, 'requirement_ids': ['Q1']}],
                    'coverage': [{'requirement_id': 'Q1', 'status': 'complete', 'source_ids': ids, 'missing': ''}]}, {'kind': 'scripted', 'role': role}
        if role == 'navigation_verify':
            return {'requirements': [{'requirement_id': 'Q1', 'status': 'verified', 'missing': ''}],
                    'findings': [{'index': 0, 'supported': True, 'reason': 'fixture'}], 'search_queries': []}, {'kind': 'scripted', 'role': role}
        raise AssertionError(role)


def ask(tmp_path, generation, provider, question='영업일 절차를 알려줘', limits=None):
    app = create_app(tmp_path/'runtime', generation, contracts_root=ROOT, provider=provider, implementation='document-navigation-v1')
    if limits: app.state.pipeline.term_agent.config['limits'] = limits
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json={'question': question})
    assert response.status_code == 200, response.text
    return response.json()


def read_pending(n):
    return lambda data: {'tool': 'READ_BATCH', 'args': {'read_handles': [x['read_handle'] for x in data['candidates']['items'] if x['review_status'] == 'unreviewed'][:n]}}


@pytest.fixture
def many(tmp_path, term_glossary):
    docs = [(f'd{i}', f'가상규정{i}', [[f'영업일에 {i}번째 절차를 따른다.']]) for i in range(8)]
    return generation_with(tmp_path, term_glossary, docs)


def test_rejected_action_is_recorded_and_the_loop_continues(tmp_path, many):
    bad = {'tool': 'READ_BATCH', 'args': {'read_handles': ['RH999']}}
    provider = Provider([bad, read_pending(3)])
    state = ask(tmp_path, many, provider)['retrieval']['term_agent']
    rejected = [e for e in state['work_state']['events'] if e['status'] == 'REJECTED']
    assert rejected and 'unoffered' in rejected[0]['error']
    assert state['failure'] is None and state['adopted'], state['stop']


def test_budget_exhaustion_synthesizes_from_adopted_evidence(tmp_path, many):
    # interpretation 1 + plan 1 + (read 1 + review 1) + synthesis 2 = 6 -> the loop must not spend the reserve.
    provider = Provider([read_pending(3), read_pending(3), read_pending(3)])
    result = ask(tmp_path, many, provider, limits={'max_calls': 6, 'wall_seconds': 300, 'context_chars': 60000})
    state = result['retrieval']['term_agent']
    assert state['failure'] is None
    assert 'navigation_synthesis' in provider.roles and 'navigation_verify' in provider.roles
    assert result['answer']['claims'] and state['candidate_review']['unreviewed'] > 0
    # interpretation + one batch only; the remaining two calls were kept for synthesis/verification
    assert provider.roles.count('structured_navigation') == 2 and state['calls'] == 6


def test_model_can_synthesize_before_every_candidate_is_read(tmp_path, many):
    provider = Provider([read_pending(2), {'tool': 'SYNTHESIZE', 'args': {'reason': '두 원문으로 충분'}}])
    result = ask(tmp_path, many, provider)
    state = result['retrieval']['term_agent']
    assert state['status'] == 'FINISH' and state['synthesis']['requested'] == '두 원문으로 충분'
    assert state['candidate_review']['unreviewed'] == 6 and len(result['answer']['claims']) == 1


def test_no_evidence_when_budget_ends_reports_requirements(tmp_path, many):
    provider = Provider([{'tool': 'WORK_PAGE', 'args': {'kind': 'events', 'offset': 0}}]*10)
    result = ask(tmp_path, many, provider, limits={'max_calls': 5, 'wall_seconds': 300, 'context_chars': 60000})
    state = result['retrieval']['term_agent']
    assert state['status'] == 'STOP' and not result['answer']['claims']
    assert any('확인 미완료' in x['reason'] for x in result['answer']['unresolved'])
    assert 'navigation_synthesis' not in provider.roles


def test_oversized_article_is_read_block_by_block(tmp_path, term_glossary):
    big = [['영업일 첫 단락 '+'가'*700] + ['영업일 후속 단락 %d ' % i + '나'*700 for i in range(12)]]
    generation = generation_with(tmp_path, term_glossary, [('big', '큰규정', big), ('small', '작은규정', [['영업일에 신청한다.']])])
    read_big = lambda data: {'tool': 'READ_BATCH', 'args': {'read_handles': [next(x['read_handle'] for x in data['candidates']['items'] if x['document_name'] == '큰규정')]}}
    provider = Provider([read_big, read_big, {'tool': 'SYNTHESIZE', 'args': {'reason': '충분'}}])
    result = ask(tmp_path, generation, provider, limits={'max_calls': 14, 'wall_seconds': 300, 'context_chars': 60000,
                                                       'active_segments': 4, 'active_chars': 3000})
    state = result['retrieval']['term_agent']
    reads = [e for e in state['trace'] if e['tool'] == 'READ' and e['status'] == 'OK']  # work_state events carry hashes only
    assert reads and reads[0]['result']['status'] == 'PARTIAL_ARTICLE'
    assert reads[0]['result']['read_block_ids'] and reads[0]['result']['unread_block_ids']
    assert reads[1]['result']['read_block_ids'][0] == reads[0]['result']['unread_block_ids'][0]
    assert state['failure'] is None and result['answer']['claims']


def test_maximal_spans_drop_nested_surfaces():
    rows = [{'id': 'a', 'question_spans': [{'start': 0, 'end': 6, 'text': '투자일임계약'}]},
            {'id': 'b', 'question_spans': [{'start': 0, 'end': 4, 'text': '투자일임'}]},
            {'id': 'c', 'question_spans': [{'start': 4, 'end': 6, 'text': '계약'}, {'start': 20, 'end': 22, 'text': '계약'}]},
            {'id': 'd', 'question_spans': [{'start': 10, 'end': 12, 'text': '서면'}]}]
    assert [r['id'] for r in maximal_spans(rows)] == ['a', 'c', 'd']


def test_candidates_are_ordered_by_distinct_question_concepts(tmp_path, term_glossary):
    docs = [('one', '한개념', [['영업일에 신청한다.']]), ('two', '두개념', [['영업일에 자금지원을 신청한다.']])]
    generation = generation_with(tmp_path, term_glossary, docs)
    provider = Provider([{'tool': 'SYNTHESIZE', 'args': {'reason': 'x'}}])
    result = ask(tmp_path, generation, provider, question='영업일 자금지원 절차')
    state = result['retrieval']['term_agent']
    hits = {c['document_name']: c['concept_hits'] for c in state['work_state']['entities'].values() if c['type'] == 'article'}
    # 자금지원 is one extra question concept; the shared 절차 title and 영업일 count once each for both
    assert hits['두개념'] == hits['한개념'] + 1
    surfaces = [e['surface'] for e in state['entry_paths'] if e['kind'] == 'term']
    assert surfaces == ['영업일', '자금지원']


def test_http_rejects_malformed_questions_with_422(tmp_path, many):
    app = create_app(tmp_path/'runtime', many, contracts_root=ROOT, provider=Provider([]), implementation='document-navigation-v1')
    with TestClient(app) as client:
        for body in ({}, {'question': 123}, {'question': ''}, {'question': '  '}):
            assert client.post('/v1/rag/ask', json=body).status_code == 422, body


class RepairProvider(Provider):
    """Breaks a contract once (or always) to exercise the repair paths."""
    def __init__(self, actions, break_role, always=False):
        super().__init__(actions); self.break_role = break_role; self.always = always; self.broken = 0
    def call(self, role, system, data, schema):
        out, receipt = super().call(role, system, data, schema)
        if role == self.break_role and (self.always or not self.broken):
            self.broken += 1
            if role == 'navigation_requirements':
                out = {'requirements': [{'id': 'Q1', 'text': '확인 항목', 'question_span': '질문에 없는 문구'}]}
            else:
                out = {'reviews': out['reviews'][:1]}
        return out, receipt


def test_requirement_span_violation_is_repaired_once(tmp_path, many):
    provider = RepairProvider([read_pending(3), {'tool': 'SYNTHESIZE', 'args': {'reason': '충분'}}], 'navigation_requirements')
    result = ask(tmp_path, many, provider)
    state = result['retrieval']['term_agent']
    assert provider.roles.count('navigation_requirements') == 2 and state['candidate_review']['requirement_repairs'] == 1
    assert state['failure'] is None and result['answer']['claims']


def test_requirement_span_violation_twice_reports_without_crashing(tmp_path, many):
    provider = RepairProvider([], 'navigation_requirements', always=True)
    result = ask(tmp_path, many, provider)
    state = result['retrieval']['term_agent']
    assert 'exact substring' in state['failure']['message'] and not result['answer']['claims']
    assert provider.roles.count('navigation_requirements') == 2  # one repair, then stop


def test_review_violation_is_repaired_once(tmp_path, many):
    provider = RepairProvider([read_pending(3), {'tool': 'SYNTHESIZE', 'args': {'reason': '충분'}}], 'navigation_review')
    result = ask(tmp_path, many, provider)
    state = result['retrieval']['term_agent']
    assert provider.roles.count('navigation_review') == 2 and state['failure'] is None
    assert result['answer']['claims'] and not state['candidate_review']['parked_segments']


def test_unreviewable_segments_are_parked_and_the_request_continues(tmp_path, many):
    # Every review is malformed, so nothing can be adopted; the request must still end cleanly.
    provider = RepairProvider([read_pending(2), {'tool': 'STOP', 'args': {'reason': '검토 불가'}}],
                              'navigation_review', always=True)
    result = ask(tmp_path, many, provider)
    state = result['retrieval']['term_agent']
    parked = [e for e in state['work_state']['events'] if e['tool'] == 'PARK_UNREVIEWED']
    assert parked and state['candidate_review']['parked_segments'] == 2
    assert state['failure'] is None  # session survived the contract violation
    assert len(state['read_segments']) == 2 and not result['answer']['claims']
    assert any('검토 계약을 만족하지 못해' in x['reason'] for x in result['answer']['unresolved'])


def test_empty_candidate_pool_gets_search_turns(tmp_path, term_glossary):
    generation = generation_with(tmp_path, term_glossary, [('a', '가상규정', [['영업일에 신청한다.']])])
    seen = {}
    def watch(data):
        seen.update(data.get('search_required') or {})
        return {'tool': 'STOP', 'args': {'reason': '찾지 못함'}}
    provider = Provider([watch])
    result = ask(tmp_path, generation, provider, question='ZZZQQ WWWPP')
    state = result['retrieval']['term_agent']
    assert state['candidate_review']['total'] == 0 and state['candidate_review']['search_turns'] == 1
    assert '등록된 용어·조문을 찾지 못해' in seen.get('reason', '')
    assert provider.roles.count('structured_navigation') == 2  # interpretation + one search turn


def test_dismissing_every_candidate_still_allows_search(tmp_path, many):
    dismiss_all = lambda data: {'tool': 'DISMISS', 'args': {'read_handles': [x['read_handle'] for x in data['candidates']['items']], 'reason': '무관'}}
    provider = Provider([dismiss_all, {'tool': 'STOP', 'args': {'reason': '없음'}}])
    result = ask(tmp_path, many, provider)
    state = result['retrieval']['term_agent']
    assert state['candidate_review']['search_turns'] >= 1  # a search turn came before the end
    assert any('없음' in x['reason'] for x in result['answer']['unresolved'])
