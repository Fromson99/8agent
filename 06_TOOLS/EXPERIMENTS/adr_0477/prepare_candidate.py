"""Mechanically snapshot parent bytes under a new ADR; no model execution."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0477-source-first-action-feedback'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0477/action-feedback'
OLD = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0476/qwen-autonomous'


def tool(*args):
    subprocess.run([str(ROOT / '.venv/bin/python'), str(ROOT / '06_TOOLS/run_tool.py'), 'adr_candidate.py', *args], cwd=ROOT, check=True)


def main():
    parent = json.loads((OLD / 'candidate.json').read_text())
    rev = next(r for r in parent['revisions'] if r['revision_id'] == 'rev-001')
    present, absent = [], []
    for row in rev['files']:
        row = dict(row, target_path=next(r['target_path'] for r in parent['files'] if r['snapshot_path'] == row['snapshot_path']))
        source = ROOT / row['frozen_path']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row['snapshot_sha256']
        (present if (ROOT / row['target_path']).is_file() else absent).append(row)
    cmd = ['snapshot', '--adr', str(ADR), '--candidate-id', 'action-feedback',
           '--experiment-id', 'ADR-0477-experiment-v1', '--arm-id', 'action-feedback', '--run-id', 'run-001']
    for row in present:
        cmd += ['--source', row['target_path']]
    tool(*cmd)
    for row in present + absent:
        dest = CAND / 'snapshot' / row['target_path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / row['frozen_path'], dest)
    for row in absent:
        tool('register', str(CAND), '--target', row['target_path'], '--upstream-state', 'absent')
    shutil.copyfile(ROOT / '04_EXPERIMENTS/ADR/ADR-0475-source-first-double-harness-wiring/fixture.json', ADR / 'fixture.json')
    print(json.dumps({'absent_targets': [r['target_path'] for r in absent]}, ensure_ascii=False))


if __name__ == '__main__':
    main()

