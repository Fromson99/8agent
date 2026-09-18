"""Scripted controller contracts; these are not model quality measurements."""
from copy import deepcopy
import json
import sqlite3

import pytest

from semantic_runtime.contracts import digest, sha
from semantic_runtime.task_harness import TaskSession
from semantic_runtime import task_policy as p
from test_navigation_loop import session as navigation_session


@pytest.fixture
def session(navigation_session, tmp_path):
    old = navigation_session
    return TaskSession(old.m, old.t, old.g, '여럿 돈을 모아 굴리는 방식', ['doc'],
                       p.DEFAULT, {'definition_sha256': digest(p.DEFAULT)},
                       {'query_id': 'query:fixture', 'generation_id': 'mock-v1', 'source_store_sha256': 'mock'},
                       journal=tmp_path/'journal.sqlite')


def action(tool, **args):
    return {'tool': tool, 'args': json.dumps(args, ensure_ascii=False), 'reason': '모의 계약 검토'}


class Provider:
    def __init__(self, verdict='SUPPORTED', invalid=False):
        self.turn = 0
        self.verdict = verdict
        self.invalid = invalid
        self.roles = []

    def call(self, role, prompt, data, schema):
        self.roles.append(role)
        if role == 'task_interpret':
            q = data['question']
            value = {'task_type': 'definition_scope', 'concepts': [
                {'start': 0, 'end': len(q), 'text': q, 'label': 'A'}], 'question_for_user': ''}
        elif role == 'task_evidence_review':
            value = {'verdict': self.verdict, 'reason': '모의 검토 결과',
                     'scope_checked': True, 'limitations': []}
        else:
            self.turn += 1
            if self.invalid and self.turn == 1:
                return {'issues': [{'id': 'definition', 'text': '모델이 바꾼 문장'}],
                        'actions': [action('STOP', status='sufficient', unresolved=[])]}, {'fixture': True}
            turn = self.turn - int(self.invalid)
            if turn == 1:
                tid = data['task_state']['concepts'][0]['term']['id']
                actions = [action('OPEN_TERM', term_id=tid)]
            elif turn == 2:
                tid = data['task_state']['concepts'][0]['term']['id']
                actions = [action('CONCEPT', term_id=tid, status='selected'), action('LIST', term_ids=[tid])]
            elif turn == 3:
                source = data['last_results'][-1]['result']['items'][0]['id']
                actions = [action('READ', source_id=source)]
            elif turn == 4:
                segment = data['active_segments'][0]
                actions = [action('JUDGE', segment_id=segment['id'], issue_id=issue,
                                  status='adopted', quote=segment['text'], claim='모의 범위 설명')
                           for issue in ['definition', 'requirements', 'exceptions']]
            else:
                actions = [action('STOP', status='sufficient' if self.verdict == 'SUPPORTED' else 'incomplete',
                                  unresolved=[] if self.verdict == 'SUPPORTED' else ['근거 의미 미확인'])]
            value = {'actions': actions}
        return value, {'fixture': True, 'role': role}


def exploring(session):
    session.provider = Provider()
    session.interpret()
    session.execute('OPEN_TERM', {'term_id': 'A'})
    session.delivered_concepts.add('A')
    session.execute('CONCEPT', {'term_id': 'A', 'status': 'selected'})
    session.listing(['A'])
    segment = session.read('s00')
    session.delivered.update(session.active)
    return segment


def test_complete_only_after_read_and_three_reviews(session):
    provider = Provider()
    result = session.run(provider)
    assert result['status'] == 'FINISH', result
    assert result['calls'] == 9
    assert provider.roles.count('task_evidence_review') == 3
    assert len(result['adopted']) == 3 and result['read_source_ids'] == ['s00']
    assert all(v['status'] == 'REVIEWED' for v in result['task_state']['obligations'].values())
    with sqlite3.connect(session.journal) as db:
        assert db.execute('SELECT count(*) FROM checkpoint').fetchone()[0] >= 5
        assert db.execute('SELECT count(*) FROM proposal').fetchone()[0] == 0


