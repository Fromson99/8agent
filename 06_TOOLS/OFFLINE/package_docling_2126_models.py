#!/usr/bin/env python3
"""Export pinned public model snapshots as regular files, without changing runtime."""
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
NAME = 'docling-models-2.126.0-v1'
PINS = {
    'docling-project/docling-layout-heron': ('main', '8f39ad3c0b4c58e9c2d2c84a38465abf757272d8'),
    'docling-project/docling-models': ('v2.3.0', 'fc0f2d45e2218ea24bce5045f58a389aed16dc23'),
}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    out = ROOT / '09_ARTIFACTS/HANDOFF/GENOS' / NAME
    out.mkdir(exist_ok=False)
    manifest = {'schema': 1, 'target_docling_version': '2.126.0',
                'scope': 'Default transformers Heron layout and TableFormer V1 accurate/fast. No OCR or GENOS VLM.',
                'models': [], 'files': [], 'upstream_sources': []}
    cache = Path.home() / '.cache/huggingface/hub'
    for repo, (ref, revision) in PINS.items():
        src = cache / ('models--' + repo.replace('/', '--')) / 'snapshots' / revision
        if not src.is_dir():
            raise ValueError('Pinned source snapshot missing: ' + repo)
        dest = out / 'models' / repo.replace('/', '--')
        shutil.copytree(src, dest, symlinks=False)
        manifest['models'].append({'repo_id': repo, 'requested_revision': ref, 'resolved_revision': revision})
        for path in sorted(dest.rglob('*')):
            if path.is_file():
                manifest['files'].append({'path': str(path.relative_to(out)), 'bytes': path.stat().st_size, 'sha256': sha(path)})
    for name in ['datamodel/pipeline_options.py', 'datamodel/stage_model_specs.py',
                 'models/stages/table_structure/table_structure_model.py', 'utils/model_downloader.py']:
        url = 'https://raw.githubusercontent.com/docling-project/docling/v2.126.0/docling/' + name
        content = urllib.request.urlopen(url, timeout=30).read()
        dest = out / 'upstream-v2.126.0' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        manifest['upstream_sources'].append({'url': url, 'sha256': sha(dest)})
    (out / 'MODEL_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copyfile(Path(__file__).with_name('check_docling_offline_models.py'), out / 'check_models.py')
    shutil.copyfile(Path(__file__).with_name('DOCLING_2126_OFFLINE.md'), out / 'README_KO.md')
    target = out.parent / (NAME + '.zip')
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path in sorted(out.rglob('*')):
            if path.is_file():
                archive.write(path, str(path.relative_to(out.parent)))
    receipt = {'zip': str(target), 'sha256': sha(target), 'bytes': target.stat().st_size}
    (out / 'package-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
