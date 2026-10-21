"""Fixed links share the real JSON/HTML/review/import path; no model calls."""
from contextlib import closing
from copy import deepcopy
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lawrag.pipeline import risk_basis_staging as risk, risk_basis_seed as fixed
from lawrag.pipeline import risk_basis_seed_cli as cli, basis_batch_artifacts as art
from lawrag.pipeline.basis_batch_candidates import JsonRepository, tool_binding
from semantic_runtime.basis_links.contracts import BasisError, digest
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.basis_links.resolver import snapshot, targets
from semantic_runtime.storage import Store

ROOT = Path(__file__).resolve().parents[2]
PHOTO = ROOT / '01_DATA/TERM_RELEASES/risk-photo-0951-r2/named-documents/generation'


@pytest.fixture
def pilot(tmp_path):
    runtime = tmp_path / 'runtime'
    job = runtime / 'basis-batch/pilot-review-20261020-r1'
    job.mkdir(parents=True)
    with closing(Store(PHOTO, verify=False)) as store:
        selected = fixed.resolve(store, {'user_id': 'tester', 'team_id': 'risk_team', 'document_ids': [], 'basis_review': True})
        who = selected['principal']
        plan = {'schema_version': 'basis-batch-v1', 'batch_id': 'fixed-pilot',
                'binding': {**art.source_pin(store), 'generation_path': str(PHOTO), 'runtime': str(runtime), 'principal': who},
                'documents': [{'document_id': selected['internal_document_id'], 'name': '위험관리기준시행세칙'}],
                'candidate_storage': {'kind': 'json-candidates-v1', 'path': str(job / 'CANDIDATES.json'),
                                      'tool': tool_binding(), 'publication': 'manual-review-only'}}
        plan['plan_sha256'] = digest(plan)
        art.atomic(job / 'PLAN.json', plan)
        state = {'plan_sha256': plan['plan_sha256'], 'status': 'running', 'documents': {selected['internal_document_id']: {'status': 'running'}}}
        state['state_sha256'] = digest(state)
        art.atomic(job / 'STATE.json', state)
    return SimpleNamespace(root=tmp_path, runtime=runtime, job=job, plan=plan, who=who,
                           selected=selected, path=job/'CANDIDATES.json')


def run(p, **kwargs):
    return risk.stage(p.job, PHOTO, p.runtime, 'tester', **kwargs)


def add(p, n=0, kind='BASIS', status=None):
    with closing(Store(PHOTO, verify=False)) as store:
        repo = JsonRepository(p.path, writable=True)
        svc = Service(repo, SourcePort(store))
        m = p.selected['links'][n]
        row = svc.propose(p.who, {'request_id': 'fixture-' + str(len(repo.data['links'])),
            'internal': m['internal'], 'external': m['external'], 'kind': kind, 'reason': '기존 발견 후보',
            'provenance': {'type': 'MODEL_OBSERVATION', 'method': 'BATCH_DISCOVERY_V1',
                'run_id': next(iter(art.batch_run_ids(p.plan))), 'retrieval_role': 'UNREVIEWED_CANDIDATE'}})
        if status:
            out = svc.review(p.who, {'request_id': 'fixture-review-' + row['link']['link_id'], 'action': status,
                'items': [{'link_id': row['link']['link_id'], 'revision': 1, 'view_hash': row['view_hash']}]})
            assert out['status'] == 'completed'
        return row['link']['link_id']


