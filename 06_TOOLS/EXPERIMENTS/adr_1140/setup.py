from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];H=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-1140-final-recovery-native-contract';P=R/'04_EXPERIMENTS/ADR/ADR-1138-scope-final-recovery-integration';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
parent=read(P/'실험/manifest.json');m=read(A/'실험/manifest.json');f=read(P/'artifacts/design/freeze.json')
m['in_sample']=True;m['decision_eligible']=False
m['design']=parent['design'];m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1138-experiment-v1/repaired'],'changes':'Historical1138 same product','controls':'Same data/model/budget'},{'id':'repaired','role':'candidate','derived_from':['baseline'],'changes':'Fixture supports empty new judgment delta at early FINISH; no product changes','controls':'Same1138product'}]
m['design']['code_isolation']['candidates']=[];m['runs']=parent['runs']
for run in m['runs']:run.update(status='planned',artifact_path='TODO',sha256='PENDING');run.pop('success_criteria_met',None)
m['dataset']=parent['dataset'];m['lineage']['hypothesis_delta']='Retest identical product with correct pending-judgment synthetic responder';put(A/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
absent=[n for n in f['files'] if not (R/n).exists()]
C=ac.snapshot(A,'repaired-r1',[n for n in f['files'] if n not in absent],experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001','run-002']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,S/n)
for n in absent:ac.register_file(C,n,upstream_state='absent')
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1138').glob('*.py'):
 if p.name=='prepare.py':continue
 (H/p.name).write_text(p.read_text().replace(P.name,A.name).replace('adr_1138','adr_1140'))
for p in (P/'artifacts/design').glob('*.json'):
 if p.name!='freeze.json':shutil.copyfile(p,D/p.name)
p=H/'test_final_recovery_native.py';t=p.read_text().replace("if mode not in ('open_need','conflict'):","if mode not in ('open_need','conflict') and rows and any(target_text in s['text'] for s in view['sources']):")
p.write_text(t)
print(S)
