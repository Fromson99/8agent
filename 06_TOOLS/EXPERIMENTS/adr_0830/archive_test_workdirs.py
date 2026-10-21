"""Losslessly compress reproducible test directories; verify every file before removal."""
from pathlib import Path
import hashlib,json,os,shutil,tarfile,time
R=Path(__file__).resolve().parents[3];A=R/'09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance';W=A/'test-workdirs'
archive=A/'TEST_WORKDIRS.tar.gz';manifest=A/'TEST_ARCHIVE_MANIFEST.json'
assert not archive.exists() and not manifest.exists()
# All qualification and working consumers must have finished first.
q=R/'04_EXPERIMENTS/ADR/ADR-0830-comparison-main-confirmation/artifacts'
assert json.loads((q/'active-consumer-v2.json').read_text())['status']=='PASS'
assert '58 passed' in (q/'working-api.log').read_text()
# Relocate the final RAM-backed working run before archival; no live tests now.
tmp=Path('/tmp/adr0830-working-api')
if tmp.exists():
 assert not (W/tmp.name).exists();shutil.move(str(tmp),str(W/tmp.name))
rows=[];dirs=[p for p in W.iterdir() if p.is_dir() and not p.is_symlink() and p.name.startswith(('adr082','adr0830'))]
def filehash(p):
 h=hashlib.sha256()
 with p.open('rb') as s:
  for block in iter(lambda:s.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
for d in sorted(dirs):
 for p in sorted(d.rglob('*')):
  n=str(p.relative_to(A))
  if p.is_symlink():rows.append({'path':n,'symlink':os.readlink(p)})
  elif p.is_file():rows.append({'path':n,'bytes':p.stat().st_size,'sha256':filehash(p)})
with tarfile.open(archive,'w:gz',compresslevel=1,dereference=False) as tar:
 for d in sorted(dirs):tar.add(d,arcname=str(d.relative_to(A)))
by={r['path']:r for r in rows};seen=set()
with tarfile.open(archive,'r:gz') as tar:
 for member in tar:
  if member.isdir():continue
  row=by[member.name];seen.add(member.name)
  if member.issym():assert row['symlink']==member.linkname
  elif member.islnk():
   source=tar.extractfile(member);h=hashlib.sha256()
   for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
   assert h.hexdigest()==row['sha256']
  else:
   assert member.isfile() and member.size==row['bytes'];source=tar.extractfile(member);h=hashlib.sha256()
   for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
   assert h.hexdigest()==row['sha256']
assert seen==set(by)
value={'archive':str(archive.relative_to(R)),'sha256':filehash(archive),'bytes':archive.stat().st_size,'original_bytes':sum(r.get('bytes',0) for r in rows),'verified_file_count':len(rows),'files':rows,'restoration':'From repository root: tar -xzf '+str(archive.relative_to(R))+' -C '+str(A.relative_to(R)),'originals':'All original/failure files retained losslessly in archive; only verified redundant test working directories removed. Real dataset and runtime records outside test-workdirs untouched.'}
manifest.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
for d in dirs:shutil.rmtree(d)
print(json.dumps({k:v for k,v in value.items() if k!='files'},ensure_ascii=False))
