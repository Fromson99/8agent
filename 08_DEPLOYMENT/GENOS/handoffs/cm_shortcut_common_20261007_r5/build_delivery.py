"""Seal common CM catalogue on prior R4 and its known predecessors."""
import ast
import base64
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
PRIOR=OUT.with_name('cm_shortcut_data_20261007_r4')
NAME='GENOS_CM_SHORTCUT_COMMON_20261007_R5'
OWNED=['02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py',
       '02_BACKEND/lawrag/pipeline/unified_memory.py','02_BACKEND/lawrag/pipeline/shortcut_package.py',
       '02_BACKEND/semantic_runtime/legal_agent/shortcut_repository.py',
       '02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py',
       '02_BACKEND/semantic_runtime/legal_agent/wiki_execution.py',
       '02_BACKEND/semantic_runtime/legal_agent/shortcut_cases.py']
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def materialize(root,payload):
    for name,raw in payload.items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)


def parent_states():
    build=load(PRIOR/'build_delivery.py','r4_build')
    installer=load(PRIOR/'apply_cm.py','r4_install')
    spec=json.loads(gzip.decompress((PRIOR/'PATCH_SPEC.json.gz').read_bytes()))
    for label,payload in build.parent_states():
        with TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory);materialize(root,payload)
            _,_,changes,_=installer.prepared(root,spec)
        r4={**payload,**changes}
        yield label,payload,r4
        yield label+'/cm-data-r4',r4,r4


