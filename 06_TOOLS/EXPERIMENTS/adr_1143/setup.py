from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-1143-recovery-framework-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-1142-main108-recovery-integration';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
for k in ('design','dataset','retrieval_accounting'):m[k]=old[k]
m['design']['code_isolation']['candidates']=[];m['integration']=None;m['lineage']['hypothesis_delta']='Exact1142product and criteria; restore existing matrix input files before test collection. New combined contracts remain unobserved.'
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1142-experiment-v1/integrated'],'changes':'Historical MAIN108 and1142 same product','controls':'Same source/model/budgets'},{'id':'integrated','role':'candidate','derived_from':['baseline'],'changes':'Same440servingfiles; complete test inputs','controls':'Same frozen1142criteria'}]
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Same1142 new combined contracts, all observed regressions',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
for p in (P/'artifacts/design').glob('*.json'):
 if p.name not in ('freeze.json','staging.json'):shutil.copyfile(p,D/p.name)
for n in ('matrix.json','regression-matrix.json','observed-matrix.json'):
 shutil.copyfile(R/'04_EXPERIMENTS/ADR/ADR-1141-exact-gap-progress/artifacts/design'/n,D/n)
m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));put(A/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'integrated-r1',present,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1142').glob('*.py'):
 if p.name=='prepare.py':continue
 (T/p.name).write_text(p.read_text().replace(P.name,A.name).replace('adr_1142','adr_1143'))
print('same product',len(f['files']))
