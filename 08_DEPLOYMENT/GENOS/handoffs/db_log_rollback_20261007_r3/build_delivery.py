"""Freeze exact original/R1/R2 repairs; never rehash unknown field code."""
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_DB_LOG_ROLLBACK_20261007_R3'
PIPELINE = '00_SYSTEM/PIPELINE.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def load(folder):
    loader = importlib.util.spec_from_file_location(folder.name, folder/'rollback_db_logs.py')
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def corrected(payload):
    """Only repair the known historical WORKSPACE pin and registry pins."""
    result = dict(payload)
    workspace_repairs = []
    for name, raw in payload.items():
        if not name.startswith('02_BACKEND/ENGINES/') or not name.endswith('.json'):
            continue
        manifest = json.loads(raw)
        for path, expected in manifest['files'].items():
            actual = sha(payload[path])
            if actual == expected:
                continue
            if path != '00_SYSTEM/WORKSPACE.json':
                raise ValueError('Unexpected historical code pin: ' + name + ': ' + path)
            needle = (json.dumps(path) + ': ' + json.dumps(expected)).encode()
            replacement = (json.dumps(path) + ': ' + json.dumps(actual)).encode()
            assert raw.count(needle) == 1
            raw = raw.replace(needle, replacement, 1)
            workspace_repairs.append({'engine_manifest': name, 'path': path,
                                      'before_sha256': expected, 'after_sha256': actual})
        result[name] = raw
    raw = result[PIPELINE]
    config = json.loads(raw)
    for entry in config['engines'].values():
        actual = sha(result[entry['manifest']])
        if actual == entry['sha256']:
            continue
        needle = ('"sha256": ' + json.dumps(entry['sha256'])).encode()
        replacement = ('"sha256": ' + json.dumps(actual)).encode()
        assert raw.count(needle) == 1
        raw = raw.replace(needle, replacement, 1)
    result[PIPELINE] = raw
    return result, workspace_repairs


