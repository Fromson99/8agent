"""Synthetic retry provenance contracts, no model or field access."""
import copy
import json
import pytest
import ast
import os
from pathlib import Path
import subprocess
import sys
from semantic_runtime.contracts import digest, sha
from lawrag.pipeline import genos_build, genos_status, document_release, structure_selection
from test_genos_failed_structure_retry import setup_run, retry


@pytest.fixture
def merged(tmp_path, monkeypatch):
    logs, rows = setup_run(tmp_path, monkeypatch)
    entry_good = {'key': 'b' * 64, 'receipt_sha256': 'good'}
    target = logs / 'structure-selection.json'
    genos_build.atomic(target, {'schema_version': 'structure-selection-v1', 'inputs_sha256': digest({'files': rows}),
        'expected_document_ids': ['bad', 'good'], 'documents': {'good': entry_good}, 'completed': False})
    folder = tmp_path / 'STRUCTURE' / ('a' * 64)
    folder.mkdir(parents=True)
    genos_build.atomic(folder / 'structure-receipt.json', {'input_row': rows[0]})
    child = tmp_path / 'LOGS/child'
    ledger = genos_status.Ledger(child).start([rows[0]], 'structure')
    ledger.update('bad', 'structure', 'PASSED')
    ledger.finish('COMPLETED')
    ledger.close()
    genos_build.atomic(child / 'structure-selection.json', {'schema_version': 'structure-selection-v1',
        'documents': {'bad': {'key': 'a' * 64, 'receipt_sha256': sha(folder / 'structure-receipt.json')}}})
    monkeypatch.setattr(retry, 'enrich', lambda rows: rows)
    from lawrag.pipeline import genos_stages
    monkeypatch.setattr(genos_stages, 'verify_structure', lambda folder: json.loads((folder / 'structure-receipt.json').read_text()))
    retry.merge_selection(tmp_path, 'original-run', 'child', {'files': rows}, sha(target))
    monkeypatch.setattr(document_release, 'verified_structures', lambda *a: ([], {}))
    return tmp_path, logs, child, folder


def test_selection_adopts_verified_retry_and_preserves_parent(merged):
    data, logs, child, folder = merged
    before = {p.name: sha(p) for p in logs.iterdir() if p.is_file()}
    result = structure_selection.select_completed(data, 'original-run', 'success', allow_incomplete=True, reason='실패 보류')
    assert result['selected'] == 2 and result['omitted'] == 0
    assert all(sha(logs / name) == value for name, value in before.items())
    origin = json.loads((data / 'LOGS/success/selection-origin.json').read_text())
    assert origin['verified_retry_adoptions'][0]['adopted_document_ids'] == ['bad']
    assert genos_status.read_report(logs)['counts']['structure']['FAILED'] == 1
    assert structure_selection.select_completed(data, 'original-run', 'success', allow_incomplete=True, reason='실패 보류') == result


@pytest.mark.parametrize('change', ['backup', 'union', 'receipt_input', 'child_state', 'lineage_missing'])
def test_unverified_adoption_is_rejected(merged, change):
    data, logs, child, folder = merged
    target = logs / 'structure-selection.json'
    if change == 'backup':
        with (logs / 'structure-selection-before-retry-child.json').open('a') as stream:
            stream.write(' ')
    elif change == 'receipt_input':
        genos_build.atomic(folder / 'structure-receipt.json', {'input_row': {'document_id': 'different'}})
    elif change == 'child_state':
        import sqlite3
        with sqlite3.connect(child / genos_status.DATABASE) as db:
            db.execute("UPDATE attempts SET status='RUNNING'")
    else:
        value = json.loads(target.read_text())
        if change == 'union': value['documents']['bad']['receipt_sha256'] = 'tampered'
        else: value.pop('failure_retry')
        genos_build.atomic(target, value)
    with pytest.raises(ValueError):
        structure_selection.select_completed(data, 'original-run', 'success', allow_incomplete=True, reason='실패 보류')
    assert not (data / 'LOGS/success').exists()


def test_handoff_apply_repeat_rollback_and_embedded_code(tmp_path):
    root = Path(__file__).resolve().parents[2]
    txt = root / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SUCCESS_CONTINUE_R2_UTF8.txt'
    subprocess.run(['bash', '-n', str(txt)], check=True)
    installer = txt.read_text().split("<<'GENOS_ADOPTION_PATCH_PY'\n", 1)[1].split('\nGENOS_ADOPTION_PATCH_PY', 1)[0]
    assignment = next(n for n in ast.parse(installer).body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'P' for t in n.targets))
    payload = json.loads(ast.literal_eval(assignment.value.args[0]))
    for row in payload['files']:
        assert row['after'] == (root / row['path']).read_text()
        if row['before'] is not None:
            p = tmp_path / row['path']
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(row['before'])
    data = tmp_path / 'data'
    data.mkdir()
    def run(*args):
        return subprocess.run([sys.executable, '-c', installer, *args], cwd=tmp_path,
            env={**os.environ, 'GENOS_DATA_ROOT': str(data)}, capture_output=True, text=True, check=True).stdout
    assert 'ADOPTION_PATCH_APPLIED' in run()
    assert 'ADOPTION_PATCH_ALREADY_APPLIED' in run()
    receipt = next((tmp_path / 'TRANSFER/BACKUPS/retry-adoption-r2').glob('*/receipt.json'))
    assert 'ADOPTION_ROLLBACK_PASS' in run('--rollback', str(receipt))
    for row in payload['files']:
        p = tmp_path / row['path']
        if row['before'] is None: assert not p.exists()
        else: assert p.read_text() == row['before']
