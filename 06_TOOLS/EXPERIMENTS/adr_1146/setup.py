from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-1146-source-recovery-main-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-1144-rejected-core-recovery-integration';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
for k in ('design','dataset','retrieval_accounting'):m[k]=old[k]
m['design']['code_isolation']['candidates']=[];m['integration']=None;m['lineage']['hypothesis_delta']='Identical1144product and criteria. Current new-review test responder and isolated stage capture. Inherit exact-code431 passed contracts and paired236 unchanged outcomes; rerun corrected216 framework integration tests.'
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1144-experiment-v1/integrated'],'changes':'HistoricalMAIN108 and1144 outcomes','controls':'Same source/model/budgets'},{'id':'integrated','role':'candidate','derived_from':['baseline'],'changes':'Same product; correct old fixture response and isolate captured stage','controls':'Same criteria/source/schema/ACL/budgets'}]
m['runs'][0].update(arm_ids=['integrated'],selection_rule='216 framework contracts with corrected current responder; inherit exact-code431 and paired236 records',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
for p in (P/'artifacts/design').glob('*.json'):
 if p.name not in ('freeze.json','staging.json'):shutil.copyfile(p,D/p.name)
m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));put(A/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'integrated-r1',present,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1144').glob('*.py'):
 if p.name=='setup.py':continue
 (T/p.name).write_text(p.read_text().replace(P.name,A.name).replace('adr_1144','adr_1146'))
for name in ('test_direct.py','test_scenario_native.py'):
 p=T/name;t=p.read_text().replace('import test_read_judgment_api as parent','import test_native_integrated as parent')
 t=t.replace('from conftest import term_glossary','from conftest import term_glossary\n# Import before monkeypatching expand_cards, so no previous test closure survives.\nfrom api_fixture_integrated import to_wire')
 if name=='test_direct.py':t=t.replace('return wire(value)','return wire(to_wire(value))')
 p.write_text(t)
put(D/'inherited-checks.json',{'source':str(P.relative_to(R)),'code_files':f['files'],'criteria_sha256':sha(P/'artifacts/design/criteria.json'),'checks':{n:{'path':str((P/'artifacts'/('check-'+n+'.json')).relative_to(R)),'sha256':sha(P/'artifacts'/('check-'+n+'.json'))} for n in ('primary','support','modes')},'regression':{n:{'path':str((P/'artifacts'/('regression-'+n+'.xml')).relative_to(R)),'sha256':sha(P/'artifacts'/('regression-'+n+'.xml'))} for n in ('baseline','integrated')},'rationale':'No product or inherited test changes; repeat only corrected framework fixture suite.'})
print('same product',len(f['files']))
