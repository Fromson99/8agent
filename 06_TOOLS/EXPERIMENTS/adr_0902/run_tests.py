from pathlib import Path
import hashlib, json, os, runpy

R = Path(__file__).resolve().parents[3]
D = R / '04_EXPERIMENTS/ADR/ADR-0902-read-input-contract-qualification/artifacts/design'
f = json.loads((D / 'freeze.json').read_text())
for name, expected in f['files'].items():
    assert hashlib.sha256((R / name).read_bytes()).hexdigest() == expected, name
os.environ['TASK_TEST_CODE_ROOT'] = str(R / f['code_root'])
runpy.run_path(str(R / '06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py'), run_name='__main__')
