"""Small synthetic contract runner. No experiment/model/corpus/MAIN mutation."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import time
import faulthandler

ROOT = Path('/home/jin/8-AGENT')
C = ROOT / json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-1259-wiki-typed-proposal-oracle-live/artifacts/design/freeze.json').read_text())['code_root']
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20261030-wiki-workspace-implementation'
p = argparse.ArgumentParser()
p.add_argument('--baseline', action='store_true')
p.add_argument('--adapt-legacy', action='store_true')
p.add_argument('--output', required=True)
p.add_argument('tests', nargs='+')
a = p.parse_args()
stack_file=open(a.output+'.stack.txt','w')
faulthandler.dump_traceback_later(25, repeat=False, file=stack_file)
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(C), LAWRAG_WORKSPACE_ROOT=str(ROOT),
                  LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT), GENOS_AUTO_WARMUP='0', AD_WORKER_ENABLED='0')
sys.path[:0] = [str(C / '02_BACKEND'), str(ROOT / '05_TESTS/CONTRACTS')]
if a.baseline:
    for package, directory in [('semantic_runtime.ontology_work', 'ontology_work'),
                               ('semantic_runtime.legal_agent', 'legal_agent')]:
        module = importlib.import_module(package)
        module.__path__.insert(0, str(AUDIT / 'before/02_BACKEND/semantic_runtime' / directory))
import semantic_runtime
assert Path(semantic_runtime.__file__).resolve().is_relative_to(C.resolve()), semantic_runtime.__file__
import lawrag,lawrag.pipeline
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
lawrag.pipeline.__path__.append(str(ROOT/'02_BACKEND/lawrag/pipeline'))
import pytest


class Results:
    rows = []
    runtime_errors = []

    def pytest_runtest_logreport(self, report):
        if report.when == 'call' or report.failed:
            self.rows.append({'test': report.nodeid, 'when': report.when, 'status': report.outcome,
                              'seconds': report.duration, 'error': report.longreprtext if report.failed else None})

    @pytest.fixture(autouse=True)
    def legacy_wire(self, monkeypatch):
        from semantic_runtime import app as app_module
        old_error=app_module.legal_error_payload
        def traced_error(exc,*args,**kwargs):
            self.runtime_errors.append({'handler':True,'type':type(exc).__name__,'error':str(exc)[:4000]})
            return old_error(exc,*args,**kwargs)
        monkeypatch.setattr(app_module,'legal_error_payload',traced_error)
        from semantic_runtime.legal_agent.gateway import ModelGateway
        call=ModelGateway.generate
        def traced(gateway,*args,**kwargs):
            try:return call(gateway,*args,**kwargs)
            except Exception as exc:
                self.runtime_errors.append({'phase':str(args[0]) if args else None,'type':type(exc).__name__,'error':str(exc)[:4000]})
                raise
        monkeypatch.setattr(ModelGateway,'generate',traced)
        if not a.adapt_legacy:
            yield
            return
        from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
        from copy import deepcopy
        original = DomainWorkflow._job
        def job(self, stage, context, prompt, schema, validator, binding_check=None):
            generator = self.generate
            if stage == 'NORMALIZE' and generator is not None:
                def modern(*args):
                    value, receipt = generator(*args)
                    if not isinstance(value, dict) or 'observations' not in value or any('recorded_reason' in o for o in value['observations']):
                        return value, receipt
                    value = deepcopy(value)
                    for row in value['observations']:
                        for key in ('reason', 'purpose'):
                            old = row.pop(key)
                            assert old['state'] != 'PRESENT'
                            row['recorded_' + key] = None
                    if isinstance(value.get('coverage'), list) and value['coverage']:
                        value['coverage'] = {r['pointer']: {k: v for k, v in r.items() if k != 'pointer'} for r in value['coverage']}
                    segments = {r['pointer']: r['text'] for r in context['raw']['index']}
                    def walk(v):
                        if isinstance(v, dict):
                            if set(v) == {'payload_hash', 'pointer', 'start', 'end', 'quote'}:
                                from semantic_runtime.ontology_work.observations import check_locator
                                check_locator(v, context['raw'])
                                starts = []; i = -1
                                while True:
                                    i = segments[v['pointer']].find(v['quote'], i + 1)
                                    if i < 0: break
                                    starts.append(i)
                                return {'pointer': v['pointer'], 'quote': v['quote'], 'occurrence': starts.index(v['start'])}
                            return {k: walk(x) for k, x in v.items()}
                        if isinstance(v, list): return [walk(x) for x in v]
                        return v
                    return walk(value), receipt
                self.generate = modern
            try: return original(self, stage, context, prompt, schema, validator, binding_check)
            finally: self.generate = generator
        monkeypatch.setattr(DomainWorkflow, '_job', job)
        yield


r = Results(); start = time.monotonic()
code = pytest.main(['-q', '-o', 'pythonpath='+str(C/'02_BACKEND')+' '+str(ROOT), '--tb=short', '--show-capture=no', *a.tests], plugins=[r])
out = Path(a.output)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({'kind': 'SYNTHETIC_CONTRACT_CHECK_NOT_MODEL_QUALITY_EXPERIMENT',
    'code_root':str(C),'loaded_semantic_runtime':semantic_runtime.__file__,'baseline_module_overlay': a.baseline, 'legacy_generator_wire_adapter': a.adapt_legacy,
    'runtime_errors':r.runtime_errors,'exit_code': int(code), 'seconds': time.monotonic()-start,
    'passed': sum(x['status']=='passed' for x in r.rows),
    'failed': sum(x['status']=='failed' for x in r.rows), 'rows': r.rows,
    'external_model_calls': 0}, ensure_ascii=False, indent=2)+'\n')
raise SystemExit(int(code))
