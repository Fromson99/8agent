"""Losslessly archive verified, owned synthetic checkouts after all tests exit."""
from pathlib import Path
import hashlib,json,os,shutil,tarfile
H=Path(__file__).resolve().parent
assert json.loads((H/'SEALED.json').read_text())['version']=='GENOS_MAIN83_HOST_ASSEMBLY_20261018_R1'
assert json.loads((H/'FINAL_VERIFICATION.json').read_text())['status']=='PASS'
source=H/'pytest-runtime';out=H/'SYNTHETIC_FIXTURES.tar.gz';receipt=H/'FIXTURE_ARCHIVE.json'
assert source.is_dir() and not source.is_symlink() and not out.exists() and not receipt.exists()
def digest(stream):return hashlib.file_digest(stream,'sha256').hexdigest()
files={};links={}
for folder,dirs,names in os.walk(source,followlinks=False):
 for name in dirs+names:
  p=Path(folder)/name;key=str(p.relative_to(H))
  if p.is_symlink():links[key]=os.readlink(p)
  elif p.is_file():
   with p.open('rb') as s:files[key]={'sha256':digest(s),'bytes':p.stat().st_size}
with tarfile.open(out,'w:gz',compresslevel=6,dereference=False) as z:z.add(source,arcname=source.name)
seen=set();seen_links=set()
with tarfile.open(out,'r:gz') as z:
 for member in z:
  if member.isfile() or member.islnk():
   with z.extractfile(member) as s:assert digest(s)==files[member.name]['sha256']
   seen.add(member.name)
  elif member.issym():assert member.linkname==links[member.name];seen_links.add(member.name)
assert seen==set(files) and seen_links==set(links)
with out.open('rb') as s:archive_hash=digest(s)
value={'status':'LOSSLESS_ARCHIVE_VERIFIED','scope':'Owned synthetic GENOS checkout/TRANSFER fixtures only; no original data, user files or active runtime.',
 'archive':out.name,'archive_sha256':archive_hash,'archive_bytes':out.stat().st_size,
 'uncompressed_file_bytes':sum(r['bytes'] for r in files.values()),'files':files,'symlinks':links,
 'restore':'From this handoff directory: tar -xzf SYNTHETIC_FIXTURES.tar.gz. Verify archive SHA256 in this receipt before restoring. Original pytest-runtime relative paths and Git metadata are retained.'}
receipt.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
shutil.rmtree(source)
print(json.dumps({k:value[k] for k in ('status','archive_bytes','uncompressed_file_bytes')}))
