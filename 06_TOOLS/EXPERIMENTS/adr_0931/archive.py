"""Lossless compression of only this experiment's closed raw records."""
from pathlib import Path
import hashlib,json,tarfile
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0931-general-research-evidence-update';O=A/'artifacts/run-001'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for P in sorted(O.glob('*/*')):
 if not (P/'audit.json').exists():continue
 files=[p for folder in ('raw','runtime') for p in (P/folder).rglob('*') if p.is_file()]
 archive=P/'raw-runtime.tar.gz'
 if archive.exists():continue
 rows=[{'path':str(p.relative_to(P)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
 with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
  for p in files:tar.add(p,arcname=str(p.relative_to(P)),recursive=False)
 with tarfile.open(archive,'r:gz') as tar:
  for row in rows:
   with tar.extractfile(row['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
 receipt={'archive':archive.name,'archive_sha256':sha(archive),'original_bytes':sum(r['bytes'] for r in rows),'compressed_bytes':archive.stat().st_size,'members':rows,'verified_lossless':True,'restore':'From this case folder: tar -xzf raw-runtime.tar.gz; paths are relative and preserve every raw request, response and runtime database.'}
 (P/'archive-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 for p in files:p.unlink()
 print(P.name,receipt['original_bytes'],receipt['compressed_bytes'],flush=True)
