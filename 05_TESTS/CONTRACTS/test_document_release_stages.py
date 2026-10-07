"""Stage/resume and explicit partial-scope contracts; synthetic sources only."""
from contextlib import closing
import fcntl
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from semantic_runtime.contracts import sha
from semantic_runtime.storage import Store
from lawrag.pipeline import document_release, genos_build, genos_stages, genos_status, structure_selection
from test_document_release import ReviewProvider, source


@pytest.fixture
def failed_run(tmp_path):
    raw = tmp_path / 'RAW/internal'
    raw.mkdir(parents=True)
    xml = '''<법령><기본정보><법령명_한글>모의규정</법령명_한글></기본정보><조문><조문단위>
      <조문번호>1</조문번호><조문제목>정의</조문제목>
      <조문내용>“영업일”이란 은행이 영업하는 날을 말한다.</조문내용>
      </조문단위></조문></법령>'''
    (raw / 'good.xml').write_text(xml)
    (raw / 'missing.xml').write_text(xml.replace('모의규정', '다른규정'))
    plan = genos_build.inventory(raw, 'internal', None)
    (raw / 'missing.xml').unlink()
    options = genos_build.parser().parse_args([
        'build', '--input-root', str(raw), '--build-dir', str(tmp_path / 'work'), '--execute'])
    logs = tmp_path / 'LOGS/failed'
    class Progress:
        def document(self, *a, **k): pass
        def emit(self, *a, **k): pass
        def finish(self, *a, **k): pass
        def error(self, *a, **k): pass
    ledger = genos_status.Ledger(logs)
    try:
        ledger.start(plan['files'], 'structure', excluded=[
            {'source': 'internal', 'item': 'old.doc', 'error': 'DOC requires companion PDF'}])
        result = genos_stages.execute(plan, options, tmp_path, 'failed', 'structure',
                                     dependencies={'fixture': 'xml'}, progress=Progress(), status=ledger)
        assert result['passed'] == 1 and not result['ok']
        selection = json.loads((logs / 'structure-selection.json').read_text())
        selection['input_inventory_valid'] = False
        genos_build.atomic(logs / 'structure-selection.json', selection)
        ledger.finish('FAILED')
    finally:
        ledger.close()
    return tmp_path


def select(data, run='success'):
    return structure_selection.select_completed(data, 'failed', run, allow_incomplete=True, reason='실패 문서 보류')


def test_snapshot_preserves_parent_and_failures_and_reuses_exact_cache(failed_run):
    data = failed_run
    original = data / 'LOGS/failed'
    before = {p.name: sha(p) for p in original.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match='allow-incomplete'):
        structure_selection.select_completed(data, 'failed', 'success')
    result = select(data)
    assert (result['selected'], result['omitted'], result['coverage']) == (1, 2, 'PARTIAL')
    assert select(data) == result  # Idempotent selection, without rewriting status or caches.
    assert all(sha(original / name) == expected for name, expected in before.items())
    origin = json.loads((data / 'LOGS/success/selection-origin.json').read_text())
    assert {row['selection'] for row in origin['omitted_documents']} == {'SELECTED', 'INPUT_FAILED'}
    paths, pins = document_release.selected_sources(data, 'success', [])
    assert len(paths) == 1 and 'STRUCTURE' in paths[0].parts
    assert str(data / 'LOGS/success/parent-status.json') in pins
    # Later retries of the original run cannot alter the frozen success-only scope.
    (original / 'structure-selection.json').write_text('{}')
    assert document_release.selected_sources(data, 'success', [])[0] == paths
    assert not (data / 'generations/CURRENT.json').exists()


@pytest.mark.parametrize('artifact', ['selection-origin.json', 'parent-status.json', 'parent-selection.json'])
def test_snapshot_tamper_blocks_release(failed_run, artifact):
    select(failed_run)
    with (failed_run / 'LOGS/success' / artifact).open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='changed'):
        document_release.selected_sources(failed_run, 'success', [])


