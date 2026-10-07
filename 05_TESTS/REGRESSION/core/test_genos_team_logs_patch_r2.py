"""R2 accepts compatible pinned field additions while preserving their bytes."""
import ast
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
PATCH = ROOT / '08_DEPLOYMENT/GENOS/patches/team_request_logs_20260928_r2'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'
NEW_FILES = ['02_BACKEND/semantic_runtime/request_summary.py',
             '02_BACKEND/semantic_runtime/legal_agent/readable_log.py']


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helpers = load(Path(__file__).with_name('test_genos_team_logs_patch.py'), 'r1_patch_test_helpers')
installer = load(PATCH / 'apply.py', 'r2_team_log_installer')
transformer = load(PATCH / 'structural_report.py', 'r2_team_log_transformer')
gate = load(PATCH / 'gate.py', 'r2_team_log_gate')
TEMPLATES = transformer.load_templates(PATCH)
EXTRA = '\n# 현장 추가 진단은 바이트 그대로 보존\nFIELD_EXTRA = "모의 현장 진단"\ndef field_extra_probe():\n    return FIELD_EXTRA\n'.encode()


def report_variants():
    raws = {hashlib.sha256(f.read_bytes()).hexdigest(): f.read_bytes()
            for f in PATCH.parent.rglob('request_report.py')}
    thinking = load(PATCH.parent / 'thinking_log_20260928_r3/structural_report.py', 'r3_thinking_transformer')
    templates = thinking.load_templates(PATCH.parent / 'thinking_log_20260928_r3')
    for raw in list(raws.values()):
        new = thinking.transform(raw, templates)
        raws[hashlib.sha256(new).hexdigest()] = new
    return list(raws.values())


def invoke(root, *extra, ok=True):
    result = subprocess.run([sys.executable, str(PATCH / 'apply.py'), '--deploy-root', str(root), *extra],
                            capture_output=True, text=True)
    assert (result.returncode == 0) == ok, result.stdout + result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]


@pytest.mark.parametrize('raw', report_variants(), ids=lambda raw: hashlib.sha256(raw).hexdigest()[:10])
@pytest.mark.parametrize('crlf', [False, True], ids=['LF', 'CRLF'])
def test_installer_preserves_field_additions_and_is_reversible_with_exact_pins(tmp_path, raw, crlf):
    raw += EXTRA
    if crlf:
        raw = raw.replace(b'\n', b'\r\n')
    root = tmp_path / 'DEV'
    before = helpers.checkout(root, raw)
    checked = invoke(root, '--check-only')[-1]
    assert checked['status'] == 'CHECK_PASS'
    assert all((root / name).read_bytes() == data for name, data in before.items())
    rows = invoke(root)
    applied = rows[-1]
    assert applied['status'] == 'APPLIED'
    assert any(row['status'] == 'STRUCTURAL_CHECK_PASS' for row in rows)
    expected = transformer.transform(raw, TEMPLATES)
    assert (root / REPORT).read_bytes() == expected
    assert expected.endswith(EXTRA.replace(b'\n', b'\r\n') if crlf else EXTRA)
    # In particular, the existing diagnostic field inventory, emit, typed
    # thinking helper and readable completed-report formatter are not replaced.
    def untouched(value):
        tree = ast.parse(value)
        result = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                result[','.join(ast.dump(t) for t in node.targets)] = ast.get_source_segment(value.decode(), node)
            elif isinstance(node, ast.FunctionDef) and node.name not in TEMPLATES['functions']:
                result[node.name] = ast.get_source_segment(value.decode(), node)
            elif isinstance(node, ast.ClassDef):
                for method in node.body:
                    if isinstance(method, ast.FunctionDef) and node.name + '.' + method.name not in TEMPLATES['functions']:
                        result[node.name + '.' + method.name] = ast.get_source_segment(value.decode(), method)
        return result
    assert untouched(expected) == untouched(raw)
    config = json.loads((root / '00_SYSTEM/PIPELINE.json').read_bytes())
    assert config['datasets']['sha256'] == 'do-not-rewrite'
    for entry in config['engines'].values():
        manifest_raw = (root / entry['manifest']).read_bytes()
        assert installer.sha(manifest_raw) == entry['sha256']
        for name, expected_sha in json.loads(manifest_raw)['files'].items():
            assert installer.sha((root / name).read_bytes()) == expected_sha
    assert invoke(root)[-1]['status'] == 'ALREADY_APPLIED'
    helpers.git(root, 'add', '.')
    helpers.git(root, 'commit', '-qm', 'structural patch fixture')
    assert gate.compare_zip_to_checkout(Path(applied['gate_zip']), root)['commit'] == helpers.git(root, 'rev-parse', 'HEAD')
    invoke(root, '--rollback-from', applied['backup'])
    assert all((root / name).read_bytes() == data for name, data in before.items())
    assert all(not (root / name).exists() for name in NEW_FILES)


