from pathlib import Path
import json,hashlib,shutil,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0773-successful-shortcut-publication';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(A/'artifacts/run-001/result.json')['strict_success'];assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');code=R/f['code_root'];cm=read(R/f['candidate']['manifest_path']);plan=[]
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']
allowed={x['path'] for x in read(D/'integration.json')['changes']}|{x['target_path'] for x in cm['files'] if x['target_path'].startswith('05_TESTS/')}
backup=A/'artifacts/working-backup';backup.mkdir(exist_ok=False)
# Current completion work is outside release scope; merge working pins only.
concurrent={x['path']:x['current'] for x in read(D/'concurrent-working-changes.json')['files'] if not x['path'].endswith('.json')}
for p,h in concurrent.items():assert sha(R/p)==h,p
for row in cm['files']:
 p=row['target_path']
 if p not in allowed:continue
 current=sha(R/p) if (R/p).is_file() else None;raw=(code/p).read_bytes()
 if p.startswith('02_BACKEND/ENGINES/'):
  e=json.loads(raw)
  for target in concurrent.keys() & e['files'].keys():e['files'][target]=sha(R/target)
  raw=(json.dumps(e,ensure_ascii=False,indent=2)+'\n').encode()
 if p=='00_SYSTEM/PIPELINE.json':continue
 after=hashlib.sha256(raw).hexdigest()
 if current==after:continue
 assert current==row.get('upstream_sha256'),f'Concurrent change: {p}'
 plan.append({'path':p,'before':current,'after':after,'candidate':sha(code/p)})
 target=R/p;target.parent.mkdir(parents=True,exist_ok=True)
 if current is not None:
  saved=backup/p;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
 temp=target.with_name('.'+target.name+'.shortcut-install');temp.write_bytes(raw);os.replace(temp,target)
p='00_SYSTEM/PIPELINE.json';current=sha(R/p);saved=backup/p;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/p,saved)
v=read(code/p)
for entry in v['engines'].values():entry['sha256']=sha(R/entry['manifest'])
put(R/p,v);plan.append({'path':p,'before':current,'after':sha(R/p),'candidate':sha(code/p)})
for p,h in concurrent.items():assert sha(R/p)==h,p
put(A/'artifacts/working-install-receipt.json',{'status':'installed','files':plan,'preserved_concurrent':concurrent,'main_pointer_unchanged':True,'candidate_release_uses_its_own_pins':True})
print('Installed',len(plan),'files; preserved concurrent completion changes')
