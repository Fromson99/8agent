import ast
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT/'06_TOOLS/OFFLINE/genos_actual_error_patch.py'


def r7_text(rel):
    text = (ROOT/rel).read_text()
    progress = ROOT/'06_TOOLS/OFFLINE/genos_error_progress_patch.py'
    if progress.exists():
        tree = ast.parse(progress.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'EDITS' for t in n.targets))
        edits = json.loads(ast.literal_eval(node.value.args[0]))[-5:]
        for edit in reversed([e for e in edits if e['path'] == rel]):
            text = text.replace(edit['new'], edit['old'])
    return text


def fixture(tmp_path):
    tree = ast.parse(INSTALLER.read_text())
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'EDITS' for t in n.targets))
    edits = json.loads(ast.literal_eval(assignment.value.args[0]))
    originals = {}
    for rel in dict.fromkeys(e['path'] for e in edits):
        text = r7_text(rel)
        for edit in reversed([e for e in edits if e['path'] == rel]):
            assert edit['new'] in text, rel
            text = text.replace(edit['new'], edit['old'])
        ast.parse(text)
        dest = tmp_path/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        originals[rel] = dest.read_bytes()
    (tmp_path/'data').mkdir()
    return originals


def run(tmp_path, **extra):
    env = dict(os.environ, GENOS_DATA_ROOT=str(tmp_path/'data'), GENOS_RUN_ID='fixture', **extra)
    return subprocess.run([sys.executable, str(INSTALLER)], cwd=tmp_path, env=env,
                          capture_output=True, text=True)


def test_apply_repeat_and_rollback_preserve_checkout_bytes(tmp_path):
    originals = fixture(tmp_path)
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    receipts = list(tmp_path.glob('TRANSFER/BACKUPS/actual-error-details-r1/*/receipt.json'))
    assert len(receipts) == 1
    for rel in originals:
        assert (tmp_path/rel).read_bytes() == r7_text(rel).encode()
    repeated = run(tmp_path)
    assert repeated.returncode == 0 and 'ALREADY_APPLIED' in repeated.stdout
    rollback = run(tmp_path, GENOS_ERROR_PATCH_MODE='rollback', GENOS_ERROR_PATCH_RECEIPT=str(receipts[0]))
    assert rollback.returncode == 0, rollback.stderr
    assert all((tmp_path/rel).read_bytes() == before for rel, before in originals.items())


def test_mismatched_anchor_stops_before_any_code_write(tmp_path):
    originals = fixture(tmp_path)
    rel = '02_BACKEND/lawrag/pipeline/genos_progress.py'
    changed = (tmp_path/rel).read_text().replace('def reason(value):', 'def customized_reason(value):')
    (tmp_path/rel).write_text(changed)
    before = {rel: (tmp_path/rel).read_bytes() for rel in originals}
    result = run(tmp_path)
    assert result.returncode != 0
    assert 'CODE_PATCH_BASE_MISMATCH' in result.stderr
    assert all((tmp_path/rel).read_bytes() == raw for rel, raw in before.items())
