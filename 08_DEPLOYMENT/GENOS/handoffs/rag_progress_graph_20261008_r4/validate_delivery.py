"""Validate the exact attached RUN, per-family code and untouched state."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
NAME='GENOS_RAG_PROGRESS_GRAPH_20261008_R4'
RUN=OUT/(NAME+'_RUN.txt')

def sha(raw):return hashlib.sha256(raw).hexdigest()

def main():
    spec=importlib.util.spec_from_file_location('display_build',OUT/'build_delivery.py')
    build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
    transcript=[];results=[];contracts=[];tested_families=set()
    selected=set()
    for label,before,_ in build.states():
        key=(label.split('/')[0],label.endswith('/applied-display-r3'))
        if key in selected:continue
        selected.add(key)
        with TemporaryDirectory(prefix='display-delivery-check-') as td:
            folder=Path(td);root=folder/'DEV';root.mkdir();build.write_payload(root,before)
            linked=folder/'linked-DEV';linked.symlink_to(root,target_is_directory=True)
            env={**os.environ,'GENOS_DEV_ROOT':str(linked),'GENOS_PYTHON_DIR':str(Path(sys.executable).parent),
                 'PYTHONPATH':str(root/'02_BACKEND')+':'+str(root)+':'+str(root/'08_DEPLOYMENT/GENOS'),
                 'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
                 'GENOS_SYSTEM_LOG_DIR':str(folder/'logs'),'GENOS_LOG_SPOOL_DIR':str(folder/'spool'),
                 'GENOS_SYSTEM_LOG_ENABLED':'1','GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'}
            for key in ('GENOS_GENERATION','GENOS_DISPLAY_CHILD','GENOS_LOG_RUN_ID'):env.pop(key,None)
            state=root/'90_RUNTIME/synthetic-state.sqlite';state.parent.mkdir();state.write_bytes(b'preserved-state')
            current=root/'CURRENT.json';current.write_bytes(b'{"synthetic": "preserved"}')
            count=0
            def run(*args,okay=True):
                nonlocal count
                result=subprocess.run(['bash',str(RUN),*args],cwd=root,env=env,capture_output=True,text=True,timeout=60)
                count+=1;transcript.append({'basis':label,'argv':list(args),'returncode':result.returncode,
                                           'stdout':result.stdout,'stderr':result.stderr})
                assert (result.returncode==0)==okay,result.stdout+result.stderr
                assert 'GENOS_SYSTEM_LOG_RESULT' in result.stdout,result.stdout+result.stderr
                return result
            run('check');run('apply');run('apply');run('verify')
            backup=next((root/'TRANSFER/rag-progress-graph-r4').glob('backup-*'))
            manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
            assert manifest['rag_display']['judgment_display_revision']=='judgment-knowledge-svg-20261008-r9'
            assert state.read_bytes()==b'preserved-state' and current.read_bytes()==b'{"synthetic": "preserved"}'
            with zipfile.ZipFile(backup/'APPLIED_CODE.zip') as z:
                assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
                assert all((root/n).read_bytes()==z.read(n) for n in z.namelist())
            family=label.split('/')[0]
            if family not in tested_families:
                # Existing clean-process tests select ROOT/.venv/bin/python.
                # Share only the local test interpreter; it is never shipped.
                (root/'.venv').symlink_to(ROOT/'.venv',target_is_directory=True)
                files=['test_main_workflow_display.py','test_genos_main_router_no_socket.py','test_rag_flow_svg.py',
                       'test_rag_key_progress.py','test_genos_sse_transport.py','test_genos_ignore.py']
                tests=root/'05_TESTS/CONTRACTS';tests.mkdir(parents=True,exist_ok=True)
                for name in files:(tests/name).write_bytes((ROOT/'05_TESTS/CONTRACTS'/name).read_bytes())
                result=subprocess.run([sys.executable,'-m','pytest','-q','--confcutdir='+str(tests),
                                       *[str(tests/name) for name in files]],cwd=root,env=env,capture_output=True,text=True,timeout=60)
                transcript.append({'basis':label,'contract_returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
                assert result.returncode==0,result.stdout+result.stderr
                contracts.append({'family':family,'output':result.stdout.splitlines()[-1]});tested_families.add(family)
            # R4 leaves R3's pipeline pins unchanged. Test restore refusal on
            # main_workflow.py, which every R4 recipe actually changes.
            target=root/'main_workflow.py';saved=target.read_bytes();target.write_bytes(saved+b'\n ')
            run('verify',okay=False);run('undo',str(backup),okay=False);assert target.read_bytes()==saved+b'\n '
            target.write_bytes(saved)
            old=(backup/'main_workflow.py').read_bytes();(backup/'main_workflow.py').write_bytes(old+b'\n ')
            run('undo',str(backup),okay=False);assert target.read_bytes()==saved
            (backup/'main_workflow.py').write_bytes(old);run('undo',str(backup))
            assert all((root/name).read_bytes()==raw for name,raw in before.items())
            doc='07_DOCS/REFERENCE/OPERATIONS/RAG_KEY_PROGRESS_SVG_20261007.md'
            if doc not in before: assert not (root/doc).exists()
            target.write_bytes(target.read_bytes()+b'\n ');drift=target.read_bytes()
            run('check',okay=False);run('apply',okay=False);assert target.read_bytes()==drift
            assert state.read_bytes()==b'preserved-state' and current.read_bytes()==b'{"synthetic": "preserved"}'
            stderr=''.join(p.read_text() for p in (folder/'logs').glob('**/*stderr.log'))
            assert 'Traceback' in stderr and 'CHECKOUT_DRIFT' in stderr
            results.append({'basis':label,'passed':True,'txt_commands':count,'runtime_and_current_preserved':True,
                            'raw_failures_recorded':True})
            print(label+' PASS',flush=True)
    with gzip.open(OUT/'DELIVERY_TESTS.json.gz','wt',encoding='utf-8') as f:json.dump(transcript,f,ensure_ascii=False)
    record={'variants':results,'txt_commands':sum(row['txt_commands'] for row in results),'contracts':contracts,
            'model_calls':0,'GENOS_deployed':False,'test_runtime_only_venv_link':True}
    record['run_txt_sha256']=sha(RUN.read_bytes())
    (OUT/'VALIDATION.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'states':len(results),'txt_commands':record['txt_commands'],'contracts':contracts},ensure_ascii=False))

if __name__=='__main__':main()
