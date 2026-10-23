"""Hash-bound reuse of actual native projections; canonical JSON boundary fix."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from lawrag.platform.paths import root_path

ADR = root_path('experiments', 'ADR', 'ADR-1039-law-version-delta-serialization')
PARENT = root_path('experiments', 'ADR', 'ADR-1038-law-version-incremental-audit')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    frozen = json.loads((ADR / 'artifacts/design-frozen.json').read_text())
    for name, expected in frozen['inputs'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('frozen input drift: ' + name)
    dataset = json.loads((PARENT / 'artifacts/dataset.json').read_text())
    for row in dataset['versions']:
        if sha(ROOT / row['path']) != row['sha256']:
            raise ValueError('actual raw input drift')
    spec = importlib.util.spec_from_file_location('frozen_audit_1038', ROOT / '06_TOOLS/EXPERIMENTS/adr_1038/audit.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Keep exact old algorithm. JSON loading normalizes ordinal tuples to arrays,
    # which matches the representation persisted in the delta database.
    def load_native(row, unused_empty_catalogue):
        version = row['params']['MST'] + '-' + row['params']['efYd']
        value = json.loads((PARENT / 'artifacts/run-001' / version / 'canonical.json').read_text())
        if value['raw_sha256'] != row['sha256']:
            raise ValueError('canonical/raw binding mismatch')
        return value
    module.build_native = load_native
    module.OUT = ADR / 'artifacts/run-001'
    module.main()

if __name__ == '__main__':
    main()
