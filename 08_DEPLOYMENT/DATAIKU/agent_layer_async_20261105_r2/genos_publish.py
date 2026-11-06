"""Publish only the verified files of the selected new pipeline checkout."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

def git(root,*args,check=True):
    return subprocess.run(['git','-C',str(root),*args],check=check,stdout=subprocess.PIPE).stdout

def main(root,remote):
    root=Path(root).resolve(strict=True)
    if not remote or remote.startswith('-') or remote not in git(root,'remote').decode().splitlines():
        raise SystemExit('NEW_PIPELINE_REMOTE_REQUIRED')
    branch=git(root,'symbolic-ref','--short','HEAD').decode().strip()
    if git(root,'diff','--cached','--name-only','-z'):
        raise SystemExit('PRESERVE_EXISTING_STAGED_CHANGES')
    with zipfile.ZipFile('GENOS_AGENT_ASYNC_R2.zip') as z:
        pins=json.loads(z.read('CODE_PINS.json'))['files']
        pins['CODE_PINS.json']=hashlib.sha256(z.read('CODE_PINS.json')).hexdigest()
    # Never publish an unrelated tracked edit. On a new checkout a committed template
    # may exist. Conflicting member paths are refused by the installer.
    changed=set(git(root,'diff','--name-only','-z').decode().split('\0'))-{''}
    if changed-set(pins):raise SystemExit('UNRELATED_TRACKED_CHANGES')
    for name,sha in pins.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise SystemExit('CHECKOUT_CHANGED:'+name)
    subprocess.run(['git','-C',str(root),'add','-f','--pathspec-from-file=-','--pathspec-file-nul'],
                   input=b'\0'.join(n.encode() for n in pins)+b'\0',check=True)
    staged=set(git(root,'diff','--cached','--name-only','-z').decode().split('\0'))-{''}
    if staged-set(pins):raise SystemExit('UNRELATED_INDEX_CHANGES')
    if staged:
        subprocess.run(['git','-C',str(root),'commit','-m','Install GENOS Agent Layer pipeline R2'],check=True)
    commit=git(root,'rev-parse','HEAD').decode().strip()
    # Compare committed blob bytes with the release, including files affected by git filters.
    ls=git(root,'ls-tree','-rz',commit)
    blobs={s.split(b'\t',1)[1].decode():s.split(b'\t',1)[0].split()[-1] for s in ls.split(b'\0') if s}
    unique={blobs[n] for n in pins}
    payload=subprocess.run(['git','-C',str(root),'cat-file','--batch'],input=b'\n'.join(unique)+b'\n',capture_output=True,check=True).stdout
    import io
    stream=io.BytesIO(payload)
    verified={}
    for _ in unique:
        oid,kind,length=stream.readline().split()
        if kind!=b'blob':raise ValueError('COMMIT_MEMBER_TYPE')
        verified[oid]=hashlib.sha256(stream.read(int(length))).hexdigest()
        if stream.read(1)!=b'\n':raise ValueError('COMMIT_READ')
    if any(verified[blobs[n]]!=h for n,h in pins.items()):raise SystemExit('COMMIT_HASH_MISMATCH')
    ref='refs/heads/'+branch
    git(root,'push',remote,commit+':'+ref)
    if git(root,'ls-remote','--heads',remote,ref).decode().split()[:1]!=[commit]:
        raise SystemExit('REMOTE_SHA_NOT_CONFIRMED')
    print('GENOS_CODE_PUSHED',branch,commit,'pin',pins['CODE_PINS.json'])
    print('GENOS 화면에서 이 커밋의 새 코드서빙 리비전을 배포하세요.')

if __name__=='__main__':main(sys.argv[1],sys.argv[2])
