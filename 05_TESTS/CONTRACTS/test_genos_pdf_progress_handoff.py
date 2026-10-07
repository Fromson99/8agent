from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT/'06_TOOLS/OFFLINE/genos_error_progress_patch.py'


def test_r8_applies_to_r7_checkout_and_is_repeatable(tmp_path, monkeypatch):
    # R7 fixture reverses only its own changes; current PDF progress remains.
    # Undo the progress layer separately to recreate the original checkout.
    import ast, json, os
    tree = ast.parse(INSTALLER.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'EDITS' for t in n.targets))
    edits = json.loads(ast.literal_eval(node.value.args[0]))
    for rel in dict.fromkeys(e['path'] for e in edits):
        dest = tmp_path/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = (ROOT/rel).read_text()
        for e in reversed([e for e in edits if e['path'] == rel]):
            assert e['new'] in text, rel
            text = text.replace(e['new'], e['old'])
        ast.parse(text)
        dest.write_text(text)
    env = dict(os.environ, GENOS_DATA_ROOT=str(tmp_path/'data'), GENOS_RUN_ID='fixture')
    for script in (ROOT/'06_TOOLS/OFFLINE/genos_actual_error_patch.py', INSTALLER, INSTALLER):
        result = subprocess.run([sys.executable, str(script)], cwd=tmp_path, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout+result.stderr
    for rel in dict.fromkeys(e['path'] for e in edits):
        assert (tmp_path/rel).read_bytes() == (ROOT/rel).read_bytes()
