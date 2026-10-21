from pathlib import Path
import hashlib,json,tarfile,shutil,time
R=Path(__file__).resolve().parents[3];D=R/'09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance/test-scratch-archives';D.mkdir(exist_ok=True)
roots=[Path('/tmp')/n for n in ['adr0840-baseline-existing','adr0840-budget-r2','adr0840-contracts-r1','adr0840-contracts-r2','adr0840-focused-r1','adr0840-focused-r2','adr0840-new-r2','adr0841-contracts-r1','adr0841-direct-r1','adr0841-direct-r2','adr0841-direct-r3','adr0841-final','adr0842-working']]
assert all(p.is_dir() and not p.is_symlink() for p in roots)
archive=D/'adr0840-0842-test-scratch.tar.gz';assert not archive.exists()
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
files={};links={};start=time.monotonic()
for root in roots:
 for p in root.rglob('*'):
  n=str(p.relative_to('/tmp'))
  if p.is_symlink():links[n]=str(p.readlink())
  elif p.is_file():files[n]={'sha256':sha(p),'bytes':p.stat().st_size}
with tarfile.open(archive,'w:gz',compresslevel=1,dereference=False) as t:
 for p in roots:t.add(p,arcname=p.name,recursive=True)
seen=set()
with tarfile.open(archive,'r:gz') as t:
 for m in t:
  if m.isfile():
   with t.extractfile(m) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==files[m.name]['sha256']
   seen.add(m.name)
  elif m.issym():assert m.linkname==links[m.name]
assert seen==set(files)
# Check that no writer changed a fixture after the archived snapshot.
for n,v in files.items():assert sha(Path('/tmp')/n)==v['sha256']
receipt={'archive':str(archive.relative_to(R)),'sha256':sha(archive),'archive_bytes':archive.stat().st_size,'original_file_bytes':sum(v['bytes'] for v in files.values()),'files':files,'symlinks':links,'verification':'Every archived file hash matched original; originals rechecked before removal. Includes failed fixtures; product/model journals are elsewhere and untouched.','restore':'python tarfile or tar -xzf '+str(archive)+' -C /tmp; restore only when listed /tmp directories do not exist.','seconds':time.monotonic()-start,'originals_removed':False}
p=D/'adr0840-0842-test-scratch.json';p.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
for root in roots:shutil.rmtree(root)
receipt['originals_removed']=True;p.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ('files','symlinks')}),flush=True)
