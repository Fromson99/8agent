"""Only after a worker exits: retain exact audit DB bytes without their full allocation."""
from pathlib import Path
import json,gzip,hashlib,argparse,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion'
p=argparse.ArgumentParser();p.add_argument('--arm',required=True);p.add_argument('--case',required=True);args=p.parse_args()
d=A/'artifacts'/('regression' if args.case.startswith('REG-') else 'run-001')/args.arm/args.case;rows=[]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
assert (d/'result.json').is_file()
for p in (d/'runtime').rglob('*.sqlite'):
 if p.name not in ('journal.sqlite','cases-v4.sqlite'):continue
 assert not any(Path(str(p)+s).exists() for s in ('-wal','-journal'))
 target=p.with_suffix('.sqlite.gz');assert not target.exists();h=hashlib.sha256();before=p.stat()
 with p.open('rb') as src,gzip.open(target,'wb',compresslevel=6) as out:
  for b in iter(lambda:src.read(8*1024*1024),b''):h.update(b);out.write(b)
 original=h.hexdigest();h=hashlib.sha256();size=0
 with gzip.open(target,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b);size+=len(b)
 assert size==before.st_size and h.hexdigest()==original and before.st_mtime_ns==p.stat().st_mtime_ns
 row={'path':str(p.relative_to(R)),'uncompressed_sha256':original,'uncompressed_bytes':size,'archive_path':str(target.relative_to(R)),'archive_sha256':sha(target),'archive_bytes':target.stat().st_size,'verified_lossless':True};rows.append(row)
 # Write the restore receipt durably before releasing the original allocation.
 receipt=d/'runtime-archives.json';receipt.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 with receipt.open('rb') as f:os.fsync(f.fileno())
 p.unlink()
print('ARCHIVE',args.case,'raw MiB',round(sum(x['uncompressed_bytes'] for x in rows)/1048576),'stored MiB',round(sum(x['archive_bytes'] for x in rows)/1048576),flush=True)
