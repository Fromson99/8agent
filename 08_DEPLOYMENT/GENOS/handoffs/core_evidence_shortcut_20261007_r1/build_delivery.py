"""Package the evaluated source-route delta on exact known GENOS R3 inventories."""
import ast
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
NAME = 'GENOS_CORE_EVIDENCE_SHORTCUT_20261007_R1'
PRIOR = OUT.with_name('db_log_rollback_20261007_r3')
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0683-core-evidence-shortcut-consumer-closure/artifacts'
BASE = ROOT/'08_DEPLOYMENT/RELEASES/session-runtime-v6-20261007-r1/code'
CAND = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0683/core-route/revisions/rev-001/snapshot'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def load(folder, filename='rollback_db_logs.py'):
    spec = importlib.util.spec_from_file_location(folder.name, folder/filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prior_states():
    parent = load(PRIOR)
    spec = json.loads(gzip.decompress((PRIOR/'PATCH_SPEC.json.gz').read_bytes()))
    legacy = [PRIOR.with_name('db_log_rollback_20261007_r'+str(i)) for i in (1, 2)]
    for label in ['query_latency_20261007_r'+str(i) for i in (3,4)]+['system_logging_20261007_r1']:
        folder = OUT.with_name(label)
        record = json.loads((folder/'HANDOFF.json').read_bytes())
        archive = folder/(record['version']+'.zip')
        assert sha(archive.read_bytes()) == record['code_zip_sha256']
        with zipfile.ZipFile(archive) as z:
            original = {n:z.read(n) for n in z.namelist()}
        for predecessor in ('original', 'rollback-r1', 'rollback-r2'):
            with TemporaryDirectory() as temporary:
                root = Path(temporary)
                for path, raw in original.items():
                    target=root/path; target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(raw)
                if predecessor != 'original':
                    previous=legacy[int(predecessor[-1])-1]
                    old=load(previous)
                    oldspec=json.loads((previous/'PATCH_SPEC.json').read_bytes())
                    _,_,changes,_=old.prepared(root,oldspec)
                    for path,raw in changes.items():(root/path).write_bytes(raw)
                _,payload,changes,_=parent.prepared(root,spec)
                yield record['version']+'/'+predecessor+'/db-log-rollback-r3', {**payload,**changes}


def merge(rel, raw, temporary):
    if not (BASE/rel).exists():
        return (CAND/rel).read_bytes()
    paths=[temporary/n for n in ('field','base','feature')]
    for path,value in zip(paths,[raw,(BASE/rel).read_bytes(),(CAND/rel).read_bytes()]):path.write_bytes(value)
    result=subprocess.run(['git','merge-file','-p',*map(str,paths)],capture_output=True)
    if result.returncode:raise ValueError('Unreviewed merge conflict: '+rel)
    return result.stdout


def main():
    if (OUT/(NAME+'_RUN.txt')).exists():
        raise ValueError('Frozen handoff exists; use a new revision')
    installer=OUT/'apply_shortcut.py'
    code=installer.read_bytes()
    ast.parse(code, feature_version=(3,11))
    module=load(OUT,'apply_shortcut.py')
    freeze=json.loads((ADR/'design/freeze.json').read_bytes())
    candidate_hashes=freeze['serving_files']
    receipt=json.loads((ADR/'working-install-receipt.json').read_bytes())
    paths=[row['path'] for row in receipt['files'] if row['kind']=='runtime']
    for rel in paths:assert sha((CAND/rel).read_bytes())==candidate_hashes[rel]
    candidate_pipeline=json.loads((CAND/'00_SYSTEM/PIPELINE.json').read_bytes())
    spec={'revision':NAME,'states':{},'blobs':{},'output_inventories':{}}
    bindings=[]
    for label,payload in prior_states():
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            final=dict(payload)
            for rel in paths:
                final[rel]=merge(rel,payload.get(rel),root)
                ast.parse(final[rel], feature_version=(3,11))
            pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
            pipeline['shortcut_v4']['features']['core_evidence_route']=True
            pipeline['shortcut_v4']['core_route_contract']=candidate_pipeline['shortcut_v4']['core_route_contract']
            core='02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py'
            for entry in pipeline['engines'].values():
                rel=entry['manifest'];engine=json.loads(payload[rel])
                for path in engine['files']:engine['files'][path]=sha(final[path])
                engine['files'][core]=sha(final[core])
                final[rel]=encoded(engine);entry['sha256']=sha(final[rel])
            final['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
            module.verify_bindings(final)
            before=payload['CODE_MANIFEST.json'];patches={}
            for rel,raw in final.items():
                if rel=='CODE_MANIFEST.json' or raw==payload.get(rel):continue
                digest=sha(raw);spec['blobs'][digest]=base64.b64encode(raw).decode()
                patches[rel]={'before_sha256':sha(payload[rel]) if rel in payload else None,'after_sha256':digest}
            state={'label':label,'patches':patches}
            spec['states'][sha(before)]=state
            for rel,raw in payload.items():
                target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            _,_,changes,after=module.prepared(root,spec)
            spec['output_inventories'][sha(changes['CODE_MANIFEST.json'])]=label
            bindings.append({'basis':label,'before_inventory_sha256':sha(before),
                'after_inventory_sha256':sha(changes['CODE_MANIFEST.json']),
                'modified_paths':sorted(changes), 'runtime_hashes':{rel:sha(final[rel]) for rel in paths},
                'db_logging_disabled':json.loads(final['CODE_MANIFEST.json']).get('query_latency',{}).get('enabled') is False})
    compressed=gzip.compress(encoded(spec),compresslevel=9,mtime=0)
    (OUT/'PATCH_SPEC.json.gz').write_bytes(compressed)
    bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    bootstrap=("import base64,hashlib,json,sys,types,zlib\n"
        f"raw=zlib.decompress(base64.b64decode({packed!r}))\n"
        f"assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n"
        "bundle=json.loads(raw)\nmodule=types.ModuleType('shortcut_handoff')\n"
        "exec(compile(base64.b64decode(bundle['code']),'apply_shortcut.py','exec'),module.__dict__)\n"
        "try:raise SystemExit(module.main(bundle['spec'],sys.argv[1:]))\n"
        "except Exception as exc:\n"
        " print('CORE_SHORTCUT FAILED: '+str(exc),file=sys.stderr,flush=True)\n"
        " raise SystemExit(1)\n")
    run=("#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n"
        'task_root="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"\n'
        'task_logs="$task_root/TRANSFER/core-evidence-shortcut-r1/logs"\n'
        'if ! mkdir -p -- "$task_logs"; then\n'
        ' task_logs="${TMPDIR:-/tmp}/8-agent-core-shortcut-r1-$(id -u)"\n'
        ' mkdir -p -- "$task_logs"\nfi\n'
        'task_log="$task_logs/$(date -u +%Y%m%dT%H%M%S)-$$.log"\n'
        'exec > >(tee -a "$task_log") 2>&1\n'
        'trap \'task_exit=$?; printf "CORE_SHORTCUT_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"\' EXIT\n'
        'printf "LOG=%s\\n" "$task_log"\n'
        'if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; '
        'elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\n'
        'python3 - --root "$task_root" "$@" <<\'CORE_SHORTCUT_PY\'\n'+bootstrap+'CORE_SHORTCUT_PY\n')
    run_path=OUT/(NAME+'_RUN.txt');run_path.write_text(run)
    subprocess.run(['bash','-n',str(run_path)],check=True)
    source_binding={'evaluated_adr':'ADR-0683','freeze_sha256':sha((ADR/'design/freeze.json').read_bytes()),
        'baseline_release':'session-runtime-v6-20261007-r1','candidate_files':{rel:candidate_hashes[rel] for rel in paths},
        'merge':'exact known field code + baseline-to-evaluated-candidate delta; no field-time rehash/merge',
        'bases':bindings,'local_working_validation':json.loads((ADR/'working-validation/result.json').read_bytes())}
    (OUT/'SOURCE_BINDING.json').write_bytes(encoded(source_binding))
    manifest={'format':'8agent-core-source-patch/1','id':NAME,'files':[
        {'path':rel,'sha256':sha((OUT/rel).read_bytes()),'bytes':(OUT/rel).stat().st_size}
        for rel in ('apply_shortcut.py','PATCH_SPEC.json.gz','SOURCE_BINDING.json')],
        'base_inventory_count':len(bindings),'GENOS_deployed':False}
    (OUT/'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    archive=OUT/(NAME+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for rel in ('apply_shortcut.py','PATCH_SPEC.json.gz','SOURCE_BINDING.json','CODE_MANIFEST.json'):
            assert Path(rel).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'};z.write(OUT/rel,rel)
    handoff={'version':NAME,'created_at':datetime.now(timezone.utc).isoformat(),'working_root':str(ROOT),
        'working_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'code_zip_sha256':sha(archive.read_bytes()),'code_manifest_sha256':sha((OUT/'CODE_MANIFEST.json').read_bytes()),
        'run_txt_sha256':sha(run.encode()),'base_inventory_count':len(bindings),'prerequisite':'DB_LOG_ROLLBACK_R3',
        'local_active_pointer_sha256':sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()),
        'local_active_pointer_changed':False,'field_generation':None,'field_generation_manifest_sha256':None,
        'field_git_commit':None,'field_code_serving_revision':None,'genos_applied':False,'genos_deployed':False,
        'workflow_test':'NOT_RUN','email_status':'NOT_SENT'}
    (OUT/'HANDOFF.json').write_bytes(encoded(handoff))
    print(json.dumps({'version':NAME,'states':len(bindings),'zip_bytes':archive.stat().st_size,'txt_bytes':len(run.encode())}))


if __name__=='__main__':main()
