"""Extend the exact mailed schema build, not unrelated current workspace files."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / '09_ARTIFACTS/HANDOFF/GENOS'
PATCH = DIRECTORY / 'genos-data-folders-20260909.zip'
UPDATES = ['02_BACKEND/lawrag/pipeline/genos_build.py',
           '06_TOOLS/COMMANDS/genos_data.sh',
           '07_DOCS/REFERENCE/OPERATIONS/GENOS_DATA_FOLDERS.md']


def build():
    prior = DIRECTORY / 'genos-schema-build-20260909.zip'
    if hashlib.sha256(prior.read_bytes()).hexdigest() != 'a8b393b6b58bc01a083240601700676e358cce70a3673ae2ced5c36c7a7eccb6':
        raise ValueError('previously mailed schema ZIP changed')
    with zipfile.ZipFile(prior) as archive:
        manifest = json.loads(archive.read('patch-manifest.json'))
        content = {name: archive.read(name) for name in manifest['files']}
    for name in UPDATES:
        content[name] = (ROOT / name).read_bytes()
        previous = manifest['files'].get(name)
        manifest['files'][name] = {
            'sha256': hashlib.sha256(content[name]).hexdigest(),
            'allow_missing': previous['allow_missing'] if previous else True,
            'previous_sha256': sorted(set(previous['previous_sha256'] + [previous['sha256']])) if previous else []}
    manifest['preserve'].append('data')
    manifest['latest_guide'] = '07_DOCS/REFERENCE/OPERATIONS/GENOS_DATA_FOLDERS.md'
    content['patch-manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    with zipfile.ZipFile(PATCH, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in content.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    print(json.dumps({'path': str(PATCH), 'bytes': PATCH.stat().st_size,
                      'sha256': hashlib.sha256(PATCH.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    build()
