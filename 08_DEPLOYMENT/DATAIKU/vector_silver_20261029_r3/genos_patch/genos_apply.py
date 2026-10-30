"""Apply only the compact-vector modules and their engine pins to a Git checkout."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def body(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def file_at(root,name):
    p=root/name
    if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('UNSAFE_PATH: '+name)
    return p

def plan(root):
    manifest=json.loads((HERE/'PATCH_MANIFEST.json').read_text())
    changes={}
    for name,row in manifest['code'].items():
        source=HERE/name;dest=file_at(root,name)
        if sha(source)!=row['after'] or sha(dest) not in (row['before'],row['after'],*row.get('compatible_before',[])):
            raise ValueError('CODE_VERSION_MISMATCH: '+name)
        ast.parse(source.read_bytes(),filename=name)
        changes[name]=source.read_bytes()
    # Check every current engine pin, then change only pins for these changed files.
    cache={}
    for path in sorted((root/'02_BACKEND/ENGINES').rglob('*.json')):
        value=json.loads(path.read_text())
        if not isinstance(value.get('files'),dict):continue
        changed=False
        for name,expected in value['files'].items():
            actual=cache.setdefault(name,sha(file_at(root,name)))
            if name in manifest['code']:
                if expected not in (manifest['code'][name]['before'],manifest['code'][name]['after'],*manifest['code'][name].get('compatible_before',[])):
                    raise ValueError('ENGINE_CODE_VERSION_MISMATCH: '+name)
                value['files'][name]=manifest['code'][name]['after'];changed=True
            elif actual!=expected:
                raise ValueError('EXISTING_ENGINE_PIN_DRIFT: '+name)
        if changed:changes[str(path.relative_to(root))]=body(value)
    pipeline=file_at(root,'00_SYSTEM/PIPELINE.json')
    value=json.loads(pipeline.read_text())
    for row in value['engines'].values():
        name=row['manifest'];actual=sha(file_at(root,name))
        if actual!=row['sha256']:raise ValueError('EXISTING_PIPELINE_PIN_DRIFT: '+name)
        if name in changes:row['sha256']=hashlib.sha256(changes[name]).hexdigest()
    changes['00_SYSTEM/PIPELINE.json']=body(value)
    return {n:b for n,b in changes.items() if file_at(root,n).read_bytes()!=b}

def apply(root,mode):
    root=root.resolve(strict=True)
    top=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=root,text=True).strip()
    if top!=str(root):raise ValueError('GIT_CHECKOUT_ROOT_REQUIRED')
    changes=plan(root)
    print('COMPACT_CODE_CHECK',mode,'files',len(changes),'root',str(root),flush=True)
    if mode=='check' or not changes:return
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True).strip():
        raise ValueError('PRESERVE_EXISTING_TRACKED_CHANGES_BEFORE_APPLY')
    backup=Path(tempfile.mkdtemp(prefix='vector-compact-backup-',dir=root.parent))
    receipt={'root':str(root),'before':{},'after':{},'created_at':time.time(),
             'git_commit_before':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
             'query_release_id':None,'genos_revision':None,'field_verified':False}
    for name,data in changes.items():
        src=file_at(root,name);dst=backup/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        receipt['before'][name]=sha(src);receipt['after'][name]=hashlib.sha256(data).hexdigest()
    (backup/'RECEIPT.json').write_bytes(body(receipt))
    try:
        for name,data in changes.items():file_at(root,name).write_bytes(data)
        if plan(root):raise ValueError('POST_APPLY_HASH_MISMATCH')
        subprocess.run(['git','diff','--check'],cwd=root,check=True)
    except BaseException:
        for name in changes:shutil.copyfile(backup/name,file_at(root,name))
        raise
    print('CODE_BYTES_AND_PINS_VERIFIED; BACKUP',str(backup),flush=True)
    print('실제 checkout에서 commit/push 및 동일 commit 리비전 배포와 Oracle/워크플로우 검증은 별도입니다.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['check','apply']);parser.add_argument('checkout',type=Path)
    args=parser.parse_args();apply(args.checkout,args.mode)
