import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TXT = ROOT/'08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_PDF_CONVERSION_DIAG_R1.txt'


def test_pending_receipt_is_reported_without_mutation_or_credentials(tmp_path):
    stage = tmp_path/'shared/pdf-job'
    stage.mkdir(parents=True)
    source = stage/'source.doc'
    source.write_bytes(b'fixture-not-a-real-document')
    job = tmp_path/'LOGS/fixture/preparation/job/conversion.json'
    job.parent.mkdir(parents=True)
    job.write_text(json.dumps({'status': 'PENDING', 'http_status': 500, 'api_code': 1,
        'staging': str(stage), 'request': {'file_path': str(source)},
        'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}))
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    env = dict(os.environ, DEPLOY_ROOT=str(ROOT), GENOS_DATA_ROOT=str(tmp_path),
               GENOS_RUN_ID='fixture', GENOS_PREPROCESSOR_API_KEY='secret-fixture')
    result = subprocess.run(['bash', str(TXT)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"http_status": 500' in result.stdout
    assert 'EXPECTED_PDF_MISSING' in result.stdout
    assert 'original_hash_matches=True' in result.stdout
    assert 'secret-fixture' not in result.stdout
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_missing_preparation_reports_explicit_error(tmp_path):
    env = dict(os.environ, DEPLOY_ROOT=str(ROOT), GENOS_DATA_ROOT=str(tmp_path), GENOS_RUN_ID='fixture')
    result = subprocess.run(['bash', str(TXT)], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Preparation directory missing' in result.stdout
