#!/usr/bin/env python3
"""Oracle scale guard for one code tree (release/code or staged candidate). Scripted model only.

  .venv/bin/python 06_TOOLS/maintenance/oracle_scale_guard/run.py --code-root <code> --out <new dir>

1. inventory.py: every SQL template the release can send to Oracle (static).
2. test_guard_oracle.py on the local Oracle container: the shipped field profile (guided mode)
   question scenarios over a scope/document larger than a scaled row budget, then every
   Oracle-reachable prepared plan with edge-case values (fixture + measured field widths).
3. Judge -> <out>/report.json and <out>/보고서.txt. Exit 0 only when there is
   no request failure, no over-budget read, no full-catalogue refusal, no Oracle SQL error under
   realistic widths and no WITH+NUMBER (ORA-22806 shape) SQL.
"""
import argparse, hashlib, importlib, json, os, subprocess, sys, time, collections
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]
p = argparse.ArgumentParser()
p.add_argument('--code-root', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
p.add_argument('--budget', default='40'); p.add_argument('--parts', default='scenarios,comparison,sweep'); p.add_argument('--scenarios', default='')
p.add_argument('--no-preflight', action='store_true', help='unmasking probes on modified copies only (engine pins not rebuilt)')
args = p.parse_args(); code = args.code_root.resolve(); out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
subprocess.run([sys.executable, str(HERE/'inventory.py'), '--code-root', str(code), '--out', str(out/'inventory.json')], check=True)
os.environ.update(GUARD_EVIDENCE=str(out), GUARD_BUDGET=args.budget, GUARD_PARTS=args.parts, GUARD_SCENARIOS=args.scenarios,
    GUARD_INVENTORY=str(out/'inventory.json'), GUARD_SHAPES=str(HERE/'shapes-gold21.json'), GUARD_WIDTHS=str(HERE/'widths-local-1547.json'),
    AD_WORKER_ENABLED='0', GENOS_AUTO_WARMUP='0', PYTHONDONTWRITEBYTECODE='1',
    LOOP_TEST_CODE_ROOT=str(code), WORKFLOW_TEST_CODE_ROOT=str(code), GENOS_ONTOLOGY_CODE_ROOT=str(code))
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(code/'02_BACKEND'), str(code), str(ROOT/'05_TESTS'), str(ROOT/'05_TESTS/CONTRACTS'), str(ROOT/'06_TOOLS/COMMANDS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for n in ('pipeline', 'core', 'research'):
    pkg = importlib.import_module('lawrag.'+n); pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
import inspect, dataclasses, traceback  # noqa: E401  stdlib before conftest (06_TOOLS/EXPERIMENTS/adr_0928/inspect.py)
import conftest
sys.path[:0] = [str(HERE), str(code/'02_BACKEND'), str(code), str(ROOT/'05_TESTS/CONTRACTS'), str(ROOT/'06_TOOLS/COMMANDS')]
from genos_codespace_engine_preflight import check
engines, count, errors = check(code)
if errors and not args.no_preflight:
    raise SystemExit('engine preflight failed: ' + str(errors)[:500])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = {str(p.relative_to(code)): sha(p) for p in (code/'02_BACKEND').rglob('*.py') if '__pycache__' not in p.parts}
import pytest
rows = []
class Recorder:
    def pytest_runtest_logreport(self, report):
        if report.when == 'call' or report.failed:
            rows.append({'test': report.nodeid, 'outcome': report.outcome, 'error': report.longreprtext[-4000:] if report.failed else None})
start = time.monotonic()
status = pytest.main(['--noconftest', '-c', '/dev/null', '-q', *(['-s'] if os.environ.get('GUARD_VERBOSE') else []), '-p', 'no:cacheprovider', '--tb=short', '--basetemp', str(out/'runtime'),
                      str(HERE/'test_guard_oracle.py'),
                      *([str(HERE/'test_guard_comparison_oracle.py')] if 'comparison' in args.parts.split(',') else [])],
                     plugins=[conftest, Recorder()])
loaded = {n: str(Path(m.__file__).resolve()) for n, m in sys.modules.items() if n.startswith('semantic_runtime') and getattr(m, '__file__', None)}

run = {'code_root': str(code), 'pytest_exit': int(status), 'seconds': time.monotonic()-start, 'tests': rows,
       'engine_preflight_errors': errors[:5] if errors else [], 'code_unchanged': all(sha(code/n) == h for n, h in before.items()),
       'loaded_outside_code': sorted(n for n, path in loaded.items() if not Path(path).is_relative_to(code))}
(out/'run.json').write_text(json.dumps(run, ensure_ascii=False, indent=1) + '\n')
import judge
raise SystemExit(judge.main(out))
