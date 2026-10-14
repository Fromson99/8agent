"""Rebase exact reviewed files over active MAIN53, preserving immutable source history."""
from pathlib import Path
import json,hashlib,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert read(A/'artifacts/run-001/result.json')['strict_success']
b=read(D/'baseline.json');f=read(D/'freeze.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
stage=A/'artifacts/release-stage';assert not stage.exists();stage.mkdir()
for name,h in b['manifest']['files'].items():
 origin=R/b['manifest']['code_root']/name;assert sha(origin)==h
 target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(origin,target)
for row in read(D/'integration.json')['changes']:
 assert row['after'] is not None
 origin=R/f['code_root']/row['path'];assert sha(origin)==row['after']
 target=stage/row['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(origin,target)
for name,h in f['serving_files'].items():assert sha(stage/name)==sha(R/name)==h,name
(A/'artifacts/stage-receipt.json').write_text(json.dumps({'stage':str(stage.relative_to(R)),'files':f['serving_files'],'base':b['manifest']['code_root'],'changed':len(read(D/'integration.json')['changes']),'candidate_match':True,'working_match':True},ensure_ascii=False,indent=2)+'\n')
print('Rebased',len(f['serving_files']),'files against active MAIN53; exact frozen and working match')
