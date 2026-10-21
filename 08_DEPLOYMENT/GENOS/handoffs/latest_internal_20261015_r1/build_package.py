"""Seal exactly the seven reviewed build files; does not export source data."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(v): return (json.dumps(v, ensure_ascii=False, indent=2) + '\n').encode()

def main():
    files = json.loads((HERE / 'PREIMAGES.json').read_bytes())
    for row in files:
        raw = (ROOT / row['path']).read_bytes()
        row['after'] = sha(raw)
    dependencies = ['06_TOOLS/pipeline.py',
        '02_BACKEND/lawrag/pipeline/genos_stages.py',
        '02_BACKEND/lawrag/pipeline/genos_doc.py',
        '02_BACKEND/lawrag/pipeline/genos_status.py',
        '02_BACKEND/lawrag/pipeline/structure_selection.py',
        '02_BACKEND/lawrag/pipeline/raw_preprocess.py',
        '06_TOOLS/COMMANDS/genos_release_gate.py',
        '06_TOOLS/COMMANDS/genos_generation_e2e.py']
    required = [{'path': p, 'sha256': sha((ROOT / p).read_bytes())} for p in dependencies]
    manifest = {'format': '8agent-code/1', 'scope': 'latest-internal-build-only',
                'files': [{'path': r['path'], 'sha256': r['after'], 'bytes': (ROOT / r['path']).stat().st_size} for r in files],
                'required_files': required}
    (HERE / 'CODE_MANIFEST.json').write_bytes(encode(manifest))
    with zipfile.ZipFile(HERE / 'CODE.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr('CODE_MANIFEST.json', encode(manifest))
        for row in files:
            z.write(ROOT / row['path'], row['path'])
    spec = {'version': 'GENOS_LATEST_INTERNAL_20261015_R1', 'files': files, 'required_files': required,
            'code_zip_sha256': sha((HERE / 'CODE.zip').read_bytes()),
            'code_manifest_sha256': sha(encode(manifest))}
    (HERE / 'PATCH_SPEC.json').write_bytes(encode(spec))
    members = ['CODE.zip', 'CODE_MANIFEST.json', 'PATCH_SPEC.json', 'apply.py', 'smoke_check.py',
               'GENOS_LATEST_INTERNAL_20261015_R1_RUN.txt', 'GUIDE_UTF8.txt', 'DESIGN.txt']
    with zipfile.ZipFile(HERE / 'GENOS_LATEST_INTERNAL_20261015_R1.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in members:
            z.write(HERE / name, name)
    print(json.dumps({'files': len(files), 'code_zip_sha256': spec['code_zip_sha256'],
                      'zip_bytes': (HERE / 'GENOS_LATEST_INTERNAL_20261015_R1.zip').stat().st_size}))

if __name__ == '__main__': main()
