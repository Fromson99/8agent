"""Data-only entrypoint, preserving exact latest mailed runtime compatibility."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / '09_ARTIFACTS/HANDOFF/GENOS'
PATCH = DIRECTORY / 'genos-data-e2e-20260910.zip'
PINS = {
    'genos-all-corpus-compatible-20260910.zip': 'ea77c3e685c957ed0a4bfe442eb6dbf9e44b01b5db1c5dcdabbaaca77922630d',
    'genos-qwen-response-fix-20260910.zip': '02678efb1dee5cc49170e257f1004f948fb1709ac92142f55289294e2d83480c',
}
sha = lambda b: hashlib.sha256(b).hexdigest()


def build():
    for name, expected in PINS.items():
        if sha((DIRECTORY / name).read_bytes()) != expected:
            raise ValueError('Previously mailed archive changed: ' + name)
    with zipfile.ZipFile(DIRECTORY / next(iter(PINS))) as z:
        manifest = json.loads(z.read('patch-manifest.json'))
        content = {name: z.read(name) for name in manifest['files']}
    for entry in manifest['files'].values():
        entry['previous_sha256'] = sorted(set(entry['previous_sha256'] + [entry['sha256']]))
    with zipfile.ZipFile(DIRECTORY / 'genos-qwen-response-fix-20260910.zip') as z:
        for name in z.namelist():
            if name.endswith('/'):
                continue
            content[name] = z.read(name)
            if content[name] != (ROOT / name).read_bytes():
                raise ValueError('Latest mailed runtime differs from checkout: ' + name)
    for name in ('06_TOOLS/COMMANDS/genos_data_e2e.sh',
                 '07_DOCS/REFERENCE/OPERATIONS/GENOS_DATA_E2E_CURRENT.md'):
        content[name] = (ROOT / name).read_bytes()
    # A new file in this delivery must not silently become an accepted old version.
    for name, data in sorted(content.items()):
        entry = manifest['files'].setdefault(name, {
            'allow_missing': True, 'previous_sha256': [], 'preserve_existing': False})
        entry['sha256'] = sha(data)
    manifest.update(base_archives=PINS, base_mail_id='1a088c5f0b5686d4',
                    latest_guide='07_DOCS/REFERENCE/OPERATIONS/GENOS_DATA_E2E_CURRENT.md',
                    scope='DATA_BUILD_ONLY_NO_OQL_NO_ANSWER', models_called=False)
    manifest['engine_dependencies'] = {}
    for name, data in content.items():
        if name.startswith('02_BACKEND/ENGINES/semantic_runtime/'):
            manifest['engine_dependencies'].update(json.loads(data).get('files', {}))
    for name, expected in manifest['engine_dependencies'].items():
        raw = content.get(name, (ROOT / name).read_bytes())
        if sha(raw) != expected:
            raise ValueError('Latest dependency hash mismatch: ' + name)
    content['patch-manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    with zipfile.ZipFile(PATCH, 'w') as z:
        for name, data in sorted(content.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    print(json.dumps({'path': str(PATCH), 'bytes': PATCH.stat().st_size,
                      'sha256': sha(PATCH.read_bytes()), 'files': len(manifest['files'])}))


if __name__ == '__main__':
    build()
