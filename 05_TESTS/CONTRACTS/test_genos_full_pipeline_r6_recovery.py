"""Recover only stable validated saved PDFs; never send a conversion request."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import fitz

ROOT = Path(__file__).resolve().parents[2]
TXT = ROOT/'08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_FULL_PIPELINE_BACKUP_E2E_R6.txt'


def setup(tmp_path, valid_pdf=True):
    stage = tmp_path/'shared/pdf-job'
    stage.mkdir(parents=True)
    source = stage/'source.doc'
    source.write_bytes(b'fixture-original')
    pdf = stage/'source.pdf'
    if valid_pdf:
        with fitz.open() as doc:
            doc.new_page()
            doc.save(pdf)
    else:
        pdf.write_bytes(b'%PDF-broken-fixture')
    receipt = tmp_path/'LOGS/fixture/preparation/job/conversion.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'status': 'FAILED', 'http_status': 200, 'api_code': 1,
        'url': 'http://preprocessor-187:8080/run', 'revision': '', 'staging': str(stage),
        'request': {'file_path': str(source)},
        'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}))
    return stage, source, pdf, receipt


def recover(tmp_path):
    section = TXT.read_text().split('stage saved_pdf_validation_and_recovery', 1)[1]
    python = section.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
    env = {k: v for k, v in os.environ.items() if not k.startswith('GENOS_')}
    env.update(GENOS_PDF_CONVERTER_SHARED_ROOT=str(tmp_path/'shared'), GENOS_PDF_CONVERTER_ID='187')
    return subprocess.run([sys.executable, '-c', python, str(tmp_path), 'fixture'], cwd=ROOT,
                          env=env, capture_output=True, text=True)


def test_valid_saved_pdf_recovers_with_warning_and_prior_history(tmp_path):
    stage, source, pdf, receipt = setup(tmp_path)
    prior = receipt.read_bytes()
    result = recover(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(receipt.read_text())
    assert record['status'] == 'PDF_WITH_API_WARNING'
    assert record['api_code'] == 1 and record['pages'] == 1
    assert record['pdf_sha256'] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert Path(record['saved_pdf_recovery']['prior_receipt']).read_bytes() == prior
    assert record['saved_pdf_recovery']['new_service_requests'] == 0
    recovered = receipt.read_bytes()
    again = recover(tmp_path)
    assert again.returncode == 0
    assert receipt.read_bytes() == recovered
    assert 'recovered=0' in again.stdout


def test_broken_pdf_preserves_failed_receipt(tmp_path):
    _, _, _, receipt = setup(tmp_path, valid_pdf=False)
    prior = receipt.read_bytes()
    result = recover(tmp_path)
    assert result.returncode != 0
    assert 'SAVED_PDF_VALIDATION_FAILED' in result.stdout
    assert receipt.read_bytes() == prior


def test_changed_input_is_rejected(tmp_path):
    _, source, _, receipt = setup(tmp_path)
    prior = receipt.read_bytes()
    source.write_bytes(b'changed-fixture')
    result = recover(tmp_path)
    assert result.returncode != 0
    assert 'SAVED_JOB_INPUT_CHANGED' in result.stderr
    assert receipt.read_bytes() == prior


def test_uncertain_http_job_is_not_adopted(tmp_path):
    _, _, _, receipt = setup(tmp_path)
    record = json.loads(receipt.read_text())
    record['transport_error_type'] = 'ReadTimeout'
    receipt.write_text(json.dumps(record))
    prior = receipt.read_bytes()
    result = recover(tmp_path)
    assert result.returncode != 0
    assert 'SAVED_JOB_UNCERTAIN' in result.stderr
    assert receipt.read_bytes() == prior
