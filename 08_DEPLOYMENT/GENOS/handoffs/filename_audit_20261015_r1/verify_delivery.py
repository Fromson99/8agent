"""Execute the sealed ZIP/TXT against a synthetic source-generation contract."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_FILENAME_AUDIT_20261015_R1'
spec = importlib.util.spec_from_file_location('delivery_tests', HERE / 'test_filename_audit.py')
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
audit = t.audit


def main():
    logs, checks = [], []
    with tempfile.TemporaryDirectory(prefix='filename-audit-delivery-') as d:
        root = Path(d); transfer = root / 'actual-upload-folder'; transfer.mkdir()
        bundle = transfer / NAME
        with zipfile.ZipFile(HERE / (NAME + '.zip')) as z:
            assert not any(Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
            z.extractall(bundle)
        for line in (bundle / 'SHA256SUMS.txt').read_text().splitlines():
            expected, relative = line.split('  ', 1)
            assert audit.sha(bundle / relative) == expected
        manifest = json.loads((bundle / 'CODE_MANIFEST.json').read_text())
        for item in manifest['required_files']:
            assert audit.sha(bundle / item['path']) == item['sha256'] == audit.sha(ROOT / item['source'])
        checks.append('sealed ZIP member hashes equal source files; no JavaScript attachments')
        gen = t.fixture(root)
        code = root / 'DEV'; (code / '00_SYSTEM').mkdir(parents=True)
        audit.write_json(code / '00_SYSTEM/GENOS_SERVING_PATHS.json', {'schema_version': 'genos-serving-paths-v1',
            'selection': 'operator-fixed', 'generation': str(gen), 'runtime': str(root / 'runtime'),
            'generation_manifest_sha256': audit.sha(gen / 'manifest.json')})
        snapshot = {str(p): audit.sha(p) for base in (gen, code) for p in base.rglob('*') if p.is_file()}
        env = {**os.environ, 'PATH': str(ROOT / '.venv/bin') + ':' + os.environ['PATH'],
               'GENOS_DATA_ROOT': '/missing/stale-data', 'GENOS_GENERATION': '/missing/stale-generation'}
        def run(label, txt, args, expected):
            command = ['bash', str(txt), *args]
            r = subprocess.run(command, cwd=transfer, env=env, text=True, capture_output=True)
            logs.append({'label': label, 'command': command, 'exit': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
            assert r.returncode == expected, (label, r.returncode, r.stdout, r.stderr)
            checks.append(label)
            return r
        txt = bundle / (NAME + '_RUN.txt')
        run('ZIP TXT 37 contract tests', txt, ['check'], 0)
        out1 = transfer / 'report1'
        run('ZIP TXT structured generation comparison with fixed NFS-style binding over stale environment', txt,
            ['compare', '--root', str(code), '--output', str(out1)], 0)
        s1 = json.loads((out1 / 'SUMMARY.json').read_text())
        assert s1['counts_by_location'] == {'OLDER': 1, 'LATEST': 1} and s1['rag_applied'] is False
        run('standalone TXT comparison matches ZIP TXT', HERE / (NAME + '_RUN.txt'),
            ['compare', '--root', str(code), '--output', str(transfer / 'report2')], 0)
        assert (out1 / 'ALL_INTERNAL.csv').read_bytes() == (transfer / 'report2/ALL_INTERNAL.csv').read_bytes()
        run('existing output refused and preserved', txt, ['compare', '--root', str(code), '--output', str(out1)], 1)
        assert json.loads((out1 / 'SUMMARY.json').read_text()) == s1
        run('missing DEV fails with durable console log', txt, ['compare', '--root', str(root / 'missing')], 1)
        assert snapshot == {str(p): audit.sha(p) for base in (gen, code) for p in base.rglob('*') if p.is_file()}
        checks.append('all generation and DEV bytes unchanged by diagnostics')
        raw = root / 'raw'; raw.mkdir()
        (raw / '모의규정_20200101.docx').write_bytes(b'not parsed')
        (raw / '모의규정_20260101.gul.docx').write_bytes(b'not parsed')
        run('explicit RAW name-only inventory', txt, ['compare', '--raw-root', str(raw), '--output', str(transfer / 'raw-report')], 0)
        # Source changed/corrupt metadata produces FAILED, never a success report.
        db = sqlite3.connect(gen / 'store.sqlite'); db.execute("UPDATE document SET json='broken'"); db.commit(); db.close()
        failed = transfer / 'failed-report'
        run('corrupt metadata fails and saves RUN_STATUS', txt, ['compare', '--root', str(code), '--output', str(failed)], 1)
        assert json.loads((failed / 'RUN_STATUS.json').read_text())['status'] == 'FAILED'
        assert not (failed / 'COMPARE.html').exists()
        original = (gen / 'manifest.json').read_bytes()
        (gen / 'manifest.json').write_text('{}')
        run('manifest pin mismatch fails before reading inventory', txt, ['compare', '--root', str(code)], 1)
        (gen / 'manifest.json').write_bytes(original)
        run('unknown apply action is rejected', txt, ['apply'], 2)
        persistent_logs = list((transfer / 'FILENAME_AUDIT_RUNS').glob('*/exit_status.txt'))
        assert len(persistent_logs) == 9
        checks.append('every actual TXT command saved durable log and exit status')
    data = {'status': 'PASS', 'contract_tests': 37, 'actual_txt_commands': 9, 'checks': checks,
        'scanner_sha256': audit.sha(ROOT / '06_TOOLS/OFFLINE/genos_filename_audit.py'),
        'code_manifest_sha256': audit.sha(HERE / 'CODE_MANIFEST.json'),
        'environment': 'WSL local synthetic generation; python3 resolves repository .venv Python',
        'field_genos_execution': 'NOT_RUN', 'rag_activation': False,
        'known_limits': ['filename dates are not effective dates', 'renamed titles remain separate',
                         'unknown date/title families preserved for review', 'whole source DB hash not recomputed; metadata and manifest binding recorded']}
    (HERE / 'VALIDATION.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    with gzip.open(HERE / 'TEST_TRANSCRIPT.json.gz', 'wt', encoding='utf-8') as f: json.dump(logs, f, ensure_ascii=False)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
