"""Apply one verified GENOS display file to the existing checkout, with rollback."""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path

def sha(p):
    digest=hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['check','apply','rollback'])
    parser.add_argument('--root',type=Path,default=Path.home()/'DEV');args=parser.parse_args()
    package=Path(__file__).resolve().parent;root=args.root.resolve(strict=True)
    actual=Path(subprocess.check_output(['git','-C',str(root),'rev-parse','--show-toplevel'],text=True).strip()).resolve()
    if actual!=root:raise ValueError('Target must be the existing Git root')
    manifest=json.loads((package/'payload/CODE_MANIFEST.json').read_text())
    row=manifest['files'][0];target=root/row['path'];target.resolve(strict=True).relative_to(root)
    original=row['previous_sha256'];updated=row['sha256'];payload=package/'payload'/row['path']
    if target.is_symlink() or sha(payload)!=updated:raise ValueError('Symlink or payload mismatch')
    compile(payload.read_bytes(),str(payload),'exec')
    current=sha(target)
    if current not in (original,updated):raise ValueError('Existing file differs from verified MAIN134; preserve it and review differences')
    backup=root/'09_ARTIFACTS/GENOS_PATCH_BACKUPS/source-display-20261103-r1/original.py'
    if args.operation=='rollback':
        if current==original:print('ALREADY_ORIGINAL');return
        if not backup.is_file() or sha(backup)!=original:raise ValueError('Original backup missing or changed')
        content=backup.read_bytes();expected=original
    else:
        for dependency in manifest['required_files']:
            path=root/dependency['path'];path.resolve(strict=True).relative_to(root)
            if path.is_symlink() or sha(path)!=dependency['sha256']:raise ValueError('Verified dependency differs: '+dependency['path'])
        if args.operation=='check':print('CHECK_PASS; target='+str(root)+'; current='+current);return
        if current==updated:print('ALREADY_APPLIED');return
        backup.parent.mkdir(parents=True,exist_ok=True)
        if backup.exists():
            if sha(backup)!=original:raise ValueError('Backup collision')
        else:
            with backup.open('xb') as stream:stream.write(target.read_bytes());stream.flush();os.fsync(stream.fileno())
        content=payload.read_bytes();expected=updated
    fd,name=tempfile.mkstemp(prefix='.source-display-',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,target.stat().st_mode & 0o777);os.replace(name,target)
    finally:
        if os.path.exists(name):os.unlink(name)
    if sha(target)!=expected:raise ValueError('Applied bytes mismatch')
    print(args.operation.upper()+'_PASS; sha256='+expected+'; backup='+str(backup))

if __name__=='__main__':main()