def test_r1_rejects_previous_thinking_variant_but_r2_preserves_it(tmp_path):
    path = PATCH.parent / 'thinking_log_20260928_r2/variants/7a16d852bc268ef913230d31cde9464bf0d490a19a0e6dc4ceb30be8973bc7ff' / REPORT
    raw = path.read_bytes()
    root = tmp_path / 'DEV'
    before = helpers.checkout(root, raw)
    old = subprocess.run([sys.executable, str(PATCH.parent / 'team_request_logs_20260928_r1/apply.py'),
                          '--deploy-root', str(root)], capture_output=True, text=True)
    assert old.returncode != 0 and 'unsupported installed version' in old.stderr
    assert all((root / name).read_bytes() == data for name, data in before.items())
    assert invoke(root)[-1]['status'] == 'APPLIED'


@pytest.mark.parametrize('baseline', ['relation_wait_20260928_r1/payload', 'latency_20260928_r1/payload'])
def test_thinking_r3_and_team_r2_can_be_applied_in_either_order(baseline):
    raw = (PATCH.parent / baseline / REPORT).read_bytes() + EXTRA
    thinking = load(PATCH.parent / 'thinking_log_20260928_r3/structural_report.py', 'thinking_order_transformer')
    templates = thinking.load_templates(PATCH.parent / 'thinking_log_20260928_r3')
    first_thinking = transformer.transform(thinking.transform(raw, templates), TEMPLATES)
    first_teams = thinking.transform(transformer.transform(raw, TEMPLATES), templates)
    assert first_thinking == first_teams


def test_new_working_diagnostic_fields_are_preserved_without_replacement():
    raw = (ROOT / REPORT).read_bytes()
    assert transformer.transform(raw, TEMPLATES) == raw


def test_gate_detects_git_line_ending_normalization_even_when_status_is_clean(tmp_path):
    raw = report_variants()[0].replace(b'\n', b'\r\n')
    root = tmp_path / 'DEV'
    helpers.checkout(root, raw)
    applied = invoke(root)[-1]
    helpers.put(root, '.gitattributes', b'*.py text eol=lf\n')
    helpers.git(root, 'add', '.')
    helpers.git(root, 'add', '--renormalize', '.')
    helpers.git(root, 'commit', '-qm', 'mock automatic line-ending normalization')
    assert not helpers.git(root, 'status', '--porcelain=v1', '--untracked-files=no')
    with pytest.raises(ValueError, match='committed bytes differ'):
        gate.compare_zip_to_checkout(Path(applied['gate_zip']), root)


def test_mid_apply_failure_restores_every_changed_file(tmp_path, monkeypatch):
    root = tmp_path / 'DEV'
    before = helpers.checkout(root, report_variants()[0])
    original = installer.atomic
    failed = False

    def fail_once(path, data):
        nonlocal failed
        if path == root / NEW_FILES[1] and not failed:
            failed = True
            raise OSError('mocked disk write failure')
        return original(path, data)

    monkeypatch.setattr(installer, 'atomic', fail_once)
    monkeypatch.setattr(sys, 'argv', ['apply.py', '--deploy-root', str(root)])
    with pytest.raises(OSError, match='mocked disk'):
        installer.main()
    assert all((root / name).read_bytes() == data for name, data in before.items())
    assert all(not (root / name).exists() for name in NEW_FILES)


