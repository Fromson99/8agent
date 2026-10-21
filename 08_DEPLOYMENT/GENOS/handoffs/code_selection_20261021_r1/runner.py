"""Install a code-relative latest-selection JSON without copying NFS source data.

One installer owns recovery. Prepare all backups before mutation; a failed or
interrupted apply resumes only exact before/after bytes, or explicitly rolls back.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import time
import traceback
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
VERSION = 'GENOS_DEV_SEARCH_SELECTION_20261021_R1'
CONFIG = '00_SYSTEM/GENOS_SERVING_PATHS.json'
SELECTION = '00_SYSTEM/SEARCH_SELECTION/generation.json'
DEFAULT_GENERATION = '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
DEFAULT_RUNTIME = '/nfs-root/diamo/8-agent/runtime'
STATE = HERE/'INSTALL_STATE.json'


def read(p): return json.loads(Path(p).read_text('utf-8'))
def encode(v): return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def digest(b): return hashlib.sha256(b).hexdigest()


def plain(p):
    p=Path(p).absolute()
    if any(q.is_symlink() for q in (p,*p.parents)): raise ValueError('symlink refused: '+str(p))
    if p.exists() and not (p.is_file() or p.is_dir()): raise ValueError('special file refused: '+str(p))
    return p


def sha(p):
    with plain(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def optional(p): return sha(p) if plain(p).exists() else None


def path(root,name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p)!=name or '\\' in name:
        raise ValueError('unsafe path: '+name)
    return plain(root/name)


def atomic(p,raw,mode=0o600):
    plain(p); p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_name('.'+p.name+'.'+uuid.uuid4().hex)
    try:
        with t.open('xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
        os.chmod(t,mode); os.replace(t,p)
        fd=os.open(p.parent,os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally: t.unlink(missing_ok=True)


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()


def event(name,**kw): print(json.dumps(dict(event=name,**kw),ensure_ascii=False),flush=True)


def binding(root):
    s=root.stat()
    return dict(root=str(root),device=s.st_dev,inode=s.st_ino,
                git_dir=str(Path(git(root,'rev-parse','--absolute-git-dir')).resolve()))


def resource_check(root):
    if shutil.disk_usage(root).free < 256*1024*1024: raise ValueError('less than 256 MiB free disk')
    mem=Path('/proc/meminfo')
    if mem.exists():
        available=next((int(l.split()[1])*1024 for l in mem.read_text().splitlines() if l.startswith('MemAvailable:')),0)
        if available and available<1024**3: raise ValueError('less than 1 GiB available RAM; stop heavy jobs before retrying')


def worker(root,action,generation,out):
    env=os.environ.copy(); env['PYTHONPATH']=str(root/'02_BACKEND');env['PYTHONDONTWRITEBYTECODE']='1'
    subprocess.run([sys.executable,str(HERE/'selection_worker.py'),str(root),action,str(generation),str(out)],
                   cwd=root,env=env,check=True,timeout=600)


def pins(root):
    """Validate existing manifests first; only reviewed source hashes may change."""
    registry=read(root/'00_SYSTEM/PIPELINE.json'); required={}
    entries=[(e,'') for e in registry['engines'].values()]
    entries += [(e,'02_BACKEND/workflow/') for e in registry.get('workflows',{}).get('registered',[])]
    for entry,prefix in entries:
        name=entry['manifest']; p=path(root,name)
        if sha(p)!=entry['sha256']: raise ValueError('existing manifest pin mismatch: '+name)
        required[name]=sha(p)
        value=read(p)
        if prefix and value['version']!=entry['version']:raise ValueError('workflow version mismatch')
        for n,h in value.get('files',{}).items():
            n=prefix+n
            if sha(path(root,n))!=h: raise ValueError('existing source pin mismatch: '+n)
            required[n]=h
    for n in ('service.py','06_TOOLS/COMMANDS/genos_generation_e2e.py'):
        required[n]=sha(path(root,n))
    return registry,required


def selection_config(root,args):
    config=read(root/CONFIG) if optional(root/CONFIG) else {}
    if os.environ.get('DP','').strip().lower() in {'oracle','1','true'}:
        raise ValueError('this repair targets the photographed NFS serving mode, not Oracle mode')
    chosen=args.generation or config.get('generation') or os.environ.get('GENOS_GENERATION') or DEFAULT_GENERATION
    generation=plain(Path(chosen).expanduser()).resolve(strict=True)
    if config:
        if config.get('schema_version')!='genos-serving-paths-v1' or config.get('selection')!='operator-fixed':
            raise ValueError('unsupported existing serving config')
        if plain(config['generation']).resolve(strict=True)!=generation:
            raise ValueError('requested generation differs from existing serving config')
        if config.get('generation_manifest_sha256')!=sha(generation/'manifest.json'):
            raise ValueError('existing generation binding changed')
        if config.get('state') is not None: raise ValueError('separate state override is unsupported')
    configured=os.environ.get('GENOS_GENERATION')
    if configured and plain(configured).resolve(strict=True)!=generation:
        raise ValueError('shell generation differs from selected generation')
    runtime=Path(args.runtime or config.get('runtime') or os.environ.get('GENOS_RUNTIME_DIR') or DEFAULT_RUNTIME)
    if not runtime.is_absolute(): raise ValueError('absolute runtime required')
    runtime=plain(runtime).resolve(strict=True)
    if config.get('runtime') and Path(config['runtime']).resolve()!=runtime:
        raise ValueError('requested runtime differs from existing config')
    for suffix in ('-wal','-journal'):
        if Path(str(generation/'store.sqlite')+suffix).exists(): raise ValueError('live source database journal')
    config.update(schema_version='genos-serving-paths-v1',selection='operator-fixed',
        generation=str(generation),runtime=str(runtime),generation_manifest_sha256=sha(generation/'manifest.json'))
    return generation,config


def data_binding(generation):
    s=plain(generation/'store.sqlite').stat()
    sidecar=generation.parent/'SEARCH_SELECTION'/(generation.name+'.json')
    return dict(manifest=sha(generation/'manifest.json'),
        store_stat=[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns],
        nfs_selection=optional(sidecar))


def make_plan(root,args,spec):
    resource_check(root)
    for name,expected in spec['required_existing_code'].items():
        actual=sha(path(root,name)); allowed={expected}
        if name in spec['payload']: allowed.add(spec['payload'][name])
        if actual not in allowed: raise ValueError('unsupported existing code: '+name)
    registry,required=pins(root)
    generation,config=selection_config(root,args); data=data_binding(generation)
    worker(root,'plan',generation,HERE/'PLANNED_SELECTION.json')
    required.update(read(HERE/'PLANNED_SELECTION.imports.json'))
    selection=(HERE/'PLANNED_SELECTION.json').read_bytes()
    if data_binding(generation)!=data: raise ValueError('generation changed during planning')
    config['search_selection']=dict(path=SELECTION,sha256=digest(selection))
    outputs={n:path(HERE/'payload',n).read_bytes() for n in spec['payload']}
    outputs[SELECTION]=selection;outputs[CONFIG]=encode(config)
    for entry in registry['engines'].values():
        name=entry['manifest']; value=read(root/name); changed=False
        for n,h in spec['payload'].items():
            if n in value['files']: value['files'][n]=h;changed=True
        if changed:
            outputs[name]=encode(value);entry['sha256']=digest(outputs[name])
    outputs['00_SYSTEM/PIPELINE.json']=encode(registry)
    # Update the checkout's own inventory if present; preserve unrelated entries.
    inventory=root/'CODE_MANIFEST.json'
    if optional(inventory):
        value=read(inventory)
        if value.get('format')!='8agent-code/1': raise ValueError('unsupported checkout code inventory')
        rows={r['path']:r for r in value['files']}
        for n,raw in outputs.items(): rows[n]=dict(path=n,sha256=digest(raw),bytes=len(raw))
        value['files']=list(rows.values());outputs['CODE_MANIFEST.json']=encode(value)
    entries={}
    for name,raw in outputs.items():
        target=path(root,name);before=target.read_bytes() if target.exists() else None
        mode=stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
        for content in (before,raw):
            if content is not None:
                blob=HERE/'blobs'/digest(content)
                if not blob.exists(): atomic(blob,content)
                elif sha(blob)!=digest(content): raise ValueError('backup blob mismatch')
        entries[name]=dict(before=digest(before) if before is not None else None,after=digest(raw),mode=mode)
    required={n:h for n,h in required.items() if n not in outputs}
    return dict(version=VERSION,status='PREPARED',binding=binding(root),generation=str(generation),runtime=config['runtime'],
        data_binding=data,files=entries,required=required,source_commit=git(root,'rev-parse','HEAD'),
        spec_sha256=sha(HERE/'PATCH_SPEC.json'),counts=json.loads(selection)['counts'])


def validate_state(root,state,spec):
    if state['version']!=VERSION or state['binding']!=binding(root) or state['spec_sha256']!=sha(HERE/'PATCH_SPEC.json'):
        raise ValueError('installer state/root/package binding differs')
    for n,row in state['files'].items():
        actual=optional(path(root,n))
        if actual not in {row['before'],row['after']}: raise ValueError('file changed since prepare: '+n)
        for h in (row['before'],row['after']):
            if h and sha(HERE/'blobs'/h)!=h: raise ValueError('backup/after snapshot changed: '+n)


def generation_unchanged(state):
    if data_binding(Path(state['generation']))!=state['data_binding']:
        raise ValueError('selected NFS data/sidecar changed since prepare; preserved')


def export_applied(root,state):
    names=[n for n in state['files'] if n!='CODE_MANIFEST.json']
    value=dict(format='8agent-code/1',files=[dict(path=n,sha256=sha(root/n),bytes=(root/n).stat().st_size) for n in names],
        required_files=[dict(path=n,sha256=h) for n,h in state['required'].items()])
    tmp=HERE/'APPLIED_CODE.zip.tmp'
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('CODE_MANIFEST.json',encode(value))
        for n in names: z.write(root/n,n)
    os.replace(tmp,HERE/'APPLIED_CODE.zip')
    atomic(HERE/'COMMIT_PATHS.txt',('\n'.join(state['files'])+'\n').encode())


def apply(root,state,spec):
    validate_state(root,state,spec);generation_unchanged(state)
    for n,h in state['required'].items():
        if sha(path(root,n))!=h: raise ValueError('required code changed after prepare: '+n)
    state['status']='APPLYING';atomic(STATE,encode(state))
    for n,row in state['files'].items():
        target=path(root,n)
        if optional(target)!=row['after']:
            atomic(target,(HERE/'blobs'/row['after']).read_bytes(),row['mode'])
            event('FILE_APPLIED',path=n)
    pins(root);generation_unchanged(state)
    worker(root,'verify',Path(state['generation']),HERE/'VERIFY.json')
    export_applied(root,state)
    state['status']='APPLIED';state['applied_at']=time.time();atomic(STATE,encode(state))
    event('APPLIED_DEV_ONLY',root=str(root),generation=state['generation'],counts=state['counts'],
          next='commit reviewed files, gate, push and deploy a new code-serving revision')


def rollback(root,state,spec):
    validate_state(root,state,spec)
    state['status']='ROLLING_BACK';atomic(STATE,encode(state))
    for n,row in reversed(list(state['files'].items())):
        target=path(root,n)
        if optional(target)==row['before']: continue
        if row['before'] is None: target.unlink()
        else: atomic(target,(HERE/'blobs'/row['before']).read_bytes(),row['mode'])
    state['status']='ROLLED_BACK';atomic(STATE,encode(state));event('ROLLED_BACK_DEV_ONLY')


def gate(root,state,code_only):
    if state['status']!='APPLIED': raise ValueError('apply must finish before deployment gate')
    generation_unchanged(state)
    for n,row in state['files'].items():
        if optional(path(root,n))!=row['after']: raise ValueError('applied file changed: '+n)
    worker(root,'verify',Path(state['generation']),HERE/'VERIFY.json')
    command=[sys.executable,str(HERE/'genos_release_gate.py'),'--code-zip',str(HERE/'APPLIED_CODE.zip'),
        '--deploy-root',str(root),'--generation',state['generation']]
    if code_only:command.append('--code-only')
    subprocess.run(command,check=True,cwd=root)
    atomic(HERE/('CODE_GATE.json' if code_only else 'RELEASE_GATE.json'),encode(dict(
        commit=git(root,'rev-parse','HEAD'),generation=state['generation'],
        generation_manifest_sha256=state['data_binding']['manifest'],code_zip_sha256=sha(HERE/'APPLIED_CODE.zip'),
        code_only=code_only,genos_revision=None,genos_verified=False)))


def commit(root,state):
    if state['status']!='APPLIED': raise ValueError('apply must finish before commit')
    generation_unchanged(state)
    for n,row in state['files'].items():
        if optional(path(root,n))!=row['after']: raise ValueError('applied file changed: '+n)
    tracked=set(git(root,'ls-files','-z').split('\0'))
    names=[n for n in state['files'] if n!='CODE_MANIFEST.json' or n in tracked]
    staged=set(filter(None,git(root,'diff','--cached','--name-only','-z').split('\0')))
    if staged-set(names): raise ValueError('unrelated staged files must be handled separately before this commit')
    subprocess.run(['git','-C',str(root),'add','-f','--',*names],check=True)
    subprocess.run(['git','-C',str(root),'diff','--cached','--check'],check=True)
    if subprocess.run(['git','-C',str(root),'diff','--cached','--quiet']).returncode:
        subprocess.run(['git','-C',str(root),'commit','-m','Read latest document selection from deployed code'],check=True)
    event('COMMITTED',commit=git(root,'rev-parse','HEAD'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['check','apply','rollback','commit','gate','gate-code'])
    p.add_argument('--root',type=Path,default=Path.home()/'DEV')
    p.add_argument('--generation');p.add_argument('--runtime')
    args=p.parse_args();root=args.root.expanduser().resolve(strict=True)
    if Path(git(root,'rev-parse','--show-toplevel')).resolve()!=root:raise ValueError('target must be existing DEV Git root')
    spec=read(HERE/'PATCH_SPEC.json')
    for n,h in spec['payload'].items():
        if sha(path(HERE/'payload',n))!=h: raise ValueError('payload changed: '+n)
    lock_path=Path(binding(root)['git_dir'])/'genos-code-selection.lock'
    with plain(lock_path).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=read(STATE) if STATE.exists() else None
        if state:
            validate_state(root,state,spec)
            if args.generation and str(plain(args.generation).resolve(strict=True))!=state['generation']:
                raise ValueError('state generation differs from requested generation')
            if args.runtime and str(plain(args.runtime).resolve(strict=True))!=state['runtime']:
                raise ValueError('state runtime differs from requested runtime')
        if args.action=='check':
            if state:
                generation_unchanged(state);event('EXISTING_STATE',status=state['status'],root=str(root))
            else:
                state=make_plan(root,args,spec);atomic(STATE,encode(state))
                event('CHECK_PASS',root=str(root),generation=state['generation'],counts=state['counts'])
        elif args.action=='apply':
            if not state:state=make_plan(root,args,spec);atomic(STATE,encode(state))
            apply(root,state,spec)
        elif args.action=='rollback':
            if not state:raise ValueError('no installation state to roll back')
            rollback(root,state,spec)
        elif args.action=='commit':
            if not state:raise ValueError('no installed state')
            commit(root,state)
        else:
            if not state:raise ValueError('no installed state')
            gate(root,state,args.action=='gate-code')


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        event('FAILED_PRESERVED',error_type=type(exc).__name__,error=str(exc),
              recovery='same folder: apply resumes exact snapshots; rollback restores saved bytes')
        traceback.print_exc();raise
