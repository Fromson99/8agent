"""Real ZIP/TXT to existing Git checkout, idempotence, gate, tamper and rollback."""
from pathlib import Path
import gzip,hashlib,json,os,shutil,subprocess,zipfile
import pytest
H=Path(__file__).resolve().parent;R=H.parents[3];NAME='GENOS_MAIN92_CUMULATIVE_20261020_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
@pytest.mark.parametrize('mode',['preserved-config-interruption','no-config-standalone'])
def test_transfer(tmp_path,mode):
    root=tmp_path/'actual checkout';root.mkdir()
    with zipfile.ZipFile(H.parent/'main90_research_20261020_r1/code.zip') as z:z.extractall(root)
    config='00_SYSTEM/GENOS_SERVING_PATHS.json'
    if mode.startswith('preserved'):
        p=root/config;p.write_bytes(enc({'schema_version':'genos-serving-paths-v1','selection':'operator-fixed',
            'generation':str(tmp_path/'OFFLINE_SOURCE_GENERATION'),'runtime':str(tmp_path/'EXTERNAL_NFS'),
            'state':None,'generation_manifest_sha256':'0'*64}))
    else:(root/config).unlink(missing_ok=True)
    kept={'.env':b'SYNTHETIC=private-test-value\n','unrelated.py':b'# user helper\n','01_DATA/source.txt':b'preserved source',
        '02_BACKEND/GENERATIONS/old/frozen.py':b'# frozen history\n'}
    for n,b in kept.items():p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    for row in json.loads((root/'00_SYSTEM/WORKSPACE.json').read_bytes())['roots']:(root/row['canonical_path']).mkdir(parents=True,exist_ok=True)
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    transfer=tmp_path/'uploaded TRANSFER files';transfer.mkdir()
    shutil.copyfile(H/(NAME+'.zip'),transfer/(NAME+'.zip'))
    env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'GENOS_DEV_ROOT':str(root),
         'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0','PYTHONDONTWRITEBYTECODE':'1'}
    for k in list(env):
        if k.startswith(('DP','ORACLE_','LLMOPS_')):env.pop(k)
    trace=[]
    def run(args,ok=True):
        out=subprocess.run(list(map(str,args)),cwd=transfer,env=env,text=True,capture_output=True,timeout=180)
        trace.append({'argv':list(map(str,args)),'exit':out.returncode,'stdout':out.stdout,'stderr':out.stderr})
        (H/('DELIVERY_'+mode+'.json.gz')).write_bytes(gzip.compress(enc(trace),mtime=0))
        assert (out.returncode==0)==ok,out.stdout+out.stderr
        return out
    run(['git','init','-q',root]);run(['git','-C',root,'config','user.name','Synthetic Validation']);run(['git','-C',root,'config','user.email','validation@example.invalid'])
    names=[n for n in before if n!='.env']
    run(['git','-C',root,'add','-f','--',*names]);run(['git','-C',root,'commit','-qm','synthetic prior checkout'])
    alias=tmp_path/'DEV';alias.symlink_to(root,target_is_directory=True)
    env['GENOS_DEV_ROOT']=str(alias)
    if mode.endswith('standalone'):
        shutil.copyfile(H/(NAME+'_RUN.txt'),transfer/(NAME+'_RUN.txt'));cmd=['bash','./'+NAME+'_RUN.txt']
    else:
        run(['python3','-m','zipfile','-e','./'+NAME+'.zip','./'+NAME]);cmd=['bash','./'+NAME+'/'+NAME+'_RUN.txt']
    run([*cmd,'deps']);run([*cmd,'check'])
    assert all((root/n).read_bytes()==b for n,b in before.items())
    package=transfer/NAME
    if mode.startswith('preserved'):
        crash="""import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import replace,run
old=replace.move
root=Path(os.environ['GENOS_DEV_ROOT']).resolve()
def move(src,dst):
 old(src,dst)
 if src==root/'service.py':os._exit(77)
replace.move=move
sys.argv=['run.py','apply'];run.main()
"""
        out=run(['python3','-c',crash,package],False);assert out.returncode==77
        run([*cmd,'check'],False)
    run([*cmd,'apply']);run([*cmd,'status']);run([*cmd,'apply'])
    state=json.loads((package/'STATUS.json').read_bytes());receipt=json.loads((Path(state['backup'])/'receipt.json').read_bytes())
    for n,b in kept.items():assert (root/n).read_bytes()==b
    if config in before:assert (root/config).read_bytes()==before[config]
    assert state['phase']=='CODE_APPLIED_DEPLOYMENT_PENDING'
    if mode.startswith('preserved'):assert state['recovery_history'][-1]['outcome']=='RESTORED'
    # Same exact installed files and committed checkout, no field generation opened.
    boot="""import asyncio,os,sys
from pathlib import Path
root=Path(os.environ['GENOS_DEV_ROOT']).resolve();sys.path[:0]=[str(root),str(root/'02_BACKEND')]
os.environ.update(DP='oracle',GENOS_RUNTIME_DIR='/external-nfs/explicit-runtime',GENOS_STATE_DIR='/external-nfs/explicit-state')
import service
assert service._DEPLOYMENT_PATHS is None
assert os.environ['GENOS_RUNTIME_DIR']=='/external-nfs/explicit-runtime'
assert os.environ['GENOS_STATE_DIR']=='/external-nfs/explicit-state'
assert service._APP is None
print('ACTUAL_ORACLE_SERVICE_IMPORT_PASS; no source generation or data cache opened')
"""
    run(['python3','-c',boot])
    run([*cmd,'gate-code'],False)
    run(['git','-C',root,'diff','--check'])
    run(['git','-C',root,'add','-f','--',*receipt['units']]);run(['git','-C',root,'commit','-qm','merged MAIN88 Oracle code'])
    run([*cmd,'gate-code'])
    target=root/'service.py';good=target.read_bytes();target.write_bytes(good+b'\n# later user edit\n')
    run([*cmd,'apply'],False);run([*cmd,'undo'],False);target.write_bytes(good)
    run([*cmd,'undo']);run([*cmd,'undo'])
    assert all((root/n).read_bytes()==b for n,b in before.items())
    added=set(receipt['units'])-set(before)
    assert all(not (root/n).exists() for n in added)
    assert list((transfer/'main92-cumulative-r1-logs').glob('*.log.exit'))
    (H/('PASS_'+mode+'.json')).write_bytes(enc({'status':'PASS','commands':len(trace),'exact_rollback':True,'preserved_data':True,
        'code_root':str(root),'code_zip_sha256':sha((package/'APPLIED_CODE.zip').read_bytes()),'source_generation_opened':False,'mode':mode}))
