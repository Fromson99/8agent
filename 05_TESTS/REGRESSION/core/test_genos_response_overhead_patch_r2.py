"""Reuse the prior R3 repairs; verify a pinned, reversible offline installation."""
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
import threading
from contextlib import contextmanager

import pytest

ROOT = Path(__file__).resolve().parents[3]
PATCHES = ROOT / '08_DEPLOYMENT/GENOS/patches'
OLD = PATCHES / 'response_overhead_20260928_r1'
PATCH = PATCHES / 'response_overhead_20260928_r2'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'
EXTRA = '\n# 현장 추가 코드는 보존\nFIELD_PROBE = "모의 진단"\ndef field_probe():\n    return FIELD_PROBE\n'.encode()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transformer = load(PATCH / 'structural_report.py', 'response_r2_transform')
installer = load(PATCH / 'apply.py', 'response_r2_installer')
gate = load(PATCH / 'gate.py', 'response_r2_gate')
templates = transformer.load_templates(PATCH)
team_dir = PATCHES / 'team_request_logs_20260928_r3'
team = load(team_dir / 'structural_report.py', 'response_previous_team_r3')
thinking_dir = PATCHES / 'thinking_log_20260928_r3'
thinking = load(thinking_dir / 'structural_report.py', 'response_previous_thinking_r3')


def cases():
    result = {}
    for file in sorted((OLD / 'baselines').glob('*/' + REPORT)):
        raw = file.read_bytes()
        typed = thinking.transform(raw, thinking.load_templates(thinking_dir))
        for suffix, data in [('base', raw), ('team-r3', team.transform(raw, team.load_templates(team_dir))),
                             ('thinking-r3', typed), ('both-r3', team.transform(typed, team.load_templates(team_dir)))]:
            result[file.parts[-4][:8] + '-' + suffix] = data
    for file in sorted((OLD / 'variants').glob('*/' + REPORT)):
        result[file.parts[-4][:8] + '-applied-r1'] = file.read_bytes()
    result['working-fulltext'] = (ROOT / REPORT).read_bytes()
    return result


CASES = cases()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), '-c', 'user.name=Fixture',
                                    '-c', 'user.email=fixture@example.invalid',
                                    '-c', 'core.hooksPath=/dev/null', *args], text=True).strip()


def put(root, name, raw):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def checkout(root, raw):
    root.mkdir()
    plan = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
    for name in plan['files']:
        put(root, name, raw if name == REPORT else (OLD / 'payload' / name).read_bytes())
    put(root, 'other.py', b'FIXTURE = True\n')
    put(root, 'schema.json', b'{}\n')
    files = {name: installer.sha((root / name).read_bytes()) for name in [*plan['files'], 'other.py']}
    put(root, 'engines/fixture.json', installer.dump({'files': files}))
    put(root, '00_SYSTEM/PIPELINE.json', installer.dump({
        'engines': {'fixture': {'manifest': 'engines/fixture.json',
                                'sha256': installer.sha((root / 'engines/fixture.json').read_bytes())}},
        'contracts': {'fixture': {'schema_path': 'schema.json', 'schema_sha256': installer.sha(b'{}\n')}},
        'datasets': {'sha256': 'do-not-change-data-pin'}}))
    git(root, 'init', '-q'); git(root, 'add', '.'); git(root, 'commit', '-qm', 'offline fixture')
    return snapshot(root)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '.git' not in p.parts and 'TRANSFER' not in p.parts}


@pytest.mark.parametrize('case', list(CASES))
@pytest.mark.parametrize('crlf', [False, True])
def test_previous_r3_combinations_preserve_unrelated_source_and_rerun(case, crlf):
    raw = CASES[case] + EXTRA
    if crlf:
        raw = raw.replace(b'\n', b'\r\n')
    after = transformer.transform(raw, templates)
    assert transformer.transform(after, templates) == after
    assert after.endswith(EXTRA.replace(b'\n', b'\r\n') if crlf else EXTRA)
    def untouched(data):
        text = data.decode()
        tree = ast.parse(data)
        result = {}
        for name, nodes in transformer.functions(tree).items():
            if name not in templates['functions'] and name not in templates['add_methods']:
                result[name] = ast.get_source_segment(text, nodes[0])
        for node in tree.body:
            if isinstance(node, ast.Assign) and not any(isinstance(t, ast.Name) and t.id == '_LIVE_FIELD_NAMES' for t in node.targets):
                result[ast.unparse(node.targets[0])] = ast.get_source_segment(text, node)
        return result
    assert untouched(raw) == untouched(after)


