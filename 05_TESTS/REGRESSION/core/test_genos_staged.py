"""Synthetic functional contracts only; no real LLM quality/latency claims."""
import copy
import json
import sqlite3

import pytest

from .test_genos_build import Fake, setup
from lawrag.pipeline import genos_build as build
from lawrag.pipeline.genos_staged import STAGES, GROUPS, stage_schema


class StagedFake(Fake):
    bad_stage = None
    failure = None
    failures = 1
    def request(self, kind, path, payload, role):
        raw, receipt = super().request(kind, path, payload, role)
        body = self.calls[-1]
        if '_staged' not in body:
            return raw, receipt
        stage = body['_staged']['stage']
        result = json.loads(raw['choices'][0]['message']['content'])
        value = {'coverage': result['coverage']} if stage == 'extract' else {'graph': {k: result['graph'][k] for k in GROUPS[stage]}}
        count = sum(x.get('_staged', {}).get('stage') == stage for x in self.calls)
        if stage == self.bad_stage and count <= self.failures:
            if self.failure == 'schema':
                value = {'wrong': []}
            elif self.failure == 'predicate':
                value['graph']['clauses'][0]['role_bindings'] = []
            elif self.failure == 'semantic':
                value['graph']['clauses'][0]['role_bindings'][0]['unresolved_reason'] = 'invalid with RESOLVED'
            elif self.failure == 'length':
                raw['choices'][0]['finish_reason'] = 'length'
        raw['choices'][0]['message']['content'] = json.dumps(value)
        return raw, receipt


def run(args, logs=None):
    args.extraction_mode = 'staged'
    return build.execute(args, provider_factory=StagedFake, emit=(logs.append if logs is not None else lambda s: None))


def stages(fake):
    return [b.get('_staged', {}).get('stage', 'review') for b in fake.calls]


def test_full_staged_e2e_and_receipts(setup):
    args, _, out = setup
    logs = []
    result = run(args, logs)
    assert result['ok'] and result['data_status'] == 'DRAFT' and not result['activated']
    assert stages(Fake.instances[-1]) == [*STAGES, 'review']
    receipt = json.loads(next((out / 'handoff').glob('*.review.json')).read_text())['staged_extraction']
    assert receipt['assembly'] == 'HOST_DETERMINISTIC_MERGE'
    assert [r['stage'] for r in receipt['receipts']] == list(STAGES)
    assert all(r['response']['model'] == 'fake-model' for r in receipt['receipts'])
    assert any('문장 의미·역할' in line for line in logs)
    args.resume = True
    assert run(args)['ok'] and not Fake.instances[-1].calls


@pytest.mark.parametrize('stage', STAGES)
def test_only_failed_stage_retries(setup, monkeypatch, stage):
    args, _, out = setup
    monkeypatch.setattr(StagedFake, 'bad_stage', stage)
    monkeypatch.setattr(StagedFake, 'failure', 'schema')
    assert run(args)['ok']
    called = stages(Fake.instances[-1])
    assert called.count(stage) == 2
    assert all(called.count(s) == 1 for s in STAGES if s != stage)


def test_budget_resume_keeps_completed_stages(setup):
    args, _, out = setup
    args.max_calls = 2
    with pytest.raises(ValueError, match='authoring incomplete'):
        run(args)
    assert stages(Fake.instances[-1]) == list(STAGES[:2])
    assert not Fake.instances[-1].batches and not (out / 'generation').exists()
    args.resume = True
    args.max_calls = 10
    assert run(args)['ok']
    assert stages(Fake.instances[-1]) == [*STAGES[2:], 'review']


def test_partial_never_admitted(setup, monkeypatch):
    args, _, out = setup
    monkeypatch.setattr(StagedFake, 'bad_stage', 'extract_clauses')
    monkeypatch.setattr(StagedFake, 'failure', 'schema')
    monkeypatch.setattr(StagedFake, 'failures', 99)
    with pytest.raises(ValueError, match='authoring incomplete'):
        run(args)
    assert stages(Fake.instances[-1]) == [STAGES[0], *([STAGES[1]] * args.max_attempts)]
    assert not Fake.instances[-1].batches and not (out / 'generation').exists()


def test_ssot_stage_projection():
    module = build.authoring()
    full = module.extraction_schema(module.contract_module().profile_schema('OBSERVATION', build.ROOT))
    owned = []
    for stage in STAGES:
        schema = stage_schema(full, stage)
        module.check_schema(schema)
        owned += list(GROUPS[stage])
        assert 'SemanticGraph' not in schema['$defs']
        if stage != 'extract':
            for key in GROUPS[stage]:
                assert schema['properties']['graph']['properties'][key] == full['$defs']['SemanticGraph']['properties'][key]
    assert set(owned) == set(full['$defs']['SemanticGraph']['properties']) - {'crosswalk'}


