"""Reproduce all three field identifiers and exercise the final nine-file ZIP."""
import ast
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
PATCHES = ROOT / '08_DEPLOYMENT/GENOS/patches'
PATCH = PATCHES / 'response_overhead_20260928_r3'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'
PRECHANGE = ROOT / '09_ARTIFACTS/AUDITS/20260928-response-overhead-r1/before'
FIELD_SHA = 'febd2ee7639102e4c376ccbb7ea98dec7a4b0dbd8ded86d32dfc7956c1d18b40'
FIELD_EMIT_SHA = '4a00a4ad8dd1f9e2e0c9c7e772dd1edb91200703ee467fec8e5d3d579d817bd4'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


helpers = load(Path(__file__).with_name('test_genos_response_overhead_patch_r2.py'), 'r3_previous_helpers')
old = load(PATCHES / 'response_overhead_20260928_r2/apply.py', 'r3_previous_installer')
installer = load(PATCH / 'apply.py', 'r3_field_installer')
transformer = load(PATCH / 'structural_report.py', 'r3_field_transform')
fulltext = load(PATCHES / 'fulltext_diagnostics_20260928_r1/report_fields.py', 'r3_fulltext_transform')
TEMPLATES = transformer.load_templates(PATCH)
FIELD = (PATCH / 'baselines' / FIELD_SHA / REPORT).read_bytes()
CASES = dict(helpers.CASES)
CASES.update({name + '-fulltext': fulltext.transform(raw) for name, raw in helpers.CASES.items()})
CASES['exact-field'] = FIELD


def actual_checkout(root, report=FIELD, service_variant=None):
    helpers.checkout(root, report)
    plan = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
    for name in plan['files']:
        if name != REPORT:
            helpers.put(root, name, (PRECHANGE / name).read_bytes())
    if service_variant:
        helpers.put(root, 'service.py', (PATCHES / 'response_overhead_20260928_r1/baselines' / service_variant / 'service.py').read_bytes())
    engine = {'files': {name: installer.sha((root / name).read_bytes()) for name in [*plan['files'], 'other.py']}}
    helpers.put(root, 'engines/fixture.json', installer.dump(engine))
    config = json.loads((root / '00_SYSTEM/PIPELINE.json').read_bytes())
    config['engines']['fixture']['sha256'] = installer.sha((root / 'engines/fixture.json').read_bytes())
    helpers.put(root, '00_SYSTEM/PIPELINE.json', installer.dump(config))
    helpers.git(root, 'add', '.'); helpers.git(root, 'commit', '-qm', 'actual prepatch bytes and exact field report')
    return helpers.snapshot(root)


def test_exact_photo_hash_size_function_and_r2_failure_are_reproduced_before_write(tmp_path):
    assert installer.sha(FIELD) == FIELD_SHA and len(FIELD) == 44082
    emit = transformer.functions(ast.parse(FIELD))['_LiveLog.emit'][0]
    assert transformer.signature(emit) == FIELD_EMIT_SHA
    root = tmp_path / 'DEV'; before = actual_checkout(root)
    # The photo's four preceding inputs are the actual R1 prechange bytes.
    for name in ['contracts.py', 'document_agent.py', 'navigation_agent.py', 'observability.py']:
        assert (root / '02_BACKEND/semantic_runtime' / name).read_bytes() == (PRECHANGE / '02_BACKEND/semantic_runtime' / name).read_bytes()
    with pytest.raises(ValueError, match='incompatible report functions: _LiveLog.emit ast_sha256=' + FIELD_EMIT_SHA):
        old.prepare(root, json.loads((PATCHES / 'response_overhead_20260928_r2/PATCH_MANIFEST.json').read_bytes()))
    assert helpers.snapshot(root) == before
    assert not list((root / 'TRANSFER').rglob('backup-*'))


