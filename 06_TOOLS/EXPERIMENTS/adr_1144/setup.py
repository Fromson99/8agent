from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-1144-rejected-core-recovery-integration';P=R/'04_EXPERIMENTS/ADR/ADR-1143-recovery-framework-qualification';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
for k in ('design','dataset','retrieval_accounting'):m[k]=old[k]
m['design']['code_isolation']['candidates']=[];m['integration']=None;m['lineage']['hypothesis_delta']='Validate/reconstruct independent core under its own unchanged schema and current reference binding at gateway; preserve rejection, deliver only separately valid core to final recovery. New corruption boundary tests plus framework interactions.'
m['design']['hypothesis']=m['lineage']['hypothesis_delta']
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1143-experiment-v1/integrated'],'changes':'HistoricalMAIN108 and1143 outcomes','controls':'Same source/model/budgets'},{'id':'integrated','role':'candidate','derived_from':['baseline'],'changes':'Strict independent core at decoding boundary; no rejected opinion adoption','controls':'Same source, schema semantics, ACL and request budgets'}]
m['runs'][0].update(arm_ids=['integrated'],selection_rule='New core corruption boundary and framework combinations; observed recovery/performance regressions',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
for p in (P/'artifacts/design').glob('*.json'):
 if p.name not in ('freeze.json','staging.json'):shutil.copyfile(p,D/p.name)
criteria=read(D/'criteria.json');criteria['hypothesis']=m['design']['hypothesis'];criteria['primary'].insert(0,'New independent-core decoding tests: host constants restored, unknown core references/extra properties rejected, original output unchanged, no complete response accepted');put(D/'criteria.json',criteria);m['design']['success_criteria']=criteria['primary'];m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));put(A/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'integrated-r1',present,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1143').glob('*.py'):
 if p.name=='setup.py':continue
 (T/p.name).write_text(p.read_text().replace(P.name,A.name).replace('adr_1143','adr_1144'))
p=T/'check_integrated_bootstrap.py';t=p.read_text().replace("str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS')","str(C/'02_BACKEND'),str(C/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS/CONTRACTS')").replace("str(Path(__file__).parent),str(ROOT/'05_TESTS/CONTRACTS')","str(Path(__file__).parent),str(C/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS/CONTRACTS')").replace("'primary':['test_recovery_limits.py'","'primary':['test_rejected_core.py','test_recovery_limits.py'");p.write_text(t)
print(S)
