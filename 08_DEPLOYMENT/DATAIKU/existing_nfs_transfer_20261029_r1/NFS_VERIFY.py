"""Run from the actual installed checkout before pushing its serving revision."""
from pathlib import Path
import json
import subprocess
import sys

root = Path(__file__).resolve().parent
sys.path[:0] = [str(root), str(root/'02_BACKEND')]
import worker
import transport as t
from nfs_source import GENERATION
from lawrag.pipeline.oracle_existing_nfs import Snapshot
from lawrag.pipeline import oracle_full_package, term_serving_bundle

worker.verify_code(root)
source = Snapshot(GENERATION, t.sha(root/'CODE_PINS.json'))
_, _, inventory = oracle_full_package.inventory(GENERATION)
if inventory['files'] != source.info['files']:
    raise ValueError('NFS_INVENTORY_CONSUMER_MISMATCH')
term_serving_bundle.verify_assets(GENERATION)
subprocess.run([sys.executable, str(root/'06_TOOLS/COMMANDS/genos_generation_e2e.py'),
                '--code-root', str(root), '--generation', GENERATION], check=True)
source.check()
print('NFS_SOURCE_VERIFIED', json.dumps({
    'code_root': str(root), 'generation': GENERATION, 'code_sha256': source.code,
    'git_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
    'python_executable': sys.executable, 'python_version': sys.version,
    'entry_sha256': {name: t.sha(root/name) for name in ('service.py', 'worker.py', 'nfs_source.py')},
    'manifest_sha256': source.info['dataset_version'],
    'snapshot_sha256': source.info['snapshot_sha256'],
    'source_counts': inventory['source_counts'], 'files': len(source.info['files']),
    'bytes': sum(v['bytes'] for v in source.info['files'].values()),
    'source_modified': False, 'structure_calls': 0, 'index_calls': 0,
    'field_revision_verified': False}, ensure_ascii=False), flush=True)