@pytest.mark.parametrize('case', list(CASES))
@pytest.mark.parametrize('crlf', [False, True])
def test_all_previous_and_fulltext_derivations_preserve_other_functions_and_rerun(case, crlf):
    raw = CASES[case] + helpers.EXTRA
    if crlf: raw = raw.replace(b'\n', b'\r\n')
    after = transformer.transform(raw, TEMPLATES)
    assert transformer.transform(after, TEMPLATES) == after
    assert after.endswith(helpers.EXTRA.replace(b'\n', b'\r\n') if crlf else helpers.EXTRA)
    def preserved(data):
        text = data.decode(); tree = ast.parse(data); result = {}
        for name, rows in transformer.functions(tree).items():
            if name not in TEMPLATES['functions'] and name not in TEMPLATES['add_methods']:
                result[name] = ast.get_source_segment(text, rows[0])
        for node in tree.body:
            if isinstance(node, ast.Assign) and not any(isinstance(t, ast.Name) and t.id == '_LIVE_FIELD_NAMES' for t in node.targets):
                result[ast.unparse(node.targets[0])] = ast.get_source_segment(text, node)
        return result
    assert preserved(raw) == preserved(after)
    before_emit = transformer.functions(ast.parse(raw))['_LiveLog.emit'][0]
    after_emit = transformer.functions(ast.parse(after))['_LiveLog.emit'][0]
    def safe_projection(node):
        return next(ast.dump(n.value, include_attributes=False) for n in ast.walk(node) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'safe' for t in n.targets))
    assert safe_projection(before_emit) == safe_projection(after_emit)


PY311 = shutil.which('python3.11')


RUNTIME_SCRIPT = '''
import pathlib,types,sys,csv,logging
from datetime import datetime,timezone
from semantic_runtime import observability as obs
root=pathlib.Path(sys.argv[1]);report=sys.argv[2]
assert __import__('hashlib').sha256(pathlib.Path(obs.__file__).read_bytes()).hexdigest()==__import__('hashlib').sha256((root/'02_BACKEND/semantic_runtime/observability.py').read_bytes()).hexdigest()
m=types.ModuleType('semantic_runtime.py311_r3_field');m.__package__='semantic_runtime';m.__file__=str(root/report)
exec(compile((root/report).read_bytes(),report,'exec'),m.__dict__)
for team in ['risk_team','financial_team']:
 with m.DeferredReport(root/'reports',root/'runtime',request_id=team,api_type='LEGAL_AGENT',request={'team_id':team,'question':'모의 질문'},events=[]) as r:
  assert r._live_ready.wait(3) and r.handler and r.handler.writer
  record=logging.LogRecord(obs.ROOT,logging.INFO,__file__ if '__file__' in globals() else 'fixture',0,'fulltext.sql.batch.finished',(),None)
  record.fields={'request_id':team,'batch_wall_ms':12.5,'sql_status':'completed','thinking_requested':False,'diagnostics_version':'thinking-log-20260928-r1'}
  r.handler.writer.handle(record)
  r.handler.queue_detail('MODEL RESPONSE / LLM ANSWER',{'phase':'plan','reply':{'intent':'검토','reason':'모의 근거'}})
  r.complete({'status':200,'body':{'answer':{'text':'모의 답변'}}})
m._FINALIZER_QUEUE.join()
paths=list((root/'reports').rglob('질문답변.csv'));assert {p.parent.name for p in paths}=={'risk_team','financial_team'}
for p in paths:
 with p.open(encoding='utf-8-sig',newline='') as s:row=next(csv.DictReader(s))
 assert row['최종 답변']=='모의 답변' and p.with_suffix('.xlsx').exists()
 text=(p.parent/row['상세 로그']).read_text()
 assert 'RAG INPUT / QUESTION' in text and 'batch_wall_ms=12.5' in text and 'sql_status=completed' in text
 assert 'live_diagnostics_version=thinking-live-20260928-r3' in text and 'thinking_requested=false' in text
summary=m.format_readable_report({'service_events':[{'ts':datetime.now(timezone.utc).isoformat(),'event':'fulltext.sql.batch.finished','batch_wall_ms':12.5,'thinking_requested':False}]})
assert 'batch_wall_ms=12.5' in summary and 'thinking_requested=false' in summary
print('EXACT_FIELD_PY311_FULLTEXT_THINKING_TEAM_LOG_EXCEL_PASS')
'''