def test_shared_json_combines_model_candidate_fixed_links_without_sqlite(pilot, monkeypatch):
    extra = add(pilot, kind='RELATED')
    old = JsonRepository(pilot.path).history(extra)
    plan, state = (pilot.job/'PLAN.json').read_bytes(), (pilot.job/'STATE.json').read_bytes()
    monkeypatch.setattr(art, 'authority', lambda *a, **k: pytest.fail('authority accessed during staging'))
    assert run(pilot, inspect=True)['status'] == 'INSPECTED'
    result = run(pilot)
    assert result['status'] == 'STAGED' and not result['published_to_sqlite']
    repo = JsonRepository(pilot.path)
    assert len(repo.links('risk_team')) == 5 and repo.history(extra) == old
    assert len([r for r in repo.links('risk_team') if r['status'] == 'APPROVED']) == 4
    assert (pilot.job/'PLAN.json').read_bytes() == plan and (pilot.job/'STATE.json').read_bytes() == state
    assert not (pilot.runtime/'basis-links').exists()
    captured = art.capture(pilot.job, PHOTO, pilot.runtime)
    assert len(captured['items']) == 5
    art.report(captured, pilot.job/'LINKS.html')
    html = (pilot.job/'LINKS.html').read_text()
    assert html.count('<tr><td class="number">') == 5
    assert '위험관리기준시행세칙' in html and '금융투자업규정' in html
    assert 'USER_FIXED_RISK_V1' in json.dumps(captured)


@pytest.mark.parametrize('status', [None, 'approve'])
def test_exact_candidate_reuses_same_id_and_history(pilot, status):
    ident = add(pilot, status=status)
    before = JsonRepository(pilot.path).history(ident)
    result = run(pilot)
    after = JsonRepository(pilot.path)
    assert result['actions'][0]['link_id'] == ident
    assert len(after.links('risk_team')) == 4
    assert after.history(ident)['revisions'][:len(before['revisions'])] == before['revisions']
    assert after.head(ident)['status'] == 'APPROVED'
    if status:
        assert after.history(ident) == before
    assert len(art.capture(pilot.job, PHOTO, pilot.runtime)['items']) == 4


def test_repeated_stage_and_response_loss_are_idempotent(pilot):
    def fail(phase):
        if phase == 'after_commit':
            raise OSError('lost acknowledgement')
    with pytest.raises(OSError):
        run(pilot, hook=fail)
    before = pilot.path.read_bytes()
    assert run(pilot)['status'] == 'STAGED_REUSED'
    assert pilot.path.read_bytes() == before
    assert run(pilot)['status'] == 'STAGED_REUSED'


@pytest.mark.parametrize('phase', ['prepared:liquidity-maintenance', 'before_commit'])
def test_all_four_commit_or_none_and_retry(pilot, phase):
    add(pilot, kind='RELATED')
    before = pilot.path.read_bytes()
    def fail(value):
        if value == phase:
            raise OSError('injected')
    with pytest.raises(OSError):
        run(pilot, hook=fail)
    assert pilot.path.read_bytes() == before
    assert run(pilot)['status'] == 'STAGED'


@pytest.mark.parametrize('status', ['reject', 'revoke', 'duplicate'])
def test_conflicting_last_mapping_does_not_partially_save(pilot, status):
    add(pilot, n=3, status=None if status == 'duplicate' else status)
    if status == 'duplicate':
        add(pilot, n=3)
    before = pilot.path.read_bytes()
    with pytest.raises(BasisError):
        run(pilot)
    assert pilot.path.read_bytes() == before


def test_lock_and_corruption_fail_without_overwrite(pilot):
    add(pilot, kind='RELATED')
    before = pilot.path.read_bytes()
    with pilot.path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='BUSY'):
            run(pilot)
    assert pilot.path.read_bytes() == before
    value = json.loads(before)
    value['links'].clear()
    pilot.path.write_text(json.dumps(value))
    bad = pilot.path.read_bytes()
    with pytest.raises(BasisError, match='해시'):
        run(pilot)
    assert pilot.path.read_bytes() == bad


@pytest.mark.parametrize('field', ['team', 'source', 'legacy', 'path', 'hash'])
def test_wrong_job_or_source_cannot_redirect_to_sqlite(pilot, field):
    p = deepcopy(pilot.plan)
    if field == 'team': p['binding']['principal']['team_id'] = 'other_team'
    if field == 'source': p['binding']['selection_sha256'] = 'wrong'
    if field == 'legacy': del p['candidate_storage']
    if field == 'path': p['candidate_storage']['path'] = str(pilot.root/'wrong.json')
    p['plan_sha256'] = digest({k:v for k,v in p.items() if k != 'plan_sha256'}) if field != 'hash' else 'wrong'
    art.atomic(pilot.job/'PLAN.json', p)
    with pytest.raises(BasisError):
        run(pilot)
    assert not pilot.path.exists() and not (pilot.runtime/'basis-links').exists()


