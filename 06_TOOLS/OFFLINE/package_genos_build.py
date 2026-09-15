"""Small reproducible onsite schema-build patch; contains no raw data or credentials."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
FROZEN = '02_BACKEND/lawrag/research/candidates/adr_0252/source-ids/revisions/rev-001/snapshot/06_TOOLS/OFFLINE/'
FILES = [
    '02_BACKEND/lawrag/pipeline/genos_build.py',
    '02_BACKEND/lawrag/pipeline/genos_e2e.py',
    '02_BACKEND/semantic_runtime/genos_backend.py',
    '02_BACKEND/semantic_runtime/genos_index.py',
    '02_BACKEND/semantic_runtime/app.py',
    'service.py',
    '06_TOOLS/COMMANDS/genos_unified_pipeline.py',
    '06_TOOLS/COMMANDS/genos_build.sh',
    '06_TOOLS/AUDIT/legal_semantic_contract.py',
    '00_SYSTEM/PIPELINE.json',
    *['02_BACKEND/ENGINES/semantic_runtime/1.0.0/' + name + '.json'
      for name in ['retrieve', 'select', 'assemble', 'answer', 'load', 'feedback']],
    *[FROZEN + f for f in ('genos_authoring.py', 'source_candidates.py', 'definition_patterns.py')],
    '07_DOCS/REFERENCE/OPERATIONS/GENOS_SCHEMA_BUILD.md',
]


def build():
    directory = ROOT / '09_ARTIFACTS/HANDOFF/GENOS'
    output = directory / 'genos-schema-build-20260909.zip'
    priors = [directory / n for n in ('genos-unified-dev-root-20260908.zip', 'genos-e2e-patch-20260909.zip')]
    previous = {name: set() for name in FILES}
    with zipfile.ZipFile(priors[0]) as original:
        original_names = set(original.namelist())
    for archive in priors:
        with zipfile.ZipFile(archive) as z:
            for name in FILES:
                if name in z.namelist():
                    previous[name].add(hashlib.sha256(z.read(name)).hexdigest())
    # Pre-change workspace versions; transport itself is deliberately NOT in FILES.
    previous['service.py'].add('217b34655ba864a7df878e1ebc2e1aafa53b8467ca4fcf6fbebcb4cac9f4e5b5')
    previous['02_BACKEND/semantic_runtime/app.py'].add('3c74a13e7359a016f7d2523719674126ba666fc71369100c436270ff0284521a')
    manifest = {'format': 'genos-schema-build-patch-v1',
                'preserve': ['02_BACKEND/semantic_runtime/genos.py', '.env', 'GENOS_DATA', '.git'],
                'files': {n: {'sha256': hashlib.sha256((ROOT/n).read_bytes()).hexdigest(),
                              'allow_missing': n not in original_names,
                              'previous_sha256': sorted(previous[n])} for n in FILES}}
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ['patch-manifest.json', *FILES]:
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            data = json.dumps(manifest, ensure_ascii=False, indent=2).encode() if name == 'patch-manifest.json' else (ROOT/name).read_bytes()
            archive.writestr(info, data)
    print(json.dumps({'path': str(output), 'bytes': output.stat().st_size,
                      'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    build()
