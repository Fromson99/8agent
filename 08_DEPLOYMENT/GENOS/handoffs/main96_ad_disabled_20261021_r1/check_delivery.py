"""Run the sealed ZIP/TXT against disposable existing Git checkouts."""
from pathlib import Path
import gzip,hashlib,importlib.util,json,os,shutil,subprocess,sys,zipfile

H=Path(__file__).resolve().parent;R=H.parents[3]
A=R/'09_ARTIFACTS/AUDITS/20261021-ad-disabled';N='GENOS_MAIN96_AD_DISABLED_20261021_R1'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=read(A/'BEFORE.json');target=read(A/'frozen.json')['target_files'];spec=read(H/'PACKAGE.json')
out=A/('delivery-runtime-'+sha(H/(N+'.zip'))[:12]);out.mkdir()
trace=[]
def command(args,cwd,ok=True):
    env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'PYTHONDONTWRITEBYTECODE':'1'}
    done=subprocess.run([str(x) for x in args],cwd=cwd,env=env,capture_output=True,text=True,timeout=60)
    trace.append({'command':[str(x) for x in args],'cwd':str(cwd),'code':done.returncode,'stdout':done.stdout,'stderr':done.stderr})
    assert (done.returncode==0)==ok,trace[-1]
    return done
def execute(transfer,package,root,mode,ok=True):
    return command(['bash',package/(N+'_RUN.txt'),mode,'--root',root],transfer,ok)
def fixture(name):
    base=out/name;base.mkdir();root=base/'DEV';root.mkdir();transfer=base/'custom-upload-location';transfer.mkdir()
    for n in b['files']:
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/b['manifest']['code_root']/n,p)
    preserved={'.gitignore':b'.Trash*/\nTRANSFER/\nuser-private/\n', 'genosIgnore':b'.Trash*/\n*.sqlite\nuser-rule\n',
               '.env':b'TEAM_ID=\nAD_WORKER_ENABLED=1\n', '00_SYSTEM/GENOS_SERVING_PATHS.json':b'{"runtime":"/field/runtime","generation":"/field/generation"}\n'}
    for n,v in preserved.items():(root/n).write_bytes(v)
    command(['git','init','-q'],root)
    command(['git','config','user.name','Synthetic patch verification'],root)
    command(['git','config','user.email','synthetic@example.invalid'],root)
    command(['git','add','.'],root)
    command(['git','commit','-qm','Synthetic MAIN95 baseline'],root)
    # User data must remain untracked and byte-identical.
    p=root/'.Trash-1001'/'sample.csv';p.parent.mkdir();p.write_bytes(b'private fixture\r\n')
    preserved['.Trash-1001/sample.csv']=p.read_bytes()
    archive=transfer/(N+'.zip');shutil.copyfile(H/(N+'.zip'),archive)
    package=transfer/N
    command([sys.executable,'-m','zipfile','-e',archive,package],transfer)
    return root,transfer,package,preserved
def unchanged(root,preserved):
    assert all((root/n).read_bytes()==v for n,v in preserved.items())
try:
    root,t,p,keep=fixture('normal')
    execute(t,p,root,'check');execute(t,p,root,'gate',False)
    execute(t,p,root,'apply');execute(t,p,root,'apply');execute(t,p,root,'gate')
    assert all(sha(root/n)==h for n,h in target.items());unchanged(root,keep)
    execute(t,p,root,'gate-code',False)
    command(['git','add','--',*spec['patch']],root);command(['git','commit','-qm','Synthetic MAIN96 patch'],root)
    execute(t,p,root,'gate-code')
    execute(t,p,root,'gate-sqlite',False)
    n='02_BACKEND/semantic_runtime/app.py';raw=(root/n).read_bytes();(root/n).write_bytes(raw+b'\n# later edit\n')
    execute(t,p,root,'check',False);execute(t,p,root,'rollback',False);(root/n).write_bytes(raw)
    payload=p/'payload'/n;raw=payload.read_bytes();payload.write_bytes(raw+b'\n# changed payload\n')
    execute(t,p,root,'apply',False);payload.write_bytes(raw)
    execute(t,p,root,'rollback');unchanged(root,keep)
    assert all(sha(root/n)==h for n,h in b['files'].items())
    execute(t,p,root,'apply',False)
    root,t,p,keep=fixture('interrupted')
    module_spec=importlib.util.spec_from_file_location('delivery_interruption',p/'runner.py')
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    original=module.write;writes=[]
    def injected(path,value):
        if Path(path).is_relative_to(root):
            if len(writes)==3:raise OSError('synthetic interruption after three code writes')
            writes.append(str(path))
        return original(path,value)
    module.write=injected
    try:module.apply(root,module.load())
    except OSError as exc:assert 'synthetic interruption' in str(exc)
    else:raise AssertionError('interruption not triggered')
    assert read(p/'INSTALL_STATE.json')['status']=='prepared'
    execute(t,p,root,'apply');execute(t,p,root,'gate');unchanged(root,keep)
    assert all(sha(root/n)==h for n,h in target.items())
    execute(t,p,root,'rollback');unchanged(root,keep)
    assert all(sha(root/n)==h for n,h in b['files'].items())
    result={'status':'PASS','archive_sha256':sha(H/(N+'.zip')),'command_count':len(trace),'expected_rejections':sum(x['code']!=0 for x in trace),
            'scenarios':['normal','interrupted'],'exact_source_files':len(target),'ignore_and_configuration_preserved':True,'data_preserved':True,
            'no_GENOS_execution':True,'generation_success_verified':False}
finally:
    with gzip.open(H/'DELIVERY_TRACE.json.gz','wt') as f:json.dump(trace,f,ensure_ascii=False)
(H/'DELIVERY_VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result))
