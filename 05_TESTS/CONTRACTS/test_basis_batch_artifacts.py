"""Copied-source transfer and live reporting; no model calls."""
from contextlib import closing
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import zipfile

import pytest
from test_authority import service, generation, WHO, BODY, review_body
from semantic_runtime.basis_links.contracts import digest, BasisError
from semantic_runtime.basis_links.repository import Repository
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.basis_links.resolver import snapshot, targets
from lawrag.pipeline.search_selection import plan as select_plan, activate
from lawrag.pipeline import basis_batch_artifacts as art
from test_ingress import app as historical_app

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/basis_transfer_report_20261020_r1'


@pytest.fixture
def app(tmp_path, generation, monkeypatch):
    # The historical fixture predates the mandatory latest-version selection.
    # Prepare its synthetic input using the real selection API, keeping the
    # current service check enabled and the historical fixture source unchanged.
    import test_ingress
    original = test_ingress.create_app
    def selected_app(root, selected, *args, **kwargs):
        activate(select_plan(selected, latest=True))
        return original(root, selected, *args, **kwargs)
    monkeypatch.setattr(test_ingress, 'create_app', selected_app)
    yield from historical_app.__wrapped__(tmp_path, generation)


@pytest.fixture
def pilot(tmp_path, generation):
    activate(select_plan(generation, latest=True))
    runtime = tmp_path / 'dev-runtime'
    job = runtime / 'basis-batch/pilot-20261020-r1'
    job.mkdir(parents=True)
    repo = Repository(runtime / 'basis-links/authority.sqlite')
    with closing(art.Store(generation)) as store:
        pin = art.source_pin(store)
        row = store.db.execute('SELECT name,source_artifact_sha256 FROM document WHERE document_id="inside"').fetchone()
        p = {'schema_version': 'basis-batch-v1', 'batch_id': 'test-batch', 'binding': {**pin, 'principal': WHO},
             'documents': [{'document_id': 'inside', 'name': row[0], 'source_artifact_sha256': row[1]}]}
        p['plan_sha256'] = digest(p)
        art.atomic(job / 'PLAN.json', p)
        state = {'plan_sha256': p['plan_sha256'], 'status': 'running', 'documents': {'inside': {'status': 'running'}}}
        state['state_sha256'] = digest(state)
        art.atomic(job / 'STATE.json', state)
        run_id = next(iter(art.batch_run_ids(p)))
        provenance = {'type': 'MODEL_OBSERVATION', 'method': 'BATCH_DISCOVERY_V1',
                      'run_id': run_id, 'retrieval_role': 'UNREVIEWED_CANDIDATE'}
        svc = Service(repo, SourcePort(store))
        a = svc.propose(WHO, {**BODY, 'provenance': provenance, 'reason': "선택 조항의 승인 기준 비교\n둘째 줄 '<script>alert(1)</script>"})
        b = svc.propose(WHO, {**BODY, 'request_id': 'b', 'provenance': {**provenance, 'run_id': 'another'}})
        c = svc.propose(WHO, {**BODY, 'request_id': 'c', 'provenance': {'type': 'USER_SELECTION'}})
    repo.close()
    return {'generation': generation, 'runtime': runtime, 'job': job, 'plan': p,
            'id': a['link']['link_id'], 'unrelated': [b['link']['link_id'], c['link']['link_id']]}


def capture(pilot):
    return approve(art.capture(pilot['job'], pilot['generation'], pilot['runtime']))


def approve(value):
    if not value['items']:
        return value
    decision = {'schema_version': 'basis-import-review-v1', 'decision': 'APPROVE_IMPORT',
                'source_snapshot_sha256': value['snapshot_sha256'],
                'link_ids': [v['link']['link_id'] for v in value['items']],
                'reviewed_by': 'test-operator', 'reviewed_at': '2026-10-20T00:00:00Z'}
    decision['review_sha256'] = digest(decision)
    return art.reviewed(value, decision)


