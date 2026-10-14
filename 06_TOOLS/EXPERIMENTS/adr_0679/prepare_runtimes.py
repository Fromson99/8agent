"""Prepare all immutable hardlinks once, before any request pins inode identities."""
from pathlib import Path
import json,os,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification';D=A/'artifacts/design'
v=json.loads((D/'dataset.json').read_text());source=R/json.loads((D/'bindings.json').read_text())['source_generation']
def copy(src,dst):
 if Path(src).suffix=='.json':return shutil.copy2(src,dst)
 os.link(src,dst);return dst
for arm in ['integrated']:
 for case in v['cases']+v['regression_cases']:
  dest=A/'artifacts/prepared-generations'/arm/case['case_id']
  dest.mkdir(parents=True,exist_ok=True)
  for src in source.rglob('*'):
   if not src.is_file():continue
   target=dest/src.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
   if target.exists():
    if src.suffix=='.sqlite' and target.stat().st_ino!=src.stat().st_ino:
     target.unlink();copy(src,target)
   else:copy(src,target)
print('prepared 40 candidate generation views; no more source hardlinks will be created during requests')
