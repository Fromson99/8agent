"""Full MAIN replacement + existing search-selection CLI; no models/network."""
import argparse, fcntl, hashlib, importlib.util, io, json, os, subprocess, sys, zipfile
from pathlib import Path
import replace as rep
from comparison import write_comparison

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
            info=zipfile.ZipInfo(n,(2026,10,16,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,raw)
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

def selection_status(root,generation):
    return json.loads(command([sys.executable,'-m','lawrag.pipeline.search_selection','status','--generation',generation],root,True))

def selection_probe(staged,generation):
    script="""import hashlib,json,sys
from pathlib import Path
from semantic_runtime.search_selection import selection_path,file_state
p=selection_path(sys.argv[1]);file_state(p)
records=[]
for r in sorted((p.parent/'receipts').glob(p.stem+'-*/receipt.json')):
    file_state(r);value=json.loads(r.read_bytes())
    if value.get('target')==str(p):records.append({'path':str(r),**value})
print(json.dumps({'target':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None,'receipts':records}))
"""
    return json.loads(command([sys.executable,'-c',script,generation],staged,True))

def recover_selection_receipt(current,staged):
    intent=current.get('selection_intent')
    if not intent or current.get('selection_receipt'):return
    probe=selection_probe(staged,current['generation'])
    if probe['target']!=intent['target']:raise ValueError('Selection target changed')
    if probe['sha256']==intent['before_sha256']:return
    if probe['sha256']!=current['plan_sha256']:raise ValueError('Selection changed outside this install')
    matches=[r for r in probe['receipts'] if r['path'] not in intent['existing_receipts'] and
             r.get('after_sha256')==current['plan_sha256'] and r.get('before_sha256')==intent['before_sha256']]
    if len(matches)!=1:raise ValueError('Interrupted selection receipt is missing or ambiguous; preserve state')
    current['selection_receipt']=matches[0]['path'];save(current)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['check','install','apply','status','gate','undo'],nargs='?',default='check')
    p.add_argument('--root',type=Path,default=Path(os.environ.get('GENOS_DEV_ROOT',str(Path.home()/'DEV'))))
    p.add_argument('--generation',type=Path)
    args=p.parse_args();root=rep.plain(args.root.expanduser().resolve(strict=True))
    print('CODE_ROOT='+str(root)+' PYTHON='+sys.executable+' VERSION='+sys.version,flush=True)
    if sys.version_info<(3,11):raise ValueError('Python 3.11+ required')
    if Path(command(['git','rev-parse','--show-toplevel'],root,True).strip()).resolve()!=root:raise ValueError('Existing DEV Git checkout required')
    with rep.plain(root/'.genos-code-replacement.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        staged,content,binding=stage();current=state()
        # A hard stop may occur between moving the old config and installing its
        # identical replacement. Recover the recorded transaction before reading
        # that file, using the same full replacement rollback implementation.
        if current and current.get('code_root')!=str(root):raise ValueError('State belongs to a different DEV checkout')
        prior_archive=H/'APPLIED_CODE.zip'
        if current and prior_archive.exists():
            if sha(prior_archive.read_bytes())!=current['code_zip_sha256']:raise ValueError('Prepared code archive changed')
            pending=backups(root,prior_archive)
            if pending and pending[0][1]['status']!='APPLIED':
                if args.action not in ('install','apply','undo'):raise ValueError('Interrupted code install; use install to recover or undo')
                folder,receipt=pending[0];verify_rollback(root,folder);rep.rollback(folder)
                current.setdefault('recovery_history',[]).append({'backup':str(folder),'prior_status':receipt['status'],'outcome':'RESTORED'})
                if args.action=='undo':
                    current['phase']='RESTORED_REDEPLOY_PREVIOUS_REVISION';save(current);print('INTERRUPTED_CODE_RESTORED');return
                save(current)
        ident,config_raw=identity(root,staged,args.generation)
        if current and any(current.get(k)!=v for k,v in ident.items()):raise ValueError('Prepared root/generation/config binding changed')
        applied=archive(content,config_raw,ident)
        current={**current,**ident,'main_release':binding['main_release'],'main_generation':binding['main_generation'],
                 'code_zip_sha256':sha(applied.read_bytes()),'python':sys.executable,'python_version':sys.version,
                 'code_serving_revision':None,'workflow_test':'NOT_RUN'}
        existing=backups(root,applied)
        if args.action=='undo':
            if not existing:
                if current.get('phase')=='RESTORED_REDEPLOY_PREVIOUS_REVISION':print('ALREADY_RESTORED');return
                raise ValueError('No active backup for this exact delivery')
            folder,receipt=existing[0];verify_rollback(root,folder)
            recover_selection_receipt(current,staged)
            if current.get('selection_receipt'):
                command([sys.executable,'-m','lawrag.pipeline.search_selection','rollback','--receipt',current['selection_receipt']],staged)
            rep.rollback(folder);current['phase']='RESTORED_REDEPLOY_PREVIOUS_REVISION';save(current);return
        if args.action in ('status','gate'):
            if not existing or existing[0][1]['status']!='APPLIED':raise ValueError('Code install incomplete; use install or undo')
            verify_code(root,applied);value=selection_status(root,ident['generation'])
            if value['selection_sha256']!=current.get('selection_sha256'):raise ValueError('Selection differs from installed receipt')
            if args.action=='gate':
                command([sys.executable,root/'06_TOOLS/COMMANDS/genos_release_gate.py','--code-zip',applied,'--deploy-root',root,'--generation',ident['generation']],root)
                current['commit']=command(['git','rev-parse','HEAD'],root,True).strip()
                current['phase']='GATE_PASSED_PUSH_REVISION_WORKFLOW_PENDING';save(current)
            print(json.dumps({**value,'phase':current['phase'],'main_release':current['main_release']},ensure_ascii=False));return
        # Check dependencies and the exact MAIN engine pins before touching DEV.
        command([sys.executable,H/'search_smoke.py',staged],staged)
        policy=H/'FILENAME_EXCEPTIONS.json'
        if sha(policy.read_bytes())!=binding['policy_sha256']:raise ValueError('Sealed filename exceptions changed; prepare a separate reviewed plan')
        plan=H/'SELECTION_PLAN.json'
        if not plan.exists():
            command([sys.executable,'-m','lawrag.pipeline.search_selection','plan','--latest','--generation',ident['generation'],'--exceptions',policy,'--plan',plan],staged,True)
        value=json.loads(plan.read_bytes())
        if current.get('plan_sha256') and current['plan_sha256']!=sha(plan.read_bytes()):raise ValueError('Prepared selection plan changed')
        current['plan_sha256']=sha(plan.read_bytes());current['plan']=str(plan)
        print('COMPARE='+str(write_comparison(value,H/'COMPARE')),flush=True)
        print(json.dumps({'selection_counts':value['counts'],'main':binding['main_generation']},ensure_ascii=False),flush=True)
        if args.action=='check':
            rep.install(root,H,False,archive=applied)
            current.setdefault('phase','CHECKED_NO_CODE_CHANGED');save(current);print('CHECK PASS; code and data unchanged');return
        if existing and existing[0][1]['status']!='APPLIED':
            verify_rollback(root,existing[0][0]);rep.rollback(existing[0][0])
            current.setdefault('recovery_history',[]).append({'backup':str(existing[0][0]),'prior_status':existing[0][1]['status'],'outcome':'RESTORED_BEFORE_RETRY'})
        current['phase']='CODE_INSTALLING';save(current)
        folder=rep.install(root,H,True,archive=applied)
        current.update(backup=str(folder),phase='CODE_APPLIED_SELECTION_PENDING');save(current)
        verify_code(root,applied)
        # Reuse the same frozen plan after interrupted application. The selector
        # owns its lock, receipt and idempotency; this wrapper adds no retry loop.
        try:
            if not current.get('selection_intent'):
                probe=selection_probe(staged,ident['generation'])
                current['selection_intent']={'target':probe['target'],'before_sha256':probe['sha256'],
                                             'existing_receipts':[r['path'] for r in probe['receipts']]};save(current)
            result=json.loads(command([sys.executable,'-m','lawrag.pipeline.search_selection','apply','--plan',plan],root,True))
            if result.get('receipt'):current['selection_receipt']=result['receipt']
            recover_selection_receipt(current,staged)
            current['selection_sha256']=result['selection_sha256'];save(current)
            command([sys.executable,H/'search_smoke.py',root],root)
            status=selection_status(root,ident['generation'])
            if status['selection_sha256']!=current['selection_sha256']:raise ValueError('Selection status mismatch')
        except BaseException:
            current['phase']='CODE_APPLIED_SELECTION_FAILED';save(current);raise
        current['phase']='CODE_AND_LATEST_APPLIED_DEPLOYMENT_PENDING';save(current)
        print('MAIN_FULL_APPLIED; commit/gate/push/new revision/editor/workflow pending',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Persist failure separately, without turning a partial install into success.
        write(H/'LAST_FAILURE.json',enc({'error_type':type(exc).__name__,'error':str(exc),'state':state()}))
        print('MAIN_FULL_FAILED: '+str(exc),file=sys.stderr,flush=True);raise SystemExit(1)
