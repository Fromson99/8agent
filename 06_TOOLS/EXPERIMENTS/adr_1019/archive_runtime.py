"""Losslessly archive stopped native research runtime; retain public result files."""
from common import *
import tarfile,hashlib,shutil

assert read(ART/'resource-run-001.json')['returncode']==0
assert read(RUN/'result.json')['complete']
runtime=RUN/'agent_layer/runtime';archive=RUN/'agent_layer/native-runtime.tar.gz'
receipt=RUN/'agent_layer/native-runtime-archive.json'
assert runtime.is_dir() and not archive.exists() and not receipt.exists()
files=sorted(p for p in runtime.rglob('*') if p.is_file())
members=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
with tarfile.open(archive,'w:gz',compresslevel=6) as out:
    for p in files:out.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
with tarfile.open(archive,'r:gz') as inp:
    for entry in members:
        f=inp.extractfile(entry['path']);assert f is not None
        assert hashlib.file_digest(f,'sha256').hexdigest()==entry['sha256']
        assert inp.getmember(entry['path']).size==entry['bytes']
put(receipt,{'schema_version':'lossless-native-runtime-archive-v1','reason':'Native experiment exited successfully; preserve original logs/state with hashes and remove verified uncompressed duplicate',
 'archive':str(archive.relative_to(ROOT)),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,
 'original_bytes':sum(x['bytes'] for x in members),'members':members,'all_members_verified':True,
 'restore_from_repository_root':'tar -xzf '+str(archive.relative_to(ROOT)),
 'limitations':'No logs deleted without lossless archived copy. Restoring these paths is required before rerunning audit.py. Gold knowledge stores and answer/input/output files remain directly available.'})
# These are now byte-verified redundant copies, scoped to this stopped run.
shutil.rmtree(runtime)
print(json.dumps({'files':len(members),'before_bytes':sum(x['bytes'] for x in members),'archive_bytes':archive.stat().st_size}))
