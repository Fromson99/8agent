"""Synthetic receipt checks; never connect to a field database."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
CODE = HERE / 'check_load_status.py'
spec = importlib.util.spec_from_file_location('r4_load_status', CODE)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def run():
    checks = []
    tree = ast.parse(CODE.read_text(encoding='utf-8'))
    imports = {n.names[0].name if isinstance(n, ast.Import) else n.module
               for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))}
    assert imports <= {'json', 'os', 'pathlib', 're', 'tempfile'}
    checks.append('syntax_and_stdlib_imports_only')
    with tempfile.TemporaryDirectory() as td:
        job = Path(td) / 'oracle-import-r2'
        source_dir = job / 'source' / 'synthetic'
        source_dir.mkdir(parents=True)
        receipt = source_dir / 'state.json'
        def write(name, value):
            name.write_text(json.dumps(value), encoding='utf-8')
        counts = {'document': 2, 'source_unit': 3, 'block_payload': 4}
        source = {'status': 'SOURCE_STAGED', 'binding': {'dataset_version': 'v1'},
                  'tables': {k: {'rows': v} for k, v in counts.items()}}
        full = {'status': 'FAILED', 'stages': {'source_load': {
            'status': 'SOURCE_STAGED', 'receipt': str(receipt),
            'counts': counts, 'dataset_version': 'v1'}},
            'deferred': {'loaded_query_batches': 37, 'loaded_parts': {'a': 2}}}
        write(receipt, source)
        write(job / 'full-state.json', full)
        before = {p: p.read_bytes() for p in job.rglob('*.json')}
        lines = diag.report(job)
        text = '\n'.join(lines)
        assert '전체 저장 상태: FAILED' in text
        assert 'LGL_DOC_VER_S: 성공응답 누적 2 / 원본 예정 2' in text
        assert 'LGL_SRCH_ROW_S: 마지막 ACK 커서 37 / 전체 적재 완료 기록 NO_RECORD' in text
        assert 'LGL_SRC_PBLS_S: 검증 후 게시 단계 NO_RECORD' in text
        assert 'LGL_SRCH_PBLS_S: 검증 후 게시 단계 NO_RECORD' in text
        assert len(lines) <= 18
        assert before == {p: p.read_bytes() for p in job.rglob('*.json')}
        checks.append('failed_search_keeps_source_ack_and_no_publication_claim_no_mutation')
        full['stages']['verify'] = {'status': 'VERIFIED'}
        full['stages']['assets'] = {'status': 'COMPLETE'}
        full['stages']['query'] = {'status': 'COMPLETE'}
        full['deferred']['load_finished'] = True
        full['status'] = 'COMPLETE'
        write(job / 'full-state.json', full)
        text = '\n'.join(diag.report(job))
        assert '별도 전수검증 단계: VERIFIED' in text
        assert '전체 적재 완료 기록 YES' in text
        assert '현재' not in text or '미검증' in text
        checks.append('completed_receipt_still_not_current_insert_or_gold_verification')
        source['binding']['dataset_version'] = 'other'
        write(receipt, source)
        text = '\n'.join(diag.report(job))
        assert 'VERSION_MISMATCH' in text
        assert 'LGL_DOC_VER_S: 성공응답 누적 ? / 원본 예정 2' in text
        checks.append('other_dataset_receipt_does_not_supply_success_counts')
        full['stages']['source_load']['receipt'] = str(Path(td) / 'foreign.json')
        write(job / 'full-state.json', full)
        lines = diag.report(job)
        assert 'RECEIPT_OUTSIDE_JOB' in '\n'.join(lines) and len(lines) <= 18
        checks.append('external_receipt_rejected_and_output_bounded')
        (job / 'full-state.json').write_text('{', encoding='utf-8')
        text = '\n'.join(diag.report(job))
        assert '읽기 실패' in text and '적재 0행이 아닙니다' in text
        (job / 'full-state.json').unlink()
        assert 'FileNotFoundError' in '\n'.join(diag.report(job))
        checks.append('missing_or_malformed_receipt_not_zero_rows')
        receipt.write_bytes(b'x' * 33)
        value, error = diag.read_json(receipt, 32)
        assert value == {} and error == 'SIZE_LIMIT'
        checks.append('bounded_json_read')
    return checks


if __name__ == '__main__':
    print(json.dumps({'status': 'PASS', 'checks': run(), 'live_database_execution': False}, indent=2))
