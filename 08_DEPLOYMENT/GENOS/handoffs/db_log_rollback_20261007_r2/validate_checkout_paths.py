"""Reproduce the photographed R1 rejection and validate R2 against linked DEV."""
from tempfile import TemporaryDirectory
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
PARENT=OUT.with_name('db_log_rollback_20261007_r1')
NAME='GENOS_DB_LOG_ROLLBACK_20261007_R2'


def main():
    cases=[]
    transcripts=[]
    for source in ('HOME_DEV_SYMLINK','GENOS_DEV_LEGACY','EXPLICIT_ROOT'):
        with TemporaryDirectory(prefix='genos-linked-checkout-') as temporary:
            t=Path(temporary);actual=t/'shared/nfs-like/DEV';actual.mkdir(parents=True)
            folder=OUT.with_name('query_latency_20261007_r4')
            record=json.loads((folder/'HANDOFF.json').read_bytes())
            with zipfile.ZipFile(folder/(record['version']+'.zip')) as archive:
                archive.extractall(actual)
            original={str(p.relative_to(actual)):p.read_bytes() for p in actual.rglob('*') if p.is_file()}
            home=t/'home/genos';home.mkdir(parents=True)
            link=home/'DEV';link.symlink_to(actual,target_is_directory=True)
            transfer=actual/'TRANSFER';transfer.mkdir()
            env={**os.environ,'HOME':str(home),'GENOS_QUERY_LATENCY':'1',
                 'GENOS_PYTHON_DIR':str(Path(sys.executable).parent)}
            for key in ('GENOS_DEV','GENOS_DEV_ROOT','GENOS_GENERATION'):env.pop(key,None)
            extra=[]
            if source=='GENOS_DEV_LEGACY':env['GENOS_DEV']=str(link)
            if source=='EXPLICIT_ROOT':env['GENOS_DEV_ROOT']=str(link)
            def run(script,mode,*args,ok=True):
                result=subprocess.run(['bash',str(script),mode,*args],env=env,cwd=transfer,
                    capture_output=True,text=True,timeout=30)
                transcripts.append(source+' '+mode+'\n'+result.stdout+result.stderr)
                assert (result.returncode==0)==ok,transcripts[-1]
                return result
            r1=run(PARENT/'GENOS_DB_LOG_ROLLBACK_20261007_R1_RUN.txt','check',ok=False)
            assert 'Existing DEV checkout required' in r1.stdout+r1.stderr
            assert all((actual/n).read_bytes()==b for n,b in original.items())
            script=OUT/(NAME+'_RUN.txt')
            check=run(script,'check')
            assert '"is_symlink": true' in check.stdout
            assert 'CHECKOUT_RESOLVED='+str(actual) in check.stdout
            run(script,'apply');run(script,'apply');run(script,'verify')
            backup=next((actual/'TRANSFER/db-log-rollback-r2').glob('backup-*'))
            receipt=json.loads((backup/'receipt.json').read_bytes())
            assert receipt['root']==str(actual)
            run(script,'undo',str(backup))
            assert all((actual/n).read_bytes()==b for n,b in original.items())
            # A link inside the checkout is still rejected even with matching
            # bytes; only its explicitly selected outer DEV path is resolved.
            module=actual/'02_BACKEND/semantic_runtime/query_latency.py'
            raw=module.read_bytes();outside=t/'outside.py';outside.write_bytes(raw)
            module.unlink();module.symlink_to(outside)
            denied=run(script,'apply',ok=False)
            assert 'Symlink preserved' in denied.stdout+denied.stderr
            assert module.is_symlink() and outside.read_bytes()==raw
            assert (actual/'CODE_MANIFEST.json').read_bytes()==original['CODE_MANIFEST.json']
            cases.append({'selection':source,'r1_failure_reproduced':True,
                'r2_apply_repeat_verify_undo_passed':True,'internal_symlink_rejected':True,
                'physical_checkout_recorded':True,'operations':8})
    (OUT/'CHECKOUT_PATH_TESTS.log').write_text('\n'.join(transcripts))
    (OUT/'CHECKOUT_PATH_VALIDATION.json').write_text(json.dumps({
        'status':'PASS','cases':cases,'operations':24,'field_link_target':'NOT_PROVIDED'},indent=2)+'\n')
    print(json.dumps({'status':'PASS','checkout_path_operations':24}))


if __name__=='__main__':
    main()
