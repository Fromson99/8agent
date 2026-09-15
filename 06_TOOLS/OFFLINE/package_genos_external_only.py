"""Add external-only selection to the latest mailed no-revision patch."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / '09_ARTIFACTS/HANDOFF/GENOS'
BASE = DIRECTORY / 'genos-no-revision-20260910.zip'
PATCH = DIRECTORY / 'genos-external-only-20260910.zip'
BASE_SHA = 'dfee35edf00173501cc66bcde6b4eb6fa2acf8564cf7dce923a98d65844e219f'
FILES = [
    '02_BACKEND/lawrag/pipeline/genos_corpus.py',
    '06_TOOLS/COMMANDS/genos_build_all.py',
    '06_TOOLS/COMMANDS/genos_data_e2e.sh',
    '07_DOCS/REFERENCE/OPERATIONS/GENOS_EXTERNAL_ONLY.md']
sha = lambda b: hashlib.sha256(b).hexdigest()


def build():
    if sha(BASE.read_bytes()) != BASE_SHA:
        raise ValueError('Previously mailed base archive changed')
    with zipfile.ZipFile(BASE) as z:
        manifest = json.loads(z.read('patch-manifest.json'))
        content = {name: z.read(name) for name in manifest['files']}
    for entry in manifest['files'].values():
        entry['previous_sha256'] = sorted(set(entry['previous_sha256'] + [entry['sha256']]))
    for name in FILES:
        content[name] = (ROOT / name).read_bytes()
        entry = manifest['files'].setdefault(name, {'allow_missing': True, 'previous_sha256': [], 'preserve_existing': False})
        entry['sha256'] = sha(content[name])
    manifest.update(base_mail_id='1a0895bf8b5e3545', base_archives={BASE.name: BASE_SHA},
                    scope='DATA_BUILD_EXCLUDE_INTERNAL_NO_OQL_NO_ANSWER', models_called=False,
                    latest_guide='07_DOCS/REFERENCE/OPERATIONS/GENOS_EXTERNAL_ONLY.md')
    for name, fingerprint in manifest['engine_dependencies'].items():
        if sha(content.get(name, (ROOT / name).read_bytes())) != fingerprint:
            raise ValueError('Runtime dependency changed: ' + name)
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

