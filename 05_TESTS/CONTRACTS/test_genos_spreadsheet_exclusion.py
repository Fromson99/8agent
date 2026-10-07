"""Spreadsheet exclusions preserve RAW and receipts; no GENOS calls."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import fitz
import pytest
from lawrag.pipeline import genos_build as build, raw_preprocess as prep, team_raw as teams

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'06_TOOLS/OFFLINE/genos_spreadsheet_exclusion_patch.py'
TXT = ROOT/'08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_FULL_PIPELINE_BACKUP_E2E_R11_UTF8.txt'


def edits_of(script):
    node = next(n for n in ast.parse(script.read_text()).body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'EDITS' for t in n.targets))
    return json.loads(ast.literal_eval(node.value.args[0]))


def test_spreadsheets_not_converted_and_exclusions_recorded(tmp_path, monkeypatch):
    branch = tmp_path/'RAW/external/risk_team/law/forms'
    branch.mkdir(parents=True)
    originals = []
    for suffix in ('.xls', '.xlsx'):
        p = branch/('report'+suffix)
        p.write_bytes(b'original fixture')
        originals.append(p)
    source = branch/'regulation.hwp'
    source.write_bytes(b'hwp fixture')
    calls = []
    def convert(p, work):
        calls.append(p)
        dest = work/'source.pdf'
        with fitz.open() as doc:
            doc.new_page()
            doc.save(dest)
        return dest, {'status': 'CONVERTED'}
    monkeypatch.setattr(prep, 'convert', convert)
    messages = []
    result = prep.run(build.ROOT, tmp_path, tmp_path/'LOGS/run/preparation',
                      execute=True, emit=messages.append)
    assert calls == [source]
    assert result['pdf_statuses']['EXCLUDED_SPREADSHEET'] == 2
    assert all(p.read_bytes() == b'original fixture' for p in originals)
    assert all(not p.with_suffix('.pdf').exists() for p in originals)
    report = json.loads(Path(result['path']).read_text())
    assert not report['errors']
    excluded = [r for r in report['files'] if r.get('status') == 'EXCLUDED_SPREADSHEET']
    assert all(r['reason'] == prep.SPREADSHEET_EXCLUSION and r['sha256'] for r in excluded)
    _, collected = teams.collect(tmp_path, emit=lambda _: None)
    assert sum(r['reason'] == prep.SPREADSHEET_EXCLUSION for r in collected['excluded']) == 2


def test_old_spreadsheet_jobs_are_skipped_without_touching_receipts(tmp_path, monkeypatch):
    from test_genos_full_pipeline_r6_recovery import setup
    _, source, pdf, receipt = setup(tmp_path)
    record = json.loads(receipt.read_text())
    record['request']['file_path'] = str(source.with_suffix('.xls'))
    receipt.write_text(json.dumps(record))
    prior = receipt.read_bytes()
    pdf.unlink()
    monkeypatch.setenv('GENOS_PDF_CONVERTER_SHARED_ROOT', str(tmp_path/'shared'))
    monkeypatch.setenv('GENOS_PDF_CONVERTER_ID', '187')
    monkeypatch.delenv('GENOS_PDF_CONVERTER_URL', raising=False)
    monkeypatch.setattr(prep, '_wait_for_pdf', lambda *a, **kw: pytest.fail('must not wait'))
    monkeypatch.setattr(prep, 'convert', lambda *a, **kw: pytest.fail('must not repost'))
    monkeypatch.setattr(sys, 'argv', ['recover', str(tmp_path), 'fixture'])
    section = TXT.read_text().split('stage saved_pdf_validation_and_recovery', 1)[1]
    python = section.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
    exec(compile(python, 'recovery', 'exec'), {})
    assert receipt.read_bytes() == prior
    excluded = json.loads((receipt.parent.parent/'spreadsheet-excluded-jobs.json').read_text())
    assert len(excluded['jobs']) == 1
    assert excluded['jobs'][0]['new_service_requests'] == 0


def test_prior_spreadsheet_derived_pdf_is_not_ingested(tmp_path):
    source = tmp_path/'RAW/external/risk_team/forms/report.xlsx'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'original spreadsheet fixture')
    derived = source.with_suffix('.pdf')
    with fitz.open() as doc:
        doc.new_page()
        doc.save(derived)
    build.atomic(tmp_path/'CATALOG/RAW_DERIVATIVES.json', {
        'schema_version': prep.VERSION,
        'files': {str(derived.relative_to(tmp_path)): {
            'origin': str(source.relative_to(tmp_path)), 'kind': 'native_rendered_pdf'}}})
    plan, report = teams.collect(tmp_path, emit=lambda _: None)
    assert not plan['files']
    assert len([r for r in report['excluded'] if r['reason'] == prep.SPREADSHEET_EXCLUSION]) == 2
    assert source.exists() and derived.exists()


def test_missing_output_console_is_status_not_repeated_exception(tmp_path, monkeypatch):
    messages = []
    ticks = [0]
    def stop(_):
        ticks[0] += 1
        if ticks[0] == 2:
            raise KeyboardInterrupt()
    monkeypatch.setattr(time, 'sleep', stop)
    with pytest.raises(KeyboardInterrupt):
        prep._wait_for_pdf(tmp_path/'absent.pdf', tmp_path, {'status': 'PENDING'}, emit=messages.append)
    assert messages and all('WAITING_FOR_PDF' in m for m in messages)
    assert all('FileNotFoundError' not in m and 'Errno' not in m for m in messages)
    assert 'FileNotFoundError' in json.loads((tmp_path/'conversion.json').read_text())['pdf_wait']['last_error']


def test_r11_upgrades_r10_repeats_and_rolls_back(tmp_path):
    edits = edits_of(SCRIPT)
    for rel in dict.fromkeys(e['path'] for e in edits):
        text = (ROOT/rel).read_text()
        for e in reversed([e for e in edits if e['path'] == rel]):
            assert e['new'] in text, rel
            text = text.replace(e['new'], e['old'])
        ast.parse(text)
        dest = tmp_path/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    env = dict(os.environ, GENOS_DATA_ROOT=str(tmp_path/'data'), GENOS_RUN_ID='fixture')
    def run(script, settings=env):
        r = subprocess.run([sys.executable, str(script)], cwd=tmp_path, env=settings,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout+r.stderr
    run(ROOT/'06_TOOLS/OFFLINE/genos_pdf_no_cutoff_patch.py')
    originals = {r: (tmp_path/r).read_bytes() for r in dict.fromkeys(e['path'] for e in edits)}
    run(SCRIPT)
    run(SCRIPT)
    for rel in originals:
        assert (tmp_path/rel).read_bytes() == (ROOT/rel).read_bytes()
    receipt = next((tmp_path/'TRANSFER/BACKUPS/actual-error-progress-r11').glob('*/receipt.json'))
    run(SCRIPT, dict(env, GENOS_ERROR_PATCH_MODE='rollback', GENOS_ERROR_PATCH_RECEIPT=str(receipt)))
    for rel in originals:
        assert (tmp_path/rel).read_bytes() == originals[rel]


def test_handoff_full_script_and_embedded_installer():
    text = TXT.read_text()
    embedded = text.split('"""Apply only verified', 1)[1].split('\nGENOS_ERROR_PATCH_PY\n', 1)[0]
    assert ('"""Apply only verified'+embedded).strip() == SCRIPT.read_text().strip()
    syntax = subprocess.run(['bash', '-n', str(TXT)], capture_output=True, text=True)
    assert syntax.returncode == 0 and not syntax.stderr
    r10 = TXT.with_name('GENOS_FULL_PIPELINE_BACKUP_E2E_R10.txt').read_text()
    assert text.split('stage reference_model_binding', 1)[1].strip() == r10.split('stage reference_model_binding', 1)[1].strip()