def test_source_plan_change_before_commit_is_rejected(pilot):
    def change(phase):
        if phase == 'prepared:liquidity-maintenance':
            p = deepcopy(pilot.plan); p['batch_id'] = 'changed'
            p['plan_sha256'] = digest({k:v for k,v in p.items() if k != 'plan_sha256'})
            art.atomic(pilot.job/'PLAN.json', p)
    with pytest.raises(BasisError):
        run(pilot, hook=change)
    assert not pilot.path.exists()


def test_fixed_document_outside_pilot_only_expands_report(pilot):
    p = deepcopy(pilot.plan); p['documents'] = []
    p['plan_sha256'] = digest({k:v for k,v in p.items() if k != 'plan_sha256'})
    art.atomic(pilot.job/'PLAN.json', p)
    (pilot.job/'STATE.json').unlink()
    before = (pilot.job/'PLAN.json').read_bytes()
    run(pilot)
    value = art.capture(pilot.job, PHOTO, pilot.runtime)
    assert len(value['items']) == 4 and len(value['documents']) == 1
    assert value['documents'][0]['selection_reason'] == 'user_fixed_links'
    assert (pilot.job/'PLAN.json').read_bytes() == before


def test_common_review_gate_combined_import_idempotence_and_revoke(pilot, tmp_path):
    add(pilot, kind='RELATED')
    run(pilot)
    value = art.capture(pilot.job, PHOTO, pilot.runtime)
    production = tmp_path/'production-runtime'
    with pytest.raises(BasisError, match='HTML'):
        art.apply(value, art.sql(value), PHOTO, production)
    assert not production.exists()
    decision = art.review(value, pilot.job/'REVIEW.json', accept_all=True)
    reviewed = art.reviewed(value, decision)
    assert not production.exists()
    assert art.apply(reviewed, art.sql(reviewed), PHOTO, production, check=True)['insert'] == 5
    assert not production.exists()
    assert len(art.apply(reviewed, art.sql(reviewed), PHOTO, production)['inserted']) == 5
    assert art.apply(reviewed, art.sql(reviewed), PHOTO, production)['status'] == 'already_applied'
    with art.authority(production/'basis-links/authority.sqlite') as repo, art.source(PHOTO, value['source'], value['principal']) as (sources, who):
        actual = targets(Service(repo,sources), who, snapshot(Service(repo,sources), who, [pilot.selected['internal_document_id']]))
        assert len(actual) == 7
    assert art.rollback(reviewed, production)['status'] == 'rolled_back'
    assert art.rollback(reviewed, production)['status'] == 'already_rolled_back'


def test_only_selected_row_imported(pilot, tmp_path):
    run(pilot)
    value = art.capture(pilot.job, PHOTO, pilot.runtime)
    ident = value['items'][0]['link']['link_id']
    decision = art.review(value, pilot.job/'REVIEW.json', link_ids=[ident])
    reviewed = art.reviewed(value, decision)
    assert len(art.apply(reviewed, art.sql(reviewed), PHOTO, tmp_path/'prod')['inserted']) == 1
    with art.authority(tmp_path/'prod/basis-links/authority.sqlite') as repo:
        assert len(repo.links('risk_team')) == 1


def test_cli_stages_to_common_default_and_refuses_direct_apply(pilot):
    config = pilot.root/'00_SYSTEM'; config.mkdir()
    art.atomic(config/'GENOS_SERVING_PATHS.json', {'generation':str(PHOTO), 'runtime':str(pilot.runtime)})
    art.atomic(config/'PIPELINE.json', {'profiles': {'legal-rag': {'nodes':[{'parameters':{'term_agent':{}}}]}}})
    assert cli.main(['stage','--root',str(pilot.root),'--operator','tester']) == 0
    assert pilot.path.exists() and not (pilot.runtime/'basis-links').exists()
    with pytest.raises(SystemExit) as exc:
        cli.main(['apply','--root',str(pilot.root)])
    assert exc.value.code == 2
