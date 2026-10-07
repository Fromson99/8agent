import json
import time

import pytest
from lawrag.pipeline import raw_preprocess as prep


def test_waiting_heartbeat_and_completed_reuse_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(prep, 'PDF_PROGRESS_INTERVAL', .01)
    output = []
    counts = dict(completed=0, reused=0, skipped=0, failed=0)
    item = {}
    with prep._pdf_item_progress(tmp_path, 1, 3, tmp_path/'native.hwp', item, counts, output.append):
        time.sleep(.035)
        item['status'] = 'EXISTING'
    assert len([x for x in output if 'RUNNING' in x]) >= 2
    assert 'PDF [1/3] 완료 1/3' in output[-1]
    row = json.loads((tmp_path/'pdf-progress.json').read_text())
    assert row['completed'] == 1 and row['reused'] == 1 and row['status'] == 'EXISTING'


def test_failure_retains_original_reason_and_does_not_count_as_complete(tmp_path):
    output = []
    counts = dict(completed=0, reused=0, skipped=0, failed=0)
    with pytest.raises(FileNotFoundError):
        with prep._pdf_item_progress(tmp_path, 2, 4, tmp_path/'bad.hwp', {}, counts, output.append):
            raise FileNotFoundError('missing generated source.pdf')
    assert counts['completed'] == 0 and counts['failed'] == 1
    assert 'FileNotFoundError: missing generated source.pdf' in output[-1]
    assert json.loads((tmp_path/'pdf-progress.json').read_text())['status'] == 'FAILED'