def test_receipt_corruption_blocks_resume_before_call(setup):
    args, _, out = setup
    args.max_calls = 1
    with pytest.raises(ValueError, match='authoring incomplete'):
        run(args)
    with sqlite3.connect(out / 'queue/queue.sqlite') as db:
        db.execute("update attempt set response=response || ' ' where stage='extract_vocabulary'")
    args.resume = True
    with pytest.raises(RuntimeError, match='RECEIPT_HASH'):
        run(args)
    assert not Fake.instances[-1].calls and not (out / 'generation').exists()


def test_received_stage_recovers_without_repeating_call(setup):
    args, _, out = setup
    args.max_calls = 1
    with pytest.raises(ValueError, match='authoring incomplete'):
        run(args)
    q = build.queue_adapter(build.authoring(), out / 'queue', lambda _: None)
    attempt = q.claim()
    assert attempt['stage'] == 'extract_clauses'
    fake = StagedFake()
    raw, _ = fake.request('llm', '/chat/completions', attempt['request'], 'synthetic')
    q.received(attempt, json.dumps(raw), 0.01)
    args.resume = True
    args.max_calls = 10
    assert run(args)['ok']
    assert stages(Fake.instances[-1]) == ['extract_rules', 'extract', 'review']


def test_review_failure_invalidates_dependent_checkpoints(setup, monkeypatch):
    args, _, out = setup
    monkeypatch.setattr(Fake, 'reject_once', True)
    assert run(args)['ok']
    assert stages(Fake.instances[-1]) == [*STAGES, 'review', *STAGES, 'review']
    with sqlite3.connect(out / 'queue/queue.sqlite') as db:
        assert db.execute('select count(*) from attempt').fetchone()[0] == 10
        assert db.execute('select min(attempt_id) from stage_checkpoint').fetchone()[0] == 6


def test_full_semantic_validation_does_not_admit_shape_only(setup, monkeypatch):
    args, _, out = setup
    monkeypatch.setattr(StagedFake, 'bad_stage', 'extract_clauses')
    monkeypatch.setattr(StagedFake, 'failure', 'semantic')
    assert run(args)['ok']
    with sqlite3.connect(out / 'queue/queue.sqlite') as db:
        errors = [r[0] for r in db.execute("select error from attempt where state='INVALID'")]
    assert any('STAGED_FULL_VALIDATION:' in e for e in errors)
    assert stages(Fake.instances[-1]).count('review') == 1


def test_stage_length_increases_only_its_budget(setup, monkeypatch):
    args, _, out = setup
    monkeypatch.setattr(StagedFake, 'bad_stage', 'extract_clauses')
    monkeypatch.setattr(StagedFake, 'failure', 'length')
    args.max_output_tokens = args.max_tokens * 2
    assert run(args)['ok']
    with sqlite3.connect(out / 'queue/queue.sqlite') as db:
        calls = [(s, json.loads(r)['max_tokens']) for s, r in db.execute('select stage,request from attempt order by id')]
    assert [n for s, n in calls if s == 'extract_clauses'] == [args.max_tokens, args.max_tokens * 2]
    assert all(n == args.max_tokens for s, n in calls if s != 'extract_clauses')


def test_export_receipts_hashes_reconstruct_exact_bodies(setup):
    import hashlib
    args, _, out = setup
    run(args)
    receipt = json.loads(next((out / 'handoff').glob('*.review.json')).read_text())
    q = build.queue_adapter(build.authoring(), out / 'queue', lambda _: None)
    chain = receipt['staged_extraction']
    with q.connect(readonly=True) as db:
        observation = json.loads(db.execute('select candidate from job').fetchone()[0])
    assert observation['provenance']['provider_receipt_sha256'] == build.authoring().digest(chain)
    for r in chain['receipts']:
        assert hashlib.sha256(r['response_text'].encode()).hexdigest() == r['response_sha256']
        assert json.loads(r['response_text']) == r['response']


def test_main_cli_is_same_genos_data_entrypoint():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, str(build.ROOT / '06_TOOLS/pipeline.py'), 'build-data', '--help'], capture_output=True, text=True)
    assert result.returncode == 0
    assert '--extraction-mode staged' in result.stdout and '모델을 호출하지 않습니다' in result.stdout