@pytest.mark.skipif(not PY311, reason='actual Python 3.11 required')
@pytest.mark.parametrize('crlf', [False, True])
@pytest.mark.parametrize('service_variant', [None, '89aa44402cbd33b8e7a2b0512f8ca903a7fefea4d7baf2906bd47d69c0e8c18f'])
def test_final_txt_actual_nine_prepatch_files_field_report_apply_rerun_commit_gate_runtime_rollback(tmp_path, crlf, service_variant):
    raw = FIELD if not crlf else FIELD.replace(b'\n', b'\r\n')
    root = tmp_path / 'workspace'; before = actual_checkout(root, raw, service_variant)
    alias = tmp_path / 'DEV'; alias.symlink_to(root, target_is_directory=True)
    txt = PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R3_APPLY.txt'
    env = {**os.environ, 'DEPLOY_ROOT': str(alias), 'PYTHON_BIN': PY311}
    def run(mode, **extra):
        result = subprocess.run(['bash', str(txt)], env={**env, 'MODE': mode, **extra}, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')][-1]
    assert run('check')['status'] == 'CHECK_PASS'; assert helpers.snapshot(root) == before
    applied = run('apply'); assert applied['status'] == 'APPLIED'
    assert applied['requested_deploy_root'] == str(alias) and applied['deploy_root'] == str(root)
    assert all(name in applied['changed_files'] for name in json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())['files'])
    assert (root / REPORT).read_bytes() == transformer.transform(raw, TEMPLATES)
    assert run('apply')['status'] == 'ALREADY_APPLIED'
    helpers.git(root, 'add', '.'); helpers.git(root, 'commit', '-qm', 'R3 exact field nine-file installation')
    result = subprocess.run([PY311, str(PATCH / 'gate.py'), '--code-only', '--code-zip', applied['gate_zip'],
                             '--deploy-root', str(root)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    runtime = subprocess.run([PY311, '-c', RUNTIME_SCRIPT, str(root), REPORT], capture_output=True, text=True,
                             env={**os.environ, 'PYTHONPATH': str(ROOT / '02_BACKEND')}, timeout=20)
    assert runtime.returncode == 0, runtime.stdout + runtime.stderr
    shutil.rmtree(root / 'reports')
    assert run('rollback', ROLLBACK_FROM=applied['backup'])['status'] == 'ROLLED_BACK'
    assert helpers.snapshot(root) == before


@pytest.mark.parametrize('drift', ['report-pin', 'manifest', 'schema', 'emit-contract', 'asset'])
def test_field_source_pin_or_contract_drift_is_rejected_before_write(tmp_path, drift):
    raw = FIELD
    if drift == 'emit-contract':
        node = transformer.functions(ast.parse(raw))['_LiveLog.emit'][0]
        source = ast.get_source_segment(raw.decode(), node).encode()
        changed = source.replace(b'if self.failed or', b'if not self.failed or', 1)
        assert changed != source
        raw = raw.replace(source, changed, 1)
    root = tmp_path / 'DEV'; actual_checkout(root, raw)
    if drift == 'report-pin': helpers.put(root, REPORT, raw + helpers.EXTRA)
    if drift == 'manifest': helpers.put(root, 'engines/fixture.json', (root / 'engines/fixture.json').read_bytes() + b'\n')
    if drift == 'schema': helpers.put(root, 'schema.json', b'{"type":"object"}\n')
    before = helpers.snapshot(root); plan = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
    if drift == 'asset': plan['files'][REPORT]['assets']['REPORT_TEMPLATES.json'] = '0' * 64
    with pytest.raises(ValueError): installer.prepare(root, plan)
    assert helpers.snapshot(root) == before


def test_actual_nine_file_partial_write_failure_restores_all_sources_and_pins(tmp_path, monkeypatch):
    root = tmp_path / 'DEV'; before = actual_checkout(root)
    atomic = installer.atomic; failed = False
    def fail_once(path, data):
        nonlocal failed
        if path == root / REPORT and not failed:
            failed = True; raise OSError('mock field write failure')
        atomic(path, data)
    monkeypatch.setattr(installer, 'atomic', fail_once)
    monkeypatch.setattr(sys, 'argv', ['apply.py', '--deploy-root', str(root)])
    with pytest.raises(OSError, match='mock field write failure'): installer.main()
    assert helpers.snapshot(root) == before
