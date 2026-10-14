"""Freeze a small, self-contained handoff for the DB diagnostic rollback."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_DB_LOG_ROLLBACK_20261007_R1'
MODULE = '02_BACKEND/semantic_runtime/query_latency.py'
INDEX = '02_BACKEND/semantic_runtime/unit_fulltext.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    if (OUT/(NAME + '_RUN.txt')).exists():
        raise ValueError('Frozen handoff exists; make a new revision')
    target = (ROOT/MODULE).read_bytes()
    spec = {'revision': NAME, 'inventories': {}, 'patches': {MODULE: {}, INDEX: {}}}
    basis = []
    folders = [ROOT/'08_DEPLOYMENT/GENOS/handoffs'/('query_latency_20261007_r'+str(i))
               for i in range(1, 5)]
    folders.append(ROOT/'08_DEPLOYMENT/GENOS/handoffs/system_logging_20261007_r1')
    for folder in folders:
        record = json.loads((folder/'HANDOFF.json').read_bytes())
        archive = folder/(record['version']+'.zip')
        zip_raw = archive.read_bytes()
        assert sha(zip_raw) == record['code_zip_sha256']
        with zipfile.ZipFile(archive) as source:
            inventory = source.read('CODE_MANIFEST.json')
            assert sha(inventory) == record['code_manifest_sha256']
            spec['inventories'][sha(inventory)] = record['version']
            old = source.read(MODULE)
            spec['patches'][MODULE][sha(old)] = {
                'replacement': base64.b64encode(target).decode(), 'after_sha256': sha(target)}
            old = source.read(INDEX)
            text = old.decode()
            start = text.index('        try:\n            facts = latency.obs.environment_facts(')
            end = text.index('        return db\n', start)
            remove = text[start:end].encode()
            new = old.replace(remove, b'', 1)
            compile(new, INDEX, 'exec')
            spec['patches'][INDEX][sha(old)] = {
                'remove': base64.b64encode(remove).decode(), 'after_sha256': sha(new)}
        basis.append({'version': record['version'], 'code_zip_sha256': sha(zip_raw),
                      'code_manifest_sha256': sha(inventory)})
    spec_raw = encoded(spec)
    code = (OUT/'rollback_db_logs.py').read_bytes()
    compile(code, 'rollback_db_logs.py', 'exec')
    bundle = encoded({'code': base64.b64encode(code).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    bootstrap = ("import base64,hashlib,json,sys,types,zlib\n"
        f"raw=zlib.decompress(base64.b64decode({packed!r}))\n"
        f"assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n"
        "bundle=json.loads(raw)\n"
        "module=types.ModuleType('db_log_rollback')\n"
        "exec(compile(base64.b64decode(bundle['code']),'rollback_db_logs.py','exec'),module.__dict__)\n"
        "try:raise SystemExit(module.main(bundle['spec'],sys.argv[1:]))\n"
        "except Exception as exc:\n"
        " print('DB_LOG_ROLLBACK FAILED: '+str(exc),file=sys.stderr,flush=True)\n"
        " raise SystemExit(1)\n")
    run = ("#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n"
        'task_root="${GENOS_DEV_ROOT:-$HOME/DEV}"\n'
        'task_logs="$task_root/TRANSFER/db-log-rollback-r1/logs"\n'
        'if ! mkdir -p -- "$task_logs"; then\n'
        '  task_logs="${TMPDIR:-/tmp}/8-agent-db-log-rollback-r1-$(id -u)"\n'
        '  mkdir -p -- "$task_logs"\nfi\n'
        'task_log="$task_logs/$(date -u +%Y%m%dT%H%M%S)-$$.log"\n'
        'exec > >(tee -a "$task_log") 2>&1\n'
        'trap \'task_exit=$?; printf "DB_LOG_ROLLBACK_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"\' EXIT\n'
        'printf "LOG=%s\\n" "$task_log"\n'
        'if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; '
        'elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\n'
        'python3 - --root "$task_root" "$@" <<\'DB_LOG_ROLLBACK_PY\'\n'
        + bootstrap + 'DB_LOG_ROLLBACK_PY\n')
    (OUT/'PATCH_SPEC.json').write_bytes(spec_raw)
    (OUT/(NAME+'_RUN.txt')).write_text(run)
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    # A tool archive, not a cumulative replacement ZIP. The applied checkout
    # produces its own exact APPLIED_CODE.zip for the existing release gate.
    manifest = {'format': '8agent-db-log-rollback/1', 'id': NAME,
        'scope': 'DB latency diagnostics only; keep search caches and request/error logs',
        'files': [{'path': n, 'sha256': sha(b), 'bytes': len(b)}
                  for n,b in [('rollback_db_logs.py',code),('PATCH_SPEC.json',spec_raw)]],
        'bases': basis, 'runtime_targets': spec['patches'], 'genos_deployed': False}
    # Runtime patch bytes are already in PATCH_SPEC; do not duplicate in reports.
    manifest['runtime_targets'] = {n:{h:v['after_sha256'] for h,v in items.items()}
                                   for n,items in spec['patches'].items()}
    (OUT/'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    with zipfile.ZipFile(OUT/(NAME+'.zip'),'x',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name in ('rollback_db_logs.py','PATCH_SPEC.json','CODE_MANIFEST.json'):
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            archive.write(OUT/name,name)
    (OUT/'HANDOFF.json').write_bytes(encoded({
        'version':NAME,'created_at':datetime.now(timezone.utc).isoformat(),
        'working_root':str(ROOT),'working_git_head':subprocess.check_output(
            ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'code_zip_sha256':sha((OUT/(NAME+'.zip')).read_bytes()),
        'code_manifest_sha256':sha((OUT/'CODE_MANIFEST.json').read_bytes()),
        'run_txt_sha256':sha(run.encode()),'supported_bases':basis,
        'local_active_pointer_sha256':sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()),
        'local_active_pointer_changed':False,'field_generation':None,
        'field_generation_manifest_sha256':None,'field_git_commit':None,
        'field_code_serving_revision':None,'genos_applied':False,
        'genos_deployed':False,'workflow_test':'NOT_RUN','email_status':'NOT_SENT'}))
    print(json.dumps({'zip_bytes':(OUT/(NAME+'.zip')).stat().st_size,
                      'txt_bytes':len(run.encode()),'bases':len(basis)}))


if __name__ == '__main__':
    main()
