#!/usr/bin/env python3
"""Verify exact MAIN112 baseline/candidate; apply only declared changed code."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def safe(root,name):
    p=root/name
    if not p.resolve().is_relative_to(root) or p.is_symlink():
        raise ValueError('unsafe target path: '+name)
    return p


def apply(root,package,mutate=False):
    root=Path(root).resolve(strict=True);package=Path(package).resolve(strict=True)
    manifest=json.loads((package/'CODE_MANIFEST.json').read_text())
    for name,expected in manifest['files'].items():
        p=safe(package,name)
        if not p.is_file() or sha(p)!=expected:raise ValueError('delivery hash mismatch: '+name)
    writes=[]
    for name,after in manifest['serving_files'].items():
        p=safe(root,name);current=sha(p) if p.is_file() else None
        if current==after:continue
        change=manifest['changed'].get(name)
        if change is None or current!=change['before']:
            raise ValueError('baseline differs; no files changed: '+name)
        writes.append(name)
    if not mutate:return {'status':'VERIFIED','changes':len(writes)}
    if not writes:return {'status':'ALREADY_APPLIED','changes':0}
    with (root/'.genos-storage-install.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Repeat all preflight checks under the installer lock.
        apply(root,package,False)
        backup=root/'.genos-storage-code-backups'/uuid.uuid4().hex
        backup.mkdir(parents=True)
        receipt={'delivery_id':manifest['delivery_id'],'target':str(root),'before':{},
                 'after':{},'field_deployed':False}
        done=[]
        try:
            for name in writes:
                target=safe(root,name);original=sha(target) if target.exists() else None
                if original!=manifest['changed'][name]['before']:raise ValueError('target changed during install: '+name)
                receipt['before'][name]=original
                if target.exists():
                    copy=backup/name;copy.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,copy)
                target.parent.mkdir(parents=True,exist_ok=True)
                temporary=target.with_name('.'+target.name+'.storage-'+uuid.uuid4().hex)
                try:
                    shutil.copy2(package/name,temporary)
                    with temporary.open('rb') as stream:os.fsync(stream.fileno())
                    os.replace(temporary,target)
                finally:temporary.unlink(missing_ok=True)
                done.append(name);receipt['after'][name]=sha(target)
            for name,expected in manifest['serving_files'].items():
                if sha(safe(root,name))!=expected:raise ValueError('installed hash differs: '+name)
        except BaseException:
            for name in reversed(done):
                target=safe(root,name)
                if receipt['before'][name] is None:target.unlink()
                else:shutil.copy2(backup/name,target)
            receipt['status']='ROLLED_BACK'
            (backup/'receipt.json').write_text(json.dumps(receipt,indent=2))
            raise
        receipt['status']='CODE_APPLIED'
        (backup/'receipt.json').write_text(json.dumps(receipt,indent=2))
        return {'status':'CODE_APPLIED','changes':len(writes),'receipt':str(backup/'receipt.json'),
                'field_deployed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True,type=Path)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    print(json.dumps(apply(args.root,Path(__file__).with_name('package'),args.apply),ensure_ascii=False))
