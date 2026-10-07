"""Backed-up file patch for the GENOS latest service/service.py loader."""
import argparse
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys

def safe(path):
    p=Path(path).absolute()
    if any(q.is_symlink() for q in (p,*p.parents)):
        raise ValueError('Symlink path: '+str(p))
    return p

def snapshot(path):
    p=safe(path)
    if not p.exists():return None
    if not p.is_file():raise ValueError('Expected regular file: '+str(p))
    return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'mode':stat.S_IMODE(p.stat().st_mode)}

def save(path,value):
    temp=path.with_suffix('.tmp')
    with temp.open('w') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def put(source,target,mode):
    safe(target);target.parent.mkdir(parents=True,exist_ok=True)
    temp=safe(target.with_name(target.name+'.genos-r3.tmp'))
    with temp.open('xb') as f:
        f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
    temp.chmod(mode);os.replace(temp,target)

def apply(root,payload,mode):
    root=safe(root);payload=safe(payload)
    manifest=json.loads(safe(payload/'CODE_MANIFEST.json').read_text())
    names=[row['path'] for row in manifest['files']]
    allowed={'service.py','service/service.py','service/__init__.py','06_TOOLS/COMMANDS/code_ship.py'}
    if set(names)!=allowed or len(names)!=len(allowed):raise ValueError('Unexpected patch scope')
    for row in manifest['files']:
        f=safe(payload/row['path'])
        if snapshot(f)['sha256']!=row['sha256'] or f.stat().st_size!=row['bytes']:
            raise ValueError('Payload hash differs: '+row['path'])
        compile(f.read_bytes(),str(f),'exec');ast.parse(f.read_bytes(),feature_version=(3,11))
    record=safe(root/'09_ARTIFACTS/BACKUPS/latest-service-entry-20261002-r3/receipt.json')
    folder=record.parent
    if mode=='undo':
        r=json.loads(safe(record).read_text())
        if r['root']!=str(root):raise ValueError('Undo receipt root differs')
        expected='before' if r['status']=='UNDONE' else 'after'
        if r['status'] not in ('APPLIED','UNDONE'):raise ValueError('Partial operation; inspect receipt')
        for name,row in r['files'].items():
            if snapshot(root/name)!=row[expected]:raise ValueError('Changed code; preserve: '+name)
            if snapshot(folder/'old'/name)!=row['before']:raise ValueError('Changed backup: '+name)
        if r['status']=='UNDONE':print('ALREADY UNDONE');return
        for name,row in r['files'].items():
            if row['before'] is None:(root/name).unlink()
            else:put(folder/'old'/name,root/name,row['before']['mode'])
        r['status']='UNDONE';save(record,r);print('UNDO OK; original four files restored');return
    for name,digest in manifest['required_v6_backend'].items():
        value=snapshot(root/name)
        if value is None or value['sha256']!=digest:
            raise ValueError('Required v6 backend differs/missing: '+name+'; apply the prior v6 code first; do not rebuild data')
    print('V6_BACKEND 5 required code dependencies verified')
    if record.exists():
        r=json.loads(record.read_text())
        if r['root']!=str(root):raise ValueError('Receipt root differs')
        if r['status']=='APPLIED' and all(snapshot(root/n)==v['after'] for n,v in r['files'].items()):
            print('ALREADY APPLIED; exact entry/backend bytes verified');return
        raise ValueError('Existing operation requires inspection; '+str(record))
    for name in names:
        current=root/name
        if current.exists() and name in ('service.py','service/service.py'):
            tree=ast.parse(safe(current).read_bytes())
            functions={n.name for n in tree.body if isinstance(n,ast.AsyncFunctionDef)}
            if 'service' not in functions and snapshot(current)['sha256']!=snapshot(payload/name)['sha256']:
                raise ValueError('Existing entry is not the known service protocol: '+name)
    rows={n:{'before':snapshot(root/n),'after':{'sha256':snapshot(payload/n)['sha256'],
         'mode':(snapshot(root/n) or {'mode':0o644})['mode']}} for n in names}
    print('PLAN: update root v6 compatibility source + latest service package + packaging allowlist')
    print('PLAN: main.py, data, NFS runtime, CURRENT, environment and engine pins preserved')
    if mode=='check':print('CHECK OK; no code changed');return
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name,row in rows.items():
        if row['before']:
            dest=safe(folder/'old'/name);dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(root/name,dest)
            if snapshot(dest)!=row['before']:raise ValueError('Backup differs: '+name)
    r={'root':str(root),'status':'PREPARED','files':rows,'generation':'KEEP_ONSITE_UNVERIFIED',
       'code_serving_revision':None,'onsite_success':False}
    save(record,r)
    changed=[]
    try:
        for name,row in rows.items():
            if snapshot(root/name)!=row['before']:raise ValueError('Concurrent edit: '+name)
            put(payload/name,root/name,row['after']['mode']);changed.append(name)
        if any(snapshot(root/n)!=v['after'] for n,v in rows.items()):raise ValueError('Installed hash differs')
    except BaseException:
        for name in reversed(changed):
            row=rows[name]
            if snapshot(root/name)!=row['after']:
                r['status']='FAILED_CONCURRENT_EDIT';save(record,r);raise
            if row['before'] is None:(root/name).unlink()
            else:put(folder/'old'/name,root/name,row['before']['mode'])
        r['status']='ROLLED_BACK';save(record,r);raise
    r['status']='APPLIED';save(record,r)
    print('APPLY OK: service/service.py now delegates to maintained v6 runtime')
    print('RECEIPT='+str(record))
    for name in ('service.py','service/service.py'):
        print('ENTRY_SHA256 '+name+' '+snapshot(root/name)['sha256'])

if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('check','apply','undo'))
    p.add_argument('--root',type=Path,required=True);p.add_argument('--payload',type=Path,required=True)
    a=p.parse_args();root=safe(a.root)
    if not (root/'02_BACKEND').is_dir() or not (root/'service.py').is_file():raise ValueError('Select existing DEV root')
    with safe(root/'.genos-code-replacement.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print('PYTHON='+sys.executable+' VERSION='+sys.version.replace('\n',' '),flush=True)
        apply(root,a.payload,a.mode)
