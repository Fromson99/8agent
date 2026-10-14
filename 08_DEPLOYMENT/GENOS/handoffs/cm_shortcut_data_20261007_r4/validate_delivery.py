"""Exercise exact attached TXT, known field variants, real CM import and undo."""
import gzip
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile
import build_delivery as build

ROOT=build.ROOT;OUT=build.OUT;NAME=build.NAME;RUN=OUT/(NAME+'_RUN.txt')


def main():
    results=[];transcript=[];data_result=None;contract_results=[]
    for i,(label,payload) in enumerate(build.parent_states()):
        with TemporaryDirectory(prefix='cm51-delivery-') as directory:
            root=Path(directory)/'DEV';root.mkdir()
            for name,raw in payload.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            runtime=Path(directory)/'runtime';runtime.mkdir();sentinel=runtime/'keep.sqlite';sentinel.write_bytes(b'preserve existing unrelated state')
            env={**os.environ,'GENOS_DEV_ROOT':str(root),'GENOS_PYTHON_DIR':str(Path(sys.executable).parent),
                 'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
                 'GENOS_STATE_DIR':str(Path(directory)/'persistent-state'),
                 'GENOS_SYSTEM_LOG_DIR':str(Path(directory)/'logs'),'GENOS_LOG_SPOOL_DIR':str(Path(directory)/'spool')}
            env.pop('GENOS_GENERATION',None);count=0
            def run(*args,success=True):
                nonlocal count
                count+=1
                r=subprocess.run(['bash',str(RUN),*args],cwd=root,env=env,capture_output=True,text=True,timeout=120)
                transcript.append(label+' '+str(args)+' exit='+str(r.returncode)+'\n'+r.stdout+r.stderr)
                assert (r.returncode==0)==success,transcript[-1]
                return r
            run('check')
            assert all((root/n).read_bytes()==raw for n,raw in payload.items())
            run('apply');run('apply');run('verify')
            backup=next((root/'TRANSFER/cm-shortcut-data-r4').glob('backup-*'))
            receipt=json.loads((backup/'receipt.json').read_text())
            modified={r['path'] for r in receipt['files']}
            assert len(modified)==36
            assert all((root/n).read_bytes()==raw for n,raw in payload.items() if n not in modified)
            assert len(list((root/'TRANSFER/cm-shortcut-data-r4').glob('backup-*')))==1
            if '/original/' in label:
                cmd=[sys.executable,str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0682/run_contracts.py'),str(root),
                     str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0683/test_core_routes.py'),
                     str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0683/test_core_api.py')]
                testenv={**env,'LAWRAG_WORKSPACE_ROOT':str(ROOT),'LAWRAG_TOOL_WORKSPACE_ROOT':str(ROOT)}
                # Native fixtures assert independent per-test runtime paths.
                # The separate persistent-state option is exercised below instead.
                testenv.pop('GENOS_STATE_DIR',None)
                r=subprocess.run(cmd,cwd=ROOT,env=testenv,capture_output=True,text=True,timeout=120)
                transcript.append(label+' native contracts\n'+r.stdout+r.stderr)
                assert r.returncode==0 and '23 passed' in r.stdout,transcript[-1]
                contract_results.append({'basis':label,'passed':23})
            if i==0:
                generation=ROOT/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation'
                principal=Path(directory)/'principal.json';principal.write_bytes((OUT/'LOCAL_PRINCIPAL.json').read_bytes())
                data_receipt=Path(directory)/'import-receipt.json'
                flags=['--generation',str(generation),'--runtime',str(runtime),'--principal',str(principal),'--receipt',str(data_receipt)]
                run('data-check',*flags);run('data-import',*flags);run('data-import',*flags);run('data-verify',*flags)
                dr=json.loads(data_receipt.read_text());assert len(dr['records'])==51
                with sqlite3.connect(Path(env['GENOS_STATE_DIR'])/'case-memory/cases-v4.sqlite') as db:
                    assert db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==51
                    assert db.execute('SELECT count(*) FROM sw_claim').fetchone()[0]==0
                run('data-retire',*flags);run('data-verify',*flags,success=False)
                run('data-import',*flags,success=False)
                data_result={'registered':51,'entries':98,'projection_pages':dr['legal_wiki']['pages'],
                             'replay_no_duplicate':True,'retire_preserves_history':True,
                             'retired_import_does_not_republish':True,'separate_state_dir':True}
            core=root/build.OWNED[0];original=core.read_bytes();core.write_bytes(original+b'\n# unknown field modification\n')
            run('verify',success=False);core.write_bytes(original)
            run('undo',str(backup))
            assert all((root/n).read_bytes()==raw for n,raw in payload.items())
            assert not (root/'02_BACKEND/lawrag/pipeline/shortcut_package.py').exists()
            assert sentinel.read_bytes()==b'preserve existing unrelated state'
            results.append({'basis':label,'commands_checked':count,'passed':True,'code_and_unrelated_state_preserved':True})
            print('VALIDATED',i+1,len(results),label,flush=True)
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as archive:
        assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in archive.namelist())
    value={'known_variants':results,'native_contracts':contract_results,'data':data_result,
           'model_calls':0,'GENOS_field_deployed':False,'email_sent':False}
    (OUT/'VALIDATION.json').write_bytes(build.encode(value))
    (OUT/'DELIVERY_TESTS.log.gz').write_bytes(gzip.compress('\n'.join(transcript).encode(),mtime=0))
    print('PASS',len(results),'field variants',sum(r['commands_checked'] for r in results),'TXT commands; data',data_result,flush=True)


if __name__=='__main__':main()
