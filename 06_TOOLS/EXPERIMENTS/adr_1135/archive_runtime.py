from common import *
import os,tarfile,shutil,hashlib
runtime=ART/'run-001/scenario/runtime';archive=ART/'runtime-native.tar.gz'
assert runtime.is_dir() and not archive.exists()
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:args=p.read_bytes().split(b'\0')
 except (OSError,PermissionError):continue
 if args and b'python' in args[0] and any(b'06_TOOLS/EXPERIMENTS/adr_1135/' in a and a.endswith((b'/native.py',b'/direct.py')) for a in args):raise RuntimeError('Model/runtime process still active')
files=[p for p in runtime.rglob('*') if p.is_file()];assert not any(p.is_symlink() for p in runtime.rglob('*'))
rows=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname=str(runtime.relative_to(ROOT)))
with tarfile.open(archive,'r:gz') as t:
 for r in rows:
  with t.extractfile(r['path']) as handle:assert hashlib.file_digest(handle,'sha256').hexdigest()==r['sha256']
receipt={'scope':'Completed request-local runtime only; raw model payloads, result, source generation and active release retained separately','archive_path':str(archive.relative_to(ROOT)),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'original_bytes':sum(r['bytes'] for r in rows),'files':rows,'restore_command':'tar -xzf '+str(archive.relative_to(ROOT))+' -C /home/jin/8-AGENT','verified_member_hashes':len(rows)}
put(ART/'runtime-archive.json',receipt);shutil.rmtree(runtime);print('Archived verified runtime',len(rows),receipt['original_bytes'],'->',receipt['archive_bytes'])
