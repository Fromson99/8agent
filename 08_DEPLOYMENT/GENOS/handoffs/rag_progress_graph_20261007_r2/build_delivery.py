"""Freeze the complete user progress/SVG display on known recent GENOS code.

Preserve each tested field family's cache, logging, source-route and session
code. Never import unrelated working-tree deltas or mutate source generations.
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
NAME='GENOS_RAG_PROGRESS_GRAPH_20261007_R2'
CORE=OUT.with_name('core_evidence_shortcut_20261007_r1')
SYSTEM=OUT.with_name('system_logging_20261007_r1')
DISPLAY_AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261007-rag-flow-svg-r8'
OWN=('02_BACKEND/semantic_runtime/progress.py','02_BACKEND/semantic_runtime/chat_adapter.py',
     '02_BACKEND/semantic_runtime/legal_agent/unified_rag.py','08_DEPLOYMENT/GENOS/stream_app.py',
     '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',
     '07_DOCS/REFERENCE/OPERATIONS/RAG_KEY_PROGRESS_SVG_20261007.md','genos_diagnostics.py','genos_log_runner.py')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def write_payload(root,payload):
    for name,raw in payload.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)

def states():
    core_builder=load('prior_core_builder',CORE/'build_delivery.py')
    core_apply=load('prior_core_apply',CORE/'apply_shortcut.py')
    core_spec=json.loads(gzip.decompress((CORE/'PATCH_SPEC.json.gz').read_bytes()))
    with redirect_stdout(io.StringIO()):
        for label,before in core_builder.prior_states():
            with TemporaryDirectory(prefix='display-prior-') as td:
                root=Path(td);write_payload(root,before)
                _,_,changes,_=core_apply.prepared(root,core_spec)
            after={**before,**changes}
            yield label,before,after
            yield label+'/core-evidence-shortcut-r1',after,after

def main():
    archive_path=OUT/(NAME+'.zip')
    if archive_path.exists():raise ValueError('Frozen output exists; use a new revision')
    apply=load('display_installer',OUT/'apply_display.py')
    owned={name:(ROOT/name).read_bytes() for name in OWN}
    system_record=json.loads((SYSTEM/'HANDOFF.json').read_bytes())
    system_zip=SYSTEM/(system_record['version']+'.zip')
    assert sha(system_zip.read_bytes())==system_record['code_zip_sha256']
    with zipfile.ZipFile(system_zip) as verified:
        for name in ('genos_diagnostics.py','genos_log_runner.py'):owned[name]=verified.read(name)
    for name,filename in [('02_BACKEND/semantic_runtime/chat_adapter.py','chat_adapter.py.gz'),
                          ('08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','genos_rag_chat.py.gz')]:
        assert owned[name]==gzip.decompress((DISPLAY_AUDIT/filename).read_bytes()),'Unverified display drift: '+name
    spec={'revision':NAME,'states':{},'blobs':{},'output_inventories':{}}
    bindings=[];canonical=None
    for label,before,core_after in states():
        final={**core_after,**owned}
        # unified_rag is also owned by the shortcut work. Preserve the exact
        # field variant and apply only this display task's re-entry event.
        base=core_after['02_BACKEND/semantic_runtime/legal_agent/unified_rag.py']
        old=b'        payload=super().stage(stage,state,parts,utterance,format)\n'
        new=(b'        from .corrected_memory import Reenter\n'
             b'        try:\n            payload=super().stage(stage,state,parts,utterance,format)\n'
             b'        except Reenter as recovery:\n'
             b"            self.s.work.event('CASE_STAGE_REENTRY', {'from_stage':stage,'stage':recovery.stage,\n"
             b"                'gaps':recovery.payload.get('gaps',[]),'reason':recovery.reason})\n"
             b'            raise\n')
        if b'CASE_STAGE_REENTRY' not in base:
            assert base.count(old)==1;final['02_BACKEND/semantic_runtime/legal_agent/unified_rag.py']=base.replace(old,new)
        else:final['02_BACKEND/semantic_runtime/legal_agent/unified_rag.py']=base
        changed={name for name,raw in final.items() if name!='CODE_MANIFEST.json' and raw!=before.get(name)}
        pipeline=json.loads(core_after['00_SYSTEM/PIPELINE.json'])
        for entry in pipeline['engines'].values():
            name=entry['manifest'];engine=json.loads(core_after[name])
            for target in set(engine['files']) & changed:engine['files'][target]=sha(final[target])
            raw=encoded(engine)
            if raw!=core_after[name]:final[name]=raw
            entry['sha256']=sha(final[name])
        final['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
        apply.verify_bindings(final)
        for name,raw in final.items():
            if name.endswith('.py'):ast.parse(raw,feature_version=(3,10) if '/workflow/' in name else (3,11))
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
        patches={}
        for name,raw in final.items():
            if name=='CODE_MANIFEST.json' or raw==before.get(name):continue
            value_hash=sha(raw);spec['blobs'][value_hash]=base64.b64encode(raw).decode()
            patches[name]={'before_sha256':sha(before[name]) if name in before else None,'after_sha256':value_hash}
        before_hash=sha(before['CODE_MANIFEST.json']);spec['states'][before_hash]={'label':label,'patches':patches}
        with TemporaryDirectory(prefix='display-build-') as td:
            root=Path(td);write_payload(root,before)
            with redirect_stdout(io.StringIO()):_,_,changes,after_manifest=apply.prepared(root,spec)
        after={**before,**changes};after_hash=sha(after['CODE_MANIFEST.json'])
        spec['output_inventories'][after_hash]=label
        assert after_manifest.get('query_latency',{}).get('enabled') is False
        assert '02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py' in after
        # No cache, ranking, source, raw logging or identity module is replaced
        # by a different family. Changes outside the display/core closure fail.
        preserve=['02_BACKEND/semantic_runtime/query_latency.py','02_BACKEND/semantic_runtime/unit_fulltext.py',
                  '02_BACKEND/semantic_runtime/fulltext.py','02_BACKEND/semantic_runtime/term_index.py',
                  '02_BACKEND/semantic_runtime/resident_data.py','service.py','main.py']
        assert all(after.get(p)==core_after.get(p) for p in preserve)
        bindings.append({'basis':label,'before_inventory_sha256':before_hash,'after_inventory_sha256':after_hash,
                         'modified_paths':sorted(changes),'preserved_family_files':{p:sha(after[p]) for p in preserve if p in after},
                         'display_files':{p:sha(after[p]) for p in OWN}})
        if label=='GENOS_SYSTEM_LOGGING_20261007_R1/original/db-log-rollback-r3/core-evidence-shortcut-r1':canonical=after
    assert canonical and len(spec['states'])==18
    code=(OUT/'apply_display.py').read_bytes();diagnostics=canonical['genos_diagnostics.py'];runner=canonical['genos_log_runner.py']
    bootstrap_module=load('logging_embed',SYSTEM/'build_delivery.py')
    bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    python=('import base64,hashlib,json,os,sys,types,zlib\nfrom pathlib import Path\n'
        +bootstrap_module.embedded_module('genos_diagnostics',diagnostics)
        +bootstrap_module.embedded_module('genos_log_runner',runner)
        +f"raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n"
        +"bundle=json.loads(raw)\nmodule=types.ModuleType('rag_display_handoff')\n"
        +"exec(compile(base64.b64decode(bundle['code']),'apply_display.py','exec'),module.__dict__)\n"
        +"def command(argv):\n"
        +" try:return module.main(bundle['spec'],argv)\n"
        +" except Exception:\n  import traceback;traceback.print_exc();return 1\n"
        +"if sys.argv[1:2]==['__child__']:\n raise SystemExit(command(sys.argv[2:]))\n"
        +f"os.environ.setdefault('GENOS_SYSTEM_LOG_DIR','/nfs-root/diamo/8-agent/logs/system')\n"
        +"os.environ.setdefault('GENOS_LOG_RUN_ID','display-'+sys.modules['genos_diagnostics'].uuid.uuid4().hex[:16])\n"
        +f"self_source=Path(sys.argv[1]).read_bytes()\n"
        +"raise SystemExit(sys.modules['genos_log_runner'].main(['--phase','display-deploy','--','bash',sys.argv[1],*sys.argv[2:]],child_env={'GENOS_DISPLAY_CHILD':'1'}))\n")
    # genos_log_runner.main has no child_env argument. Use an explicit inherited
    # flag; the child executes the same checked bootstrap without wrapping twice.
    python=python.replace("if sys.argv[1:2]==['__child__']:\n raise SystemExit(command(sys.argv[2:]))\n",
        "if os.environ.get('GENOS_DISPLAY_CHILD')=='1':\n raise SystemExit(command(['--root',os.environ['GENOS_DISPLAY_DEV'],*sys.argv[2:]]))\n")
    python=python.replace("self_source=Path(sys.argv[1]).read_bytes()\n", "os.environ['GENOS_DISPLAY_CHILD']='1'\n")
    python=python.replace(",child_env={'GENOS_DISPLAY_CHILD':'1'}",'')
    run=("#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n"
        'export GENOS_DISPLAY_DEV="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"\n'
        'if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; '
        'elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\n'
        'python3 - "${BASH_SOURCE[0]}" "$@" <<\'RAG_DISPLAY_PY\'\n'+python+'RAG_DISPLAY_PY\n')
    workflow=('import base64,hashlib,os,sys,types,zlib\nfrom pathlib import Path\n'
              +bootstrap_module.embedded_module('genos_diagnostics',diagnostics)
              +owned['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'].decode())
    ast.parse(python,feature_version=(3,11));ast.parse(workflow,feature_version=(3,10))
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),compresslevel=9,mtime=0))
    (OUT/'SOURCE_BINDING.json').write_bytes(encoded({'variants':bindings,'canonical':
        'GENOS_SYSTEM_LOGGING_20261007_R1 + DB_LOG_ROLLBACK_R3 + CORE_EVIDENCE_SHORTCUT_R1 + RAG_DISPLAY_R8',
        'source_display_audit':str(DISPLAY_AUDIT.relative_to(ROOT))}))
    (OUT/'CODE_MANIFEST.json').write_bytes(canonical['CODE_MANIFEST.json'])
    with zipfile.ZipFile(archive_path,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(canonical.items()):z.writestr(name,raw)
    (OUT/(NAME+'_RUN.txt')).write_text(run)
    (OUT/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_text(workflow)
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    with zipfile.ZipFile(archive_path) as z:
        assert set(z.namelist())==set(canonical)
        assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
    pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    record={'version':NAME,'created_at':datetime.now(timezone.utc).isoformat(),'working_root':str(ROOT),
            'working_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'code_zip_sha256':sha(archive_path.read_bytes()),'code_manifest_sha256':sha(canonical['CODE_MANIFEST.json']),
            'code_files':len(canonical)-1,'known_predecessor_inventories':len(spec['states']),
            'run_txt_sha256':sha(run.encode()),'workflow_txt_sha256':sha(workflow.encode()),
            'display_revision':'judgment-knowledge-svg-20261007-r8',
            'progress_revision':'rag-key-progress-20261007-r1','local_active_pointer_sha256':sha(pointer.read_bytes()),
            'local_active_pointer_changed':False,'field_generation':None,'field_generation_manifest_sha256':None,
            'field_git_commit':None,'field_code_serving_revision':None,'genos_applied':False,
            'genos_deployed':False,'workflow_test':'NOT_RUN','email_status':'NOT_SENT'}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print(json.dumps({'zip':str(archive_path),'files':record['code_files'],'variants':len(bindings),
                      'zip_bytes':archive_path.stat().st_size,'run_bytes':len(run.encode())}))

if __name__=='__main__':main()
