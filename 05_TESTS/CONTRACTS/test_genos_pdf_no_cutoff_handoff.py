import pytest
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'06_TOOLS/OFFLINE/genos_pdf_no_cutoff_patch.py'
TXT = ROOT/'08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_FULL_PIPELINE_BACKUP_E2E_R10.txt'


def edits_of(script):
    tree = ast.parse(script.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'EDITS' for t in n.targets))
    return json.loads(ast.literal_eval(node.value.args[0]))


def r10_source(rel):
    text = (ROOT/rel).read_text()
    r11 = edits_of(ROOT/'06_TOOLS/OFFLINE/genos_spreadsheet_exclusion_patch.py')
    for edit in reversed(r11[32:]):
        if edit['path'] == rel:
            text = text.replace(edit['new'], edit['old'])
    helper = next(e for e in r11 if e.get('variants'))
    if rel == helper['path']:
        text = text.replace(helper['new'], helper['variants'][-1])
    return text


def test_r10_upgrades_r9_repeats_and_rolls_back(tmp_path):
    edits = edits_of(SCRIPT)
    for rel in dict.fromkeys(e['path'] for e in edits):
        text = r10_source(rel)
        for e in reversed([e for e in edits if e['path'] == rel]):
            assert e['new'] in text, rel
            text = text.replace(e['new'], e['old'])
        ast.parse(text)
        dest = tmp_path/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    env = dict(os.environ, GENOS_DATA_ROOT=str(tmp_path/'data'), GENOS_RUN_ID='fixture')
    def run(script, environ=env):
        r = subprocess.run([sys.executable, str(script)], cwd=tmp_path, env=environ, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout+r.stderr
        return r
    run(ROOT/'06_TOOLS/OFFLINE/genos_pdf_wait_patch.py')
    before = {rel: (tmp_path/rel).read_bytes() for rel in dict.fromkeys(e['path'] for e in edits)}
    run(SCRIPT)
    run(SCRIPT)
    for rel in before:
        assert (tmp_path/rel).read_text() == r10_source(rel)
    receipt = next((tmp_path/'TRANSFER/BACKUPS/actual-error-progress-r10').glob('*/receipt.json'))
    run(SCRIPT, dict(env, GENOS_ERROR_PATCH_MODE='rollback', GENOS_ERROR_PATCH_RECEIPT=str(receipt)))
    for rel in before:
        assert (tmp_path/rel).read_bytes() == before[rel]


def test_embedded_installer_is_identical():
    embedded = TXT.read_text().split('"""Apply only verified error-display edits', 1)[1].split('\nGENOS_ERROR_PATCH_PY\n', 1)[0]
    assert ('"""Apply only verified error-display edits'+embedded).strip() == SCRIPT.read_text().strip()
    check = subprocess.run(['bash', '-n', str(TXT)], capture_output=True, text=True)
    assert check.returncode == 0 and not check.stderr, check.stderr
    previous = TXT.with_name('GENOS_FULL_PIPELINE_BACKUP_E2E_R9.txt')
    assert TXT.read_text().split('stage reference_model_binding', 1)[1].strip() == previous.read_text().split('stage reference_model_binding', 1)[1].strip()


def test_saved_job_waits_without_reposting_and_preserves_history(tmp_path, monkeypatch):
    from lawrag.pipeline import raw_preprocess as prep
    from test_genos_full_pipeline_r6_recovery import setup
    stage, source, pdf, receipt = setup(tmp_path)
    prior = receipt.read_bytes()
    pdf.unlink()
    monkeypatch.setenv('GENOS_PDF_CONVERTER_SHARED_ROOT', str(tmp_path/'shared'))
    monkeypatch.setenv('GENOS_PDF_CONVERTER_ID', '187')
    monkeypatch.delenv('GENOS_PDF_CONVERTER_URL', raising=False)
    monkeypatch.delenv('GENOS_PDF_CONVERTER_REVISION', raising=False)
    monkeypatch.setattr(prep, 'convert', lambda *args: pytest.fail('must not repost'))
    import time, fitz
    def tick(_):
        if not pdf.exists():
            with fitz.open() as doc:
                doc.new_page()
                doc.save(pdf)
    monkeypatch.setattr(time, 'sleep', tick)
    monkeypatch.setattr(sys, 'argv', ['recovery', str(tmp_path), 'fixture'])
    section = TXT.read_text().split('stage saved_pdf_validation_and_recovery', 1)[1]
    python = section.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
    exec(compile(python, 'recovery', 'exec'), {})
    record = json.loads(receipt.read_text())
    assert record['pages'] == 1
    assert record['pdf_wait']['limit_seconds'] is None
    assert record['saved_pdf_recovery']['new_service_requests'] == 0
    assert Path(record['saved_pdf_recovery']['prior_receipt']).read_bytes() == prior
