"""Seal a display-only R9/concise-progress overlay on verified field inventories.

Original full code remains shared in previous hash-bound archives. CM/operator
generation bindings and budget fragments are preserved, never reinstalled.
"""
import ast
import base64
from contextlib import redirect_stdout
from datetime import datetime, timezone
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
PRIOR=OUT.with_name('rag_progress_graph_20261007_r2')
CM=OUT.with_name('cm_shortcut_oneclick_20261008_r14')
CM15=OUT.with_name('cm_shortcut_oneclick_20261008_r15')
SYSTEM=OUT.with_name('system_logging_20261007_r1')
NAME='GENOS_RAG_PROGRESS_GRAPH_20261008_R3'
OWN=('02_BACKEND/semantic_runtime/progress.py','02_BACKEND/semantic_runtime/chat_adapter.py',
     '08_DEPLOYMENT/GENOS/stream_app.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',
     '07_DOCS/REFERENCE/OPERATIONS/RAG_KEY_PROGRESS_SVG_20261007.md',
     'genos_diagnostics.py','genos_log_runner.py')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def inventory_signature(pins):return sha(json.dumps(pins,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def write_payload(root,payload):
    for name,raw in payload.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)


def source_material():
    """Recover immutable code bytes by hash; store no duplicate source cache."""
    catalogue={};bases={};cm=json.loads(gzip.decompress((CM/'PATCH_SPEC.json.gz').read_bytes()))
    def collect(raw):catalogue.setdefault(sha(raw),raw)
    for folder in (OUT.with_name('query_latency_20261007_r3'),OUT.with_name('query_latency_20261007_r4'),SYSTEM,PRIOR):
        record=json.loads((folder/'HANDOFF.json').read_bytes());archive=folder/(record['version']+'.zip')
        assert sha(archive.read_bytes())==record['code_zip_sha256']
        with zipfile.ZipFile(archive) as z:
            payload={name:z.read(name) for name in z.namelist()}
            for raw in payload.values():collect(raw)
    nfs=OUT.with_name('data_transfer_list_20261007_r1')/'CODE_PAYLOAD.zip'
    with zipfile.ZipFile(nfs) as z:
        for name in z.namelist():collect(z.read(name))
    for folder in ('core_evidence_shortcut_20261007_r1','rag_progress_graph_20261007_r2',
                   'cm_shortcut_data_20261007_r4','cm_shortcut_common_20261007_r6',
                   'cm_shortcut_oneclick_20261007_r8','cm_shortcut_oneclick_20261007_r10',
                   'cm_shortcut_oneclick_20261007_r11','cm_shortcut_oneclick_20261007_r12',
                   'cm_shortcut_oneclick_20261008_r13','cm_shortcut_oneclick_20261008_r14'):
        frozen=json.loads(gzip.decompress((OUT.with_name(folder)/'PATCH_SPEC.json.gz').read_bytes()))
        for pin,value in frozen['blobs'].items():
            raw=base64.b64decode(value);assert sha(raw)==pin;collect(raw)
    prior_build=load('r2_build',PRIOR/'build_delivery.py')
    prior_install=load('r2_install',PRIOR/'apply_display.py')
    prior_spec=json.loads(gzip.decompress((PRIOR/'PATCH_SPEC.json.gz').read_bytes()))
    with redirect_stdout(io.StringIO()):
        for label,before,_ in prior_build.states():
            with TemporaryDirectory(prefix='r3-prior-') as td:
                root=Path(td);write_payload(root,before)
                _,_,changes,_=prior_install.prepared(root,prior_spec)
            for suffix,payload in (('',before),('/display-r2',{**before,**changes})):
                pins={name:sha(raw) for name,raw in payload.items() if name!='CODE_MANIFEST.json'}
                key=inventory_signature(pins);bases.setdefault(key,{'label':label+suffix,'pins':pins,'manifest':payload['CODE_MANIFEST.json']})
                for raw in payload.values():collect(raw)
    versions={'GENOS_CM_ONECLICK_20261008_R14':{rid:recipe['after'] for rid,recipe in cm['recipes'].items()}}
    for ver in ('r8','r10','r11','r12','r13'):
        day='20261008' if ver=='r13' else '20261007'
        versions['GENOS_CM_ONECLICK_'+day+'_'+ver.upper()]=cm[ver+'_inventories']
    binding={'schema_version':'genos-serving-paths-v1','selection':'operator-fixed',**cm['paths'],
             'generation_manifest_sha256':'0'*64,'source':'offline code-inventory display validation'}
    config=encoded(binding);collect(config)
    for version,mapping in versions.items():
        for rid,pin in mapping.items():
            pins=cm['inventories'][pin];key=inventory_signature(pins)
            if key in bases:continue
            missing={name:digest for name,digest in pins.items() if digest not in catalogue}
            assert not missing,('Unrecovered frozen CM bytes',version,missing)
            manifest={'schema_version':'genos-code-ship-v1','id':version,
                      'files':[{'path':n,'sha256':p,'bytes':len(catalogue[p])} for n,p in sorted(pins.items())],
                      'required_files':[],
                      'cm_oneclick':{'revision':version,'recipe_id':rid,'generation_manifest_sha256':'0'*64}}
            manifest['files'].append({'path':'00_SYSTEM/GENOS_SERVING_PATHS.json','sha256':sha(config),'bytes':len(config)})
            bases[key]={'label':version+'/'+cm['recipes'].get(rid,{}).get('label',rid),
                        'pins':pins,'manifest':encoded(manifest),'config':config}
    # R15 has the same CM recipe code as R14, with the authenticated R10
    # error-log transformation preserved. Freeze those complete outputs too;
    # do not reverse or rewrite the field's error-log source or receipts.
    spec15=json.loads(gzip.decompress((CM15/'PATCH_SPEC.json.gz').read_bytes()))
    hand15=json.loads((CM15/'HANDOFF.json').read_bytes())
    overlay=spec15['full_error_logging_overlay']
    library=base64.b64decode(overlay['library'],validate=True)
    assert sha(library)==overlay['library_sha256']==hand15['full_error_library_sha256']
    assert sha(encoded(overlay['spec']))==overlay['spec_sha256']==hand15['full_error_spec_sha256']
    namespace={};exec(compile(library,'sealed_full_error_installer.py','exec'),namespace)
    for state in list(bases.values()):
        if not state['label'].startswith('GENOS_CM_ONECLICK_20261008_R14/'):continue
        payload={n:catalogue[p] for n,p in state['pins'].items()};final=dict(payload)
        for name,operations in overlay['spec']['files'].items():final[name]=namespace['transform'](payload[name],operations)
        affected={n for n in final if final[n]!=payload[n]}
        pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
        if affected:
            for entry in pipeline['engines'].values():
                name=entry['manifest'];engine=json.loads(payload[name])
                if set(engine['files'])&affected:
                    for target in set(engine['files'])&affected:engine['files'][target]=sha(final[target])
                    final[name]=encoded(engine)
                entry['sha256']=sha(final[name])
            final['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
        with redirect_stdout(io.StringIO()):
            namespace['verify_bindings'](final);namespace['local_verification'](final,overlay['spec'])
        pins={n:sha(v) for n,v in final.items()};key=inventory_signature(pins)
        if key in bases:continue
        for raw in final.values():collect(raw)
        manifest=json.loads(state['manifest'])
        for row in manifest['files']:
            if row['path'] in final:row.update(sha256=sha(final[row['path']]),bytes=len(final[row['path']]))
        manifest['id']='GENOS_CM_ONECLICK_20261008_R15'
        manifest['cm_oneclick']['revision']='GENOS_CM_ONECLICK_20261008_R15'
        manifest['full_error_logging']={'revision':overlay['spec']['revision'],
            'fixture':'offline exact R15 recipe + frozen R10 transform; no field receipt claim'}
        bases[key]={'label':'GENOS_CM_ONECLICK_20261008_R15/full-error/'+state['label'].split('/',1)[1],
                    'pins':pins,'manifest':encoded(manifest),'config':state['config']}
    return catalogue,bases,cm


def states():
    catalogue,bases,_=source_material()
    for state in bases.values():
        payload={name:catalogue[pin] for name,pin in state['pins'].items()}
        payload['CODE_MANIFEST.json']=state['manifest']
        if state.get('config'):payload['00_SYSTEM/GENOS_SERVING_PATHS.json']=state['config']
        yield state['label'],payload,None


def main():
    if (OUT/(NAME+'.zip')).exists():raise ValueError('Sealed delivery exists; use a new revision')
    apply=load('r3_installer',OUT/'apply_display.py')
    catalogue,bases,cm=source_material()
    owned={name:(ROOT/name).read_bytes() for name in OWN}
    record=json.loads((SYSTEM/'HANDOFF.json').read_bytes())
    with zipfile.ZipFile(SYSTEM/(record['version']+'.zip')) as z:
        for name in ('genos_diagnostics.py','genos_log_runner.py'):owned[name]=z.read(name)
    r9=json.loads((ROOT/'09_ARTIFACTS/AUDITS/20261008-rag-flow-svg-r9/working-binding.json').read_bytes())
    for name in ('02_BACKEND/semantic_runtime/chat_adapter.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'):
        assert sha(owned[name])==r9['source_sha256'][name],'Unverified R9 source drift'
    spec={'revision':NAME,'signatures':{},'blobs':{},'budget_policy':cm['investigation_budget_overlay']['spec']}
    bindings=[]
    for key,state in bases.items():
        before={name:catalogue[pin] for name,pin in state['pins'].items()}
        before['CODE_MANIFEST.json']=state['manifest']
        if state.get('config'):before[apply.CONFIG]=state['config']
        final={**before,**owned}
        base=before['02_BACKEND/semantic_runtime/legal_agent/unified_rag.py']
        old=b'        payload=super().stage(stage,state,parts,utterance,format)\n'
        replacement=(b'        from .corrected_memory import Reenter\n'
                     b'        try:\n            payload=super().stage(stage,state,parts,utterance,format)\n'
                     b'        except Reenter as recovery:\n'
                     b"            self.s.work.event('CASE_STAGE_REENTRY', {'from_stage':stage,'stage':recovery.stage,\n"
                     b"                'gaps':recovery.payload.get('gaps',[]),'reason':recovery.reason})\n"
                     b'            raise\n')
        if b'CASE_STAGE_REENTRY' not in base:
            assert base.count(old)==1;final['02_BACKEND/semantic_runtime/legal_agent/unified_rag.py']=base.replace(old,replacement)
        changed={n for n,v in final.items() if n!='CODE_MANIFEST.json' and v!=before.get(n)}
        pipeline=json.loads(before['00_SYSTEM/PIPELINE.json'])
        for entry in pipeline['engines'].values():
            name=entry['manifest'];engine=json.loads(before[name])
            for target in set(engine['files']) & changed:engine['files'][target]=sha(final[target])
            final[name]=encoded(engine);entry['sha256']=sha(final[name])
        final['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
        apply.verify_bindings(final)
        if state['label'].startswith('GENOS_CM_ONECLICK_20261008_R15/'):
            logging=load('frozen_full_error_check',OUT.with_name('full_error_logging_20261007_r10')/'INSTALL.py')
            policy=json.loads((OUT.with_name('full_error_logging_20261007_r10')/'PATCH_SPEC.json').read_bytes())
            with redirect_stdout(io.StringIO()):logging.local_verification(final,policy)
        for name in OWN:
            if name.endswith('.py'):ast.parse(final[name],feature_version=(3,10) if '/workflow/' in name else (3,11))
        patches={}
        engine_paths={entry['manifest'] for entry in pipeline['engines'].values()}
        for name,raw in final.items():
            if name=='CODE_MANIFEST.json' or raw==before.get(name):continue
            if name=='00_SYSTEM/PIPELINE.json' or name in engine_paths:continue
            pin=sha(raw);spec['blobs'][pin]=base64.b64encode(raw).decode()
            patches[name]={'before_sha256':sha(before[name]) if name in before else None,'after_sha256':pin}
        after_pins=apply.normalized_inventory(final,json.loads(state['manifest']),spec)
        output=inventory_signature(after_pins)
        spec['signatures'][key]={'label':state['label'],'patches':patches,'output_signature':output}
        assert apply.signature(before,json.loads(state['manifest']),spec)==key
        preserved=[name for name in state['pins'] if name not in patches and name!='CODE_MANIFEST.json']
        bindings.append({'basis':state['label'],'before_signature':key,'after_signature':output,
                         'modified_paths':sorted(patches),'preserved_files':len(preserved),
                         'service_sha256':sha(before['service.py']),
                         'cm_package_sha256':sha(before['02_BACKEND/lawrag/pipeline/shortcut_package.py']) if '02_BACKEND/lawrag/pipeline/shortcut_package.py' in before else None})
    code=(OUT/'apply_display.py').read_bytes();ast.parse(code,feature_version=(3,11))
    bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    embed=load('system_embed',SYSTEM/'build_delivery.py')
    python=('import base64,hashlib,json,os,sys,types,zlib\nfrom pathlib import Path\n'
            +embed.embedded_module('genos_diagnostics',owned['genos_diagnostics.py'])
            +embed.embedded_module('genos_log_runner',owned['genos_log_runner.py'])
            +f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
            +"bundle=json.loads(raw);module=types.ModuleType('r3_display_installer')\n"
            +"exec(compile(base64.b64decode(bundle['code']),'apply_display.py','exec'),module.__dict__)\n"
            +"if os.environ.get('GENOS_DISPLAY_CHILD')=='1':\n"
            +" raise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_DISPLAY_DEV'],*sys.argv[2:]]))\n"
            +"os.environ['GENOS_DISPLAY_CHILD']='1'\n"
            +"os.environ.setdefault('GENOS_SYSTEM_LOG_DIR','/nfs-root/diamo/8-agent/logs/system')\n"
            +"os.environ.setdefault('GENOS_LOG_RUN_ID','display-r3-'+sys.modules['genos_diagnostics'].uuid.uuid4().hex[:16])\n"
            +"raise SystemExit(sys.modules['genos_log_runner'].main(['--phase','display-r3-deploy','--','bash',sys.argv[1],*sys.argv[2:]]))\n")
    run='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export GENOS_DISPLAY_DEV="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"
task_logs="$GENOS_DISPLAY_DEV/TRANSFER/rag-progress-graph-r3/bootstrap-logs"
if ! mkdir -p -- "$task_logs"; then task_logs="${TMPDIR:-/tmp}/8-agent-display-r3-$(id -u)"; mkdir -p -- "$task_logs"; fi
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
if [[ "${GENOS_DISPLAY_CHILD:-0}" != 1 ]]; then
    export GENOS_DISPLAY_BOOTSTRAP_LOG="$task_log"
    exec > >(tee -a "$task_log") 2>&1
else
    task_log="$GENOS_DISPLAY_BOOTSTRAP_LOG"
fi
trap 'task_exit=$?; printf "DISPLAY_R3_EXIT=%s BOOTSTRAP_LOG=%s\\n" "$task_exit" "$task_log"' EXIT
printf 'DISPLAY_R3_BOOTSTRAP_LOG=%s\\n' "$task_log"
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
if [[ $# -eq 0 ]]; then set -- apply; fi
python3 - "${BASH_SOURCE[0]}" "$@" <<'RAG_DISPLAY_PY'
'''+python+'RAG_DISPLAY_PY\n'
    workflow=('import base64,hashlib,os,sys,types,zlib\nfrom pathlib import Path\n'
              +embed.embedded_module('genos_diagnostics',owned['genos_diagnostics.py'])
              +owned['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'].decode())
    ast.parse(python,feature_version=(3,11));ast.parse(workflow,feature_version=(3,10))
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
    (OUT/(NAME+'_RUN.txt')).write_text(run)
    (OUT/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_text(workflow)
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    for name,raw in owned.items():
        path=OUT/'payload'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (OUT/'SOURCE_BINDING.json').write_bytes(encoded({'variants':bindings,'source_display_audit':'09_ARTIFACTS/AUDITS/20261008-rag-flow-svg-r9',
        'cm_predecessor':str(CM.relative_to(ROOT)),'change_scope':'display/progress only; preserve cache, CM, service, budgets, data, settings'}))
    pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    record={'version':NAME,'created_at':datetime.now(timezone.utc).isoformat(),'working_root':str(ROOT),
            'working_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'known_code_signatures':len(bindings),'run_txt_sha256':sha(run.encode()),'workflow_txt_sha256':sha(workflow.encode()),
            'display_revision':'judgment-knowledge-svg-20261008-r9','progress_revision':'rag-key-progress-20261007-r1',
            'source_sha256':{n:sha(v) for n,v in owned.items()},'local_active_pointer_sha256':sha(pointer.read_bytes()),
            'local_active_pointer_changed':False,'field_generation':None,'field_generation_manifest_sha256':None,
            'field_git_commit':None,'field_code_serving_revision':None,'genos_applied':False,
            'genos_deployed':False,'workflow_test':'NOT_RUN','email_status':'NOT_SENT'}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print(json.dumps({'states':len(bindings),'spec_bytes':(OUT/'PATCH_SPEC.json.gz').stat().st_size,'run_bytes':len(run.encode())}))


if __name__=='__main__':main()
