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
NAME = 'GENOS_FILENAME_AUDIT_20261015_R2'
spec = importlib.util.spec_from_file_location('delivery_tests', HERE / 'test_filename_audit.py')
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
audit = t.audit


def main():
    logs, checks = [], []
    with tempfile.TemporaryDirectory(prefix='filename-audit-delivery-') as d:
        root = Path(d); code = root / 'workspace'; transfer = code / 'TRANSFER'; transfer.mkdir(parents=True)
        dev_alias = root / 'DEV'; dev_alias.symlink_to(code, target_is_directory=True)
        reports = transfer / 'FILENAME_AUDIT_RESULTS'
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
        (code / '00_SYSTEM').mkdir(parents=True)
        (code / 'service.py').write_text('# existing code must stay unchanged\n')
        audit.write_json(code / '00_SYSTEM/GENOS_SERVING_PATHS.json', {'schema_version': 'genos-serving-paths-v1',
            'selection': 'operator-fixed', 'generation': str(gen), 'runtime': str(root / 'runtime'),
            'generation_manifest_sha256': audit.sha(gen / 'manifest.json')})
        snapshot = {str(p): audit.sha(p) for base in (gen, code) for p in base.rglob('*') if p.is_file() and not p.is_relative_to(transfer)}
        env = {**os.environ, 'PATH': str(ROOT / '.venv/bin') + ':' + os.environ['PATH'],
               'GENOS_DATA_ROOT': '/missing/stale-data', 'GENOS_GENERATION': '/missing/stale-generation'}
        def run(label, txt, args, expected, cwd=None):
            command = ['bash', str(txt), *args]
            r = subprocess.run(command, cwd=cwd or transfer, env=env, text=True, capture_output=True)
            logs.append({'label': label, 'command': command, 'exit': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
            assert r.returncode == expected, (label, r.returncode, r.stdout, r.stderr)
            checks.append(label)
            return r
        txt = bundle / (NAME + '_RUN.txt')
        r1 = HERE.parent / 'filename_audit_20261015_r1/GENOS_FILENAME_AUDIT_20261015_R1_RUN.txt'
        failure = run('sealed R1 reproduces photographed failure inside DEV/TRANSFER', r1, ['compare', '--root', str(dev_alias)], 1)
        assert 'output must be outside DEV checkout' in failure.stdout
        assert not reports.exists()
        run('ZIP TXT 44 contract tests', txt, ['check'], 0)
        run('R2 default output works inside DEV/TRANSFER through symlink DEV', txt, ['compare', '--root', str(dev_alias)], 0)
        default_reports = list(reports.glob('*/SUMMARY.json'))
        assert len(default_reports) == 1
        run('R2 repeated default execution preserves previous result', txt, ['compare', '--root', str(dev_alias)], 0)
        assert len(list(reports.glob('*/SUMMARY.json'))) == 2
        out1 = reports / 'report1'
        run('ZIP TXT structured generation comparison with fixed NFS-style binding over stale environment', txt,
            ['compare', '--root', str(code), '--output', str(out1)], 0)
        s1 = json.loads((out1 / 'SUMMARY.json').read_text())
        assert s1['counts_by_location'] == {'OLDER': 1, 'LATEST': 1} and s1['rag_applied'] is False
        run('standalone TXT comparison matches ZIP TXT', HERE / (NAME + '_RUN.txt'),
            ['compare', '--root', str(code), '--output', str(reports / 'report2')], 0)
        assert (out1 / 'ALL_INTERNAL.csv').read_bytes() == (reports / 'report2/ALL_INTERNAL.csv').read_bytes()
        run('existing output refused and preserved', txt, ['compare', '--root', str(code), '--output', str(out1)], 1)
        assert json.loads((out1 / 'SUMMARY.json').read_text()) == s1
        run('missing DEV fails with durable console log', txt, ['compare', '--root', str(root / 'missing')], 1)
        assert snapshot == {str(p): audit.sha(p) for base in (gen, code) for p in base.rglob('*') if p.is_file() and not p.is_relative_to(transfer)}
        checks.append('all generation and DEV bytes unchanged by diagnostics')
        run('output inside selected generation remains rejected', txt, ['compare', '--root', str(code), '--output', str(gen / 'report')], 1)
        assert not (gen / 'report').exists()
        run('arbitrary output inside code remains rejected', txt, ['compare', '--root', str(code), '--output', str(code / '02_BACKEND/report')], 1)
        assert not (code / '02_BACKEND').exists()
        external = root / 'external-TRANSFER'; external.mkdir()
        run('external TRANSFER layout still works', txt, ['compare', '--root', str(dev_alias)], 0, cwd=external)
        raw = root / 'raw'; raw.mkdir()
        (raw / '모의규정_20200101.docx').write_bytes(b'not parsed')
        (raw / '모의규정_20260101.gul.docx').write_bytes(b'not parsed')
        run('explicit RAW name-only inventory', txt, ['compare', '--raw-root', str(raw), '--output', str(transfer / 'raw-report')], 0)
        # Source changed/corrupt metadata produces FAILED, never a success report.
        db = sqlite3.connect(gen / 'store.sqlite'); db.execute("UPDATE document SET json='broken'"); db.commit(); db.close()
        failed = reports / 'failed-report'
        run('corrupt metadata fails and saves RUN_STATUS', txt, ['compare', '--root', str(code), '--output', str(failed)], 1)
        assert json.loads((failed / 'RUN_STATUS.json').read_text())['status'] == 'FAILED'
        assert not (failed / 'COMPARE.html').exists()
        original = (gen / 'manifest.json').read_bytes()
        (gen / 'manifest.json').write_text('{}')
        run('manifest pin mismatch fails before reading inventory', txt, ['compare', '--root', str(code)], 1)
        (gen / 'manifest.json').write_bytes(original)
        run('unknown apply action is rejected', txt, ['apply'], 2)
        persistent_logs = [p for base in (transfer, external) for p in (base / 'FILENAME_AUDIT_RUNS').glob('*/exit_status.txt')]
        assert len(persistent_logs) == len(logs) == 15
        checks.append('every actual TXT command saved durable log and exit status')
    original = json.loads((HERE / 'R1_PRESERVATION.json').read_text())
    assert original == {str(p.relative_to(HERE.parent / 'filename_audit_20261015_r1')): audit.sha(p) for p in (HERE.parent / 'filename_audit_20261015_r1').rglob('*') if p.is_file()}
    checks.append('all sealed R1 artifacts and failure history preserved')
    data = {'status': 'PASS', 'contract_tests': 44, 'actual_txt_commands': 15, 'checks': checks,
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
