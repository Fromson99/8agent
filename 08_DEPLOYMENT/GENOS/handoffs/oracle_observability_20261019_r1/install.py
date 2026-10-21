"""Observability delta on sealed MAIN87/session-identity; preserve field data."""
import argparse, ast, fcntl, hashlib, importlib.util, json, os, subprocess, sys, zipfile
from pathlib import Path
H=Path(__file__).resolve().parent
SPEC=json.loads((H/'PATCH_SPEC.json').read_text())
NAME=SPEC['id']
PACKAGE=SPEC
VARIANT=None
CONFIG='00_SYSTEM/GENOS_SERVING_PATHS.json'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def plain(p):
    if any(x.is_symlink() for x in [p,*p.parents]):raise ValueError('Symlink refused: '+str(p))
    return p

def raw(p):
    plain(p)
    return p.read_bytes() if p.is_file() else None

def digest(p):
    value=raw(p);return sha(value) if value is not None else None

def write(p,value):
    plain(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_name(p.name+'.oracle-log-tmp');plain(temp)
    with temp.open('wb') as f:f.write(value);f.flush();os.fsync(f.fileno())
    os.replace(temp,p)

def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def command(root,args):
    result=subprocess.run(list(map(str,args)),cwd=root,env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),
        'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0','GENOS_SYSTEM_LOG_ENABLED':'0','PYTHONDONTWRITEBYTECODE':'1'})
    if result.returncode:raise ValueError('Command failed; exit='+str(result.returncode))

def verify(root,phase):
    after=SPEC['after'];before=SPEC['before']
    for n,pin in before.items():
        allowed={pin,after[n]} if n in after and phase=='mixed' else {after.get(n,pin) if phase=='after' else pin}
        if digest(root/n) not in allowed:raise ValueError('Sealed base file differs: '+n)
    for n,pin in after.items():
        if n not in before and digest(root/n) not in ({None,pin} if phase=='mixed' else {pin} if phase=='after' else {None}):
            raise ValueError('Added path conflicts: '+n)
    for n,pin in after.items():
        if digest(H/'payload'/VARIANT/n)!=pin:raise ValueError('Patch bytes differ: '+n)
        ast.parse((H/'payload'/VARIANT/n).read_bytes(),filename=n,feature_version=(3,11))

def final_inventory(root,folder):
    manifest=json.loads(raw(folder/'old/CODE_MANIFEST.json'))
    paths=set(SPEC['before'])|set(SPEC['after'])
    if (root/CONFIG).is_file():paths.add(CONFIG)
    manifest['files']=[{'path':n,'sha256':digest(root/n),'bytes':(root/n).stat().st_size} for n in sorted(paths)]
    manifest['id']=NAME
    manifest['oracle_observability_patch']={'base_code_zip_sha256':SPEC['base_zip_sha256'],'payload_sha256':SPEC['payload_sha256'],
        'field_generation':'selected by explicit DP_RELEASE_ID; NFS source unchanged','field_verification':'PENDING'}
    manifest['required_files']=[{'path':r['path'],'sha256':r['sha256']} for r in manifest['files']]
    return encoded(manifest)

def make_archive(root,folder):
    value=raw(root/'CODE_MANIFEST.json');manifest=json.loads(value)
    archive=folder/'APPLIED_CODE.zip';temp=archive.with_suffix('.tmp');plain(temp)
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for r in manifest['files']:
            data=raw(root/r['path'])
            if data is None or sha(data)!=r['sha256']:raise ValueError('Inventory changed')
            z.writestr(r['path'],data)
        z.writestr('CODE_MANIFEST.json',value)
    os.replace(temp,archive)
    return archive