@pytest.mark.parametrize('drift', ['report-pin', 'other-pin', 'manifest', 'schema', 'new-file', 'target-shape', 'helper-collision'])
def test_incompatible_contract_or_pin_is_rejected_before_write(tmp_path, drift):
    raw = report_variants()[0]
    if drift == 'target-shape':
        raw = raw.replace(b'self.admitted = False', b'self.admitted = True', 1)
    if drift == 'helper-collision':
        raw += b'\nreport_directory = None\n'
    root = tmp_path / 'DEV'
    before = helpers.checkout(root, raw)
    if drift == 'report-pin': helpers.put(root, REPORT, raw + EXTRA)
    elif drift == 'other-pin': helpers.put(root, 'unchanged.py', b'FIXTURE = False\n')
    elif drift == 'manifest': helpers.put(root, 'engines/legal.json', before['engines/legal.json'] + b'\n')
    elif drift == 'schema': helpers.put(root, 'schema.json', b'{}\n')
    elif drift == 'new-file': helpers.put(root, NEW_FILES[0], b'# unknown module\n')
    rows = invoke(root, ok=False)
    assert not any(row['status'] in {'BACKUP_READY', 'APPLIED'} for row in rows)
    assert (root / '00_SYSTEM/PIPELINE.json').read_bytes() == before['00_SYSTEM/PIPELINE.json']
    assert (root / 'engines/term.json').read_bytes() == before['engines/term.json']
    assert not (root / NEW_FILES[1]).exists()


@pytest.mark.parametrize('asset', ['structural_report.py', 'REPORT_TEMPLATES.json'])
def test_transform_assets_are_hash_bound(tmp_path, asset):
    root = tmp_path / 'DEV'
    before = helpers.checkout(root, report_variants()[0])
    spec = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
    spec['files'][REPORT]['assets'][asset] = '0' * 64
    with pytest.raises(ValueError, match='asset hash mismatch'):
        installer.prepare(root, spec)
    assert (root / REPORT).read_bytes() == before[REPORT]


@pytest.mark.parametrize('baseline', ['relation_wait_20260928_r1/payload',
                                     'thinking_log_20260928_r2/variants/7a16d852bc268ef913230d31cde9464bf0d490a19a0e6dc4ceb30be8973bc7ff'])
def test_transformed_runtime_writes_plain_log_and_team_excel(tmp_path, baseline):
    import semantic_runtime
    raw = (PATCH.parent / baseline / REPORT).read_bytes() + EXTRA
    module = type(semantic_runtime)('semantic_runtime.r2_report_fixture')
    module.__package__ = 'semantic_runtime'
    exec(compile(transformer.transform(raw, TEMPLATES), REPORT, 'exec'), module.__dict__)
    for team in ['risk_team', 'financial_team']:
        with module.DeferredReport(tmp_path / 'nfs', tmp_path / 'runtime', request_id='same-id',
                                   api_type='LEGAL_AGENT', request={'team_id': team, 'question': '모의 질문'},
                                   events=[]) as deferred:
            deferred.handler.write_detail('MODEL RESPONSE / LLM ANSWER', {'phase': 'plan',
                                         'reply': {'intent': '검토', 'reason': '모의 근거'}})
            deferred.complete({'status': 200, 'body': {'answer': {'text': '모의 최종 답변'}}})
    module._FINALIZER_QUEUE.join()
    paths = list((tmp_path / 'nfs').rglob('질문답변.csv'))
    assert {p.parent.name for p in paths} == {'risk_team', 'financial_team'}
    for p in paths:
        with p.open(encoding='utf-8-sig', newline='') as stream:
            row = next(csv.DictReader(stream))
        assert row['최종 답변'] == '모의 최종 답변' and row['팀'] == p.parent.name
        log = (p.parent / row['상세 로그']).read_text()
        assert '판단' in log and '이유' in log
        assert p.with_suffix('.xlsx').exists()
