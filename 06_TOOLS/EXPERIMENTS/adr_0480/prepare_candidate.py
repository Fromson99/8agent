"""Copy verified parent candidate bytes; never select this from production."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0480-cm003-reviewed-source-relations'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0480/explicit-link'
OLD = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0479/linked-context'

def tool(*args):
    subprocess.run([str(ROOT/'.venv/bin/python'), str(ROOT/'06_TOOLS/run_tool.py'), 'adr_candidate.py', *args], cwd=ROOT, check=True)

def main():
    parent = json.loads((OLD/'candidate.json').read_text())
    rev = next(r for r in parent['revisions'] if r['revision_id'] == 'rev-001')
    present, absent = [], []
    for row in rev['files']:
        row = dict(row, target_path=next(r['target_path'] for r in parent['files'] if r['snapshot_path'] == row['snapshot_path']))
        assert hashlib.sha256((ROOT/row['frozen_path']).read_bytes()).hexdigest() == row['snapshot_sha256']
        (present if (ROOT/row['target_path']).is_file() else absent).append(row)
    args = ['snapshot', '--adr', str(ADR), '--candidate-id', 'explicit-link', '--experiment-id', 'ADR-0480-experiment-v1', '--arm-id', 'explicit-link', '--run-id', 'run-001']
    for r in present:
        args += ['--source', r['target_path']]
    tool(*args)
    for r in present+absent:
        dest = CAND/'snapshot'/r['target_path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/r['frozen_path'], dest)
    for r in absent:
        tool('register', str(CAND), '--target', r['target_path'], '--upstream-state', 'absent')
    shutil.copyfile(ROOT/'04_EXPERIMENTS/ADR/ADR-0479-bounded-linked-evidence/fixture.json', ADR/'fixture.json')

if __name__ == '__main__':
    main()