def main():
    if (OUT/(NAME+'_RUN.txt')).exists():
        raise ValueError('Frozen handoff exists; create another revision')
    parent_folders = [OUT.with_name('db_log_rollback_20261007_r'+str(i)) for i in (1, 2)]
    parents = [load(d) for d in parent_folders]
    parent_specs = [json.loads((d/'PATCH_SPEC.json').read_bytes()) for d in parent_folders]
    module = load(OUT)
    spec = {'revision': NAME, 'states': {}, 'blobs': {}, 'output_inventories': {}}
    bases = []
    reproduction = []
    folders = [OUT.with_name('query_latency_20261007_r'+str(i)) for i in range(1, 5)]
    folders.append(OUT.with_name('system_logging_20261007_r1'))
    for folder in folders:
        record = json.loads((folder/'HANDOFF.json').read_bytes())
        archive = folder/(record['version']+'.zip')
        assert sha(archive.read_bytes()) == record['code_zip_sha256']
        with TemporaryDirectory(prefix='db-log-r3-build-') as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(archive) as z:
                z.extractall(root)
                original = {n: z.read(n) for n in z.namelist()}
            assert sha(original['CODE_MANIFEST.json']) == record['code_manifest_sha256']
            variants = [('original', original)]
            parent_results = []
            for number, (parent, parent_spec) in enumerate(zip(parents, parent_specs), 1):
                _, payload, changes, _ = parent.prepared(root, parent_spec)
                variant = {**payload, **changes}
                variants.append(('rollback-r'+str(number), variant))
                parent_results.append(variant)
            final, workspace_repairs = corrected(parent_results[-1])
            module.verify_bindings(final)
            config = json.loads(original[PIPELINE])
            broken = []
            for step in config['profiles']['legal-agent-rag-v6']['nodes']:
                entry = config['engines'][step['engine']]
                actual = sha(parent_results[-1][entry['manifest']])
                if actual != entry['sha256']:
                    broken.append({'engine': step['engine'], 'manifest': entry['manifest'],
                                   'expected': entry['sha256'], 'actual': actual})
            reproduction.append({'basis': record['version'], 'r2_active_profile_mismatches': broken,
                                 'known_workspace_pin_repairs': workspace_repairs})
            for predecessor, candidate in variants:
                inventory = candidate['CODE_MANIFEST.json']
                inventory_hash = sha(inventory)
                patches = {}
                for path, target in final.items():
                    if path == 'CODE_MANIFEST.json' or target == candidate[path]:
                        continue
                    target_hash = sha(target)
                    spec['blobs'][target_hash] = base64.b64encode(target).decode()
                    patches[path] = {'before_sha256': sha(candidate[path]), 'after_sha256': target_hash}
                spec['states'][inventory_hash] = {'label': record['version']+'/'+predecessor,
                    'patches': patches, 'known_workspace_pin_repair': bool(workspace_repairs)}
                for path, raw in candidate.items():
                    target = root/path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                _, _, changes, after = module.prepared(root, spec)
                output_hash = sha(changes['CODE_MANIFEST.json'])
                spec['output_inventories'][output_hash] = spec['states'][inventory_hash]['label']
                bases.append({'label': spec['states'][inventory_hash]['label'],
                    'code_zip_sha256': record['code_zip_sha256'], 'input_inventory_sha256': inventory_hash,
                    'output_inventory_sha256': output_hash, 'modified_paths': sorted(changes),
                    'unchanged_serving_code': predecessor != 'original'})
                # Parent recipes must always read the unmodified source archive.
                for path, raw in original.items():
                    (root/path).write_bytes(raw)
    spec_raw = encoded(spec)
    code = (OUT/'rollback_db_logs.py').read_bytes()
    compile(code, 'rollback_db_logs.py', 'exec')
    compressed_spec = gzip.compress(spec_raw, compresslevel=9, mtime=0)
    (OUT/'PATCH_SPEC.json.gz').write_bytes(compressed_spec)
    bundle = encoded({'code': base64.b64encode(code).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    bootstrap = ("import base64,hashlib,json,sys,types,zlib\n"
        f"raw=zlib.decompress(base64.b64decode({packed!r}))\n"
        f"assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n"
        "bundle=json.loads(raw)\nmodule=types.ModuleType('db_log_rollback')\n"
        "exec(compile(base64.b64decode(bundle['code']),'rollback_db_logs.py','exec'),module.__dict__)\n"
        "try:raise SystemExit(module.main(bundle['spec'],sys.argv[1:]))\n"
        "except Exception as exc:\n"
        " print('DB_LOG_ROLLBACK FAILED: '+str(exc),file=sys.stderr,flush=True)\n"
        " raise SystemExit(1)\n")
    run = ("#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n"
        'task_root="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"\n'
        'task_logs="$task_root/TRANSFER/db-log-rollback-r3/logs"\n'
        'if ! mkdir -p -- "$task_logs"; then\n'
        ' task_logs="${TMPDIR:-/tmp}/8-agent-db-log-rollback-r3-$(id -u)"\n'
        ' mkdir -p -- "$task_logs"\nfi\n'
        'task_log="$task_logs/$(date -u +%Y%m%dT%H%M%S)-$$.log"\n'
        'exec > >(tee -a "$task_log") 2>&1\n'
        'trap \'task_exit=$?; printf "DB_LOG_ROLLBACK_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"\' EXIT\n'
        'printf "LOG=%s\\n" "$task_log"\n'
        'if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; '
        'elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\n'
        'python3 - --root "$task_root" "$@" <<\'DB_LOG_ROLLBACK_PY\'\n'
        + bootstrap + 'DB_LOG_ROLLBACK_PY\n')
    run_path = OUT/(NAME+'_RUN.txt')
    run_path.write_text(run)
    subprocess.run(['bash', '-n', str(run_path)], check=True)
    manifest = {'format': '8agent-db-log-rollback/1', 'id': NAME,
        'files': [{'path': n, 'sha256': sha(b), 'bytes': len(b)} for n, b in
                  [('rollback_db_logs.py', code), ('PATCH_SPEC.json.gz', compressed_spec)]],
        'input_inventory_count': len(spec['states']), 'all_engine_bindings_verified_before_write': True,
        'field_deployed': False}
    (OUT/'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    zip_path = OUT/(NAME+'.zip')
    with zipfile.ZipFile(zip_path, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in ('rollback_db_logs.py', 'PATCH_SPEC.json.gz', 'CODE_MANIFEST.json'):
            z.write(OUT/name, name)
    (OUT/'REPRODUCTION.json').write_bytes(encoded(reproduction))
    handoff = {'version': NAME, 'created_at': datetime.now(timezone.utc).isoformat(),
        'working_root': str(ROOT), 'working_git_head': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'code_zip_sha256': sha(zip_path.read_bytes()),
        'code_manifest_sha256': sha((OUT/'CODE_MANIFEST.json').read_bytes()),
        'run_txt_sha256': sha(run.encode()), 'supported_bases': bases,
        'cause': 'R1/R2 updated engine manifests but omitted PIPELINE registry hash updates',
        'local_active_pointer_sha256': sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()),
        'local_active_pointer_changed': False, 'genos_applied': False, 'genos_deployed': False,
        'field_generation': None, 'field_generation_manifest_sha256': None,
        'field_git_commit': None, 'field_code_serving_revision': None,
        'workflow_test': 'NOT_RUN', 'email_status': 'NOT_SENT'}
    (OUT/'HANDOFF.json').write_bytes(encoded(handoff))
    print(json.dumps({'version': NAME, 'states': len(spec['states']),
                      'zip_bytes': zip_path.stat().st_size, 'txt_bytes': len(run.encode())}))


if __name__ == '__main__':
    main()
