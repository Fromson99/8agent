"""Seal curated CM data plus a minimal importer delta on known core R1 code."""
import ast
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
PRIOR=OUT.with_name('core_evidence_shortcut_20261007_r1')
NAME='GENOS_CM_SHORTCUT_DATA_20261007_R1'
OWNED=['02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py',
       '02_BACKEND/lawrag/pipeline/unified_memory.py','02_BACKEND/lawrag/pipeline/shortcut_package.py']
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def parent_states():
    build=load(PRIOR/'build_delivery.py','prior_build')
    installer=load(PRIOR/'apply_shortcut.py','prior_install')
    spec=json.loads(gzip.decompress((PRIOR/'PATCH_SPEC.json.gz').read_bytes()))
    for label,payload in build.prior_states():
        with TemporaryDirectory() as directory:
            root=Path(directory)
            for name,raw in payload.items():
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            _,_,changes,_=installer.prepared(root,spec)
            yield label+'/core-shortcut-r1',{**payload,**changes}


def main():
    assert not (OUT/(NAME+'.zip')).exists(),'Use a new revision after sealing'
    code=(PRIOR/'apply_shortcut.py').read_text()
    code=code.replace('GENOS_CORE_EVIDENCE_SHORTCUT_20261007_R1',NAME)
    code=code.replace('core-evidence-shortcut-r1','cm-shortcut-data-r1')
    code=code.replace('core_evidence_shortcut','cm_curated_registration')
    code=code.replace('Known DB log rollback R3 inventory required','Known core shortcut R1 inventory required')
    code=code.replace("from semantic_runtime.legal_agent import core_evidence_route",
        "from semantic_runtime.legal_agent import core_evidence_route\nfrom lawrag.pipeline.shortcut_package import CONTRACT\nassert CONTRACT == 'curated-core-evidence-route-v1'")
    code=code.replace("if __name__ == '__main__':",(OUT/'data_dispatch.py').read_text()+"\n\nif __name__ == '__main__':")
    code=code.replace('raise SystemExit(main(spec))','raise SystemExit(dispatch(spec,sys.argv[1:]))')
    installer=OUT/'apply_cm.py';installer.write_text(code)
    ast.parse(code,feature_version=(3,11));module=load(installer,'cm_installer')
    data=(OUT/'CM51_SOURCE_PACKAGE.json').read_bytes()
    spec={'revision':NAME,'states':{},'blobs':{sha(data):base64.b64encode(data).decode()},
          'output_inventories':{},'data_package_sha256':sha(data)}
    bindings=[]
    for label,payload in parent_states():
        final=dict(payload)
        for path in OWNED:
            if path.endswith('unified_memory.py'):
                base=ROOT/'08_DEPLOYMENT/RELEASES/session-runtime-v6-20261007-r1/code'/path
                with TemporaryDirectory() as directory:
                    old=Path(directory)/'field';old.write_bytes(payload[path])
                    result=subprocess.run(['git','merge-file','-p',str(old),str(base),str(ROOT/path)],capture_output=True)
                    assert result.returncode==0,(path,result.stderr.decode());final[path]=result.stdout
            else:final[path]=(ROOT/path).read_bytes()
            ast.parse(final[path],feature_version=(3,11))
        config=json.loads(payload['00_SYSTEM/PIPELINE.json'])
        for entry in config['engines'].values():
            path=entry['manifest'];engine=json.loads(payload[path])
            for owned in OWNED:engine['files'][owned]=sha(final[owned])
            final[path]=encode(engine);entry['sha256']=sha(final[path])
        final['00_SYSTEM/PIPELINE.json']=encode(config)
        module.verify_bindings(final)
        patches={}
        for path,raw in final.items():
            if path=='CODE_MANIFEST.json' or raw==payload.get(path):continue
            digest=sha(raw);spec['blobs'][digest]=base64.b64encode(raw).decode()
            patches[path]={'before_sha256':sha(payload[path]) if path in payload else None,'after_sha256':digest}
        before=sha(payload['CODE_MANIFEST.json']);spec['states'][before]={'label':label,'patches':patches}
        with TemporaryDirectory() as directory:
            root=Path(directory)
            for path,raw in payload.items():
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            _,_,changes,after=module.prepared(root,spec)
        after_hash=sha(changes['CODE_MANIFEST.json']);spec['output_inventories'][after_hash]=label
        bindings.append({'basis':label,'before_inventory_sha256':before,'after_inventory_sha256':after_hash,
                         'modified_paths':sorted(changes),'code':{p:sha(final[p]) for p in OWNED}})
    packed_spec=gzip.compress(encode(spec),mtime=0)
    (OUT/'PATCH_SPEC.json.gz').write_bytes(packed_spec)
    bundle=encode({'code':base64.b64encode(code.encode()).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    bootstrap=('import base64,hashlib,json,sys,types,zlib\n'
        f'raw=zlib.decompress(base64.b64decode({packed!r}))\n'
        f'assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
        "bundle=json.loads(raw); module=types.ModuleType('cm_handoff')\n"
        "exec(compile(base64.b64decode(bundle['code']),'apply_cm.py','exec'),module.__dict__)\n"
        "try:raise SystemExit(module.dispatch(bundle['spec'],sys.argv[1:]))\n"
        "except Exception as exc:\n print('CM_DATA FAILED: '+str(exc),file=sys.stderr,flush=True)\n raise SystemExit(1)\n")
    run=('#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n'
        'task_root="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"\n'
        'task_logs="$task_root/TRANSFER/cm-shortcut-data-r1/logs"\n'
        'if ! mkdir -p -- "$task_logs"; then task_logs="${TMPDIR:-/tmp}/8-agent-cm-data-$(id -u)"; mkdir -p -- "$task_logs"; fi\n'
        'task_log="$task_logs/$(date -u +%Y%m%dT%H%M%S)-$$.log"\n'
        'exec > >(tee -a "$task_log") 2>&1\n'
        'trap \'task_exit=$?; printf "CM_DATA_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"\' EXIT\n'
        'printf "LOG=%s\\n" "$task_log"\n'
        'if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\n'
        'python3 - --root "$task_root" "$@" <<\'CM_DATA_PY\'\n'+bootstrap+'CM_DATA_PY\n')
    runpath=OUT/(NAME+'_RUN.txt');runpath.write_text(run)
    subprocess.run(['bash','-n',str(runpath)],check=True)
    binding={'kind':'USER_DIRECTED_DATA_REGISTRATION; NO_MODEL_EXPERIMENT','cases':51,'source_entries':98,
             'legal_claim_reuse':False,'requires_core_shortcut_r1':True,'bases':bindings,
             'local_MAIN_pointer':json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text()),
             'GENOS_apply_push_revision_workflow':'NOT_VERIFIED'}
    (OUT/'SOURCE_BINDING.json').write_bytes(encode(binding))
    with zipfile.ZipFile(OUT/(NAME+'.zip'),'x',zipfile.ZIP_DEFLATED) as z:
        for file in [installer,OUT/'PATCH_SPEC.json.gz',OUT/'SOURCE_BINDING.json',OUT/'CM51_SOURCE_PACKAGE.json']:
            z.write(file,file.name)
    sums=[]
    for file in [OUT/(NAME+'.zip'),runpath]:sums.append(sha(file.read_bytes())+'  '+file.name)
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n')
    print('Sealed CM51/98 package on',len(bindings),'known GENOS core R1 inventories')


if __name__=='__main__':main()
