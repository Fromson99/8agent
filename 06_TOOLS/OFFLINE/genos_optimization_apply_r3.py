"""R3 preflight reports every file hash and preserves unknown field code for diagnosis."""
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dependency():
    spec = importlib.util.spec_from_file_location('optimization_apply_r2_dependency', HERE / 'APPLY_R2.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = HERE
    return module


def preflight(dev):
    dev = dev.resolve(strict=True)
    manifest = json.loads((HERE / 'CODE_MANIFEST.json').read_text())
    rows, drift = [], []
    for item in manifest['files']:
        if digest(HERE / item['path']) != item['sha256']:
            raise ValueError('Package drift: ' + item['path'])
        if item['role'] != 'code':
            continue
        target = dev / item['path']
        actual = digest(target) if target.is_file() else None
        unsafe = target.is_symlink() or not target.resolve().is_relative_to(dev)
        accepted = not unsafe and (actual in item.get('allowed_predecessors', []) + [item['sha256']]
                                  or actual is None and item.get('allow_missing', False))
        row = {'path': item['path'], 'actual_sha256': actual, 'target_sha256': item['sha256'],
               'allowed_predecessors': item.get('allowed_predecessors', []),
               'allow_missing': item.get('allow_missing', False), 'accepted': accepted, 'unsafe_path': unsafe}
        rows.append(row)
        print('FILE HASH ' + item['path'] + ' actual=' + str(actual) + ' status=' + ('PASS' if accepted else 'FILE_DRIFT'), flush=True)
        if not accepted:
            drift.append(row)
    report = {'schema_version': 'genos-optimization-field-preflight-r3', 'dev': str(dev),
              'files': rows, 'drift': drift, 'code_applied': False,
              'checked_at': datetime.now(timezone.utc).isoformat(),
              'code_manifest_sha256': digest(HERE / 'CODE_MANIFEST.json')}
    report_path = HERE.parent / 'field-code-preflight.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('FIELD PREFLIGHT REPORT ' + str(report_path), flush=True)
    if drift:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        archive = HERE.parent / ('GENOS_OPTIMIZATION_FIELD_DRIFT_' + stamp + '.zip')
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('field-code-preflight.json', report_path.read_bytes())
            for row in drift:
                path = dev / row['path']
                if row['unsafe_path'] or not path.is_file() or path.stat().st_size > 1024 * 1024:
                    continue
                # Only explicit Python code paths from the selected package; no input/model/env files.
                if path.suffix != '.py':
                    continue
                actual = path.read_bytes()
                z.writestr('field/' + row['path'], actual)
                wanted = (HERE / row['path']).read_text()
                changes = ''.join(difflib.unified_diff(actual.decode('utf-8').splitlines(True),
                    wanted.splitlines(True), fromfile='field/' + row['path'], tofile='package/' + row['path']))
                z.writestr('diff/' + row['path'] + '.diff', changes)
        print('FIELD DRIFT DIAGNOSTIC ZIP ' + str(archive), flush=True)
        for row in drift:
            print('FILE_DRIFT ' + row['path'] + ' actual_sha256=' + str(row['actual_sha256']), flush=True)
        raise ValueError('FILE_DRIFT: ' + ', '.join(r['path'] for r in drift) + '; no files applied; diagnostic ZIP preserved')
    return report


def apply(dev, *, check=False):
    preflight(dev)
    return dependency().apply(dev, check=check)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--dev', type=Path, default=Path.home() / 'DEV')
    p.add_argument('--check', action='store_true')
    p.add_argument('--rollback', type=Path)
    a = p.parse_args()
    if a.rollback:
        dependency().rollback(a.rollback.resolve())
    else:
        apply(a.dev, check=a.check)
