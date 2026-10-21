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
NAME='GENOS_BASIS_BATCH_20261020_R3'
BASE=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main92_cumulative_20261020_r1/code.zip'
TRACE=[]
TEST_ENV={}


def command(args,cwd,expected=0):
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1',**TEST_ENV}
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
        # Both the HOME parent and DEV itself are ordinary codespace symlinks.
        physical_home=root/'physical-home';physical_home.mkdir()
        home_alias=root/'home-alias';home_alias.symlink_to(physical_home,target_is_directory=True)
        dev_alias=physical_home/'DEV';dev_alias.symlink_to(checkout,target_is_directory=True)
        TEST_ENV['HOME']=str(home_alias)
        original=HERE.with_name('basis_batch_20261020_r1')/'runner.py'
        failed=command(['python3',original,'check'],transfer,1)
        assert 'Symlink path refused' in failed.stderr
        package=transfer/NAME
        command(['python3','-m','zipfile','-e',HERE/(NAME+'.zip'),package],transfer)
        script=package/(NAME+'_RUN.txt')
        call=lambda cmd,*args,expected=0:command(['bash',script,cmd,*args],transfer,expected)
        call('check')
        standalone=transfer/(NAME+'_RUN.txt');shutil.copyfile(script,standalone)
        command(['bash',standalone,'check'],transfer)
        assert json.loads((package/'ROOT_BINDING.json').read_text())['root']==str(checkout)
        # Same physical root via an explicit argument must stay valid.
        call('check','--root',checkout)
        # Changed aliases must not cause apply to silently target another checkout.
        other=root/'other-checkout';other.mkdir()
        command(['git','init','-q',other],transfer)
        dev_alias.unlink();dev_alias.symlink_to(other,target_is_directory=True)
        refused=call('apply',expected=1)
        assert 'DEV target changed' in refused.stderr+refused.stdout
        assert not (package/'INSTALL_STATE.json').exists()
        dev_alias.unlink();dev_alias.symlink_to(checkout,target_is_directory=True)
        call('check','--root',root/'missing',expected=1)
        call('check','--root',physical_home,expected=1)
        call('check','--root',checkout/'02_BACKEND',expected=1)
        # Symlinks below the physical checkout remain forbidden.
        code=checkout/'service.py';raw=code.read_bytes()
        outside=root/'outside-service.py';outside.write_bytes(raw)
        code.unlink();code.symlink_to(outside)
        refused=call('apply',expected=1)
        assert 'Symlink path refused' in refused.stderr+refused.stdout
        assert not (package/'INSTALL_STATE.json').exists()
        code.unlink();code.write_bytes(raw)
        # A linked binding file is not followed.
        binding=package/'ROOT_BINDING.json';raw=binding.read_bytes()
        saved_binding=root/'outside-binding.json';saved_binding.write_bytes(raw)
        binding.unlink();binding.symlink_to(saved_binding)
        call('check',expected=1)
        binding.unlink();binding.write_bytes(raw)
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
        logs=list((transfer/'basis-batch-r3-logs').glob('*.log.exit'))
        assert logs and all(p.read_text().strip().isdigit() for p in logs)
    summary={'status':'PASS','shell_commands':len(TRACE),
             'intentional_nonzero':sum(r['expected']!=0 for r in TRACE),'interruption_recovered':True,
             'exact_rollback':True,'data_preserved':True,
             'R1_photo_error_reproduced':True,'default_HOME_and_DEV_symlinks':True,
             'retarget_rejected':True,'nested_file_symlinks_rejected':True,
             'invalid_roots_rejected':True,'binding_symlink_rejected':True,
             'model_calls':0,'field_GENOS_verified':False,
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
