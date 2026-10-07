"""Synthetic recovery contracts; no GENOS/provider access."""
import copy
import fcntl
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
from lawrag.pipeline import genos_status, genos_stages, team_raw

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '06_TOOLS/OFFLINE/genos_failed_structure_retry.py'
TXT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SPAN_FIX_SHORTEST_R1_UTF8.txt'
spec = importlib.util.spec_from_file_location('failed_retry', SCRIPT)
retry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retry)


def setup_run(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_DATA_ROOT', str(tmp_path))
    rows = [{'document_id': 'bad', 'relative': 'external/risk_team/law/a.xml',
             'name': '<문서>', 'path': str(tmp_path / 'RAW/a.xml'), 'sha256': 'original'},
            {'document_id': 'good', 'relative': 'external/risk_team/law/b.xml',
             'name': '정상', 'path': str(tmp_path / 'RAW/b.xml'), 'sha256': 'original'}]
    logs = tmp_path / 'LOGS/original-run'
    logs.mkdir(parents=True)
    ledger = genos_status.Ledger(logs).start(rows, 'structure')
    ledger.update('bad', 'structure', 'FAILED', error='ValueError: invalid_tree_parent')
    ledger.update('good', 'structure', 'PASSED')
    ledger.finish('FAILED')
    ledger.close()
    (logs / 'inventory-1.json').write_text(json.dumps({'files': rows}))
    return logs, rows


def test_only_failed_structure_selected():
    rows = [{'document_id': str(i), 'selection': selection,
             'phases': {'structure': {'state': state}, 'index': {'state': 'FAILED'}}}
            for i, (selection, state) in enumerate([
                ('SELECTED', 'FAILED'), ('SELECTED', 'RUNNING'), ('SELECTED', 'PASSED'),
                ('EXCLUDED', 'FAILED'), ('SELECTED', 'PENDING')])]
    assert [r['document_id'] for r in retry.failures({'documents': rows})] == ['0']


def test_categories_and_budget_evidence(tmp_path):
    folder = tmp_path / 'structure-recipe-runs/id'
    folder.mkdir(parents=True)
    (folder / 'events.jsonl').write_text(json.dumps({
        'event': 'recipe.review.budget_exhausted', 'calls': 64, 'pending_pages': 117,
        'prompt': 'must not export'}) + '\n{unfinished')
    rows = [{'phases': {'structure': {'error': 'invalid_tree_parent', 'output_path': str(tmp_path)}}}]
    item = retry.enrich(rows)[0]
    assert item['failure_categories'] == ['TREE_PARENT', 'CALL_BUDGET']
    assert item['budget_events'][0]['pending_pages'] == 117
    assert 'prompt' not in item['budget_events'][0]


def test_input_identity_and_selection(tmp_path, monkeypatch):
    logs, rows = setup_run(tmp_path, monkeypatch)
    report = genos_status.read_report(logs)
    plan = {'files': rows}
    retry.verify_inventory_snapshot(logs, report, plan)
    assert len(retry.select_plan(plan, retry.failures(report))['files']) == 1
    changed = copy.deepcopy(plan)
    changed['files'][0]['sha256'] = 'changed'
    with pytest.raises(ValueError, match='changed'):
        retry.verify_inventory_snapshot(logs, report, changed)
    (logs / 'inventory-2.json').write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='ambiguous'):
        retry.verify_inventory_snapshot(logs, report, plan)


