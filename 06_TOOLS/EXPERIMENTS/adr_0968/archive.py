"""Compress this experiment's closed raw records; verify every byte before removal."""
from common import *
import tarfile,os

for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:args=p.read_bytes().split(b'\0')
    except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    assert not any(x.endswith(b'/adr_0968/live.py') for x in args), 'Live worker still running'
assert (RUN/'result.json').exists()
archive=RUN/'closed-records.tar.gz';receipt=RUN/'archive-manifest.json'
assert not archive.exists() and not receipt.exists(),'Archive is immutable; do not overwrite'
files=sorted([p for p in (RUN/'runtime').rglob('*') if p.is_file()]+[p for folder in RUN.glob('cm-*/raw') for p in folder.rglob('*') if p.is_file()])
rows=[{'path':str(p.relative_to(RUN)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
with tarfile.open(archive,'w:gz',compresslevel=6) as t:
    for p in files:t.add(p,arcname=str(p.relative_to(RUN)),recursive=False)
with tarfile.open(archive,'r:gz') as t:
    for row in rows:
        with t.extractfile(row['path']) as content:assert hashlib.file_digest(content,'sha256').hexdigest()==row['sha256'],row['path']
put(receipt,{'schema_version':'verified-lossless-archive-v1','archive':archive.name,'archive_sha256':sha(archive),
    'original_bytes':sum(r['bytes'] for r in rows),'compressed_bytes':archive.stat().st_size,'verified_lossless':True,
    'restore':'From artifacts/run-001: tar -xzf closed-records.tar.gz. Verify restored paths against members SHA256.',
    'members':rows})
for p in files:p.unlink()
for p in sorted([p for p in RUN.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True):
    if not any(p.iterdir()):p.rmdir()
print(json.dumps({k:v for k,v in read(receipt).items() if k!='members'}))
