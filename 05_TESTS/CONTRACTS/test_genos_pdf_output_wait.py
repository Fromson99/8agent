import json
import time

import fitz
import pytest
from lawrag.pipeline import raw_preprocess as prep


@pytest.mark.parametrize('old_setting', ['0', '300', '-1', 'not-a-number'])
def test_wait_ignores_retired_cutoff_and_finishes_after_long_delay(tmp_path, monkeypatch, old_setting):
    monkeypatch.setenv('GENOS_PDF_OUTPUT_WAIT_SECONDS', old_setting)
    output = tmp_path/'source.pdf'
    evidence = {'status': 'PENDING', 'http_status': 200, 'api_code': 0}
    elapsed = [0]
    ticks = []
    notices = []
    monkeypatch.setattr(time, 'monotonic', lambda: elapsed[0])
    def tick(seconds):
        ticks.append(seconds)
        elapsed[0] += 601
        if len(ticks) == 3:
            with fitz.open() as doc:
                doc.new_page()
                doc.save(output)
    monkeypatch.setattr(time, 'sleep', tick)
    assert prep._wait_for_pdf(output, tmp_path, evidence, emit=notices.append) == 1
    assert elapsed[0] > 1800
    assert evidence['pdf_wait']['limit_seconds'] is None
    assert evidence['pdf_wait']['status'] == 'READY'
    assert len(notices) >= 3


def test_user_interrupt_preserves_pending_receipt_and_actual_missing_error(tmp_path, monkeypatch):
    def interrupt(_):
        raise KeyboardInterrupt()
    monkeypatch.setattr(time, 'sleep', interrupt)
    with pytest.raises(KeyboardInterrupt):
        prep._wait_for_pdf(tmp_path/'missing.pdf', tmp_path, {'status': 'PENDING'})
    record = json.loads((tmp_path/'conversion.json').read_text())
    assert record['status'] == 'PENDING'
    assert record['pdf_wait']['limit_seconds'] is None
    assert 'FileNotFoundError' in record['pdf_wait']['last_error']


@pytest.mark.parametrize('exc', [ImportError('PyMuPDF missing'), PermissionError('access denied')])
def test_real_dependency_and_permission_errors_are_immediate(tmp_path, monkeypatch, exc):
    def fail(_):
        raise exc
    monkeypatch.setattr(prep, 'pdf_check', fail)
    monkeypatch.setattr(time, 'sleep', lambda _: pytest.fail('must fail without waiting'))
    with pytest.raises(type(exc), match=str(exc)):
        prep._wait_for_pdf(tmp_path/'source.pdf', tmp_path, {})


def test_stable_invalid_pdf_is_not_hidden_forever(tmp_path, monkeypatch):
    output = tmp_path/'source.pdf'
    output.write_bytes(b'not a PDF')
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    with pytest.raises(ValueError):
        prep._wait_for_pdf(output, tmp_path, {})
