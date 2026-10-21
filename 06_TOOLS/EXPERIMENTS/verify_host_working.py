"""Run unchanged working tests serially, isolating the real-index service test."""
from pathlib import Path
import hashlib, json, os, re, subprocess, sys
R = Path(__file__).resolve().parents[2]
A = R / '04_EXPERIMENTS/ADR/ADR-0870-host-owned-enum-contract/artifacts'
p = json.loads((A / 'design/execution-plan.json').read_text())
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest() == h for n,h in p['test_hashes'].items())
env = {**os.environ, 'TASK_TEST_CODE_ROOT': str(R)}
heavy = 'test_selected_local_release_receives_settings_without_rewriting_frozen_files'
logs = []
for name, tests, extra, limits in [
    ('unit', p['tests'], ['-k', 'not '+heavy], ['--rss-gib','2','--as-gib','3']),
    ('index', ['05_TESTS/CONTRACTS/test_investigation_budget_settings.py::'+heavy], [], []),
]:
    log = A / ('working-'+name+'.log')
    with log.open('x') as out:
        subprocess.run([sys.executable, '06_TOOLS/EXPERIMENTS/resource_guard.py',
            '--record', str(A/('working-'+name+'-resources.json')), *limits, '--',
            sys.executable, '06_TOOLS/EXPERIMENTS/adr_0870/run_tests.py',
            '-q','--tb=short',*tests,*extra], cwd=R, env=env, stdout=out, stderr=subprocess.STDOUT, check=True)
    logs.append(log.read_text())
assert [int(re.findall(r'(\d+) passed', text)[-1]) for text in logs] == [414,1]
with (A/'working-api.log').open('x') as out:
    out.write('\n'.join(logs)+'\nSequential aggregate: 415 passed; frozen tests unchanged.\n')
print('Working tests: 415 passed in sequential bounded processes')
