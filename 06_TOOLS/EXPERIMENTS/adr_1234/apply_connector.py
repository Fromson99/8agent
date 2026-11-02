"""Apply only the user-requested Gold connector after completed checks; no MAIN switch."""
from pathlib import Path
import json,sys,hashlib,shutil
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1234-gold-ontology-reference-repair';D=A/'artifacts/design';O=A/'artifacts/run-001';P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';U=R/'09_ARTIFACTS/AUDITS/20261030-gold-ontology-on'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(O/'checks.json')['passed']==40 and read(O/'checks.json')['failed']==0
r=read(O/'live/gold-369/result.json');e=read(O/'ontology-e2e.json');assert e['gates']['all_three_paths_in_wire'] and e['gates']['all_four_provisions_prepared']
# User asked to turn the separate connector ON; an incomplete final inference,
# if any, remains explicit in the receipt and is never described as E2E success.
assert not r['unknown'] and not (O/'live/gold-369/resource-stop.json').exists()
c=read(D/'candidate.json');S=R/c['root'];F=R/c['snapshot'];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
assert not ac.validate(S),ac.validate(S)
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'before.json')['main_pointer_sha256']
files=[F/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'/x for x in ('connect.py','ontology_settings.json','runtime_patch_binding.json','runtime_patches/navigation_input.py','runtime_patches/ontology_assessment.py')]
rollback=U/'rollback';assert not rollback.exists();rollback.mkdir(parents=True)
rows=[]
for source in files:
 rel=source.relative_to(F/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12');target=P/rel;old=sha(target) if target.exists() else None
 if target.exists():saved=rollback/rel;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);assert sha(target)==sha(source)
 rows.append({'path':str(target.relative_to(R)),'before_sha256':old,'after_sha256':sha(target),'rollback':str((rollback/rel).relative_to(R)) if old else None})
put(U/'applied.json',{'authorization':'ON해보고 돌아가는지 확이냏봐','scope':'separate Gold connector only','ontology':'ON/DB','candidate':c,'files':rows,'real_inference_status':e['status'],'actual_http_status':r.get('http_status'),'main_promoted':False,'source_engine_edited':False})
print('Applied Gold ON/DB; actual inference status:',e['status'])
