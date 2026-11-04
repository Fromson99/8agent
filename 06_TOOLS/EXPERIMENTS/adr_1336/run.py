"""Contract runner for the exact MAIN140-derived Gold handoff candidate."""
from pathlib import Path
import os, sys, json, time, importlib, inspect
import pytest

ROOT=Path(__file__).resolve().parents[3]
AUDIT=ROOT/'04_EXPERIMENTS/ADR/ADR-1336-gold-workflow-review-main/artifacts'
CODE=ROOT/json.loads((AUDIT/'design/candidate-prepared.json').read_text())['code_root']
name=sys.argv[1]; tests=sys.argv[2:]
out=AUDIT/name;out.mkdir(exist_ok=False)
os.environ.update(LOOP_TEST_CODE_ROOT=str(CODE),WORKFLOW_TEST_CODE_ROOT=str(CODE),
    GENOS_ONTOLOGY_CODE_ROOT=str(CODE),LOOP_TEST_REPOSITORY_ROOT=str(ROOT),GENOS_AUTO_WARMUP='0',
    AD_WORKER_ENABLED='0',PYTHONDONTWRITEBYTECODE='1',MALLOC_ARENA_MAX='1')
os.environ.pop('DP',None)
sys.dont_write_bytecode=True
sys.path[:0]=[str(CODE/'02_BACKEND'),str(CODE),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for part in ('pipeline','core'):
    package=importlib.import_module('lawrag.'+part)
    package.__path__.append(str(ROOT/'02_BACKEND/lawrag'/part))
import conftest, pytest
sys.path[:0]=[str(CODE/'02_BACKEND'),str(CODE),str(Path(__file__).parent),
             str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1317')]
rows=[]
class Recorder:
    def pytest_runtest_logreport(self, report):
        if report.when=='call' or report.failed:
            rows.append({'test':report.nodeid,'phase':report.when,'outcome':report.outcome,
                         'error':report.longreprtext if report.failed else None})
from resource_guard import Guard
guard=Guard(out);guard.start();started=time.monotonic()
status=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','-p','no:cacheprovider',
    '--basetemp='+str(out/'runtime'),*[str(ROOT/p) for p in tests]],plugins=[conftest,Recorder()])
guard.done.set();guard.thread.join(timeout=2)
(out/'result.json').write_text(json.dumps({'code_root':str(CODE),'exit_code':int(status),
    'passed':sum(r['outcome']=='passed' for r in rows),'failed':sum(r['outcome']=='failed' for r in rows),
    'seconds':time.monotonic()-started,'rows':rows,'resources':guard.check()},ensure_ascii=False,indent=2)+'\n')
raise SystemExit(int(status))