def resigned(value):
    value['snapshot_sha256'] = digest({k: v for k, v in value.items() if k != 'snapshot_sha256'})
    return value


def test_live_report_is_exact_read_only_and_no_hash_scan(pilot, tmp_path, monkeypatch):
    import semantic_runtime.storage as storage
    monkeypatch.setattr(storage, 'verify_store_binding', lambda *a: pytest.fail('whole source checksum'))
    db_path = pilot['runtime'] / 'basis-links/authority.sqlite'
    before = db_path.read_bytes()
    with (pilot['job'] / 'batch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        value = capture(pilot)
    assert [i['link']['link_id'] for i in value['items']] == [pilot['id']]
    assert value['batch_status'] == 'running'
    assert value['items'][0]['source_check']['status'] == 'verified'
    assert value['items'][0]['retrievable']
    output = tmp_path / 'LINKS.html'
    art.report(value, output)
    html = output.read_text()
    assert '중간 결과' in html and '미검토 후보' in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html and '<script>' not in html
    assert '모의내규' in html and '모의외규' in html and '영업일에 승인을 받는다.' in html
    assert html.count('<tr><td class="number">') == 1
    assert db_path.read_bytes() == before
    assert not (pilot['runtime'] / 'basis-links/SQLITE_ENABLED.json').exists()


def test_running_run_identity_matches_real_runtime(pilot):
    from workflow.contracts import digest as wdigest
    p = pilot['plan']
    ident = wdigest([{k: WHO[k] for k in ('user_id', 'team_id')}, 'basis-batch:' + p['batch_id'],
                    'basis-batch:' + digest([p['batch_id'], 'inside'])])[:32]
    assert art.batch_run_ids(p) == {ident}


def test_copy_to_other_path_import_reuse_and_real_resolver(pilot, tmp_path):
    value = capture(pilot)
    copied = tmp_path / 'prod-data' / pilot['generation'].name
    copied.parent.mkdir()
    shutil.copytree(pilot['generation'], copied)
    shutil.copytree(pilot['generation'].parent / 'SEARCH_SELECTION', copied.parent / 'SEARCH_SELECTION')
    runtime = tmp_path / 'prod-runtime'
    assert art.apply(value, art.sql(value), copied, runtime, check=True)['insert'] == 1
    assert not runtime.exists()
    result = art.apply(value, art.sql(value), copied, runtime)
    assert result['inserted'] == [pilot['id']]
    assert art.apply(value, art.sql(value), copied, runtime)['status'] == 'already_applied'
    with art.authority(runtime / 'basis-links/authority.sqlite') as repo, art.source(copied, value['source'], WHO) as (sources, who):
        assert repo.head(pilot['id'])['status'] == 'PROPOSED'
        service = Service(repo, sources)
        actual = targets(service, who, snapshot(service, who, ['inside']))
        assert len(actual) == 1 and actual[0]['link_id'] == pilot['id']
        assert repo.db.execute('SELECT count(*) FROM basis_document_lookup').fetchone()[0] == 2
        assert repo.db.execute('SELECT count(*) FROM basis_head').fetchone()[0] == 1
    assert art.read_json(runtime / 'basis-links/SQLITE_ENABLED.json') == art.MARKER


def test_existing_identical_skips_and_rollback_preserves(pilot):
    value = capture(pilot)
    r = art.apply(value, art.sql(value), pilot['generation'], pilot['runtime'])
    assert r['inserted'] == [] and r['skipped'] == [pilot['id']]
    assert art.rollback(value, pilot['runtime'])['revoked'] == []
    with art.authority(pilot['runtime'] / 'basis-links/authority.sqlite') as repo:
        assert repo.head(pilot['id'])['status'] == 'PROPOSED'
        assert all(repo.head(i) for i in pilot['unrelated'])


def test_rollback_revokes_only_imported_and_is_idempotent(pilot, tmp_path):
    value = capture(pilot)
    runtime = tmp_path / 'prod'
    art.apply(value, art.sql(value), pilot['generation'], runtime)
    assert art.rollback(value, runtime)['status'] == 'rolled_back'
    assert art.rollback(value, runtime)['status'] == 'already_rolled_back'
    with art.authority(runtime / 'basis-links/authority.sqlite') as repo, art.source(pilot['generation'], value['source'], WHO) as (sources, who):
        assert repo.head(pilot['id'])['status'] == 'REVOKED'
        assert len(repo.history(pilot['id'])['revisions']) == 2
        assert targets(Service(repo, sources), who, snapshot(Service(repo, sources), who, ['inside'])) == []
    with pytest.raises(BasisError, match='원복'):
        art.apply(value, art.sql(value), pilot['generation'], runtime)


def test_later_review_blocks_import_and_rollback(pilot, tmp_path):
    value = capture(pilot)
    runtime = tmp_path / 'prod'
    art.apply(value, art.sql(value), pilot['generation'], runtime)
    with art.authority(runtime / 'basis-links/authority.sqlite', write=True) as repo, art.source(pilot['generation'], value['source'], WHO) as (sources, who):
        svc = Service(repo, sources)
        view = svc.list(who, 'inside')['items'][0]
        assert svc.review(who, review_body(view))['status'] == 'completed'
    with pytest.raises(BasisError, match='변경'):
        art.rollback(value, runtime)
    with pytest.raises(BasisError, match='다른 상태'):
        art.apply(value, art.sql(value), pilot['generation'], runtime)


@pytest.mark.parametrize('stage', ['before_commit', 'after_commit'])
def test_commit_failure_recovery_without_duplicate(pilot, tmp_path, stage):
    value = capture(pilot)
    runtime = tmp_path / 'prod'
    def fail(phase):
        if phase == stage:
            raise OSError('injected')
    with pytest.raises(OSError):
        art.apply(value, art.sql(value), pilot['generation'], runtime, hook=fail)
    st = art.status(value, runtime)
    assert st['status'] == ('not_applied' if stage == 'before_commit' else 'applied')
    result = art.apply(value, art.sql(value), pilot['generation'], runtime)
    assert result['status'] == ('applied' if stage == 'before_commit' else 'already_applied')
    assert art.status(value, runtime)['marker_enabled']


def test_multiple_link_conflict_is_all_or_nothing(pilot, tmp_path):
    value = capture(pilot)
    runtime = tmp_path / 'prod'
    art.apply(value, art.sql(value), pilot['generation'], runtime)
    broken = deepcopy(value)
    broken['items'][0]['link']['reason'] = 'changed'
    broken['items'][0]['history']['revisions'][-1]['reason'] = 'changed'
    resigned(broken)
    with pytest.raises(BasisError, match='다른 상태'):
        art.apply(broken, art.sql(broken), pilot['generation'], runtime)
    assert art.status(broken, runtime)['status'] == 'not_applied'


@pytest.mark.parametrize('kind', ['sql', 'hash', 'span', 'metadata', 'team', 'generation'])
def test_tamper_and_permissions_rejected_before_mutation(pilot, tmp_path, kind):
    value = capture(pilot)
    if kind == 'hash':
        value['batch_id'] = 'changed'
    elif kind == 'span':
        value['items'][0]['history']['revisions'][0]['internal'][0]['spans'][0]['text'] = 'wrong'
        resigned(value)
    elif kind == 'metadata':
        value['document_hashes']['inside'] = '0' * 64
        resigned(value)
    elif kind == 'team':
        value['principal']['team_id'] = 'other_team'
        resigned(value)
    elif kind == 'generation':
        value['source']['generation_id'] = 'wrong'
        resigned(value)
    script = art.sql(value) + ('DELETE FROM basis_head;\n' if kind == 'sql' else '')
    runtime = tmp_path / 'prod'
    with pytest.raises((BasisError, ValueError)):
        art.apply(value, script, pilot['generation'], runtime)
    assert not runtime.exists()


def test_raw_sql_cannot_skip_source_validation(pilot):
    value = capture(pilot)
    with sqlite3.connect(':memory:') as db, pytest.raises(sqlite3.OperationalError, match='basis_transfer_guard'):
        db.executescript(art.sql(value))


def test_empty_report_and_export_refusal(pilot, tmp_path):
    with art.authority(pilot['runtime'] / 'basis-links/authority.sqlite', write=True) as repo:
        repo.db.execute('DELETE FROM basis_head')
    value = capture(pilot)
    art.report(value, tmp_path / 'empty.html')
    assert '현재 저장된 연결이 없습니다' in (tmp_path / 'empty.html').read_text()
    with pytest.raises(BasisError):
        art.export_bundle(value, tmp_path / 'bundle', KIT)


def test_lineage_effectivity_preserved(pilot, tmp_path):
    with art.authority(pilot['runtime'] / 'basis-links/authority.sqlite', write=True) as repo:
        link = repo.head(pilot['id'])
        repo.register_lineage({'version_id': 'outside', 'family_id': 'outside-family',
                               'source_artifact_hash': link['external'][0]['source_artifact_hash'],
                               'provenance': {'type': 'USER_SELECTION'}, 'effective_from': '2999-01-01'})
    value = capture(pilot)
    assert not value['items'][0]['retrievable']
    runtime = tmp_path / 'prod'
    art.apply(value, art.sql(value), pilot['generation'], runtime)
    with art.authority(runtime / 'basis-links/authority.sqlite') as repo:
        assert repo.lineage('outside')['effective_from'] == '2999-01-01'


def test_symlink_paths_fail_closed(pilot, tmp_path):
    link = tmp_path / 'alias'
    link.symlink_to(pilot['job'], target_is_directory=True)
    with pytest.raises(BasisError):
        art.capture(link, pilot['generation'], pilot['runtime'])


def test_real_handoff_and_generated_production_script(pilot, tmp_path):
    # Exact extracted ZIP -> script -> real source/authority/resolver.
    transfer = tmp_path / 'TRANSFER'
    transfer.mkdir()
    name = 'GENOS_BASIS_ARTIFACTS_20261020_R1'
    with zipfile.ZipFile(KIT / (name + '.zip')) as z:
        assert not any(Path(n).suffix.lower() in ('.js', '.jsx', '.mjs', '.cjs') for n in z.namelist())
        z.extractall(transfer / name)
    code = tmp_path / 'checkout'
    frozen = ROOT / '09_ARTIFACTS/AUDITS/20261020-basis-transfer-report/validation-code'
    shutil.copytree(frozen, code)
    home = tmp_path / 'home'
    home.mkdir()
    (home / 'DEV').symlink_to(code, target_is_directory=True)
    config = {'generation': str(pilot['generation']), 'runtime': str(pilot['runtime'])}
    art.atomic(code / '00_SYSTEM/GENOS_SERVING_PATHS.json', config)
    env = {**os.environ, 'HOME': str(home), 'PATH': str(ROOT / '.venv/bin') + ':' + os.environ['PATH'],
           'PYTHONDONTWRITEBYTECODE': '1'}
    trace = []
    def command(args, expect=0):
        cp = subprocess.run(args, cwd=transfer, env=env, capture_output=True, text=True, timeout=60)
        trace.append({'args': [str(a) for a in args], 'exit': cp.returncode, 'output': cp.stdout + cp.stderr})
        assert (cp.returncode == 0) == (expect == 0), trace[-1]
        return cp
    script = transfer / name / (name + '_RUN.txt')
    before = (pilot['job'] / 'STATE.json').read_bytes()
    command(['bash', str(script), 'report', '--output', str(transfer / 'LIVE.html')])
    command(['bash', str(script), 'export', '--output', str(transfer / 'RELATIONS_OUT')])
    assert (pilot['job'] / 'STATE.json').read_bytes() == before
    generated = transfer / 'RELATIONS_OUT/APPLY_RELATIONS.txt'
    command(['bash', str(generated), 'check', '--local-validation'], expect=1)
    command(['bash', str(generated), 'review', '--all'])
    # The generated portable archive must work independently of the initial kit.
    moved = tmp_path / 'OPERATING_TRANSFER'
    moved.mkdir()
    with zipfile.ZipFile(transfer / 'RELATIONS_OUT_REVIEWED.zip') as z:
        z.extractall(moved)
    runtime = tmp_path / 'production-runtime'
    config['runtime'] = str(runtime)
    art.atomic(code / '00_SYSTEM/GENOS_SERVING_PATHS.json', config)
    prod = moved / 'RELATIONS_OUT/APPLY_RELATIONS.txt'
    command(['bash', str(prod), 'check', '--local-validation'])
    assert not runtime.exists()
    command(['bash', str(prod), 'apply', '--local-validation'])
    command(['bash', str(prod), 'apply', '--local-validation'])
    command(['bash', str(prod), 'status'])
    command(['bash', str(prod), 'rollback', '--local-validation'])
    command(['bash', str(prod), 'rollback', '--local-validation'])
    command(['bash', str(prod), 'apply', '--local-validation'], expect=1)
    # Code and SQL tampering must be visible failures.
    sqlpath = moved / 'RELATIONS_OUT/REVIEWED.sql'
    sqlpath.write_text(sqlpath.read_text() + 'DELETE FROM basis_head;\n')
    command(['bash', str(prod), 'check', '--local-validation'], expect=1)
    (code / '02_BACKEND/semantic_runtime/basis_links/resolver.py').write_text('# changed\n')
    command(['bash', str(script), 'report'], expect=1)
    art.atomic(tmp_path / 'EXECUTION_TRACE.json', trace)
    assert (transfer / 'LIVE.html').is_file()


def test_apply_requires_explicit_review_and_review_is_bound(pilot, tmp_path):
    raw = art.capture(pilot['job'], pilot['generation'], pilot['runtime'])
    with pytest.raises(BasisError, match='검토'):
        art.apply(raw, art.sql(raw), pilot['generation'], tmp_path / 'prod')
    decision = art.review(raw, tmp_path / 'REVIEW.json', accept_all=True)
    assert art.review(raw, tmp_path / 'REVIEW.json', accept_all=True) == decision
    changed = deepcopy(raw)
    changed['batch_status'] = 'changed'
    resigned(changed)
    with pytest.raises(BasisError):
        art.reviewed(changed, decision)
    assert not (tmp_path / 'prod').exists()


def test_json_candidates_are_not_written_to_shared_sqlite(pilot, tmp_path):
    from lawrag.pipeline.basis_batch_candidates import JsonRepository
    candidates = tmp_path / 'candidate-job'
    candidates.mkdir()
    p = deepcopy(pilot['plan'])
    p['candidate_storage'] = {'kind': 'json-candidates-v1', 'path': str(candidates / 'CANDIDATES.json')}
    p['plan_sha256'] = digest({k: v for k, v in p.items() if k != 'plan_sha256'})
    art.atomic(candidates / 'PLAN.json', p)
    dbpath = pilot['runtime'] / 'basis-links/authority.sqlite'
    dbbefore = dbpath.read_bytes()
    pin = {k: p['binding'][k] for k in ('generation_id', 'manifest_sha256', 'store_sha256', 'selection_sha256')}
    with art.source(pilot['generation'], pin, WHO) as (sources, who):
        repo = JsonRepository(candidates / 'CANDIDATES.json', writable=True)
        svc = Service(repo, sources)
        prov = {'type': 'MODEL_OBSERVATION', 'method': 'BATCH_DISCOVERY_V1',
                'run_id': next(iter(art.batch_run_ids(p))), 'retrieval_role': 'UNREVIEWED_CANDIDATE'}
        first = svc.propose(who, {**BODY, 'provenance': prov})
        assert svc.propose(who, {**BODY, 'provenance': prov}) == first
        reloaded = JsonRepository(candidates / 'CANDIDATES.json')
        assert reloaded.head(first['link']['link_id']) == first['link']
    assert dbpath.read_bytes() == dbbefore
    assert not (candidates / 'authority.sqlite').exists()
    raw = art.capture(candidates, pilot['generation'], pilot['runtime'])
    assert raw['storage'] == 'json_candidates_not_published'
    assert [x['link']['link_id'] for x in raw['items']] == [first['link']['link_id']]
    art.report(raw, tmp_path / 'staged.html')
    assert '아직 적용하지 않았습니다' in (tmp_path / 'staged.html').read_text()
    approved = approve(raw)
    art.apply(approved, art.sql(approved), pilot['generation'], tmp_path / 'prod')
    assert dbpath.read_bytes() == dbbefore


def test_json_transaction_failure_and_hash_conflict(pilot, tmp_path, monkeypatch):
    from lawrag.pipeline.basis_batch_candidates import JsonRepository
    import lawrag.pipeline.basis_batch_candidates as candidates
    repo = JsonRepository(tmp_path / 'CANDIDATES.json', writable=True)
    pin = {k: pilot['plan']['binding'][k] for k in ('generation_id', 'manifest_sha256', 'store_sha256', 'selection_sha256')}
    with art.source(pilot['generation'], pin, WHO) as (sources, who):
        svc = Service(repo, sources)
        original_replace = candidates.os.replace
        monkeypatch.setattr(candidates.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('injected')))
        with pytest.raises(OSError):
            svc.propose(who, BODY)
        assert not repo.path.exists() and not repo.data['links']
        monkeypatch.setattr(candidates.os, 'replace', original_replace)
        p = svc.propose(who, BODY)
        assert svc.propose(who, BODY) == p
        with pytest.raises(BasisError):
            svc.propose(who, {**BODY, 'reason': 'different'})
        repo.path.write_text(repo.path.read_text().replace('PROPOSED', 'APPROVED'))
        with pytest.raises(BasisError, match='해시'):
            JsonRepository(repo.path)


