import ast
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'06_TOOLS/OFFLINE/genos_pdf_wait_patch.py'


def test_r9_upgrades_r8_and_repeats_without_rewriting(tmp_path):
    tree = ast.parse(SCRIPT.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'EDITS' for t in n.targets))
    edits = json.loads(ast.literal_eval(node.value.args[0]))
    # Recreate the historical R9 source; current code has R10's unlimited wait.
    r10 = ast.parse((ROOT/'06_TOOLS/OFFLINE/genos_pdf_no_cutoff_patch.py').read_text())
    r10_node = next(n for n in r10.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'EDITS' for t in n.targets))
    helper = next(e for e in json.loads(ast.literal_eval(r10_node.value.args[0]))
                  if e.get('variants'))
    for rel in dict.fromkeys(e['path'] for e in edits):
        from test_genos_pdf_no_cutoff_handoff import r10_source
        text = r10_source(rel)
        if rel == helper['path']:
            text = text.replace(helper['new'], helper['variants'][0])
        for e in reversed([e for e in edits if e['path'] == rel]):
            assert e['new'] in text, rel
            text = text.replace(e['new'], e['old'])
        ast.parse(text)
        dest = tmp_path/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    env = dict(os.environ, GENOS_DATA_ROOT=str(tmp_path/'data'), GENOS_RUN_ID='fixture')
    for script in (ROOT/'06_TOOLS/OFFLINE/genos_error_progress_patch.py', SCRIPT, SCRIPT,
                   ROOT/'06_TOOLS/OFFLINE/genos_pdf_no_cutoff_patch.py'):
        r = subprocess.run([sys.executable, str(script)], cwd=tmp_path, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout+r.stderr
    for rel in dict.fromkeys(e['path'] for e in edits):
        assert (tmp_path/rel).read_text() == r10_source(rel)
