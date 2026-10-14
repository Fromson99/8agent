"""Install evaluated UI and its tests, preserving unrelated current transport work."""
from pathlib import Path
import json,hashlib,shutil,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0772-source-provider-display';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(A/'artifacts/run-001/result.json')['strict_success'];assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');code=R/f['code_root'];cm=read(R/f['candidate']['manifest_path']);plan=[]
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']
allowed={x['path'] for x in read(D/'integration.json')['changes']}|{'05_TESTS/CONTRACTS/'+n for n in ['test_workflow_source_cards.py','test_main_workflow_display.py','test_main_source_cards.py']}
assert {x for x in allowed if not x.startswith('05_TESTS/')}=={'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'}
for row in cm['files']:
 p=row['target_path']
 if p not in allowed:continue
 current=sha(R/p) if (R/p).is_file() else None;after=sha(code/p)
 if current==after:continue
 assert current==row.get('upstream_sha256'),f'Concurrent change: {p}'
 plan.append({'path':p,'before':current,'after':after,'source':str((code/p).relative_to(R))})
backup=A/'artifacts/working-backup';backup.mkdir(exist_ok=False)
before={p:sha(R/p) for p in f['serving_files'] if p not in allowed}
put(A/'artifacts/working-install-plan.json',{'files':plan,'backup':str(backup.relative_to(R)),'unrelated_serving_before':before})
for row in plan:
 p=row['path'];target=R/p;saved=backup/p;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
 temp=target.with_name('.'+target.name+'.provider-install');shutil.copy2(code/p,temp);assert sha(temp)==row['after'];os.replace(temp,target)
for p,h in before.items():assert sha(R/p)==h,p
saved=backup/'00_SYSTEM/PIPELINE.json';saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/'00_SYSTEM/PIPELINE.json',saved)
put(A/'artifacts/working-install-receipt.json',{'status':'installed','files':plan,'selected_serving_files':len(f['serving_files']),'scoped_candidate_match':True,'unrelated_working_preserved':True,'main_pointer_unchanged':True,'unselected_worktree_differences':read(D/'preserved-worktree-differences.json')})
print('Installed',len(plan),'scoped files; preserved all unrelated work')
