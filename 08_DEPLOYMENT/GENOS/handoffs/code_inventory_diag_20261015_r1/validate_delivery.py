"""Exercise the actual Bash TXT against preserved installation fixtures."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
PRIOR = OUT.with_name('length_recovery_20261014_r1')
NAME = 'GENOS_CODE_INVENTORY_DIAG_20261015_R1'
sha = lambda b: hashlib.sha256(b).hexdigest()


def snapshot(root):
    return {str(p.relative_to(root)): [sha(p.read_bytes()), p.stat().st_mode & 0o777]
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


def main():
    fixtures = json.loads((PRIOR / 'FIXTURES.json').read_bytes())
    records = []
    for case in ['known_r3', 'known_r4', 'unknown_inventory', 'drift', 'missing_manifest',
                 'invalid_manifest', 'sensitive_path', 'known_output', 'engine_mismatch']:
        with tempfile.TemporaryDirectory(prefix='code-diag-test-') as td:
            base = Path(td)
            root, transfer = base / 'checkout', base / 'TRANSFER'
            root.mkdir(); transfer.mkdir()
            fixture = fixtures[case == 'known_r4']
            archive = PRIOR / fixture['path']
            assert sha(archive.read_bytes()) == fixture['sha256']
            with zipfile.ZipFile(archive) as z:
                z.extractall(root)
            link = base / 'DEV'
            link.symlink_to(root, target_is_directory=True)
            cm = root / 'CODE_MANIFEST.json'
            manifest = json.loads(cm.read_bytes())
            expected = 'KNOWN_PREDECESSOR'
            expected_exit = 0
            if case == 'unknown_inventory':
                name = '00_SYSTEM/DIAG_TEST_ONLY.json'
                raw = b'{}\n'
                (root / name).write_bytes(raw)
                manifest['files'].append({'path': name, 'sha256': sha(raw), 'bytes': len(raw)})
                cm.write_text(json.dumps(manifest))
                expected, expected_exit = 'UNSUPPORTED_INVENTORY', 2
            elif case == 'drift':
                path = root / 'service.py'
                path.write_bytes(path.read_bytes() + b'\n# diagnostic fixture drift\n')
                expected, expected_exit = 'CHECKOUT_DRIFT_OR_UNREADABLE', 2
            elif case == 'missing_manifest':
                cm.unlink()
                expected, expected_exit = 'DIAGNOSTIC_INCOMPLETE', 3
            elif case == 'invalid_manifest':
                cm.write_bytes(b'{invalid json')
                expected, expected_exit = 'DIAGNOSTIC_INCOMPLETE', 3
            elif case == 'sensitive_path':
                raw = b'PRIVATE_SENTINEL_DO_NOT_EXPORT'
                (root / '.env').write_bytes(raw)
                manifest['files'].append({'path': '.env', 'sha256': sha(raw), 'bytes': len(raw)})
                cm.write_text(json.dumps(manifest))
                expected, expected_exit = 'CHECKOUT_DRIFT_OR_UNREADABLE', 2
            elif case == 'known_output':
                prior = OUT.with_name('fact_reason_20261015_r1')
                module_spec = importlib.util.spec_from_file_location('sealed_fact_reason', prior / 'apply_patch.py')
                module = importlib.util.module_from_spec(module_spec)
                module_spec.loader.exec_module(module)
                spec = json.loads(gzip.decompress((prior / 'PATCH_SPEC.json.gz').read_bytes()))
                _, _, changes, _, _ = module.prepared(root, spec)
                for name, raw in changes.items():
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    (root / name).write_bytes(raw)
                expected = 'KNOWN_FACT_REASON_OUTPUT'
            elif case == 'engine_mismatch':
                p = root / '00_SYSTEM/PIPELINE.json'
                config = json.loads(p.read_bytes())
                next(iter(config['engines'].values()))['sha256'] = '0' * 64
                raw = json.dumps(config).encode()
                p.write_bytes(raw)
                for row in manifest['files']:
                    if row['path'] == '00_SYSTEM/PIPELINE.json':
                        row.update(sha256=sha(raw), bytes=len(raw))
                cm.write_text(json.dumps(manifest))
                expected, expected_exit = 'ENGINE_BINDING_FAILED', 2
            before = snapshot(root)
            env = dict(os.environ, GENOS_DEV_ROOT=str(link), PYTHONDONTWRITEBYTECODE='1')
            env['PATH'] = str(ROOT / '.venv/bin') + os.pathsep + env['PATH']
            repeats = 2 if case == 'known_r3' else 1
            for attempt in range(repeats):
                result = subprocess.run(['bash', str(OUT / (NAME + '_RUN.txt'))], cwd=transfer,
                                        env=env, capture_output=True, text=True, timeout=200)
                assert result.returncode == expected_exit, (case, result.stdout[-4000:], result.stderr)
                reports = list((transfer / 'code-inventory-diag-r1-results').glob('*/DIAGNOSIS.json'))
                assert len(reports) == attempt + 1
                report_path = max(reports, key=lambda p: p.stat().st_mtime_ns)
                report = json.loads(report_path.read_bytes())
                assert report['status'] == expected, (case, report['status'])
                assert report['code_modified'] is False
                assert snapshot(root) == before, case
                assert 'PRIVATE_SENTINEL_DO_NOT_EXPORT' not in result.stdout + report_path.read_text()
                assert (report_path.parent / 'SUMMARY.txt').is_file()
                assert (report_path.parent / 'EXIT.txt').read_text().strip() == str(expected_exit)
                records.append({'case': case, 'attempt': attempt + 1, 'status': expected,
                                'exit_code': result.returncode, 'code_bytes_and_modes_preserved': True})
    validation = {'revision': NAME, 'actual_txt_runs': len(records), 'passed': len(records),
                  'records': records, 'python': sys.executable, 'model_calls': 0,
                  'genos_connections': 0, 'field_status': 'NOT_VERIFIED'}
    (OUT / 'VALIDATION.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(validation, ensure_ascii=False))


if __name__ == '__main__':
    main()