def test_reworded_obligation_recovers_without_mutating_spec(session):
    result = session.run(Provider(invalid=True))
    assert result['status'] == 'FINISH'
    assert result['issues']['definition'] == p.DEFAULT['obligations'][0]['text']
    assert result['task_state']['errors'] == 1
    assert any(row['status'] == 'REJECTED' for row in result['trace'])
    with sqlite3.connect(session.journal) as db:
        proposal = json.loads(db.execute('SELECT payload FROM proposal').fetchone()[0])
    assert proposal['status'] == 'PROPOSED' and not proposal['canonical_approval']
    assert proposal['question_span']['text'] == session.question


@pytest.mark.parametrize('verdict', ['UNKNOWN', 'CONFLICT'])
def test_exact_quote_does_not_override_semantic_review(session, verdict):
    result = session.run(Provider(verdict))
    assert result['status'] == 'STOP' and not result['adopted']
    assert result['stop']['unresolved']


def test_unread_and_fabricated_quote_cannot_be_adopted(session):
    segment = exploring(session)
    calls = session.calls
    with pytest.raises(ValueError, match='exact'):
        session.judge(segment['id'], 'adopted', 'definition', '원문에 없는 표현', '주장')
    session.delivered.clear()
    with pytest.raises(ValueError, match='undiscovered'):
        session.judge(segment['id'], 'adopted', 'definition', segment['text'], '주장')
    assert session.calls == calls


def test_incomplete_obligation_blocks_finish(session):
    segment = exploring(session)
    session.judge(segment['id'], 'adopted', 'definition', segment['text'], '모의 정의')
    with pytest.raises(ValueError, match='every obligation'):
        session.execute('STOP', {'status': 'sufficient', 'unresolved': []})


def test_unknown_or_conflict_not_hidden_by_other_adoption(session):
    segment = exploring(session)
    session.judge(segment['id'], 'adopted', 'definition', segment['text'], '모의 정의')
    other = session.read('s01')
    session.delivered.update(session.active)
    session.provider.verdict = 'CONFLICT'
    session.judge(other['id'], 'adopted', 'definition', other['text'], '모순 정의')
    assert session.obligations()['definition']['status'] == 'CONFLICT'
    assert not session.result()['adopted']
    with pytest.raises(ValueError, match='cannot discard'):
        session.judge(other['id'], 'excluded', 'definition')


def test_concept_preview_is_not_completed_candidate_review(session):
    session.provider = Provider()
    session.interpret()
    with pytest.raises(ValueError, match='read candidate'):
        session.execute('CONCEPT', {'term_id': 'A', 'status': 'selected'})
    session.execute('OPEN_TERM', {'term_id': 'A'})
    with pytest.raises(ValueError, match='read candidate'):
        session.execute('CONCEPT', {'term_id': 'A', 'status': 'selected'})


@pytest.mark.parametrize('scope_checked,limitations', [(False, []), (True, ['예외 범위 미확인'])])
def test_supported_verdict_still_requires_scope_and_no_limitations(session, scope_checked, limitations):
    segment = exploring(session)
    class Limited(Provider):
        def call(self, role, prompt, data, schema):
            value, receipt = super().call(role, prompt, data, schema)
            value.update(scope_checked=scope_checked, limitations=limitations)
            return value, receipt
    session.provider = Limited()
    session.judge(segment['id'], 'adopted', 'definition', segment['text'], '범위 확인')
    assert not session.result()['adopted']


def test_late_model_response_cannot_advance_state(session):
    class Late(Provider):
        def call(self, *args):
            value = super().call(*args)
            session.started -= 301
            return value
    result = session.run(Late())
    assert result['calls'] == 1 and session.interpretation is None
    assert result['stop']['unresolved'][0] == 'TIME_BUDGET'


def test_candidate_review_and_scope_guards(session):
    exploring(session)
    with pytest.raises(ValueError):
        session.execute('CONCEPT', {'term_id': 'invented', 'status': 'selected'})
    with pytest.raises(ValueError):
        session.execute('LIST', {'term_ids': ['A'], 'document_id': 'private'})
    with pytest.raises(ValueError):
        session.execute('RUN_SQL', {'query': 'DELETE'})


