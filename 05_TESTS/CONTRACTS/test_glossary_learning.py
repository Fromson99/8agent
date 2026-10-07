"""Feature contracts on synthetic data, not retrieval quality experiments."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from semantic_runtime import learning_store as ledger
from semantic_runtime.navigation_learning import LearnedMatcher, bind_learning, validate_bundle
from semantic_runtime.navigation_loop import NavigationSession
from semantic_runtime.contracts import sha
from test_navigation_loop import session
from test_document_release import source


def review_stamp():
    return {'reviewer': 'fixture-reviewer', 'reason': 'synthetic contract', 'event_id': 'review:1',
            'candidate_sha256': 'a'*64, 'evidence': 'synthetic run'}


def bundle():
    return {'schema_version': 'navigation-learning-v1', 'id': 'fixture-bundle',
            'generation_id': 'fixture-generation', 'generation_manifest_sha256': 'b'*64,
            'expressions': [{'id': 'expression:1', 'expression': '돈을 잃을', 'term_id': 'D',
                             'document_version_ids': ['doc'], 'review': review_stamp()}],
            'recipes': [{'id': 'recipe:1', 'document_version_ids': ['doc'], 'trigger_term_ids': ['D'],
                         'required_phrases': [], 'excluded_phrases': ['세금'],
                         'issues': [{'id': 'R1', 'text': '조건과 예외 확인'}], 'require_references': True,
                         'steps': [{'tool': 'OPEN_TERM', 'args': {'term_id': 'D'}},
                                   {'tool': 'GRAPH', 'args': {'term_id': 'D', 'hops': 1}},
                                   {'tool': 'LIST', 'args': {'term_ids': ['D'], 'match': 'all'}}],
                         'review': review_stamp()}]}


def learned(session, value=None, question='돈을 잃을 수 있나요?'):
    value = value or bundle()
    session.m.tools = session.t
    validate_bundle(value, 'fixture-generation', 'b'*64, session.t.terms, session.m.documents)
    matcher = LearnedMatcher(session.m, value)
    return NavigationSession(matcher, session.t, session.g, question, ['doc'])


def test_expression_adds_registered_seed_but_not_evidence(session):
    s = learned(session)
    assert 'D' in s.known_terms
    assert s.learning['matches'][0]['text'] == '돈을 잃을'
    assert not s.read_segments and not s.judgments and not s.history


def test_scope_guard_and_recipe_ambiguity_fall_back(session):
    value = bundle()
    m = LearnedMatcher(session.m, value)
    seeds = m.starts('돈을 잃을 수 있나요?', ['different'])
    assert not seeds['learning']['matches'] and seeds['learning']['recipe'] is None
    assert m.starts('돈을 잃을 때 세금', ['doc'])['learning']['recipe'] is None
    value['recipes'].append({**deepcopy(value['recipes'][0]), 'id': 'recipe:2'})
    assert LearnedMatcher(session.m, value).starts('돈을 잃을', ['doc'])['learning']['recipe_status'] == 'AMBIGUOUS_FALLBACK'


@pytest.mark.parametrize('mutate', [
    lambda b: b['expressions'][0].update(term_id='UNKNOWN'),
    lambda b: b['expressions'][0].update(document_version_ids=['private']),
    lambda b: b['recipes'][0]['steps'].append({'tool': 'JUDGE', 'args': {}}),
    lambda b: b['recipes'][0]['steps'][0]['args'].update(term_id='A'),
    lambda b: b['expressions'].append({**deepcopy(b['expressions'][0]), 'id': 'expr:2', 'term_id': 'A'}),
])
def test_invalid_or_conflicting_bundles_rejected(session, mutate):
    value = bundle(); mutate(value)
    with pytest.raises(ValueError):
        validate_bundle(value, 'fixture-generation', 'b'*64, session.t.terms, session.m.documents)


@pytest.mark.parametrize('question', ['돈을 잃을 수 있나요?', '혹시 돈을 잃을 수도 있어요?'])
def test_same_reviewed_procedure_then_fresh_read_and_judge(session, question):
    s = learned(session, question=question)
    class Provider:
        def __init__(self): self.calls = 0
        def call(self, role, system, data, schema):
            self.calls += 1
            assert 'R1' in data['issues']
            if self.calls == 1:
                assert [r['tool'] for r in data['last_results']] == ['OPEN_TERM', 'GRAPH', 'LIST']
                self.sid = data['last_results'][-1]['result']['items'][0]['id']
                actions = [('READ', {'source_id': self.sid})]
            elif self.calls == 2:
                seg = data['active_segments'][0]
                actions = [('REFERENCES', {'source_id': self.sid}),
                           ('JUDGE', {'segment_id': seg['id'], 'status': 'adopted',
                                      'issue_id': 'R1', 'quote': seg['text'], 'claim': '모의 원문 확인'})]
            else:
                actions = [('STOP', {'status': 'sufficient', 'unresolved': []})]
            return {'issues': [], 'actions': [{'tool': t, 'args': json.dumps(a), 'reason': 'fixture'} for t, a in actions]}, {}
    out = s.run(Provider())
    assert out['failure'] is None and out['status'] == 'FINISH'
    assert out['read_source_ids'] == ['s11'] and out['adopted'][0]['issue_id'] == 'R1'
    assert [r['tool'] for r in out['trace'][:3]] == ['OPEN_TERM', 'GRAPH', 'LIST']
    assert all(r['recipe_id'] == 'recipe:1' for r in out['trace'][:3])


def test_recipe_cannot_skip_reference_lookup_or_issue_evidence(session):
    s = learned(session); s.prepare_recipe()
    with pytest.raises(ValueError): s.execute('STOP', {'status': 'sufficient', 'unresolved': []})
    seg = s.read('s11'); s.delivered.add(seg['id'])
    s.judge(seg['id'], 'adopted', 'R1', seg['text'], 'fixture')
    with pytest.raises(ValueError, match='reference metadata'):
        s.execute('STOP', {'status': 'sufficient', 'unresolved': []})
    s.execute('REFERENCES', {'source_id': 's11'})
    assert s.execute('STOP', {'status': 'sufficient', 'unresolved': []})['status'] == 'sufficient'


def test_recipe_uses_existing_budget(session):
    s = learned(session); s.limits['max_actions'] = 1
    provider = SimpleNamespace(call=lambda *a: pytest.fail('budget already exhausted'))
    out = s.run(provider)
    assert out['actions'] == 1 and out['status'] == 'STOP'
    assert not out['adopted'] and s.learning['recipe_status'] == 'BUDGET_EXHAUSTED'


def test_binding_hash_generation_and_path_guards(session, tmp_path):
    from semantic_runtime.control import copy_learning_bundle
    session.m.tools = session.t
    generation = tmp_path/'generation'; generation.mkdir()
    (generation/'manifest.json').write_text(json.dumps({'generation_id': 'fixture-generation'}))
    value = bundle(); value['generation_manifest_sha256'] = sha(generation/'manifest.json')
    path = tmp_path/'learning.json'; path.write_text(json.dumps(value))
    binding = {'path': 'learning.json', 'sha256': sha(path)}
    assert bind_learning(session.m, binding, tmp_path, generation).starts('돈을 잃을', ['doc'])['learning']['status'] == 'READY'
    prepared = tmp_path/'release-code'
    copy_learning_bundle(binding, tmp_path, prepared, generation, session.t.terms, session.m.documents)
    assert sha(prepared/'learning.json') == binding['sha256']
    assert bind_learning(session.m, binding, prepared, generation).status['status'] == 'READY'
    for bad in [{'path': '../escape', 'sha256': sha(path)}, {**binding, 'sha256': '0'*64}]:
        assert bind_learning(session.m, bad, tmp_path, generation).status['status'] == 'INVALID_BINDING_FALLBACK'
    (generation/'manifest.json').write_text(json.dumps({'generation_id': 'changed'}))
    assert bind_learning(session.m, binding, tmp_path, generation).status['status'] == 'INVALID_BINDING_FALLBACK'


def run_file(tmp_path):
    p = tmp_path/'run.json'
    p.write_text(json.dumps({'query': {'id': 'query:mock', 'question': '영업일 돈을 잃을?',
        'generation_id': 'fixture-generation', 'scope': {'document_version_ids': ['doc']}},
        'answer': {'source_store_sha256': 'c'*64}, 'retrieval': {'term_agent': {
            'matched_question_spans': [{'start': 0, 'end': 3, 'text': '영업일'}]}}}))
    return p


def test_capture_review_publish_revoke_lifecycle(session, tmp_path):
    db = tmp_path/'review.sqlite'; run = run_file(tmp_path)
    ids = ledger.collect_run(db, run)
    assert ids == ledger.collect_run(db, run) and len(ledger.candidates(db)) == 1
    assert ledger.candidates(db)[0]['payload']['expression'] == '돈을 잃을'
    assert ledger.candidates(db)[0]['status'] == 'PROPOSED'
    empty = tmp_path/'empty.json'
    ledger.publish(db, empty, 'fixture-generation', 'b'*64, 'c'*64, session.t.terms, ['doc'])
    assert not json.loads(empty.read_text())['expressions']
    ledger.review(db, ids[0], 'APPROVED', 'operator', '근거 확인', 'D')
    with pytest.raises(ValueError, match='transition'):
        ledger.review(db, ids[0], 'APPROVED', 'operator', 'double approval', 'A')
    output = tmp_path/'approved.json'
    ledger.publish(db, output, 'fixture-generation', 'b'*64, 'c'*64, session.t.terms, ['doc'])
    value = json.loads(output.read_text())
    assert value['expressions'][0]['term_id'] == 'D'
    assert value['expressions'][0]['review']['evidence'] == sha(run)
    with pytest.raises(FileExistsError):
        ledger.publish(db, output, 'fixture-generation', 'b'*64, 'c'*64, session.t.terms, ['doc'])
    with pytest.raises(ValueError, match='store changed'):
        ledger.publish(db, tmp_path/'stale.json', 'fixture-generation', 'b'*64, 'd'*64, session.t.terms, ['doc'])
    ledger.review(db, ids[0], 'REVOKED', 'operator', 'mapping withdrawn')
    new = tmp_path/'revoked.json'
    ledger.publish(db, new, 'fixture-generation', 'b'*64, 'c'*64, session.t.terms, ['doc'])
    assert not json.loads(new.read_text())['expressions']
    assert json.loads(output.read_text()) == value  # historical bundles remain immutable
    replacement = ledger.resubmit(db, ids[0], '의미를 다시 검토')
    assert replacement != ids[0]
    ledger.review(db, replacement, 'APPROVED', 'operator', '정정 연결', 'A')
    corrected = tmp_path/'corrected.json'
    ledger.publish(db, corrected, 'fixture-generation', 'b'*64, 'c'*64, session.t.terms, ['doc'])
    assert json.loads(corrected.read_text())['expressions'][0]['term_id'] == 'A'
    with pytest.raises(ValueError, match='rejected or revoked'):
        ledger.resubmit(db, replacement, 'cannot edit an active approval')


def test_concurrent_collection_and_review_are_serialized(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    db = tmp_path/'review.sqlite'; run = run_file(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ledger.collect_run(db, run), range(8)))
    assert all(r == results[0] for r in results) and len(ledger.candidates(db)) == 1
    def approve(_):
        try:
            ledger.review(db, results[0][0], 'APPROVED', 'reviewer', 'fixture', 'D')
            return 'ok'
        except ValueError:
            return 'already reviewed'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(approve, range(2))) == ['already reviewed', 'ok']


def test_bad_capture_span_or_old_run_is_not_reinterpreted(tmp_path):
    run = run_file(tmp_path); value = json.loads(run.read_text())
    value['retrieval']['term_agent']['matched_question_spans'][0]['text'] = 'invented'
    run.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='span text'):
        ledger.collect_run(tmp_path/'review.sqlite', run)
    value['retrieval']['term_agent'].pop('matched_question_spans')
    run.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='lacks complete matcher'):
        ledger.collect_run(tmp_path/'review.sqlite', run)


def test_http_capture_cli_publish_and_serving_reuse(tmp_path, term_glossary, monkeypatch):
    from semantic_runtime.app import create_app
    from semantic_runtime.provider import Haiku
    from lawrag.pipeline.term_generation import build_generation
    from lawrag.pipeline.glossary_learning import main
    root = Path(__file__).resolve().parents[2]
    # Only copy contracts and code; do not alter any active release or real data.
    contracts = tmp_path/'code'
    for relative in ['00_SYSTEM/PIPELINE.json',
                     '02_BACKEND/lawrag/core/legal_coordinate.py']:
        target = contracts/relative; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/relative, target)
    # Contracts verifies every schema declared by the current pipeline, including
    # legal-agent schemas that are not executed by this navigation-loop fixture.
    pipeline = json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())
    for relative in {c['schema_path'] for c in pipeline['contracts'].values()}:
        target = contracts/relative; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/relative, target)
    for relative in ['02_BACKEND/semantic_runtime', '02_BACKEND/ENGINES/term_runtime']:
        shutil.copytree(root/relative, contracts/relative, ignore=shutil.ignore_patterns('__pycache__'))
    original = source(tmp_path/'source.sqlite', [('doc', '가상법', ['영업일에 관한 모의 원문이다.'])])
    build_generation(original, term_glossary, tmp_path/'built', serving=True)
    generation = tmp_path/'built/generation'
    provider = Haiku(root, tmp_path/'provider', False, backend='fixture', trust_zone='internal')
    # Question-span learning belongs to the navigation loop, not the document MAIN default.
    app = create_app(tmp_path, generation, contracts_root=contracts, provider=provider,
                     implementation='navigation-loop-v1')
    app.state.pipeline.term_agent.config['learning'] = {'capture': True}
    db = tmp_path/'90_RUNTIME/semantic/learning/review.sqlite'
    with TestClient(app) as client:
        req = {'question': '은행 문 여는 날?', 'document_ids': ['doc'], 'use_llm': False}
        first = client.post('/v1/rag/ask', json=req)
        assert first.status_code == 200, first.text
        rows = ledger.candidates(db); assert len(rows) == 1
        ident = rows[0]['id']
        main(['--ledger', str(db), 'review', '--candidate', ident, '--status', 'APPROVED',
              '--term-id', 'fixture:day', '--reviewer', 'operator', '--reason', '모의 문서 범위에서 승인'])
        output = contracts/'learning.json'
        main(['--ledger', str(db), 'publish', '--generation', str(generation), '--output', str(output)])
        app.state.pipeline.term_agent.config['learning']['bundle'] = {'path': 'learning.json', 'sha256': sha(output)}
        second = client.post('/v1/rag/ask', json=req)
        assert second.status_code == 200, second.text
        state = second.json()['retrieval']['term_agent']
        assert state['learning']['matches'][0]['term_id'] == 'fixture:day'
        assert state['selected_ids'] == [] and state['calls'] == 0
        assert len(ledger.candidates(db)) == 1  # approved phrase no longer proposed
        recipe = deepcopy(bundle()['recipes'][0]); recipe.pop('review')
        recipe['trigger_term_ids'] = ['fixture:day']
        recipe['steps'] = [{'tool': 'OPEN_TERM', 'args': {'term_id': 'fixture:day'}},
                           {'tool': 'LIST', 'args': {'term_ids': ['fixture:day'], 'match': 'all'}}]
        recipe_path = tmp_path/'recipe.json'; recipe_path.write_text(json.dumps(recipe))
        main(['--ledger', str(db), 'propose-recipe', '--generation', str(generation),
              '--file', str(recipe_path), '--evidence', 'synthetic contract: definition then source'])
        recipe_id = next(r['id'] for r in ledger.candidates(db) if r['kind'] == 'recipe')
        main(['--ledger', str(db), 'review', '--candidate', recipe_id, '--status', 'APPROVED',
              '--reviewer', 'operator', '--reason', '모의 절차 확인'])
        output2 = contracts/'learning-v2.json'
        main(['--ledger', str(db), 'publish', '--generation', str(generation), '--output', str(output2)])
        app.state.pipeline.term_agent.config['learning']['bundle'] = {'path': 'learning-v2.json', 'sha256': sha(output2)}
        def call(role, system, data, schema):
            if data['active_segments']:
                segment = data['active_segments'][0]
                actions = [('REFERENCES', {'source_id': segment['source_id']}),
                           ('JUDGE', {'segment_id': segment['id'], 'status': 'adopted', 'issue_id': 'R1',
                                      'quote': segment['text'], 'claim': '모의 원문 확인'}),
                           ('STOP', {'status': 'sufficient', 'unresolved': []})]
            else:
                assert [r['tool'] for r in data['last_results']] == ['OPEN_TERM', 'LIST']
                actions = [('READ', {'source_id': data['last_results'][-1]['result']['items'][0]['id']})]
            value = {'issues': [], 'actions': [{'tool': t, 'args': json.dumps(a), 'reason': 'fixture'} for t, a in actions]}
            return value, provider.record_local({'synthetic': True})
        provider.call = call
        third = client.post('/v1/rag/ask', json={**req, 'use_llm': True})
        assert third.status_code == 200, third.text
        state = third.json()['retrieval']['term_agent']
        assert state['learning']['recipe_status'] == 'APPLIED'
        assert state['status'] == 'FINISH' and state['read_source_ids']
        assert third.json()['answer']['claims'][0]['text'] == '모의 원문 확인'
        def unavailable(*args):
            import sqlite3
            raise sqlite3.OperationalError('synthetic database failure')
        monkeypatch.setattr(ledger, 'collect_run', unavailable)
        failed_capture = client.post('/v1/rag/ask', json=req)
        assert failed_capture.status_code == 200
        run_id = failed_capture.json()['run_id']
        assert (tmp_path/'90_RUNTIME/semantic/runs'/f'{run_id}.json').is_file()
