import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('quick_diagnosis', HERE / 'quick_diagnosis.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def fixture(job, restarted=False):
    state = {'status': 'LOADING_UNVERIFIED', 'deferred': {'loaded_query_batches': 150,
             'plan': {'source_release_id': 'source', 'files': {'one': 'hash'}}}}
    desc = {'binding': {'source': 'source', 'files': {'one': 'hash'}},
            'tables': {'posting': {'asset': 'fulltext/units.sqlite', 'rows': 10000}}}
    desc['checksum'] = hashlib.sha256(json.dumps(desc, ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
    (job / 'full-state.json').write_text(json.dumps(state))
    (job / 'projection-descriptor-r7.json').write_text(json.dumps(desc))
    progress = []
    if restarted:
        progress.append({'at': 800, 'elapsed_seconds': 5000, 'write_rows_this_run': 8000,
                         'write_requests_this_run': 16})
    for i in range(5):
        progress.append({'at': 880 + i * 30, 'elapsed_seconds': 300 + i * 30,
                         'write_rows_this_run': 1000 + i * 500, 'write_requests_this_run': 2 + i,
                         'query_batches_loaded': 50 + i * 25,
                         'asset': 'fulltext/units.sqlite', 'phase': 'FTS_POSTINGS_SORT'})
    (job / 'progress.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in progress))
    logs = [{'call': i, 'at': 900 + i * 20 + offset, 'status': status}
            for i in range(1, 4) for offset, status in ((0, 'STARTED'), (12, 'ACKNOWLEDGED'))]
    (job / 'deferred_load.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in logs))
    return state, desc


def test_compact_report_real_count_and_no_file_changes(tmp_path):
    fixture(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    lines = d.build_report(tmp_path, now=1000)
    assert len(lines) == 24
    assert len(d.build_report(tmp_path, now=1000, detail=False)) == 15
    text = '\n'.join(lines)
    assert '10,000행(저장 명세)' in text
    assert '16.7행/초' in text
    assert '중앙 12.0초' in text
    assert '7,000~7,000행' in text
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_resume_counts_are_bounds_not_twenty_times_frames(tmp_path):
    fixture(tmp_path)
    p = tmp_path / 'full-state.json'
    state = json.loads(p.read_text()); state['deferred']['loaded_query_batches'] = 1000
    p.write_text(json.dumps(state))
    text = '\n'.join(d.build_report(tmp_path, now=1000))
    assert '0~9,000행' in text
    assert '20,000행' not in text


def test_rate_does_not_mix_restarted_runs(tmp_path):
    fixture(tmp_path, restarted=True)
    assert '16.7행/초' in '\n'.join(d.build_report(tmp_path, now=1000))


@pytest.mark.parametrize('change', ['checksum', 'source', 'files', 'rows'])
def test_corrupt_or_unbound_descriptor_never_gives_total(tmp_path, change):
    fixture(tmp_path)
    p = tmp_path / 'projection-descriptor-r7.json'
    desc = json.loads(p.read_text())
    if change == 'checksum': desc['checksum'] = 'wrong'
    else:
        if change == 'source': desc['binding']['source'] = 'different'
        if change == 'files': desc['binding']['files'] = {}
        if change == 'rows': desc['tables']['posting']['rows'] = '10000'
        body = {k: v for k, v in desc.items() if k != 'checksum'}
        desc['checksum'] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                         separators=(',', ':')).encode()).hexdigest()
    p.write_text(json.dumps(desc))
    text = '\n'.join(d.build_report(tmp_path, now=1000))
    assert '05 전체 검색행: 미확인' in text
    assert '09 추가 적재 예상: 속도 0 또는 표본·전체량 부족으로 보류' in text


def test_stale_and_zero_rate_do_not_promise_completion(tmp_path):
    fixture(tmp_path)
    assert '09 추가 적재 예상: 진행 기록이 오래되었거나 없어 보류' in '\n'.join(d.build_report(tmp_path, now=2000))
    p = tmp_path / 'progress.jsonl'
    rows = [json.loads(v) for v in p.read_text().splitlines()]
    for r in rows: r['write_rows_this_run'] = 1000
    p.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    assert '09 추가 적재 예상: 속도 0 또는 표본·전체량 부족으로 보류' in '\n'.join(d.build_report(tmp_path, now=1000))


def test_partial_log_tail_is_bounded_and_not_printed(tmp_path):
    p = tmp_path / 'x.jsonl'
    p.write_bytes(b'x' * 5000 + b'\n{"call":1,"status":"STARTED","at":990}\n{"SECRET":"unfinished')
    rows, info = d.tail_jsonl(p, 256)
    assert len(rows) == 1 and info['truncated'] and info['skipped'] == 1
    assert d.sql_samples(rows, 1000)['pending_age'] == 10


def test_missing_path_is_not_zero_or_stopped(tmp_path):
    text = '\n'.join(d.build_report(tmp_path, now=1000))
    assert '0행으로 판단하지 않습니다' in text and 'ETA' not in text


def test_last_failed_request_not_reported_running():
    logs = [{'call': 1, 'status': 'STARTED', 'at': 10},
            {'call': 1, 'status': 'WRITE_UNCONFIRMED', 'at': 20}]
    result = d.sql_samples(logs, 30)
    assert result['pending_age'] is None and result['recent'] == []


def test_failed_state_suppresses_eta_even_when_heartbeat_is_fresh(tmp_path):
    fixture(tmp_path)
    path = tmp_path / 'full-state.json'
    state = json.loads(path.read_text()); state['status'] = 'FAILED'
    path.write_text(json.dumps(state))
    assert '09 추가 적재 예상: 저장 상태가 중단·실패이므로 보류' in '\n'.join(d.build_report(tmp_path, now=1000))


@pytest.mark.parametrize('detail', [True, False])
def test_complete_notebook_txt_with_managed_zip(tmp_path, monkeypatch, capsys, detail):
    import io
    import sys
    import types
    job = (tmp_path / 'legal-existing-nfs-20261029-r1'
           / 'financial-risk-success-20261005-schema-r2' / 'oracle-import-r2')
    job.mkdir(parents=True)
    fixture(job)
    archive = (HERE / 'DATAIKU_NFS_QUICK_DIAG_20261031_R1.zip').read_bytes()
    reads = []
    class Folder:
        def __init__(self, identity): assert identity == 'ehA8dpVm'
        def get_download_stream(self, path):
            assert path == '/DATAIKU_NFS_QUICK_DIAG_20261031_R1.zip'
            reads.append(path)
            return io.BytesIO(archive)
    sdk = types.SimpleNamespace(Folder=Folder, get_custom_variables=lambda: {'LEGAL_PIPELINE_SCRATCH': str(tmp_path)})
    monkeypatch.setitem(sys.modules, 'dataiku', sdk)
    before = {p: p.read_bytes() for p in job.iterdir()}
    text = (HERE / 'DATAIKU_NFS_QUICK_DIAG_RUN_R1.txt').read_text().replace('SHOW_DETAIL = True', 'SHOW_DETAIL = ' + str(detail))
    exec(compile(text, 'handoff.txt', 'exec'), {})
    output = capsys.readouterr().out
    assert len(output.splitlines()) == (24 if detail else 15)
    assert '10,000행(저장 명세)' in output and 'Traceback' not in output
    assert len(reads) == 1
    assert before == {p: p.read_bytes() for p in job.iterdir()}
