"""Repackage the identical R1 rollback with GENOS checkout-link support."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
PARENT=OUT.with_name('db_log_rollback_20261007_r1')
NAME='GENOS_DB_LOG_ROLLBACK_20261007_R2'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def main():
    if (OUT/(NAME+'_RUN.txt')).exists():
        raise ValueError('Frozen handoff exists')
    parent=json.loads((PARENT/'HANDOFF.json').read_bytes())
    spec=json.loads((PARENT/'PATCH_SPEC.json').read_bytes())
    spec['revision']=NAME
    code=(OUT/'rollback_db_logs.py').read_bytes()
    compile(code,'rollback_db_logs.py','exec')
    bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    bootstrap=("import base64,hashlib,json,sys,types,zlib\n"
        f"raw=zlib.decompress(base64.b64decode({packed!r}))\n"
        f"assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n"
        "bundle=json.loads(raw)\nmodule=types.ModuleType('db_log_rollback')\n"
        "exec(compile(base64.b64decode(bundle['code']),'rollback_db_logs.py','exec'),module.__dict__)\n"
        "try:raise SystemExit(module.main(bundle['spec'],sys.argv[1:]))\n"
        "except Exception as exc:\n"
        " print('DB_LOG_ROLLBACK FAILED: '+str(exc),file=sys.stderr,flush=True)\n"
        " raise SystemExit(1)\n")
    run=("#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n"
        'task_root="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"\n'
        'task_logs="$task_root/TRANSFER/db-log-rollback-r2/logs"\n'
        'if ! mkdir -p -- "$task_logs"; then\n'
        ' task_logs="${TMPDIR:-/tmp}/8-agent-db-log-rollback-r2-$(id -u)"\n'
        ' mkdir -p -- "$task_logs"\nfi\n'
        'task_log="$task_logs/$(date -u +%Y%m%dT%H%M%S)-$$.log"\n'
        'exec > >(tee -a "$task_log") 2>&1\n'
        'trap \'task_exit=$?; printf "DB_LOG_ROLLBACK_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"\' EXIT\n'
        'printf "LOG=%s\\n" "$task_log"\n'
        'if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; '
        'elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\n'
        'python3 - --root "$task_root" "$@" <<\'DB_LOG_ROLLBACK_PY\'\n'
        +bootstrap+'DB_LOG_ROLLBACK_PY\n')
    (OUT/'PATCH_SPEC.json').write_bytes(encoded(spec))
    (OUT/(NAME+'_RUN.txt')).write_text(run)
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    manifest={'format':'8agent-db-log-rollback/1','id':NAME,
        'parent_handoff':parent['version'],'parent_code_zip_sha256':parent['code_zip_sha256'],
        'runtime_targets_unchanged_from_r1':True,
        'checkout_root_policy':'Resolve requested DEV symlink; reject links inside code inventory',
        'files':[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in
                 [('rollback_db_logs.py',code),('PATCH_SPEC.json',encoded(spec))]],
        'bases':parent['supported_bases'],
        'runtime_targets':{n:{h:v['after_sha256'] for h,v in entries.items()}
                           for n,entries in spec['patches'].items()},'genos_deployed':False}
    (OUT/'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    with zipfile.ZipFile(OUT/(NAME+'.zip'),'x',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name in ('rollback_db_logs.py','PATCH_SPEC.json','CODE_MANIFEST.json'):
            archive.write(OUT/name,name)
    record={'version':NAME,'created_at':datetime.now(timezone.utc).isoformat(),
        'working_root':str(ROOT),'working_git_head':subprocess.check_output(
            ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'code_zip_sha256':sha((OUT/(NAME+'.zip')).read_bytes()),
        'code_manifest_sha256':sha((OUT/'CODE_MANIFEST.json').read_bytes()),
        'run_txt_sha256':sha(run.encode()),'supported_bases':parent['supported_bases'],
        'local_active_pointer_sha256':sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()),
        'local_active_pointer_changed':False,'runtime_code_unchanged_from_r1':True,
        'field_generation':None,'field_generation_manifest_sha256':None,
        'field_git_commit':None,'field_code_serving_revision':None,
        'genos_applied':False,'genos_deployed':False,'workflow_test':'NOT_RUN',
        'user_field_evidence':{'photo':'Existing DEV checkout required; check/apply/verify exit 1',
                             'r1_patch_applied':False,'actual_symlink_target':'NOT_PROVIDED'},
        'email_status':'NOT_SENT'}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print(json.dumps({'version':NAME,'zip_bytes':(OUT/(NAME+'.zip')).stat().st_size,
                      'txt_bytes':len(run.encode())}))


if __name__=='__main__':
    main()
