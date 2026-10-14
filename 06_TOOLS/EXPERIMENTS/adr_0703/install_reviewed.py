"""Install only changed reviewed files against frozen upstream bytes; no full snapshot copy."""
from pathlib import Path
import json,hashlib,shutil,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0703-exception-coupled-final-holdout';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(A/'artifacts/run-001/result.json')['strict_success']
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');code=R/f['code_root'];cm=read(R/f['candidate']['manifest_path']);plan=[]
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']
for row in cm['files']:
 p=row['target_path'];current=sha(R/p) if (R/p).is_file() else None;after=sha(code/p)
 if current==after:continue
 assert current==row.get('upstream_sha256'),f'Concurrent change needs merge: {p}'
 assert p.startswith(('00_SYSTEM/LEGAL_AGENT/','02_BACKEND/ENGINES/','02_BACKEND/semantic_runtime/','05_TESTS/CONTRACTS/','01_DATA/PROJECTIONS/','08_DEPLOYMENT/GENOS/')) or p in ('00_SYSTEM/PIPELINE.json','service.py','main_workflow.py'),p
 plan.append({'path':p,'before':current,'after':after,'source':str((code/p).relative_to(R))})
# Stable contract locations preserve reusable new tests without changing serving bytes.
new_tests={
 '05_TESTS/CONTRACTS/test_exception_wire.py':('06_TOOLS/EXPERIMENTS/adr_0702/test_exception_wire.py',None),
 '05_TESTS/CONTRACTS/test_named_menu.py':('06_TOOLS/EXPERIMENTS/adr_0700/test_named_menu.py',None),
 '05_TESTS/CONTRACTS/test_document_focus.py':('06_TOOLS/EXPERIMENTS/adr_0698/test_document_focus.py',None),
 '05_TESTS/CONTRACTS/test_completion_v4.py':('06_TOOLS/EXPERIMENTS/adr_0693/test_completion_v4.py',None),
 '05_TESTS/CONTRACTS/test_structure_reading.py':('06_TOOLS/EXPERIMENTS/adr_0694/test_structure_reading.py',None),
 '05_TESTS/CONTRACTS/test_wire_repair.py':('06_TOOLS/EXPERIMENTS/adr_0696/test_wire_repair.py',"sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'adr_0694'))\n"),
 '05_TESTS/CONTRACTS/test_public_display_boundary.py':('06_TOOLS/EXPERIMENTS/adr_0693/test_public_boundary.py',None)}
extra={}
for p,(src,remove) in new_tests.items():
 assert not (R/p).exists(),p
 text=(R/src).read_text()
 if remove:text=text.replace(remove,'')
 extra[p]=text;plan.append({'path':p,'before':None,'after':hashlib.sha256(text.encode()).hexdigest(),'source':src,'test_only':True})
# Everything outside this exact list must retain its current bytes.
before={str(p.relative_to(R)):sha(p) for p in (R/'02_BACKEND/semantic_runtime').rglob('*.py')};backup=A/'artifacts/working-backup';backup.mkdir(exist_ok=False)
put(A/'artifacts/working-install-plan.json',{'files':plan,'backup':str(backup.relative_to(R)),'unrelated_runtime_before':before})
for row in plan:
 p=row['path'];target=R/p
 if row['before']:
  saved=backup/p;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
 target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_name('.'+target.name+'.structured-install')
 if p in extra:temp.write_text(extra[p])
 else:shutil.copy2(code/p,temp)
 assert sha(temp)==row['after'];os.replace(temp,target)
for p,h in before.items():
 if p not in {x['path'] for x in plan}:assert sha(R/p)==h,p
for p,h in f['serving_files'].items():assert sha(R/p)==h,f'Working/release drift: {p}'
put(A/'artifacts/working-install-receipt.json',{'status':'installed','files':plan,'same_serving_files':len(f['serving_files']),'exact_candidate_match':True,'unrelated_runtime_preserved':True,'main_pointer_unchanged':True})
print('Selectively installed',len(plan),'files; entire284-file serving inventory is identical to tested package')
