"""Reproducible additive patch over the exact previously delivered folder ZIP."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / '09_ARTIFACTS/HANDOFF/GENOS'
PATCH = DIRECTORY / 'genos-all-corpus-20260909.zip'
UPDATES = ['02_BACKEND/lawrag/pipeline/genos_build.py',
           '02_BACKEND/lawrag/pipeline/genos_corpus.py',
           '06_TOOLS/COMMANDS/genos_build_all.py',
           '06_TOOLS/COMMANDS/genos_build_all.sh',
           '07_DOCS/REFERENCE/OPERATIONS/GENOS_ALL_CORPUS_BUILD.md']


def build():
    prior = DIRECTORY / 'genos-data-folders-20260909.zip'
    if hashlib.sha256(prior.read_bytes()).hexdigest() != '302561fb7b334502137ea90a0ac819e5be2c274ed79ff1c5308f70b46cf6e6a8':
        raise ValueError('previously mailed folder ZIP changed')
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
    manifest['latest_guide'] = UPDATES[-1]
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
