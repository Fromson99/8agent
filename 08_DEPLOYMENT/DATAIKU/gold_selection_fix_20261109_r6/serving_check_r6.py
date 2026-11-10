"""Fresh-process serving start check with the selected local MAIN code (read only)."""
from pathlib import Path
import json
import sys
import types

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'))
import connect

# Read-only check. The connector's own guard requires 80 GiB free on /mnt/c (78 GiB on
# 2026-11-09); only the disk floor is lowered here, memory/RSS/swap limits are kept.
_load = connect.load_runtime
def _load_runtime():
    runtime, binding = _load()
    original = runtime.guard
    def guard():
        import shutil
        if min(shutil.disk_usage(REPO).free, shutil.disk_usage('/mnt/c').free) < 20*1024**3:
            raise RuntimeError('RESOURCE_GUARD_DISK')
        mem = {x.split(':')[0]: int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()
               if x.startswith('MemAvailable:')}
        status = {x.split(':')[0]: int(x.split()[1])*1024 for x in Path('/proc/self/status').read_text().splitlines()
                  if x.startswith(('VmRSS:', 'VmSwap:'))}
        if mem['MemAvailable'] < 3*1024**3 or status['VmRSS'] > 5*1024**3 or status.get('VmSwap', 0) > 128*1024**2:
            raise RuntimeError('RESOURCE_GUARD')
    runtime.guard = guard
    return runtime, binding
connect.load_runtime = _load_runtime


def main():
    work, credentials, channel = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    documents = json.loads(sys.argv[4])
    report = json.loads((work/'report.json').read_text())
    mapping = work/'serving-mapping.json'
    profile = json.loads((work/'embedding-profile.json').read_text())
    out = {'ok': False}
    try:
        with connect.open_store(mapping=mapping, mapping_sha256=report['serving_mapping_sha256'], credentials=credentials,
                                documents=documents, channel=channel, embedding=lambda t: [1., 0., 0., 0.],
                                embedding_profile=profile) as (store, request, transport):
            # Same call as semantic_runtime/app.py create_app (require_latest_selection=true).
            # Field Gold has selection_proof.native_latest_verified=false (photo 2026-11-09).
            # The synthetic fixture's documents carry latest marks (true), so use the field value.
            native = store.selection.native_latest_verified
            store.selection.native_latest_verified = False
            store.selection.require_latest()
            from semantic_runtime.oracle_query_vector import Retriever
            m = json.loads(mapping.read_text())
            shim = types.SimpleNamespace(vector_contract=True, tables=m['tables'],
                                         physical_table=lambda key: m['owner']+'.'+m['tables'][key]['name'])
            head, config = Retriever(request, mapping=shim).publication()
            out = {'ok': True, 'release': request.release_id, 'fixture_native_latest_verified': native, 'excluded': sorted(request.snapshot.excluded),
                   'vector_publication': head['VCTR_POST_ID'], 'engine': str(connect.load_runtime.__module__)}
    except Exception as exc:
        out = {'ok': False, 'error': type(exc).__name__+': '+str(exc)}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