def main():
    global SPEC,VARIANT
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['check','apply','status','gate-code','gate','undo'],nargs='?',default='check')
    parser.add_argument('--root',type=Path,default=Path.home()/'DEV');args=parser.parse_args()
    root=plain(args.root.expanduser().absolute())
    gitroot=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=root,text=True).strip()
    if Path(gitroot).resolve()!=root.resolve():raise ValueError('Existing DEV Git root required')
    print('CODE_ROOT='+str(root)+' PYTHON='+sys.executable+' VERSION='+sys.version,flush=True)
    if sys.version_info<(3,11):raise ValueError('Python 3.11+ required')
    folder=root/'09_ARTIFACTS/BACKUPS'/NAME;folder.mkdir(parents=True,exist_ok=True);plain(folder)
    receipt=folder/'STATE.json'
    with plain(root/'.genos-code-replacement.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=json.loads(receipt.read_text()) if receipt.exists() else None
        if state:
            VARIANT=state['variant']
        else:
            actual=digest(root/'service.py')
            choices=[n for n,v in PACKAGE['variants'].items() if v['before']['service.py']==actual]
            if len(choices)!=1:raise ValueError('Unknown service revision; preserve current code and provide CODE_MANIFEST.json')
            VARIANT=choices[0]
        SPEC=PACKAGE['variants'][VARIANT]
        SPEC['payload_sha256']=sha(encoded(SPEC['after']))
        print('BASE_VARIANT='+VARIANT,flush=True)
        if state and (state['root']!=str(root) or state['payload_sha256']!=SPEC['payload_sha256']):raise ValueError('Backup binding differs')
        if args.action=='undo':
            if not state:raise ValueError('No patch backup')
            if state['status']=='RESTORED':print('ALREADY_RESTORED');return
            for n,row in state['files'].items():
                if digest(root/n) not in {row['before'],row['after']}:raise ValueError('Changed file; rollback refused: '+n)
                if row['before'] is not None and digest(folder/'old'/n)!=row['before']:raise ValueError('Backup changed: '+n)
            for n,row in state['files'].items():
                if row['before'] is None:
                    if (root/n).exists():(root/n).unlink()
                else:write(root/n,raw(folder/'old'/n))
            state['status']='RESTORED';write(receipt,encoded(state));print('RESTORED; redeploy previous code revision with previous DP setting');return
        verify(root,'mixed' if args.action in ('check','apply') else 'after')
        if args.action=='check':print('CHECK PASS: base/payload verified; no code/data changes');return
        if state and state['status']=='RESTORED':raise ValueError('This installation was rolled back; preserve its receipt and use a new patch revision')
        if args.action=='apply':
            if not state:
                names=[*SPEC['after'],'CODE_MANIFEST.json'];files={}
                for n in names:
                    value=raw(root/n)
                    if value is not None:write(folder/'old'/n,value)
                    files[n]={'before':sha(value) if value is not None else None,'after':SPEC['after'].get(n)}
                state={'root':str(root),'payload_sha256':SPEC['payload_sha256'],'status':'APPLYING','files':files,
                    'base_family':'MAIN87','variant':VARIANT,'commit':None,'code_serving_revision':None,'workflow_test':'NOT_RUN'}
                write(receipt,encoded(state))
            for n in SPEC['after']:write(root/n,raw(H/'payload'/VARIANT/n))
            inventory=final_inventory(root,folder);state['files']['CODE_MANIFEST.json']['after']=sha(inventory)
            write(receipt,encoded(state));write(root/'CODE_MANIFEST.json',inventory)
            verify(root,'after');command(root,[sys.executable,H/'code_smoke.py',root])
            archive=make_archive(root,folder);state.update(status='APPLIED',code_zip_sha256=digest(archive),code_archive=str(archive))
            write(receipt,encoded(state))
            editor=H/'WORKFLOW_PASTE_ALL.txt'
            editor_bytes=raw(root/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
            if editor.exists() and raw(editor)!=editor_bytes:raise ValueError('Generated workflow file differs; preserve and inspect')
            write(editor,editor_bytes)
            print('WORKFLOW_EDITOR_FILE='+str(editor))
            print('ORACLE_LOGGING_PATCH_APPLIED; commit/gate/push/revision/workflow pending');return
        if not state or state['status']!='APPLIED':raise ValueError('Patch installation incomplete')
        for n,row in state['files'].items():
            if digest(root/n)!=row['after']:raise ValueError('Installed patch changed: '+n)
        if args.action in ('gate-code','gate'):
            archive=Path(state['code_archive'])
            if digest(archive)!=state['code_zip_sha256']:raise ValueError('Applied code archive changed')
            command(root,[sys.executable,root/'06_TOOLS/COMMANDS/genos_release_gate.py','--code-zip',archive,'--deploy-root',root,'--code-only'])
            if args.action=='gate':
                env={**os.environ,'GENOS_AUTO_WARMUP':'0','PYTHONPATH':str(root/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1'}
                script="import subprocess,sys; from semantic_runtime.oracle_dp import enabled,resolve,verify_runtime; assert enabled(); _,g,b=resolve('.'); assert verify_runtime(g)['verified']; print('DP_GENERATION='+str(g)); print('DP_RELEASE_ID='+b['release_id']); subprocess.run([sys.executable,'06_TOOLS/COMMANDS/genos_release_gate.py','--code-zip',sys.argv[1],'--deploy-root','.', '--generation',str(g)],check=True)"
                result=subprocess.run([sys.executable,'-c',script,str(archive)],cwd=root,env=env)
                if result.returncode:raise ValueError('Oracle cache gate failed; checkpoint retained')
            state['commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
            state['last_gate']=args.action;write(receipt,encoded(state))
        print(json.dumps(state,ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('ORACLE_LOGGING_PATCH_FAILED: '+type(exc).__name__+': '+str(exc),file=sys.stderr,flush=True)
        raise SystemExit(1)
