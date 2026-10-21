"""Narrow verified code installer; no rebuild or automatic Git commit/push."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
VERSION = 'GENOS_SEARCH_LATEST_20261015_R1'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(v): return (json.dumps(v, ensure_ascii=False, indent=2)+'\n').encode()


def at(root, relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative or str(p)!=relative:
        raise ValueError('unsafe path: '+relative)
    target = root/relative
    if any(p.is_symlink() for p in (target,*target.parents)):
        raise ValueError('symlink refused: '+str(target))
    return target


def atomic(path, raw, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    try:
        with temp.open('xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
        os.chmod(temp,mode); os.replace(temp,path)
    finally: temp.unlink(missing_ok=True)


def payload():
    spec=json.loads((HERE/'PATCH_SPEC.json').read_bytes())
    if sha((HERE/'CODE.zip').read_bytes())!=spec['code_zip_sha256']: raise ValueError('CODE.zip changed')
    with zipfile.ZipFile(HERE/'CODE.zip') as z:
        manifest=json.loads(z.read('CODE_MANIFEST.json'))
        expected={r['path']:r for r in spec['files']}
        if len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!={'CODE_MANIFEST.json',*expected}:
            raise ValueError('code inventory mismatch')
        if manifest['files']!=spec['manifest']['files']: raise ValueError('manifest changed')
        files={name:z.read(name) for name in expected}
        for name,raw in files.items():
            at(HERE,name)
            if sha(raw)!=expected[name]['after']: raise ValueError('code hash mismatch: '+name)
            compile(raw,name,'exec')
    return spec,files


def proposed(root,spec,files):
    """Preserve unrelated pins; verify before changing only this patch's pins."""
    for row in spec['files']:
        target=at(root,row['path']); actual=sha(target.read_bytes()) if target.exists() else None
        if actual not in [*row['before'],row['after']]: raise ValueError('unknown code preimage: '+row['path'])
    for row in spec['manifest']['required_files']:
        if sha(at(root,row['path']).read_bytes())!=row['sha256']: raise ValueError('dependency differs: '+row['path'])
    outputs=dict(files)
    cfg_path='00_SYSTEM/PIPELINE.json'; config=json.loads(at(root,cfg_path).read_bytes())
    pins={p:sha(raw) for p,raw in files.items()}
    for entry in config['engines'].values():
        path=entry['manifest']; original=at(root,path).read_bytes()
        if sha(original)!=entry['sha256']: raise ValueError('engine manifest pin mismatch: '+path)
        m=json.loads(original)
        # All existing pins must match before an installer can extend them.
        for file,pin in m['files'].items():
            actual=sha(at(root,file).read_bytes())
            if actual!=pin: raise ValueError('existing engine code pin mismatch: '+file)
        change=False
        for file,pin in pins.items():
            if file in m['files'] and m['files'][file]!=pin:
                m['files'][file]=pin; change=True
        if '02_BACKEND/semantic_runtime/storage.py' in m['files']:
            file='02_BACKEND/semantic_runtime/search_selection.py'
            if m['files'].get(file)!=pins[file]: m['files'][file]=pins[file]; change=True
        if change:
            m['files']=dict(sorted(m['files'].items())); raw=encode(m)
            if not original.endswith(b'\n'): raw=raw.rstrip(b'\n')
            outputs[path]=raw; entry['sha256']=sha(raw)
    cfg_raw=encode(config)
    if not at(root,cfg_path).read_bytes().endswith(b'\n'): cfg_raw=cfg_raw.rstrip(b'\n')
    if json.loads(at(root,cfg_path).read_bytes())!=config: outputs[cfg_path]=cfg_raw
    # Full checkout inventories are maintained, never discarded or blindly rehashed.
    if at(root,'CODE_MANIFEST.json').exists():
        m=json.loads(at(root,'CODE_MANIFEST.json').read_bytes())
        for field in ('files','required_files'):
            for row in m.get(field,[]):
                target=at(root,row['path'])
                if sha(target.read_bytes())!=row['sha256']: raise ValueError('checkout inventory mismatch: '+row['path'])
                if row['path'] in outputs:
                    raw=outputs[row['path']]; row['sha256']=sha(raw)
                    if 'bytes' in row: row['bytes']=len(raw)
        existing={r['path'] for r in m['files']}
        for name,raw in outputs.items():
            if name not in existing: m['files'].append({'path':name,'sha256':sha(raw),'bytes':len(raw)})
        m['files'].sort(key=lambda r:r['path']); outputs['CODE_MANIFEST.json']=encode(m)
    return outputs