def main():
    assert not (OUT/(NAME+'.zip')).exists(),'Use a new revision after sealing'
    code=(PRIOR/'apply_cm.py').read_text().split('\n\n"""Data commands')[0]
    code=code.replace('GENOS_CM_SHORTCUT_DATA_20261007_R4',NAME)
    code=code.replace('cm-shortcut-data-r4','cm-shortcut-common-r5')
    code=code.replace('Known core shortcut R1 inventory required','Known CM R4 or core/display inventory required')
    code=code.replace("'registry_pins_verified': True,","'registry_pins_verified': True, 'common_catalogue': True, 'consumer_user_team_registration': False,")
    code=code.replace('from lawrag.pipeline.shortcut_package import CONTRACT',
        'from lawrag.pipeline.shortcut_package import CONTRACT, COMMON_VISIBILITY, common_scope_id\nfrom semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository\nassert COMMON_VISIBILITY == \'COMMON_CATALOG\'\nassert hasattr(ShortcutRepository, \'knowledge_scopes\')')
    code=code.replace("assert c.pipeline['shortcut_v4']['features']['core_evidence_route'] is True",
        "assert c.pipeline['shortcut_v4']['features']['core_evidence_route'] is True\nassert c.pipeline['shortcut_v4']['common_catalogue']['consumer_user_team_registration'] is False")
    code += '\n\n'+(OUT/'data_dispatch.py').read_text()+"\n\nif __name__ == '__main__':\n    raise SystemExit('Use the embedded RUN TXT with its sealed specification')\n"
    installer=OUT/'apply_cm.py';installer.write_text(code)
    ast.parse(code,feature_version=(3,11));module=load(installer,'common_installer')
    previous=json.loads(gzip.decompress((OUT/'WORKING_BEFORE.json.gz').read_bytes()))
    base={p:base64.b64decode(v['base64']) for p,v in previous['files'].items()}
    working={p:(ROOT/p).read_bytes() for p in OWNED}
    data=(OUT/'CM51_SOURCE_PACKAGE.json').read_bytes()
    assert json.loads(data)['visibility']=='COMMON_CATALOG'
    spec={'revision':NAME,'states':{},'blobs':{sha(data):base64.b64encode(data).decode()},
          'output_inventories':{},'data_package_sha256':sha(data)}
    bindings=[]
    for label,payload,r4 in parent_states():
        final=dict(payload)
        for path in OWNED:
            with TemporaryDirectory() as directory:
                field=Path(directory)/'field';field.write_bytes(r4[path])
                prior=Path(directory)/'base';prior.write_bytes(base[path])
                current=Path(directory)/'working';current.write_bytes(working[path])
                result=subprocess.run(['git','merge-file','-p',str(field),str(prior),str(current)],capture_output=True)
                assert result.returncode==0,(label,path,result.stderr.decode(),result.stdout.decode())
                final[path]=result.stdout
            ast.parse(final[path],feature_version=(3,11))
        config=json.loads(r4['00_SYSTEM/PIPELINE.json'])
        config['shortcut_v4']['common_catalogue']=json.loads((ROOT/'00_SYSTEM/PIPELINE.json').read_text())['shortcut_v4']['common_catalogue']
        for entry in config['engines'].values():
            path=entry['manifest'];engine=json.loads(r4[path])
            for owned in OWNED:engine['files'][owned]=sha(final[owned])
            final[path]=encode(engine);entry['sha256']=sha(final[path])
        final['00_SYSTEM/PIPELINE.json']=encode(config)
        module.verify_bindings(final)
        patches={}
        for path,raw in final.items():
            if path=='CODE_MANIFEST.json' or raw==payload.get(path):continue
            digest=sha(raw);spec['blobs'][digest]=base64.b64encode(raw).decode()
            patches[path]={'before_sha256':sha(payload[path]) if path in payload else None,'after_sha256':digest}
        before=sha(payload['CODE_MANIFEST.json'])
        assert before not in spec['states'],label
        spec['states'][before]={'label':label,'patches':patches}
        with TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory);materialize(root,payload)
            _,_,changes,_=module.prepared(root,spec)
        after_hash=sha(changes['CODE_MANIFEST.json']);spec['output_inventories'][after_hash]=label
        bindings.append({'basis':label,'before_inventory_sha256':before,'after_inventory_sha256':after_hash,
                         'modified_paths':sorted(changes),'code':{p:sha(final[p]) for p in OWNED}})
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encode(spec),mtime=0))
    bundle=encode({'code':base64.b64encode(code.encode()).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    bootstrap=('import base64,hashlib,json,sys,types,zlib\n'
        f'raw=zlib.decompress(base64.b64decode({packed!r}))\n'
        f'assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
        "bundle=json.loads(raw); module=types.ModuleType('cm_common_handoff')\n"
        "exec(compile(base64.b64decode(bundle['code']),'apply_cm.py','exec'),module.__dict__)\n"
        "try:raise SystemExit(module.dispatch(bundle['spec'],sys.argv[1:]))\n"
        "except Exception as exc:\n print('CM_COMMON FAILED: '+str(exc),file=sys.stderr,flush=True)\n raise SystemExit(1)\n")
    run=('#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n'
        'task_root="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"\n'
        'task_logs="$task_root/TRANSFER/cm-shortcut-common-r5/logs"\n'
        'if ! mkdir -p -- "$task_logs"; then task_logs="${TMPDIR:-/tmp}/8-agent-cm-common-$(id -u)"; mkdir -p -- "$task_logs"; fi\n'
        'task_log="$task_logs/$(date -u +%Y%m%dT%H%M%S)-$$.log"\n'
        'exec > >(tee -a "$task_log") 2>&1\n'
        'trap \'task_exit=$?; printf "CM_COMMON_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"\' EXIT\n'
        'printf "LOG=%s\\n" "$task_log"\n'
        'if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\n'
        'python3 - --root "$task_root" "$@" <<\'CM_COMMON_PY\'\n'+bootstrap+'CM_COMMON_PY\n')
    runpath=OUT/(NAME+'_RUN.txt');runpath.write_text(run)
    subprocess.run(['bash','-n',str(runpath)],check=True)
    binding={'kind':'USER_DIRECTED_COMMON_DATA_REGISTRATION; NO_MODEL_EXPERIMENT','cases':51,'source_entries':98,
             'visibility':'COMMON_CATALOG','consumer_user_team_registration':False,
             'legal_claim_reuse':False,'bases':bindings,
             'working_before_sha256':sha((OUT/'WORKING_BEFORE.json.gz').read_bytes()),
             'working_code_sha256':{p:sha(v) for p,v in working.items()},
             'local_MAIN_pointer':json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text()),
             'GENOS_apply_push_revision_workflow':'NOT_VERIFIED'}
    (OUT/'SOURCE_BINDING.json').write_bytes(encode(binding))
    with zipfile.ZipFile(OUT/(NAME+'.zip'),'x',zipfile.ZIP_DEFLATED) as z:
        for file in [installer,OUT/'PATCH_SPEC.json.gz',OUT/'SOURCE_BINDING.json',OUT/'CM51_SOURCE_PACKAGE.json']:
            z.write(file,file.name)
    (OUT/'SHA256SUMS.txt').write_text(''.join(sha(f.read_bytes())+'  '+f.name+'\n' for f in [OUT/(NAME+'.zip'),runpath]))
    print('Sealed common CM51/98 package on',len(bindings),'known GENOS inventories')


if __name__=='__main__':main()
