from pathlib import Path
import hashlib,json,tarfile,sys
R=Path(__file__).resolve().parents[3];A=R/sys.argv[1]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for P in sorted((A/'artifacts/run-001').glob('*/*')):
 if not P.is_dir():continue
 assert (A/f'artifacts/resource-{P.parent.name}-{P.name}.json').exists(),'worker must have completed'
 archive=P/'raw-runtime.tar.gz'
 if archive.exists():continue
 files=[p for p in (P/'runtime').rglob('*') if p.is_file()]+[p for t in P.iterdir() if t.is_dir() and t.name!='runtime' for p in (t/'raw').rglob('*') if p.is_file()]
 if not files:continue
 rows=[{'path':str(p.relative_to(P)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
 with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
  for p in files:tar.add(p,arcname=str(p.relative_to(P)),recursive=False)
 with tarfile.open(archive,'r:gz') as tar:
  for row in rows:
   with tar.extractfile(row['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
 out={'archive':archive.name,'sha256':sha(archive),'original_bytes':sum(x['bytes'] for x in rows),'compressed_bytes':archive.stat().st_size,'members':rows,'verified_lossless':True,'restore':'From this scenario directory: tar -xzf raw-runtime.tar.gz. Restores every original path; verify member hashes from this receipt.'}
 (P/'archive-manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 for p in files:p.unlink()
 print(P.parent.name,P.name,out['original_bytes'],out['compressed_bytes'])