def verify(root,spec):
    for row in spec['files']:
        if sha(at(root,row['path']).read_bytes())!=row['after']: raise ValueError('installed bytes differ: '+row['path'])
    subprocess.run([sys.executable,str(HERE/'smoke_check.py'),str(root)],check=True,cwd=root,
        env={**os.environ,'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root)})


def applied_archive(root,files,spec):
    paths=sorted(set(files)-{'CODE_MANIFEST.json'})
    manifest={'format':'8agent-code/1','scope':VERSION,
              'files':[{'path':p,'sha256':sha(at(root,p).read_bytes()),'bytes':at(root,p).stat().st_size} for p in paths],
              'required_files':spec['manifest']['required_files']}
    with zipfile.ZipFile(HERE/'CODE_APPLIED.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('CODE_MANIFEST.json',encode(manifest))
        for p in paths:z.write(at(root,p),p)
    atomic(HERE/'APPLIED_CODE_MANIFEST.json',encode(manifest))


def restore(root,backup):
    record=json.loads((backup/'receipt.json').read_bytes())
    if record['root']!=str(root) or record['version']!=VERSION: raise ValueError('foreign backup')
    for row in record['files']:
        target=at(root,row['path']); actual=sha(target.read_bytes()) if target.exists() else None
        if actual not in (row['before'],row['after']): raise ValueError('code changed since backup: '+row['path'])
        if row['before'] is not None and sha(at(backup,row['path']).read_bytes())!=row['before']:
            raise ValueError('backup changed')
    for row in record['files']:
        target=at(root,row['path'])
        if row['before'] is None: target.unlink(missing_ok=True)
        else: atomic(target,at(backup,row['path']).read_bytes(),row['mode'])
    record['state']='RESTORED';atomic(backup/'receipt.json',encode(record))


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['check','apply','verify','undo'])
    p.add_argument('--root',type=Path,default=Path.home()/'DEV');p.add_argument('--backup',type=Path)
    a=p.parse_args(); root=a.root.expanduser().absolute(); at(root,'00_SYSTEM/PIPELINE.json')
    root=root.resolve(strict=True)
    top=subprocess.run(['git','-C',str(root),'rev-parse','--show-toplevel'],check=True,capture_output=True,text=True).stdout.strip()
    if Path(top).resolve()!=root:raise ValueError('existing Git checkout root required')
    spec,files=payload(); base=at(root,'08_DEPLOYMENT/GENOS/backups/search-latest-r1');base.mkdir(parents=True,exist_ok=True)
    with (base/'apply.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.action=='undo':
            if a.backup is None:p.error('--backup required')
            backup=a.backup.resolve(strict=True);backup.relative_to(base)
            restore(root,backup);print('CODE RESTORED; restart required');return
        if a.action=='verify':verify(root,spec);print('CODE VERIFIED');return
        outputs=proposed(root,spec,files)
        if a.action=='check':print('CODE CHECK PASS '+str(root));return
        pending={p:raw for p,raw in outputs.items() if not at(root,p).exists() or at(root,p).read_bytes()!=raw}
        if not pending:
            verify(root,spec)
            if not (HERE/'CODE_APPLIED.zip').exists():applied_archive(root,outputs,spec)
            print('ALREADY_APPLIED; existing backup retained');return
        backup=base/uuid.uuid4().hex;record={'version':VERSION,'root':str(root),'state':'PREPARED','files':[]}
        for name,raw in pending.items():
            target=at(root,name);before=target.read_bytes() if target.exists() else None
            mode=stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
            if before is not None:atomic(at(backup,name),before,mode)
            record['files'].append({'path':name,'before':sha(before) if before is not None else None,'after':sha(raw),'mode':mode})
        atomic(backup/'receipt.json',encode(record));print('CODE_BACKUP='+str(backup),flush=True)
        try:
            for row in record['files']:atomic(at(root,row['path']),pending[row['path']],row['mode'])
            verify(root,spec);applied_archive(root,outputs,spec)
        except BaseException:
            record['state']='FAILED';atomic(backup/'receipt.json',encode(record));restore(root,backup);raise
        record['state']='VERIFIED';atomic(backup/'receipt.json',encode(record))
        atomic(HERE/'CODE_APPLIED.json',encode({'root':str(root),'backup':str(backup),'files':list(outputs),
            'code_zip_sha256':sha((HERE/'CODE_APPLIED.zip').read_bytes())}))
        print('CODE APPLIED; selection/deployment are separate states',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('CODE_FAILED: '+str(exc),file=sys.stderr);raise SystemExit(1)