def test_scope_rejects_busy_unfinished_mismatched_or_existing_runs(failed_run):
    data = failed_run
    with (data / 'LOGS/failed/run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='busy'):
            select(data)
    with pytest.raises(ValueError, match='new run ID'):
        select(data, 'failed')
    (data / 'LOGS/occupied').mkdir()
    with pytest.raises(ValueError, match='Destination run exists'):
        select(data, 'occupied')
    path = data / 'LOGS/failed/structure-selection.json'
    value = json.loads(path.read_text())
    value['expected_document_ids'].append('unrecorded')
    genos_build.atomic(path, value)
    with pytest.raises(ValueError, match='disagree'):
        select(data)


@pytest.mark.parametrize('change', ['running', 'run_error', 'no_success', 'receipt'])
def test_invalid_parent_cannot_be_turned_into_a_success(failed_run, change):
    data = failed_run
    if change in {'running', 'run_error'}:
        with sqlite3.connect(data / 'LOGS/failed' / genos_status.DATABASE) as db:
            if change == 'running':
                db.execute("UPDATE attempts SET status='RUNNING'")
            else:
                db.execute("UPDATE attempts SET error='repository manifest mismatch'")
    else:
        path = data / 'LOGS/failed/structure-selection.json'
        value = json.loads(path.read_text())
        if change == 'no_success':
            value['documents'] = {}
        else:
            next(iter(value['documents'].values()))['receipt_sha256'] = '0' * 64
        genos_build.atomic(path, value)
    with pytest.raises(ValueError):
        select(data)
    assert not (data / 'LOGS/success').exists()


def test_separate_stages_resume_without_reparse_or_index_model_calls(failed_run, term_glossary, monkeypatch):
    data = failed_run
    select(data)
    release = data / 'TERM_RELEASES/success'
    provider = ReviewProvider()
    def stage(name, **kw):
        return document_release.build(data, 'success', term_glossary, stage=name, provider=provider, **kw)
    with pytest.raises(ValueError, match='prepare first'):
        stage('review')
    assert stage('merge')['status'] == 'MERGED'
    assert not (release / 'glossary-draft').exists()
    assert stage('prepare')['status'] == 'PREPARED'
    assert provider.calls == 0
    with pytest.raises(ValueError, match='review to completion'):
        stage('index')
    reviewed = stage('review')
    assert reviewed['stage_completed'] and not reviewed['completed']
    assert provider.calls > 0 and not (release / 'serving').exists()
    before = provider.calls
    assert stage('review')['status'] == 'REVIEWED'
    assert provider.calls == before
    monkeypatch.setattr(document_release.glossary_review, 'complete',
                        lambda *a, **kw: pytest.fail('index must not run the model/review workflow'))
    result = stage('index')
    assert result['completed'] and result['structure_coverage']['omitted_count'] == 2
    assert stage('index')['cached']
    generation, receipt = document_release.verify_release(release)
    with closing(Store(generation)) as store:
        assert store.manifest['counts']['document'] == 1
    status = document_release.recorded_status(data, 'success')
    assert all(value['recorded'] for value in status['stages'].values())
    assert status['structure_coverage']['coverage'] == 'PARTIAL'
    assert not (data / 'generations/CURRENT.json').exists()
    with (release / 'structure-selection-origin.json').open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='audit changed'):
        document_release.verify_release(release)


def test_stage_cli_pending_exit_and_readonly_status(tmp_path, term_glossary, monkeypatch, capsys):
    original = source(tmp_path / 'source.sqlite', [('new', '모의규정', [
        '“영업일”이란 은행이 영업하는 날을 말한다.', '“영업일”이란 은행이 근무하는 날을 말한다.'])])
    monkeypatch.setattr(document_release, 'selected_sources', lambda *a: ([original], {str(original): sha(original)}))
    monkeypatch.setattr(genos_stages, 'offline_data_root', lambda *a: tmp_path)
    complete = document_release.glossary_review.complete
    monkeypatch.setattr(document_release.glossary_review, 'complete',
                        lambda *a, **kw: complete(*a, **{**kw, 'provider': ReviewProvider()}))
    args = ['--run-id', 'stages', '--glossary-dir', str(term_glossary)]
    assert document_release.main(['prepare', *args]) == 0
    assert document_release.main(['review', *args, '--max-review-jobs', '1']) == 3
    assert document_release.main(['review', *args, '--max-review-jobs', '100']) == 0
    assert document_release.main(['index', *args]) == 0
    before = sorted(str(p) for p in tmp_path.rglob('*'))
    assert document_release.main(['status', '--run-id', 'not-created']) == 0
    assert sorted(str(p) for p in tmp_path.rglob('*')) == before
    with pytest.raises(SystemExit):
        document_release.main(['index', *args, '--allow-incomplete'])
    with pytest.raises(SystemExit):
        document_release.main(['index', *args, '--retry-review-failed'])


def test_raw_runner_cannot_overwrite_frozen_success_scope(failed_run, monkeypatch):
    select(failed_run)
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('staged_command', root / '06_TOOLS/COMMANDS/genos_data_stages.py')
    command = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(command)
    monkeypatch.setattr(genos_stages, 'offline_data_root', lambda *a: failed_run)
    pointer = failed_run / 'LOGS/success/structure-selection.json'
    before = sha(pointer)
    with pytest.raises(SystemExit) as exc:
        command.main(['--run-id', 'success', '--stage', 'structure', '--execute'])
    assert exc.value.code == 2
    assert sha(pointer) == before


def test_lost_origin_and_path_escape_rejected(failed_run):
    select(failed_run)
    path = failed_run / 'LOGS/success/structure-selection.json'
    value = json.loads(path.read_text())
    del value['origin_sha256']
    genos_build.atomic(path, value)
    with pytest.raises(ValueError, match='origin binding'):
        document_release.selected_sources(failed_run, 'success', [])
    with pytest.raises(ValueError, match='run-id'):
        select(failed_run, '../escape')