def test_photo_failure_reproduces_and_r2_applies_rolls_back_exact_pins(tmp_path, monkeypatch, capsys):
    raw = team.transform(thinking.transform(CASES[next(iter(CASES))], thinking.load_templates(thinking_dir)),
                         team.load_templates(team_dir)) + EXTRA
    root = tmp_path / 'DEV'; before = checkout(root, raw)
    old = load(OLD / 'apply.py', 'response_old_rejection')
    with pytest.raises(ValueError, match='unsupported installed version; no changes: ' + REPORT):
        old.prepare(root, json.loads((OLD / 'PATCH_MANIFEST.json').read_bytes()))
    assert snapshot(root) == before
    monkeypatch.setattr(sys, 'argv', ['apply.py', '--deploy-root', str(root)])
    installer.main(); rows = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{')]
    applied = rows[-1]; assert applied['status'] == 'APPLIED'
    assert (root / REPORT).read_bytes() == transformer.transform(raw, templates)
    installer.main(); assert 'ALREADY_APPLIED' in capsys.readouterr().out
    config = json.loads((root / '00_SYSTEM/PIPELINE.json').read_bytes())
    assert config['datasets']['sha256'] == 'do-not-change-data-pin'
    engine_raw = (root / 'engines/fixture.json').read_bytes()
    assert installer.sha(engine_raw) == config['engines']['fixture']['sha256']
    for name, digest in json.loads(engine_raw)['files'].items():
        assert installer.sha((root / name).read_bytes()) == digest
    git(root, 'add', '.'); git(root, 'commit', '-qm', 'R2 fixture')
    assert gate.compare_zip_to_checkout(Path(applied['gate_zip']), root)['commit'] == git(root, 'rev-parse', 'HEAD')
    installer.rollback(root, Path(applied['backup']))
    assert snapshot(root) == before


@pytest.mark.parametrize('drift', ['report-pin', 'other-pin', 'manifest', 'schema', 'function', 'live-fields', 'asset'])
def test_invalid_pin_contract_or_asset_is_rejected_before_source_write(tmp_path, drift):
    raw = CASES[next(iter(CASES))]
    if drift == 'function': raw = raw.replace(b'self.admitted = False', b'self.admitted = True', 1)
    if drift == 'live-fields': raw = raw.replace(b'_LIVE_FIELD_NAMES = frozenset({', b'_LIVE_FIELD_NAMES = set({', 1)
    root = tmp_path / 'DEV'; checkout(root, raw)
    if drift == 'report-pin': put(root, REPORT, raw + EXTRA)
    if drift == 'other-pin': put(root, 'other.py', b'FIXTURE = False\n')
    if drift == 'manifest': put(root, 'engines/fixture.json', (root / 'engines/fixture.json').read_bytes() + b'\n')
    if drift == 'schema': put(root, 'schema.json', b'{"type":"object"}\n')
    before = snapshot(root)
    spec = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
    if drift == 'asset': spec['files'][REPORT]['assets']['REPORT_TEMPLATES.json'] = '0' * 64
    with pytest.raises(ValueError): installer.prepare(root, spec)
    assert snapshot(root) == before


def test_mid_apply_failure_restores_every_source_and_pin(tmp_path, monkeypatch):
    root = tmp_path / 'DEV'; before = checkout(root, CASES[next(iter(CASES))])
    atomic = installer.atomic; failed = False
    def fail_once(path, data):
        nonlocal failed
        if path == root / REPORT and not failed:
            failed = True
            raise OSError('mock write failure')
        atomic(path, data)
    monkeypatch.setattr(installer, 'atomic', fail_once)
    monkeypatch.setattr(sys, 'argv', ['apply.py', '--deploy-root', str(root)])
    with pytest.raises(OSError, match='mock write failure'): installer.main()
    assert snapshot(root) == before


@pytest.mark.parametrize('case', [name for name in CASES if name.endswith('both-r3')])
def test_runtime_returns_while_open_is_blocked_and_keeps_team_plain_log_and_excel(case, tmp_path, monkeypatch):
    module = load(PATCH / 'payload' / REPORT, 'semantic_runtime.overhead_r2_fixture_' + case)
    raw = transformer.transform(CASES[case], templates)
    exec(compile(raw, REPORT, 'exec'), module.__dict__)
    entered, release = threading.Event(), threading.Event()
    original = module.live_log
    @contextmanager
    def blocked(*args, **kwargs):
        entered.set(); assert release.wait(5)
        with original(*args, **kwargs) as result: yield result
    monkeypatch.setattr(module, 'live_log', blocked)
    try:
        for team_id in ['risk_team', 'financial_team']:
            with module.DeferredReport(tmp_path / 'nfs', tmp_path / 'runtime', request_id=team_id,
                    api_type='LEGAL_AGENT', request={'team_id': team_id, 'question': '모의 질문'}, events=[]) as report:
                assert entered.wait(2)
                report.complete({'status': 200, 'body': {'answer': {'text': '모의 최종 답변'}}})
            assert not report._live_ready.is_set()
    finally:
        release.set(); module._FINALIZER_QUEUE.join()
    paths = list((tmp_path / 'nfs').rglob('질문답변.csv'))
    assert {p.parent.name for p in paths} == {'risk_team', 'financial_team'}
    for path in paths:
        with path.open(encoding='utf-8-sig', newline='') as stream: row = next(csv.DictReader(stream))
        assert row['최종 답변'] == '모의 최종 답변'
        assert path.with_suffix('.xlsx').exists()
        assert 'RAG INPUT / QUESTION' in (path.parent / row['상세 로그']).read_text()


PY311 = shutil.which('python3.11')


@pytest.mark.skipif(not PY311, reason='actual Python 3.11 required')
def test_canonical_signatures_and_result_bytes_match_actual_python_311():
    script = '''
import hashlib,importlib.util,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);s=importlib.util.spec_from_file_location('r',p/'structural_report.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
t=m.load_templates(p);rows={}
for file in (p.parent/'response_overhead_20260928_r1').rglob('request_report.py'):
 raw=file.read_bytes();after=m.transform(raw,t);assert m.transform(after,t)==after;rows[str(file)]=hashlib.sha256(after).hexdigest()
print(json.dumps(rows,sort_keys=True))
'''
    runs = [subprocess.run([python, '-c', script, str(PATCH)], capture_output=True, text=True)
            for python in [PY311, sys.executable]]
    assert all(r.returncode == 0 for r in runs), [r.stderr for r in runs]
    assert runs[0].stdout == runs[1].stdout


@pytest.mark.skipif(not PY311, reason='actual Python 3.11 required')
@pytest.mark.parametrize('crlf', [False, True])
def test_final_zip_txt_apply_rerun_committed_gate_and_rollback_on_python311_dev_symlink(tmp_path, crlf):
    raw = next(raw for name, raw in CASES.items() if name.endswith('both-r3')) + EXTRA
    if crlf: raw = raw.replace(b'\n', b'\r\n')
    root = tmp_path / 'workspace'; before = checkout(root, raw)
    alias = tmp_path / 'DEV'; alias.symlink_to(root, target_is_directory=True)
    txt = PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R2_APPLY.txt'
    env = {**os.environ, 'DEPLOY_ROOT': str(alias), 'PYTHON_BIN': PY311, 'MODE': 'apply'}
    def run(mode, **updates):
        result = subprocess.run(['bash', str(txt)], env={**env, 'MODE': mode, **updates}, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')][-1]
    assert run('check')['status'] == 'CHECK_PASS'
    assert snapshot(root) == before
    applied = run('apply'); assert applied['status'] == 'APPLIED'
    assert applied['requested_deploy_root'] == str(alias) and applied['deploy_root'] == str(root)
    assert run('apply')['status'] == 'ALREADY_APPLIED'
    git(root, 'add', '.'); git(root, 'commit', '-qm', 'actual Python 3.11 offline fixture')
    check = subprocess.run([PY311, str(PATCH / 'gate.py'), '--code-only', '--code-zip', applied['gate_zip'],
                            '--deploy-root', str(root)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
    runtime_script = '''
import pathlib,types,sys,csv
root=pathlib.Path(sys.argv[1]);report=sys.argv[2]
m=types.ModuleType('semantic_runtime.py311_overhead');m.__package__='semantic_runtime'
m.__file__=str(root/report)
exec(compile((root/report).read_bytes(),report,'exec'),m.__dict__)
for team in ['risk_team','financial_team']:
 with m.DeferredReport(root/'reports',root/'runtime',request_id=team,api_type='LEGAL_AGENT',request={'team_id':team,'question':'모의 질문'},events=[]) as r:
  assert r._live_ready.wait(3) and r.handler and r.handler.writer
  r.handler.queue_detail('MODEL RESPONSE / LLM ANSWER',{'phase':'plan','reply':{'intent':'검토','reason':'모의 근거'}})
  r.complete({'status':200,'body':{'answer':{'text':'모의 답변'}}})
m._FINALIZER_QUEUE.join()
paths=list((root/'reports').rglob('질문답변.csv'));assert {p.parent.name for p in paths}=={'risk_team','financial_team'}
for p in paths:
 with p.open(encoding='utf-8-sig',newline='') as s:row=next(csv.DictReader(s))
 assert row['최종 답변']=='모의 답변' and p.with_suffix('.xlsx').exists()
 assert 'RAG INPUT / QUESTION' in (p.parent/row['상세 로그']).read_text()
print('PY311_RUNTIME_PASS')
'''
    runtime = subprocess.run([PY311, '-c', runtime_script, str(root), REPORT], capture_output=True, text=True,
                             env={**os.environ, 'PYTHONPATH': str(ROOT / '02_BACKEND')}, timeout=20)
    assert runtime.returncode == 0 and 'PY311_RUNTIME_PASS' in runtime.stdout, runtime.stdout + runtime.stderr
    shutil.rmtree(root / 'reports')
    assert run('rollback', ROLLBACK_FROM=applied['backup'])['status'] == 'ROLLED_BACK'
    assert snapshot(root) == before
