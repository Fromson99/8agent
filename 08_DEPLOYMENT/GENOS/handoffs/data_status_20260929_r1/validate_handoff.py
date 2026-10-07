"""Synthetic read-only checks for the exact Bash TXT being emailed."""
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
SCRIPT = BASE / 'GENOS_DATA_STATUS_20260929_R1.txt'
spec = importlib.util.spec_from_file_location('status_ledger_fixture', ROOT / '02_BACKEND/lawrag/pipeline/genos_status.py')
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


def checksums(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def run(data, output, *args):
    env = dict(os.environ, GENOS_STATUS_OUTPUT_BASE=str(output),
               GENOS_STATUS_PYTHON=str(ROOT / '.venv/bin/python'), GENOS_TEST_KEY='SYNTHETIC_SECRET_987')
    return subprocess.run(['bash', str(SCRIPT), '--repo', str(ROOT), '--data-root', str(data), *args],
                          cwd=ROOT, env=env, text=True, capture_output=True)


def report_dir(output):
    return next(p.parent for p in output.glob('*/요약.txt'))


def main():
    passed = []
    subprocess.run(['bash', '-n', str(SCRIPT)], check=True)
    passed.append('Bash syntax')
    with tempfile.TemporaryDirectory(prefix='genos-data-status-') as folder:
        temp = Path(folder)
        data = temp / 'data'
        logs = data / 'LOGS/demo'
        store = data / 'STRUCTURE/synthetic'
        store.mkdir(parents=True)
        (store / 'source.sqlite').write_bytes(b'synthetic fixture; no corpus')
        (store / 'structure-receipt.json').write_text('{}')
        rows = [{'document_id': key, 'relative': name, 'name': name, 'source': 'SYNTHETIC'} for key, name in
                [('ok', '=parsed.xml'), ('fail', 'failed.pdf'), ('wait', 'pending.docx'),
                 ('running', 'running.pdf'), ('missing', 'missing-output.xml')]]
        ledger = status.Ledger(logs).start(rows, 'all',
            excluded=[{'item': 'unsupported.gul', 'error': 'unsupported format'}],
            ignored=[{'path': 'reference.pdf', 'reason': 'reference representation'}])
        ledger.update('ok', 'structure', 'PASSED', output_path=str(store), mode='NEW')
        ledger.update('ok', 'index', 'FAILED', error='index failed SYNTHETIC_SECRET_987')
        ledger.update('fail', 'structure', 'FAILED', error='parser failed')
        ledger.update('fail', 'index', 'BLOCKED', error='structure failed')
        ledger.update('running', 'structure', 'RUNNING')
        ledger.update('missing', 'structure', 'PASSED', output_path=str(data / 'missing-store'))
        ledger.close()
        before = checksums(data)
        output = temp / 'reports'
        result = run(data, output, '--run-id', 'demo', '--limit', '0')
        assert result.returncode == 0, result.stdout + result.stderr
        report = report_dir(output) / 'demo'
        parsed = (report / '파싱완료.txt').read_text()
        failed = (report / '실패_보류_중단.txt').read_text()
        unknown = (report / '대기_미확인.txt').read_text()
        excluded = (report / '의도적제외.txt').read_text()
        assert '=parsed.xml' in parsed and 'failed.pdf' not in parsed
        assert 'parser failed' in failed and 'index failed' in failed and 'unsupported.gul' in failed
        assert '=parsed.xml' in failed  # parsing passed, later index failed
        passed.append('Parsing success distinct from later index failure; input failure and blocked documents')
        assert 'pending.docx' in unknown and 'running.pdf' in unknown and 'missing-output.xml' in unknown
        assert 'RUNNING은 프로세스' in result.stdout
        assert '원문 DB 없음' in unknown and '영수증/원문 DB 존재' in parsed
        passed.append('Pending/running and missing outputs remain unconfirmed; presence check only')
        assert 'reference.pdf' in excluded and 'reference.pdf' not in failed
        table = list(csv.reader((report / '전체.csv').open(encoding='utf-8-sig')))
        assert all(len(row) == 19 for row in table)
        assert "'=parsed.xml" in table[1]
        assert 'SYNTHETIC_SECRET_987' not in failed and '[REDACTED]' in failed
        passed.append('Intentional exclusion, Excel escaping and credential redaction')
        assert before == checksums(data)
        passed.append('All source SQLite, fixtures and directory contents unchanged')
        ledger = status.Ledger(logs).start(rows, 'raw')
        ledger.finish()
        ledger.close()
        current = run(data, temp / 'current', '--list')
        assert current.returncode == 0
        overview = report_dir(temp / 'current')
        summary = list(csv.DictReader((overview / '실행요약.csv').open(encoding='utf-8-sig')))[0]
        assert summary['구조화완료'] == '0' and summary['구조화대상아님'] == '5'
        passed.append('Current attempt cannot inherit earlier parsing success')
        (data / 'LOGS/old').mkdir()
        old = run(data, temp / 'old-report', '--run-id', 'old')
        assert old.returncode == 2 and '상태 원장이 없습니다' in old.stdout
        old_csv = list(csv.reader((report_dir(temp / 'old-report') / '실행요약.csv').open(encoding='utf-8-sig')))
        assert all(len(row) == 18 for row in old_csv)
        corrupt = data / 'LOGS/corrupt'
        corrupt.mkdir()
        (corrupt / status.DATABASE).write_bytes(b'bad database')
        bad = run(data, temp / 'bad-report')
        assert bad.returncode == 2 and '조회 실패·미확인' in bad.stdout and 'demo' in bad.stdout
        passed.append('Missing and corrupt ledgers give explicit unknown/failed query, preserving other runs')
        missing = run(temp / 'absent', temp / 'missing-report')
        assert missing.returncode == 2 and 'LOGS 폴더가 없습니다' in missing.stdout
        invalid = run(data, temp / 'invalid-report', '--run-id', '../escape')
        assert invalid.returncode == 2 and 'run-id' in invalid.stdout
        passed.append('Missing LOGS and invalid run IDs produce a persistent failed execution log')
    result = {'status': 'PASSED', 'checks': passed, 'script_sha256': hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
              'script_bytes': SCRIPT.stat().st_size, 'source_ingestion': False, 'model_calls': 0,
              'genos_onsite_executed': False}
    (BASE / 'VALIDATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
