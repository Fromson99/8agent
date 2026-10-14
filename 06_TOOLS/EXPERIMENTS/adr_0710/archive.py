"""Lossless archive of completed generated raw records, verified before dedup."""
from pathlib import Path
import hashlib,json,tarfile,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0710-grounded-entry-profile-bound-main';O=A/'artifacts/run-001'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert len(list(O.glob('*/*/result.json')))==6 and (O/'result.json').exists()
roots=[p for arm in ('baseline','integrated') for case in ('H01','H02','H03') for p in (O/arm/case/'provider',O/arm/case/'runtime',O/arm/case/'binding-runtime')]
files=[p for root in roots for p in sorted(root.rglob('*')) if p.is_file()]
assert all(not p.is_symlink() for p in files)
rows=[{'path':str(p.relative_to(O)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
archive=O/'raw.tar.gz';assert not archive.exists()
with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
 for p in files:tar.add(p,arcname=str(p.relative_to(O)),recursive=False)
expected={x['path']:x for x in rows}
with tarfile.open(archive,'r:gz') as tar:
 assert len(tar.getmembers())==len(rows)
 for member in tar:
  row=expected[member.name];stream=tar.extractfile(member);h=hashlib.file_digest(stream,'sha256').hexdigest()
  assert member.size==row['bytes'] and h==row['sha256']
for row in rows:assert sha(O/row['path'])==row['sha256']
receipt={'archive':str(archive.relative_to(R)),'sha256':sha(archive),'archive_bytes':archive.stat().st_size,
 'original_bytes':sum(x['bytes'] for x in rows),'files':rows,'verified':True,
 'restore':'Extract raw.tar.gz into a NEW empty directory; member paths reproduce arm/case/provider and arm/case/runtime. Verify every member against this receipt. Never overwrite an existing run.',
 'removed_only_verified_duplicate_raw_directories':[str(p.relative_to(O)) for p in roots]}
(O/'raw-archive.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
for root in roots:shutil.rmtree(root)
print('Verified lossless archive:',len(rows),'files,',receipt['original_bytes'],'->',receipt['archive_bytes'],'bytes')