def test_no_progress_detects_repeated_metadata(session):
    class Repeater(Provider):
        def call(self, role, prompt, data, schema):
            if role != 'task_navigation':
                return super().call(role, prompt, data, schema)
            return {'actions': [action('LIST', term_ids=['A'])]}, {'fixture': True}
    result = session.run(Repeater())
    assert result['status'] == 'STOP' and 'NO_PROGRESS' in result['stop']['unresolved'][0]
    assert not result['read_segments'] and result['calls'] < session.limits['max_calls']


def test_valid_pagination_counts_as_progress(session):
    class Pager(Provider):
        def call(self, role, prompt, data, schema):
            if role != 'task_navigation':
                return super().call(role, prompt, data, schema)
            self.turn += 1
            a = (action('LIST', term_ids=['A'], offset=(self.turn-1)*8) if self.turn < 3
                 else action('STOP', status='incomplete', unresolved=['검토 전 종료']))
            return {'actions': [a]}, {'fixture': True}
    session.limits['max_no_progress'] = 1
    result = session.run(Pager())
    assert result['known_source_ids'] == [f's{i:02}' for i in range(12)]
    assert not any('NO_PROGRESS' in s for s in result['stop']['unresolved'])


def test_budget_includes_interpretation_and_semantic_review(session):
    session.limits['max_calls'] = 6
    result = session.run(Provider())
    assert result['calls'] == 6 and result['status'] == 'STOP'
    assert len(result['adopted']) == 1
    assert any('BUDGET' in s for s in result['stop']['unresolved'])


def test_provider_failures_retry_within_shared_budget(session):
    class Broken:
        def call(self, *args):
            raise RuntimeError('fixture unavailable')
    result = session.run(Broken())
    assert result['calls'] == 3 and result['task_state']['errors'] == 3
    assert result['status'] == 'STOP' and result['failure']['type'] == 'RuntimeError'


def test_unsupported_task_requests_clarification_without_navigation(session):
    class Unsupported:
        def call(self, role, *args):
            assert role == 'task_interpret'
            return {'task_type': 'unsupported', 'concepts': [], 'question_for_user': '설명할 개념을 알려 주세요.'}, {}
    result = session.run(Unsupported())
    assert result['task_state']['phase'] == 'WAITING_USER'
    assert result['question_for_user'] and result['calls'] == 1 and not result['adopted']


def test_bad_semantic_span_never_saved_as_approved_interpretation(session):
    class Bad(Provider):
        def call(self, role, prompt, data, schema):
            value, receipt = super().call(role, prompt, data, schema)
            value['concepts'][0]['text'] = '변조'
            return value, receipt
    result = session.run(Bad())
    assert result['status'] == 'STOP' and session.interpretation is None
    assert result['task_spec']['question_span']['text'] == session.question


def test_definition_requires_review_and_hash_binding(tmp_path):
    db = tmp_path/'definitions.sqlite'
    proposed = p.propose_definition(db, p.DEFAULT)
    binding = {**proposed, 'sha256': sha(db), 'review_sha256': 'missing'}
    with pytest.raises(ValueError, match='reviewed'):
        p.load_definition(db, binding)
    receipt = p.review_definition(db, proposed['id'], proposed['version'], 'fixture reviewer', 'contract test only')
    binding.update(sha256=sha(db), review_sha256=receipt['review_sha256'])
    loaded = p.load_definition(db, binding)
    with pytest.raises(sqlite3.IntegrityError):
        p.propose_definition(db, p.DEFAULT)
    new = deepcopy(p.DEFAULT)
    new['version'] = 2
    new['obligations'][0]['text'] = '새 정의 확인'
    p.propose_definition(db, new)
    assert loaded['version'] == 1
    with pytest.raises(ValueError, match='DB hash'):
        p.load_definition(db, binding)


def test_unsupported_db_operators_and_budget_escalation_rejected():
    for key, value in [('completion', 'eval(code)'), ('tools', {'SQL': 'query'})]:
        definition = deepcopy(p.DEFAULT)
        definition[key] = value
        with pytest.raises(ValueError):
            p.validate_definition(definition)
    definition = deepcopy(p.DEFAULT)
    definition['limits']['max_calls'] = 999
    with pytest.raises(ValueError, match='ceiling'):
        p.validate_definition(definition)


def test_policy_path_escape_rejected(tmp_path):
    with pytest.raises(ValueError):
        p.load_bound_definition(tmp_path, {'path': '../escape.sqlite'})
