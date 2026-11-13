"""ADR-1509: pack a finished request's runtime folder (local SQLite records) losslessly to save disk.

Run only after the request process exited. Every file's SHA256 is recorded, the archive is re-read and
each member compared, and only then the folder is removed. Restore: tar -xzf runtime.tar.gz -C <case folder>."""
from common import *
import tarfile,shutil
def _sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def archive(folder):
    folder=Path(folder);src=folder/'runtime';dest=folder/'runtime.tar.gz'
    if not src.is_dir() or dest.exists():return None
    files={};links={};total=0
    for p in sorted(src.rglob('*')):
        r=str(p.relative_to(folder))
        if p.is_symlink():links[r]=os.readlink(p)
        elif p.is_file():files[r]=_sha(p);total+=p.stat().st_size
    tmp=folder/'.runtime.tar.gz.partial'
    with tarfile.open(tmp,'w:gz',compresslevel=6) as t:t.add(src,arcname='runtime')
    seen={}
    with tarfile.open(tmp,'r:gz') as t:
        for m in t:
            if m.isfile():
                h=hashlib.sha256();f=t.extractfile(m)
                for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
                seen[m.name]=h.hexdigest()
            elif m.issym():seen[m.name]=('link',m.linkname)
    assert {k:v for k,v in seen.items() if not isinstance(v,tuple)}==files,'archive members differ from the folder'
    assert {k:v[1] for k,v in seen.items() if isinstance(v,tuple)}==links,'archive links differ'
    os.replace(tmp,dest)
    receipt={'archive':dest.name,'archive_sha256':_sha(dest),'archive_bytes':dest.stat().st_size,'original_bytes':total,
             'files':len(files),'symlinks':len(links),'file_sha256':files,'verified_by_reread':True,
             'restore':'tar -xzf runtime.tar.gz -C <case folder>'}
    put(folder/'runtime.archive.json',receipt);shutil.rmtree(src)
    return {k:receipt[k] for k in ('archive_bytes','original_bytes','files')}
if __name__=='__main__':
    print(archive(sys.argv[1]))
