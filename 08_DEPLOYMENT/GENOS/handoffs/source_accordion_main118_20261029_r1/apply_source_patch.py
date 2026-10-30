#!/usr/bin/env python3
"""Apply the verified MAIN117 -> MAIN118 display change, with exact rollback."""
import argparse,fcntl,hashlib,json,os,shutil,uuid
from pathlib import Path,PurePosixPath

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def safe(root,name):
 pure=PurePosixPath(name)
 if pure.is_absolute() or '..' in pure.parts or str(pure)!=name or '\\' in name:raise ValueError('Unsafe path')
 p=root/name
 if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('Unsafe target: '+name)
 return p
def write_json(p,data):
 with p.open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2)
def atomic(source,target):
 temporary=target.with_name('.'+target.name+'.source-'+uuid.uuid4().hex)
 try:
  shutil.copy2(source,temporary)
  with temporary.open('rb') as f:os.fsync(f.fileno())
  os.replace(temporary,target)
 finally:temporary.unlink(missing_ok=True)
def verify(root,package,installed=False):
 manifest=read(package/'CODE_MANIFEST.json');pending=[]
 for row in manifest['files']:
  name=row['path'];after=row['sha256'];source=safe(package,name);target=safe(root,name)
  if not source.is_file() or sha(source)!=after:raise ValueError('Package hash mismatch: '+name)
  current=sha(target) if target.is_file() else None
  if current==after:continue
  if installed or current!=manifest['baseline_files'][name]:raise ValueError('Checkout differs from MAIN117/118; no install: '+name)
  pending.append(name)
 return manifest,pending
def run(root,package,mode='check',receipt=None):
 root=Path(root).resolve(strict=True);package=Path(package).resolve(strict=True)
 if mode=='check':
  _,pending=verify(root,package);return {'status':'VERIFIED','changes':pending}
 if mode=='verify':
  verify(root,package,True);return {'status':'INSTALLED_BYTES_VERIFIED','field_deployed':False}
 with (root/'.genos-source-install.lock').open('a+b') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if mode=='rollback':
   receipt=Path(receipt).resolve(strict=True)
   if not receipt.is_relative_to(root/'.genos-source-backups'):raise ValueError('Receipt is outside target backup')
   r=read(receipt);backup=receipt.parent
   if r['target']!=str(root) or r['status']!='CODE_APPLIED':raise ValueError('Receipt differs')
   for name,h in r['after'].items():
    if sha(safe(root,name))!=h or sha(safe(backup,name))!=r['before'][name]:raise ValueError('Changed after install; rollback refused')
   for name in r['before']:atomic(safe(backup,name),safe(root,name))
   out={'status':'ROLLED_BACK','receipt':str(receipt),'files':r['before'],'field_deployed':False}
   write_json(backup/'rollback.json',out);return out
  manifest,pending=verify(root,package)
  if not pending:return {'status':'ALREADY_APPLIED','changes':[],'field_deployed':False}
  backup=root/'.genos-source-backups'/uuid.uuid4().hex;backup.mkdir(parents=True)
  r={'status':'CODE_APPLIED','target':str(root),'release_id':manifest['release_id'],'before':{},'after':{},'field_deployed':False};done=[]
  try:
   for name in pending:
    target=safe(root,name);copy=safe(backup,name);copy.parent.mkdir(parents=True,exist_ok=True)
    if sha(target)!=manifest['baseline_files'][name]:raise ValueError('Concurrent target change')
    shutil.copy2(target,copy);r['before'][name]=sha(copy)
   for name in pending:
    if sha(safe(root,name))!=r['before'][name]:raise ValueError('Concurrent target change')
    atomic(safe(package,name),safe(root,name));done.append(name);r['after'][name]=sha(safe(root,name))
   verify(root,package,True);write_json(backup/'receipt.json',r)
  except BaseException:
   for name in reversed(done):atomic(safe(backup,name),safe(root,name))
   r['status']='INSTALL_FAILED_RESTORED';write_json(backup/'failure.json',r);raise
  return {'status':'CODE_APPLIED','changes':pending,'receipt':str(backup/'receipt.json'),'field_deployed':False}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['check','apply','verify','rollback']);p.add_argument('--root',type=Path,default=Path.home()/'DEV');p.add_argument('--receipt',type=Path)
 a=p.parse_args()
 if a.mode=='rollback' and a.receipt is None:p.error('--receipt required for rollback')
 print(json.dumps(run(a.root,Path(__file__).resolve().parent/'package',a.mode,a.receipt),ensure_ascii=False))
