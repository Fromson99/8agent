"""External-only inventory and CLI contracts: no network or real model calls."""
import json
import subprocess
import pytest
from lawrag.pipeline import genos_build as build, genos_corpus as corpus, genos_batch as batch
from .test_genos_all_corpus import fixture_corpus, runner, save
from .test_genos_build import setup, Fake


@pytest.mark.parametrize('skip', [False, True])
def test_internal_never_inventoried(tmp_path, monkeypatch, skip):
    raw = fixture_corpus(tmp_path)
    save(raw / 'internal/DRM.docx', '<## NASCA')
    original = build.inventory
    def guarded(root, source, *a, **kw):
        assert source != 'internal', 'internal inventory must never run'
        return original(root, source, *a, **kw)
    monkeypatch.setattr(build, 'inventory', guarded)
    plan, report = corpus.collect(raw, exclude_internal=True, skip_invalid=skip)
    assert report['ok'] and len(plan['files']) == 7
    assert set(report['sources']) == set(corpus.SOURCES)
    assert all(r['source'] == 'external' for r in plan['files'])
    assert report['source_selection']['excluded'] == ['internal']
    assert batch.input_summary(plan, report)['total'] == 7


def test_missing_internal_is_not_an_error(tmp_path):
    raw = fixture_corpus(tmp_path)
    (raw / 'internal').rename(raw / '.internal-kept')
    plan, report = corpus.collect(raw, exclude_internal=True, skip_invalid=True)
    assert report['ok'] and len(plan['files']) == 7


def test_check_only_and_execute_forward_scope(tmp_path, monkeypatch):
    root = tmp_path / 'DEV'
    fixture_corpus(root / 'data')
    module = runner(monkeypatch, root)
    assert module.main(['--run-id', 'ext', '--check-only', '--exclude-internal']) == 0
    received = []
    def execute(args, plan, report):
        received.append(plan)
        assert len(plan['files']) == 7
        return {'status': 'COMPLETED', 'accounting': batch.accounting(7, 0), 'source_errors': []}
    monkeypatch.setattr(batch, 'execute', execute)
    assert module.main(['--run-id', 'ext', '--exclude-internal', '--skip-failed']) == 0
    assert received[0]['source_selection']['excluded'] == ['internal']
    for p in (root / 'data/logs/ext').glob('attempt-*.json'):
        assert json.loads(p.read_text())['source_selection']['excluded'] == ['internal']


def test_external_batch_fake_end_to_end_and_scope_resume(setup):
    args, _, out = setup
    raw = fixture_corpus(out.parent / 'external')
    plan, report = corpus.collect(raw, exclude_internal=True)
    result = batch.execute(args, plan, report, provider_factory=Fake, emit=lambda _: None)
    assert result['accounting'] == batch.accounting(7, 0)
    assert len(result['generations']) == 7
    assert json.loads((out / 'batch-plan.json').read_text())['source_selection']['excluded'] == ['internal']
    args.resume = True
    all_plan, all_report = corpus.collect(raw)
    with pytest.raises(ValueError, match='NEW run-id'):
        batch.execute(args, all_plan, all_report, provider_factory=Fake)


def test_shell_forwards_flag_and_describes_external(tmp_path):
    commands = tmp_path / '06_TOOLS/COMMANDS'
    commands.mkdir(parents=True)
    script = commands / 'genos_data_e2e.sh'
    script.write_bytes((build.ROOT / '06_TOOLS/COMMANDS/genos_data_e2e.sh').read_bytes())
    (commands / 'genos_build_all.sh').write_text('printf "ARG:%s\\n" "$@"\n')
    result = subprocess.run(['bash', str(script), '--exclude-internal', '--execute'], capture_output=True, text=True)
    assert result.returncode == 0
    assert 'ARG:--exclude-internal' in result.stdout
    assert '외규만 (internal 제외)' in result.stdout
