from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1139-ontology-framework-local-http';P=R/'04_EXPERIMENTS/ADR/ADR-1137-ontology-framework-qualification';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True);T=Path(__file__).parent
read=lambda p:json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');src=R/f['code_root'];m=read(P/'실험/manifest.json');s=read(A/'실험/manifest.json')
for k in ('adr_id','experiment_id','reservation','lineage','relationships'):m[k]=s[k]
m.pop('integration',None);m['design']['code_isolation']['candidates']=[];m['design']['arms']=s['design']['arms'];m['lineage']['hypothesis_delta']='Identical product/tests; enable local TestClient event-loop wakeup. No remote model calls.'
for arm in m['design']['arms']:arm.update(changes='Immutable MAIN107 comparison' if arm['id']=='baseline' else 'Exact1136product; runner reports with pytest required parameter name',controls='Same fixed1136criteria and fixtures; no quality regrade')
m['results'].update(status='not_run',by_arm={},error_taxonomy=[],main_wiring='unchanged');m['runs']=s['runs'];m['runs'][0].update(arm_ids=['baseline','integrated'],selection_rule='Same1136fixed synthetic contracts plus affected MAIN107 regression comparison',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(R)));put(A/'실험/manifest.json',m)
for n in ['baseline.json','criteria.json','source-composition.json']:shutil.copyfile(P/'artifacts/design'/n,D/n)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'framework-r1',present,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(src/n)==h
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for n in ['freeze.py','check.py','test_projection.py','test_direct.py','test_semantics.py','test_scenarios.py','test_scenario_native.py','test_sufficiency.py','test_toggle.py','regression.py']:
 t=(R/'06_TOOLS/EXPERIMENTS/adr_1137'/n).read_text().replace('ADR-1137-ontology-framework-qualification','ADR-1139-ontology-framework-local-http').replace('adr_1137','adr_1139')
 if n=='check.py':t=t.replace('def pytest_runtest_logreport(self,r):','def pytest_runtest_logreport(self,report):\n  r=report')
 (T/n).write_text(t)
print('SAME_PRODUCT',len(f['files']))