def test_list_allowed_while_locked(tmp_path, monkeypatch):
    logs, rows = setup_run(tmp_path, monkeypatch)
    with (logs / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert retry.main(['--run-id', 'original-run']) == 0
        with pytest.raises(BlockingIOError):
            retry.main(['--run-id', 'original-run', '--execute'])
    report_dir = next((tmp_path / 'LOGS').glob('failure-retry-*'))
    assert '&lt;문서&gt;' in (report_dir / 'failures.html').read_text()
    assert (report_dir / 'failures.csv').read_bytes().startswith(b'\xef\xbb\xbf')
    assert genos_status.read_report(logs)['counts']['structure']['FAILED'] == 1


def test_execute_delegates_failed_only_and_keeps_parent(tmp_path, monkeypatch):
    logs, rows = setup_run(tmp_path, monkeypatch)
    monkeypatch.setattr(team_raw, 'collect', lambda *a, **kw: ({'files': rows}, {}))
    monkeypatch.setattr(genos_stages, 'parser_identity', lambda root: {'synthetic': True})
    captured = []
    def execute(plan, options, data, run_id, stage, *, progress, status):
        import os
        captured.extend(r['document_id'] for r in plan['files'])
        assert stage == 'structure'
        assert os.environ['STRUCTURE_RECIPE_MAX_CALLS'] == '256'
        assert os.environ['STRUCTURE_RECIPE_MAX_PAGES'] == '3'
        assert os.environ['LLM_BACKEND'] == 'genos'
        status.update('bad', 'structure', 'PASSED')
        return {'ok': True, 'passed': 1, 'skipped': 0}
    monkeypatch.setattr(genos_stages, 'execute', execute)
    assert retry.main(['--run-id', 'original-run', '--execute']) == 0
    assert captured == ['bad']
    assert genos_status.read_report(logs)['counts']['structure']['FAILED'] == 1
    assert not (logs / 'structure-selection.json').exists()


def test_txt_exact_python_and_bash_syntax():
    text = TXT.read_text()
    embedded = text.split("<<'GENOS_SHORTEST_RETRY_PY'\n", 1)[1].rsplit('GENOS_SHORTEST_RETRY_PY\n', 1)[0]
    assert embedded == SCRIPT.read_text()
    subprocess.run(['bash', '-n', str(TXT)], check=True)


def test_shortest_uses_actual_pages_and_executes_one(tmp_path, monkeypatch):
    import fitz
    logs, rows = setup_run(tmp_path, monkeypatch)
    rows[0].update(relative='external/risk_team/law/long.pdf', path=str(tmp_path / 'long.pdf'))
    rows[1].update(relative='external/risk_team/law/short.pdf', path=str(tmp_path / 'short.pdf'))
    for row, pages in zip(rows, [3, 1]):
        with fitz.open() as pdf:
            for _ in range(pages):
                pdf.new_page()
            pdf.save(row['path'])
    ledger = genos_status.Ledger(logs).start(rows, 'structure')
    for row in rows:
        ledger.update(row['document_id'], 'structure', 'FAILED', error='invalid_tree_parent')
    ledger.finish('FAILED')
    ledger.close()
    (logs / 'inventory-1.json').write_text(json.dumps({'files': rows}))
    monkeypatch.setattr(team_raw, 'collect', lambda *a, **kw: ({'files': rows}, {}))
    monkeypatch.setattr(genos_stages, 'parser_identity', lambda root: {'synthetic': True})
    captured = []
    def execute(plan, options, data, run_id, stage, *, progress, status):
        captured.extend(r['document_id'] for r in plan['files'])
        status.update('good', 'structure', 'PASSED')
        return {'ok': True, 'passed': 1, 'skipped': 0}
    monkeypatch.setattr(genos_stages, 'execute', execute)
    assert retry.main(['--run-id', 'original-run', '--format', 'pdf', '--shortest', '--execute']) == 0
    assert captured == ['good']
    selection = json.loads(next((tmp_path / 'LOGS').glob('failure-retry-*/shortest-selection.json')).read_text())
    assert [r['pages'] for r in selection['candidates']] == [1, 3]
    assert genos_status.read_report(logs)['counts']['structure']['FAILED'] == 2


def test_docx_filter_with_linked_data_root(tmp_path, monkeypatch):
    logs, rows = setup_run(tmp_path / 'data', monkeypatch)
    rows[0]['relative'] = 'external/risk_team/law/a.docx'
    ledger = genos_status.Ledger(logs).start(rows, 'structure')
    ledger.update('bad', 'structure', 'FAILED', error='old docling error')
    ledger.update('good', 'structure', 'FAILED', error='overlapping_sibling_spans')
    ledger.finish('FAILED')
    ledger.close()
    linked = tmp_path / 'linked'
    linked.symlink_to(tmp_path / 'data', target_is_directory=True)
    monkeypatch.setenv('GENOS_DATA_ROOT', str(linked))
    assert retry.main(['--run-id', 'original-run', '--format', 'docx']) == 0
    report = json.loads(next((tmp_path / 'data/LOGS').glob('failure-retry-*/failures.json')).read_text())
    assert report['count'] == 1
    assert report['documents'][0]['relative'].endswith('.docx')
    assert retry.classify('overlapping_sibling_spans') == ['TREE_SPANS']


def test_merge_verified_receipt_preserves_backup(tmp_path, monkeypatch):
    from semantic_runtime.contracts import digest, sha
    from lawrag.pipeline import genos_build
    logs, rows = setup_run(tmp_path, monkeypatch)
    plan = {'files': rows}
    original = {'schema_version': 'structure-selection-v1', 'inputs_sha256': digest(plan),
                'expected_document_ids': ['bad', 'good'], 'documents': {}, 'completed': False}
    target = logs / 'structure-selection.json'
    genos_build.atomic(target, original)
    before = target.read_bytes()
    key = 'a' * 64
    folder = tmp_path / 'STRUCTURE' / key
    folder.mkdir(parents=True)
    receipt = {'input_row': rows[0]}
    genos_build.atomic(folder / 'structure-receipt.json', receipt)
    child = tmp_path / 'LOGS/child-run'
    child.mkdir()
    genos_build.atomic(child / 'structure-selection.json', {
        'schema_version': 'structure-selection-v1', 'documents': {
            'bad': {'key': key, 'receipt_sha256': sha(folder / 'structure-receipt.json')}}})
    monkeypatch.setattr(genos_stages, 'verify_structure', lambda folder: receipt)
    assert retry.merge_selection(tmp_path, 'original-run', 'child-run', plan, sha(target)) is False
    assert (logs / 'structure-selection-before-retry-child-run.json').read_bytes() == before
    assert list(json.loads(target.read_text())['documents']) == ['bad']
    assert genos_status.read_report(logs)['counts']['structure']['FAILED'] == 1
