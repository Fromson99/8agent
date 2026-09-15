"""Package exact latest mailed runtime + offline build, without runtime edits."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / '09_ARTIFACTS/HANDOFF/GENOS'
PATCH = DIRECTORY / 'genos-all-corpus-compatible-20260910.zip'
PINS = {
    'genos-all-corpus-20260909.zip': '88fee4772e62c52f09dcc0d2ddaccf5ac1002f481ca18a59b7d81eb9778636c1',
    'genos-semantic-backend-hash-fix-20260910.zip': 'e53c345c187a165a84350f529a68312b6d446e6c86d15906649b4ff0a1da7231',
}
sha = lambda b: hashlib.sha256(b).hexdigest()


def build():
    for name, expected in PINS.items():
        if sha((DIRECTORY / name).read_bytes()) != expected:
            raise ValueError('mailed ZIP changed: ' + name)
    with zipfile.ZipFile(DIRECTORY / 'genos-all-corpus-20260909.zip') as z:
        old = json.loads(z.read('patch-manifest.json'))
        content = {n: z.read(n) for n in old['files']}
    previous = {n: set(r['previous_sha256'] + [r['sha256']]) for n, r in old['files'].items()}
    with zipfile.ZipFile(DIRECTORY / 'genos-semantic-backend-hash-fix-20260910.zip') as z:
        latest = {n: z.read(n) for n in z.namelist() if not n.endswith('/')}
    content.update(latest)
    dependencies = {}
    for name, data in latest.items():
        if name.startswith('02_BACKEND/ENGINES/semantic_runtime/'):
            for path, expected in json.loads(data)['files'].items():
                raw = content.get(path)
                if raw is None or sha(raw) != expected:
                    raw = (ROOT / path).read_bytes()
                if sha(raw) != expected:
                    raise ValueError('latest mailed dependency not reproducible: ' + path)
                content[path] = raw
                dependencies[path] = expected
    logging_path = '02_BACKEND/semantic_runtime/observability.py'
    content[logging_path] = (ROOT / logging_path).read_bytes()
    if sha(content[logging_path]) != 'c9df02c550d9a2b960c7b8d9ab1b335e19d9203787c61869e781ff0f17263a79':
        raise ValueError('logging dependency changed')
    # Known historical shipped file fingerprints, not arbitrary workspace versions.
    history = ['genos-unified-dev-root-20260908.zip', 'genos-three-axis-20260909.zip',
               'genos-e2e-patch-20260909.zip', 'genos-schema-build-20260909.zip',
               'genos-data-folders-20260909.zip', 'genos-chat-screen-patch-20260909.zip']
    history_hashes = {}
    for name in history:
        history_hashes[name] = sha((DIRECTORY / name).read_bytes())
        with zipfile.ZipFile(DIRECTORY / name) as z:
            for path in content.keys() & set(z.namelist()):
                previous.setdefault(path, set()).add(sha(z.read(path)))
    guide = '07_DOCS/REFERENCE/OPERATIONS/GENOS_LATEST_COMPATIBLE.md'
    content[guide] = (ROOT / guide).read_bytes()
    manifest = {'format': 'genos-latest-compatible-v1', 'base_mail_id': '1a0888c42c33f95c',
                'base_archives': PINS, 'history_archives': history_hashes,
                'engine_dependencies': dependencies,
                'preserve': ['.env', 'data', 'GENOS_DATA', '.git', 'runtime', '01_DATA'],
                'files': {}}
    for name, data in sorted(content.items()):
        manifest['files'][name] = {'sha256': sha(data), 'previous_sha256': sorted(previous.get(name, set())),
                                   'allow_missing': True,
                                   'preserve_existing': name == '02_BACKEND/semantic_runtime/genos.py'}
    content['patch-manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    with zipfile.ZipFile(PATCH, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(content.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    print(json.dumps({'path': str(PATCH), 'bytes': PATCH.stat().st_size, 'sha256': sha(PATCH.read_bytes()),
                      'files': len(manifest['files'])}))


if __name__ == '__main__':
    build()
