"""Build the small, deterministic one-document GENOS patch (no data/secrets)."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    '02_BACKEND/semantic_runtime/genos_backend.py',
    '02_BACKEND/lawrag/pipeline/genos_e2e.py',
    '06_TOOLS/COMMANDS/genos_unified_pipeline.py',
    '06_TOOLS/COMMANDS/genos_e2e.sh',
    '00_SYSTEM/PIPELINE.json',
    *['02_BACKEND/ENGINES/semantic_runtime/1.0.0/' + name + '.json'
      for name in ['retrieve', 'select', 'assemble', 'answer', 'load', 'feedback']],
    '07_DOCS/REFERENCE/OPERATIONS/GENOS_ONE_DOCUMENT_E2E.md',
]


def build():
    output = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-e2e-patch-20260909.zip'
    original = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-unified-dev-root-20260908.zip'
    entries = {}
    with zipfile.ZipFile(original) as prior:
        for name in FILES:
            data = (ROOT / name).read_bytes()
            entries[name] = {'sha256': hashlib.sha256(data).hexdigest(),
                             'previous_sha256': [hashlib.sha256(prior.read(name)).hexdigest()]
                             if name in prior.namelist() else []}
    manifest = {'format': 'genos-e2e-patch-v1', 'files': entries,
                'preserve': ['02_BACKEND/semantic_runtime/genos.py', '.env', 'GENOS_DATA', '.git']}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ['patch-manifest.json', *FILES]:
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            data = json.dumps(manifest, indent=2).encode() if name == 'patch-manifest.json' else (ROOT/name).read_bytes()
            archive.writestr(info, data)
    print(json.dumps({'path': str(output), 'bytes': output.stat().st_size,
                      'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    build()
