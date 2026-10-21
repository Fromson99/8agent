"""MAIN87 code-only delivery; preserve existing field data and selection."""
import argparse, fcntl, hashlib, importlib.util, io, json, os, subprocess, sys, zipfile
from pathlib import Path
import replace as rep

H=Path(__file__).resolve().parent
CONFIG='00_SYSTEM/GENOS_SERVING_PATHS.json'

def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def write(path,raw):
    rep.plain(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp');rep.plain(temporary)
    with temporary.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)
def immutable(path,raw):
    rep.plain(path)
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('Prepared state changed: '+str(path))
    else:write(path,raw)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def command(args,root,capture=False):
    env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1',
         'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
         'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'}
    result=subprocess.run(list(map(str,args)),cwd=root,env=env,text=True,capture_output=capture)
    if result.returncode:
        if capture:print(result.stdout+result.stderr,flush=True)
        raise RuntimeError('Command failed; exit='+str(result.returncode))
    return result.stdout if capture else None
def state():return json.loads((H/'STATUS.json').read_bytes()) if (H/'STATUS.json').exists() else {}
def save(value):write(H/'STATUS.json',enc(value))

def stage():
    binding=json.loads((H/'PACKAGE_SPEC.json').read_bytes())
    if sha((H/'code.zip').read_bytes())!=binding['code_zip_sha256']:raise ValueError('Packaged code ZIP changed')
    content,_,_=rep.full_payload(H/'code.zip')
    root=H/'preflight-code';root.mkdir(exist_ok=True)
    for n,(raw,mode) in content.items():immutable(root/n,raw)
    return root,content,binding

def identity(root,staged,explicit):
    paths=load('field_deployment_paths',staged/'02_BACKEND/semantic_runtime/deployment_paths.py')
    environment=dict(os.environ);config=paths.install(root,environment=environment)
    if config is None:raise ValueError('Existing GENOS_SERVING_PATHS.json required; preserve the field generation binding')
    generation=Path(config['generation'])
    if explicit is not None and explicit.resolve(strict=True)!=generation:raise ValueError('Explicit generation differs from existing field binding')
    if generation.is_symlink() or not generation.is_dir():raise ValueError('Existing physical generation required')
    paths.verify_generation(config,generation)
    config_raw=rep.plain(root/CONFIG).read_bytes()
    old_manifest=root/'CODE_MANIFEST.json'
    if old_manifest.exists():
        manifest=json.loads(rep.plain(old_manifest).read_bytes())
        recorded=next((r for r in manifest.get('files',[]) if r['path']==CONFIG),None)
        if recorded and (recorded['sha256']!=sha(config_raw) or recorded['bytes']!=len(config_raw)):
            raise ValueError('Existing fixed deployment config differs from its inventory')
    os.environ['GENOS_GENERATION']=str(generation)
    return {'code_root':str(root),'generation':str(generation),'generation_manifest_sha256':sha((generation/'manifest.json').read_bytes()),
            'fixed_config_sha256':sha(config_raw)},config_raw

