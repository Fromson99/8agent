"""Exact standalone patch against both sealed field bases, no data/model load."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

H=Path(__file__).resolve().parent
NAME='GENOS_ORACLE_LOGGING_20261019_R1'
spec=json.loads((H/'PATCH_SPEC.json').read_bytes())
transcript=[]


def run(args, cwd, *, ok=True, env=None):
    result=subprocess.run(list(map(str,args)),cwd=cwd,env=env,capture_output=True,text=True,timeout=60)
    transcript.append({'argv':list(map(str,args)),'cwd':str(cwd),'returncode':result.returncode,
                       'stdout':result.stdout,'stderr':result.stderr})
    (H/'INSTALL_TRANSCRIPT.json.gz').write_bytes(gzip.compress(json.dumps(transcript,ensure_ascii=False).encode(),mtime=0))
    if (result.returncode==0)!=ok:
        raise AssertionError(str(args)+'\n'+result.stdout[-4000:]+'\n'+result.stderr[-4000:])
    return result


results={}
for variant in spec['variants']:
    with tempfile.TemporaryDirectory(prefix='logging-install-',dir=H) as td:
        temp=Path(td);root=temp/'DEV';transfer=temp/'TRANSFER';root.mkdir();transfer.mkdir()
        with zipfile.ZipFile(H.parent/variant/'code.zip') as z:
            z.extractall(root)
            original={n:z.read(n) for n in spec['files'] if n in z.namelist()}
            original['CODE_MANIFEST.json']=z.read('CODE_MANIFEST.json')
        env={**os.environ,'GENOS_PYTHON_DIR':str(Path(sys.executable).parent),'PYTHONDONTWRITEBYTECODE':'1',
             'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0','GENOS_SYSTEM_LOG_ENABLED':'0'}
        for key in ('GENOS_GENERATION','GENOS_DATA_ROOT','DP','DP_RELEASE_ID','DP_CACHE_DIR'):
            env.pop(key,None)
        run(['git','init','-q'],root)
        run(['git','add','-f','.'],root)
        run(['git','-c','user.name=Logging fixture','-c','user.email=logging@example.invalid','commit','-qm','Sealed base'],root)
        shutil.copyfile(H/(NAME+'.zip'),transfer/(NAME+'.zip'))
        run([sys.executable,'-m','zipfile','-e','./'+NAME+'.zip','./'+NAME],transfer,env=env)
        cmd=['bash','./'+NAME+'/'+NAME+'_RUN.txt']
        run([*cmd,'check','--root',root],transfer,env=env)
        run([*cmd,'apply','--root',root],transfer,env=env)
        assert (transfer/'oracle-logging-r1-state/WORKFLOW_PASTE_ALL.txt').read_bytes()==(root/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes()
        backup=root/'09_ARTIFACTS/BACKUPS'/NAME
        # Recover a partial application using its original durable state and backups.
        state=json.loads((backup/'STATE.json').read_bytes());state['status']='APPLYING'
        (backup/'STATE.json').write_text(json.dumps(state))
        (root/'02_BACKEND/semantic_runtime/oracle_dp_io.py').write_bytes(original['02_BACKEND/semantic_runtime/oracle_dp_io.py'])
        run([*cmd,'apply','--root',root],transfer,env=env)
        run([*cmd,'apply','--root',root],transfer,env=env)
        run([*cmd,'status','--root',root],transfer,env=env)
        for n,pin in spec['variants'][variant]['after'].items():
            assert hashlib.sha256((root/n).read_bytes()).hexdigest()==pin
        run(['git','add','-f','--',*spec['files'],'CODE_MANIFEST.json'],root)
        run(['git','-c','user.name=Logging fixture','-c','user.email=logging@example.invalid','commit','-qm','Install logging delta'],root)
        gate=run([*cmd,'gate-code','--root',root],transfer,env=env)
        applied=(root/'service.py').read_bytes()
        (root/'service.py').write_bytes(applied+b'\n# unknown local edit\n')
        run([*cmd,'apply','--root',root],transfer,env=env,ok=False)
        run([*cmd,'undo','--root',root],transfer,env=env,ok=False)
        (root/'service.py').write_bytes(applied)
        state=json.loads((backup/'STATE.json').read_bytes())
        results[variant]={'status':'PASS','commit':state['commit'],'code_zip_sha256':state['code_zip_sha256'],
                          'generation':'unchanged; no source data loaded','service_smoke':'PASS','workflow_smoke':'PASS'}
        run([*cmd,'undo','--root',root],transfer,env=env)
        run([*cmd,'undo','--root',root],transfer,env=env)
        for n,b in original.items():assert (root/n).read_bytes()==b,n
        assert not (root/'02_BACKEND/semantic_runtime/preparation_progress.py').exists()
        # Preserve state, receipts and complete command evidence; these fixture code copies
        # are reproducible from the sealed base ZIP plus this exact tested patch.
        (H/(variant+'-STATE.json')).write_bytes((backup/'STATE.json').read_bytes())
        print(variant+' PASS',flush=True)
(H/'INSTALL_VALIDATION.json').write_text(json.dumps({'status':'PASS','variants':results,'commands':len(transcript),
    'fixture_cleanup':'only reproducible synthetic checkouts; original sealed ZIPs and receipts retained',
    'package_sha256':hashlib.sha256((H/(NAME+'.zip')).read_bytes()).hexdigest()},indent=2)+'\n')
