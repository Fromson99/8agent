"""Run the exact uploaded shell script against isolated Git checkouts."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
NAME='GENOS_BASIS_BATCH_20261020_R1'
BASE=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main92_cumulative_20261020_r1/code.zip'
TRACE=[]


def command(args,cwd,expected=0):
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    result=subprocess.run([str(a) for a in args],cwd=cwd,env=env,text=True,capture_output=True)
    TRACE.append({'args':[str(a) for a in args],'exit':result.returncode,'expected':expected,'output':result.stdout+result.stderr})
    if expected==0:
        assert result.returncode==0,TRACE[-1]
    else:assert result.returncode!=0,TRACE[-1]
    return result


def main():
    with tempfile.TemporaryDirectory(prefix='basis-delivery-') as temporary:
        root=Path(temporary);transfer=root/'actual-transfer';transfer.mkdir()
        checkout=root/'DEV';checkout.mkdir()
        with zipfile.ZipFile(BASE) as archive:archive.extractall(checkout)
        command(['git','init','-q',checkout],transfer)
        package=transfer/NAME
        command(['python3','-m','zipfile','-e',HERE/(NAME+'.zip'),package],transfer)
        script=package/(NAME+'_RUN.txt')
        call=lambda cmd,*args,expected=0:command(['bash',script,cmd,'--root',checkout,*args],transfer,expected)
        call('check')
        before={p.relative_to(checkout).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in checkout.rglob('*') if p.is_file() and '.git' not in p.parts}
        call('apply')
        call('apply')
        call('gate')
        call('install-status')
        # Status is read-only and works while a batch execution lock exists.
        runtime=root/'shared-runtime';job=runtime/'basis-batch/pilot-20261020-r1';job.mkdir(parents=True)
        (job/'STATE.json').write_text('{"status":"running","test":"synthetic"}')
        config=checkout/'00_SYSTEM/GENOS_SERVING_PATHS.json'
        config.write_text(json.dumps({'runtime':str(runtime),'generation':str(root/'generation')}))
        call('status')
        config.unlink()
        changed=checkout/'02_BACKEND/semantic_runtime/basis_links/grouping.py'
        raw=changed.read_bytes();changed.write_bytes(raw+b'\n# unexpected edit\n')
        call('gate',expected=1)
        call('rollback',expected=1)
        changed.write_bytes(raw)
        call('rollback')
        call('rollback')
        after={p.relative_to(checkout).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in checkout.rglob('*') if p.is_file() and '.git' not in p.parts}
        assert before==after,(set(before)^set(after))
        assert json.loads((job/'STATE.json').read_text())['status']=='running'
        call('apply',expected=1)
        # Actual interruption after first checkout write, then same TXT apply.
        second=transfer/(NAME+'-interrupt')
        with zipfile.ZipFile(HERE/(NAME+'.zip')) as archive:archive.extractall(second)
        spec=importlib.util.spec_from_file_location('delivery_interrupt',second/'runner.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        write=runner.write;once=[True]
        class Crash(BaseException):pass
        def interrupted(path,value):
            write(path,value)
            if Path(path).is_relative_to(checkout) and once[0]:
                once[0]=False;raise Crash()
        runner.write=interrupted
        try:runner.apply(checkout,runner.load())
        except Crash:pass
        else:raise AssertionError('Crash was not injected')
        command(['bash',second/(NAME+'_RUN.txt'),'apply','--root',checkout],transfer)
        command(['bash',second/(NAME+'_RUN.txt'),'gate','--root',checkout],transfer)
        command(['bash',second/(NAME+'_RUN.txt'),'rollback','--root',checkout],transfer)
        after={p.relative_to(checkout).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in checkout.rglob('*') if p.is_file() and '.git' not in p.parts}
        assert after==before
        # A changed package payload fails even before installation.
        payload=second/'payload/02_BACKEND/semantic_runtime/basis_links/grouping.py'
        payload.write_bytes(payload.read_bytes()+b'\n# tampered\n')
        command(['bash',second/(NAME+'_RUN.txt'),'check','--root',checkout],transfer,1)
        logs=list((transfer/'basis-batch-r1-logs').glob('*.log.exit'))
        assert logs and all(p.read_text().strip().isdigit() for p in logs)
    summary={'status':'PASS','shell_commands':len(TRACE),
             'intentional_nonzero':sum(r['expected']!=0 for r in TRACE),'interruption_recovered':True,
             'exact_rollback':True,'data_preserved':True,
             'zip_sha256':hashlib.sha256((HERE/(NAME+'.zip')).read_bytes()).hexdigest()}
    (HERE/'DELIVERY_VALIDATION.json').write_text(json.dumps(summary,indent=2)+'\n')
    import gzip
    with gzip.open(HERE/'DELIVERY_TRACE.json.gz','wt') as stream:json.dump(TRACE,stream,ensure_ascii=False)
    print(json.dumps(summary))


if __name__=='__main__':
    try:main()
    except BaseException:
        (HERE/'DELIVERY_FAILURE.json').write_text(json.dumps(TRACE,ensure_ascii=False,indent=2)+'\n')
        raise