def test_actual_workflow_api_only_publishes_json_candidates(app, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from test_basis_batch import link_transport
    from lawrag.pipeline.basis_batch_candidates import factory, JsonRepository
    calls = link_transport(app, monkeypatch)
    path = tmp_path / 'review-job/CANDIDATES.json'
    shared = app.state.workflow_runtime.services.runtime / 'basis-links/authority.sqlite'
    assert not shared.exists()
    app.state.pipeline.basis_factory = factory(app, path)
    body = {'workflow_id': 'internal_basis_discovery_workflow', 'session_id': 'json-review',
            'request_id': 'same', 'input': {'internal_document_id': 'inside',
                'scope_policy': 'parent-overlap-v1', 'publish_candidates': True}}
    with TestClient(app) as client:
        response = client.post('/v1/workflows/run', json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['status'] == 'completed' and result['basis_link_ids'], result
        count = len(calls)
        again = client.post('/v1/workflows/run', json=body).json()
        assert again['basis_link_ids'] == result['basis_link_ids'] and len(calls) == count
    repo = JsonRepository(path)
    assert repo.head(result['basis_link_ids'][0])['status'] == 'PROPOSED'
    assert not shared.exists()
    assert not shared.with_name('SQLITE_ENABLED.json').exists()


def test_stage_batch_run_and_resume_port_use_existing_runner(app, tmp_path):
    from lawrag.pipeline.basis_batch_candidates import factory
    import importlib.util
    spec = importlib.util.spec_from_file_location('sealed_batch', KIT / 'basis_batch.py')
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    app.state.workflow_runtime.services.release = {'mode': 'local-release'}
    value, _ = batch.plan(app, 'risk_team')
    job = tmp_path / 'stage-job'
    job.mkdir()
    value['candidate_storage'] = {'kind': 'json-candidates-v1', 'path': str(job / 'CANDIDATES.json')}
    value['plan_sha256'] = digest({k: v for k, v in value.items() if k != 'plan_sha256'})
    with pytest.raises(BasisError, match='stage-run'):
        batch.run(app, value, job, use_llm=False)
    kwargs = {'use_llm': False, 'candidate_factory': factory(app, job / 'CANDIDATES.json')}
    state = batch.run(app, value, job, **kwargs)
    again = batch.run(app, value, job, resume=True, **kwargs)
    assert state['status'] == 'completed' and again['documents'] == state['documents']
    assert state['documents']['inside']['usage']['model_reserved'] == 0
    assert not (app.state.workflow_runtime.services.runtime / 'basis-links/authority.sqlite').exists()


def test_uploaded_stage_plan_actual_service_boot(tmp_path, generation):
    from lawrag.pipeline.fulltext_stage import derive
    selected = tmp_path / 'native-generation'
    derive(generation, selected, workers=1)
    activate(select_plan(selected, latest=True))
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    with zipfile.ZipFile(ROOT / '08_DEPLOYMENT/GENOS/handoffs/main92_cumulative_20261020_r1/code.zip') as z:
        z.extractall(checkout)
    frozen = ROOT / '09_ARTIFACTS/AUDITS/20261020-basis-transfer-report/validation-code'
    for path in frozen.rglob('*'):
        if path.is_file():
            target = checkout / path.relative_to(frozen)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    home = tmp_path / 'home'
    home.mkdir()
    (home / 'DEV').symlink_to(checkout, target_is_directory=True)
    runtime = tmp_path / 'runtime'
    art.atomic(checkout / '00_SYSTEM/GENOS_SERVING_PATHS.json',
               {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed',
                'generation': str(selected), 'runtime': str(runtime),
                'generation_manifest_sha256': hashlib.sha256((selected / 'manifest.json').read_bytes()).hexdigest()})
    transfer = tmp_path / 'TRANSFER'
    transfer.mkdir()
    name = 'GENOS_BASIS_ARTIFACTS_20261020_R1'
    with zipfile.ZipFile(KIT / (name + '.zip')) as z:
        z.extractall(transfer / name)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('GENOS_', 'SEMANTIC_', 'LEGAL_AGENT_', 'PYTHON', 'LAWRAG_', 'SOURCE_PROVIDER_', 'WORKFLOW_', 'TASK_TEST_'))}
    env.update(HOME=str(home), PATH=str(ROOT / '.venv/bin') + ':' + os.environ['PATH'],
               PYTHONDONTWRITEBYTECODE='1', GENOS_RAG_IMPLEMENTATION='"retired"')
    trace = []
    def call(command, expected=0):
        result = subprocess.run(['bash', str(transfer / name / (name + '_RUN.txt')), command],
                                env=env, cwd=transfer, capture_output=True, text=True, timeout=60)
        trace.append({'command': command, 'exit': result.returncode, 'output': result.stdout + result.stderr})
        assert (result.returncode == 0) == (expected == 0), trace[-1]
    call('stage-plan')
    job = runtime / 'basis-batch/pilot-review-20261020-r1'
    saved = (job / 'PLAN.json').read_bytes()
    p = json.loads(saved)
    assert p['candidate_storage']['kind'] == 'json-candidates-v1'
    assert p['documents'][0]['document_id'] == 'inside'
    call('stage-plan', expected=1)
    assert (job / 'PLAN.json').read_bytes() == saved
    call('report')
    call('stage-run', expected=1)  # No GENOS credentials/model; no fallback.
    assert not (runtime / 'basis-links/authority.sqlite').exists()
    assert not (runtime / 'basis-links/SQLITE_ENABLED.json').exists()
    assert not (job / 'STATE.json').exists()
    art.atomic(tmp_path / 'STAGE_BOOTSTRAP_TRACE.json', trace)