def archive(content,config_raw,ident):
    manifest=json.loads(content['CODE_MANIFEST.json'][0])
    files={n:raw for n,(raw,_) in content.items() if n!='CODE_MANIFEST.json'};files[CONFIG]=config_raw
    manifest['files']=[{'path':n,'sha256':sha(raw),'bytes':len(raw)} for n,raw in sorted(files.items())]
    manifest['field_binding']=ident;manifest['required_files'].append({'path':CONFIG,'sha256':sha(config_raw)})
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,raw in sorted({**files,'CODE_MANIFEST.json':enc(manifest)}.items()):
            info=zipfile.ZipInfo(n,(2026,10,19,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,raw)
    target=H/'APPLIED_CODE.zip';immutable(target,buf.getvalue());return target

def backups(root,archive):
    digest=sha(archive.read_bytes());result=[]
    for p in sorted((root/'09_ARTIFACTS/BACKUPS/code-replacement').glob('*/receipt.json')):
        rep.plain(p);value=json.loads(p.read_bytes())
        if value.get('root')==str(root) and value.get('code_zip_sha256')==digest and value['status']!='ROLLED_BACK':result.append((p.parent,value))
    if len(result)>1:raise ValueError('Multiple active backups for this delivery; preserve and inspect')
    return result

def verify_code(root,archive):
    content,_,_=rep.full_payload(archive)
    for n,(raw,_) in content.items():
        target=rep.plain(root/n)
        if not target.is_file() or sha(target.read_bytes())!=sha(raw):raise ValueError('Installed code changed: '+n)

def verify_rollback(root,folder):
    receipt=json.loads(rep.plain(folder/'receipt.json').read_bytes())
    if receipt['root']!=str(root):raise ValueError('Backup root mismatch')
    for n,row in receipt['units'].items():
        current=rep.snapshot(root/n);old=rep.snapshot(folder/'old'/n)
        if old is not None:
            if old!=row['before'] or current not in (None,row['after']):raise ValueError('Changed code/backup; rollback refused: '+n)
        elif row['before'] is None:
            if current not in (None,row['after']):raise ValueError('Changed added file; rollback refused: '+n)
        elif current!=row['before']:raise ValueError('Missing original backup: '+n)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','apply','install','status','gate-code','gate','undo'],nargs='?',default='check')
    parser.add_argument('--root',type=Path,default=Path(os.environ.get('GENOS_DEV_ROOT',str(Path.home()/'DEV'))))
    parser.add_argument('--generation',type=Path)
    args=parser.parse_args();root=rep.plain(args.root.expanduser().resolve(strict=True))
    print('CODE_ROOT='+str(root)+' PYTHON='+sys.executable+' VERSION='+sys.version,flush=True)
    if sys.version_info<(3,11):raise ValueError('Python 3.11+ required')
    if Path(command(['git','rev-parse','--show-toplevel'],root,True).strip()).resolve()!=root:
        raise ValueError('Existing DEV Git checkout required')
    with rep.plain(root/'.genos-code-replacement.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        staged,content,binding=stage();current=state()
        if current and current.get('code_root')!=str(root):raise ValueError('State belongs to another checkout')
        prior=H/'APPLIED_CODE.zip'
        if current and prior.exists():
            if sha(prior.read_bytes())!=current['code_zip_sha256']:raise ValueError('Prepared archive changed')
            pending=backups(root,prior)
            if pending and pending[0][1]['status']!='APPLIED':
                if args.action not in ('install','apply','undo'):
                    raise ValueError('Interrupted code install; apply to recover or undo')
                folder,receipt=pending[0];verify_rollback(root,folder);rep.rollback(folder)
                current.setdefault('recovery_history',[]).append({'backup':str(folder),'prior_status':receipt['status'],'outcome':'RESTORED'})
                if args.action=='undo':
                    current['phase']='RESTORED_REDEPLOY_PREVIOUS_REVISION';save(current)
                    print('INTERRUPTED_CODE_RESTORED');return
                save(current)
        ident,config_raw=identity(root,staged,args.generation)
        if current and any(current.get(k)!=v for k,v in ident.items()):raise ValueError('Root/generation/config binding changed')
        applied=archive(content,config_raw,ident)
        current={**current,**ident,'main_release':binding['main_release'],'main_generation':binding['main_generation'],
                 'code_zip_sha256':sha(applied.read_bytes()),'python':sys.executable,'python_version':sys.version,
                 'code_serving_revision':current.get('code_serving_revision'),'workflow_test':'NOT_RUN',
                 'data_changes':'NONE','selection_changes':'NONE'}
        existing=backups(root,applied)
        if args.action=='undo':
            if not existing:
                if current.get('phase')=='RESTORED_REDEPLOY_PREVIOUS_REVISION':print('ALREADY_RESTORED');return
                raise ValueError('No active backup for this delivery')
            folder,_=existing[0];verify_rollback(root,folder);rep.rollback(folder)
            current['phase']='RESTORED_REDEPLOY_PREVIOUS_REVISION';save(current);return
        if args.action in ('status','gate-code','gate'):
            if not existing or existing[0][1]['status']!='APPLIED':raise ValueError('Code install incomplete; apply or undo')
            verify_code(root,applied)
            if args.action in ('gate-code','gate'):
                argv=[sys.executable,root/'06_TOOLS/COMMANDS/genos_release_gate.py','--code-zip',applied,'--deploy-root',root,'--generation',ident['generation']]
                if args.action=='gate-code':argv.append('--code-only')
                command(argv,root)
                current['commit']=command(['git','rev-parse','HEAD'],root,True).strip()
                current['phase']=('CODE_GATE_PASSED_GENERATION_UNVERIFIED' if args.action=='gate-code' else 'GATE_PASSED_PUSH_REVISION_WORKFLOW_PENDING')
                save(current)
            print(json.dumps(current,ensure_ascii=False));return
        command([sys.executable,H/'code_smoke.py',staged],staged)
        if args.action=='check':
            rep.install(root,H,False,archive=applied)
            current.setdefault('phase','CHECKED_NO_CODE_CHANGED');save(current)
            print('CHECK PASS; no code/data/selection changed');return
        current['phase']='CODE_INSTALLING';save(current)
        folder=rep.install(root,H,True,archive=applied)
        current.update(backup=str(folder),phase='CODE_APPLIED_VALIDATION_PENDING');save(current)
        verify_code(root,applied)
        command([sys.executable,H/'code_smoke.py',root],root)
        current['phase']='CODE_APPLIED_DEPLOYMENT_PENDING';save(current)
        print('MAIN87_CODE_APPLIED; commit/gate/push/revision/editor/workflow pending',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        write(H/'LAST_FAILURE.json',enc({'error_type':type(exc).__name__,'error':str(exc),'state':state()}))
        print('MAIN87_APPLY_FAILED: '+str(exc),file=sys.stderr,flush=True)
        raise SystemExit(1)

