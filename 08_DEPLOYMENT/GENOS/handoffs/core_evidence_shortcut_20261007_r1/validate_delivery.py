"""Exercise the attached TXT, installed feature, and guarded rollback."""
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
NAME='GENOS_CORE_EVIDENCE_SHORTCUT_20261007_R1'
RUN=OUT/(NAME+'_RUN.txt')


def main():
    loader=importlib.util.spec_from_file_location('build_shortcut',OUT/'build_delivery.py')
    build=importlib.util.module_from_spec(loader);loader.loader.exec_module(build)
    transcript=[];results=[];contracts=[]
    for label,before in build.prior_states():
        with TemporaryDirectory(prefix='core-shortcut-check-') as temporary:
            root=Path(temporary)/'DEV';root.mkdir()
            for name,raw in before.items():
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            linked=Path(temporary)/'linked-DEV';linked.symlink_to(root,target_is_directory=True)
            env={**os.environ,'GENOS_DEV_ROOT':str(linked),'GENOS_PYTHON_DIR':str(Path(sys.executable).parent),
                 'PYTHONPATH':str(root/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(root),
                 'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'GENOS_SYSTEM_LOG_DIR':str(Path(temporary)/'logs'),
                 'GENOS_LOG_SPOOL_DIR':str(Path(temporary)/'spool')}
            env.pop('GENOS_GENERATION',None)
            current=root/'CURRENT.json';current.write_bytes(b'{"generation":"preserve"}\n')
            runtime=root/'runtime/keep.sqlite';runtime.parent.mkdir();runtime.write_bytes(b'synthetic preserve')
            count=0
            def run(*args,ok=True):
                nonlocal count
                count+=1
                result=subprocess.run(['bash',str(RUN),*args],cwd=root,env=env,capture_output=True,text=True,timeout=90)
                transcript.append(label+' '+str(args)+' exit='+str(result.returncode)+'\n'+result.stdout+result.stderr)
                assert (result.returncode==0)==ok,transcript[-1]
                return result
            run('check')
            assert all((root/n).read_bytes()==b for n,b in before.items())
            run('apply');run('apply');run('verify')
            backup=next((root/'TRANSFER/core-evidence-shortcut-r1').glob('backup-*'))
            receipt=json.loads((backup/'receipt.json').read_bytes())
            assert receipt['state']=='VERIFIED'
            modified={row['path'] for row in receipt['files']}
            assert len(modified)==40 and '00_SYSTEM/PIPELINE.json' in modified
            assert all((root/n).read_bytes()==b for n,b in before.items() if n not in modified)
            assert len(list((root/'TRANSFER/core-evidence-shortcut-r1').glob('backup-*')))==1
            assert current.read_bytes()==b'{"generation":"preserve"}\n' and runtime.read_bytes()==b'synthetic preserve'
            # Run the primary HTTP/SQL contracts on each actual field source variant.
            if '/original/' in label:
                cmd=[sys.executable,str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0682/run_contracts.py'),str(root),
                     str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0683/test_core_routes.py'),
                     str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0683/test_core_api.py')]
                test_env={**env,'LAWRAG_WORKSPACE_ROOT':str(ROOT),'LAWRAG_TOOL_WORKSPACE_ROOT':str(ROOT)}
                result=subprocess.run(cmd,cwd=ROOT,env=test_env,capture_output=True,text=True,timeout=120)
                transcript.append(label+' primary contracts\n'+result.stdout+result.stderr)
                assert result.returncode==0,transcript[-1]
                assert '23 passed' in result.stdout
                contracts.append({'basis':label,'tests':23,'passed':23})
            subprocess.run(['git','init','-q',str(root)],check=True)
            manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
            subprocess.run(['git','-C',str(root),'add','-f','--','CODE_MANIFEST.json',
                            *[r['path'] for r in manifest['files']]],check=True)
            subprocess.run(['git','-C',str(root),'-c','user.name=Synthetic validation',
                            '-c','user.email=validation@example.invalid','commit','-qm','shortcut fixture'],check=True)
            gate_loader=importlib.util.spec_from_file_location('gate',root/'06_TOOLS/COMMANDS/genos_release_gate.py')
            gate=importlib.util.module_from_spec(gate_loader);gate_loader.loader.exec_module(gate)
            comparison=gate.compare_zip_to_checkout(backup/'APPLIED_CODE.zip',root)
            with zipfile.ZipFile(backup/'APPLIED_CODE.zip') as z:
                assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
            pipeline=root/'00_SYSTEM/PIPELINE.json';applied=pipeline.read_bytes()
            pipeline.write_bytes(applied+b'\n ')
            run('verify',ok=False);run('undo',str(backup),ok=False)
            assert pipeline.read_bytes()==applied+b'\n '
            pipeline.write_bytes(applied)
            saved=(backup/'00_SYSTEM/PIPELINE.json').read_bytes()
            (backup/'00_SYSTEM/PIPELINE.json').write_bytes(saved+b'\n ')
            run('undo',str(backup),ok=False);assert pipeline.read_bytes()==applied
            (backup/'00_SYSTEM/PIPELINE.json').write_bytes(saved)
            run('undo',str(backup))
            assert all((root/n).read_bytes()==b for n,b in before.items())
            assert not (root/'02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py').exists()
            old=pipeline.read_bytes();pipeline.write_bytes(old+b'\n ')
            run('check',ok=False);run('apply',ok=False)
            assert pipeline.read_bytes()==old+b'\n '
            results.append({'basis':label,'passed':True,'txt_commands':count,
                            'modified_files':len(modified),'same_checkout_code_comparison':comparison,
                            'runtime_and_current_preserved':True})
            print(label+' PASS',flush=True)
    raw='\n'.join(transcript).encode()
    (OUT/'DELIVERY_TESTS.log.gz').write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
    report={'status':'PASS','inventories':len(results),'txt_commands':sum(r['txt_commands'] for r in results),
            'primary_contracts_by_field_variant':contracts,'basis_results':results,'external_model_calls':0,
            'transcript_sha256':hashlib.sha256(raw).hexdigest(),'field_applied':False,'field_deployed':False}
    (OUT/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'PASS','inventories':len(results),'txt_commands':report['txt_commands'],
                     'primary_contract_runs':len(contracts)}))


if __name__=='__main__':main()
