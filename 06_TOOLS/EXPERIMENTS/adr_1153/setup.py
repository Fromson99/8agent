from common import *
import sys,shutil
T=Path(__file__).parent;P=ROOT/'04_EXPERIMENTS/ADR/ADR-1152-ontology-selection-main-integration';DES.mkdir(parents=True,exist_ok=True)
f=read(P/'artifacts/design/freeze.json');old=read(P/'실험/manifest.json');m=read(ADR/'실험/manifest.json')
for k in ('design','dataset','retrieval_accounting'):m[k]=old[k]
m.update(in_sample=False,decision_eligible=True);m['integration']=None;m['design']['code_isolation']['candidates']=[]
m['lineage']['hypothesis_delta']='Identical665product/440servingfiles and technical criteria; test-only REPO_ROOT avoids existing pytestROOTredirection. Rerun10newconditions; inherit216passedcurrentframeworkcontracts by exact hashes.'
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1152-experiment-v1/integrated'],'changes':'Historical MAIN109 and1152technical result','controls':'Exact product/no data/switch/recovery/budget drift'},{'id':'integrated','role':'candidate','derived_from':['baseline'],'changes':'No product change; test path constant correction only','controls':'Same365char instruction and440runtimefiles'}]
m['runs'][0].update(arm_ids=['integrated'],selection_rule='10technicalconditions with corrected fixture path;216currentframeworkconditions inherited by exact product hash',artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
for p in (P/'artifacts/design').glob('*.json'):
 if p.name not in ('freeze.json','staging.json'):shutil.copyfile(p,DES/p.name)
m['dataset'].update(frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'));put(ADR/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (ROOT/n).is_file()];C=ac.snapshot(ADR,'integrated-r1',present,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(ROOT/f['code_root']/n)==h;p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f['code_root']/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1152').glob('test_*.py'):
 s=p.read_text()
 if p.name=='test_prompt_integration.py':s=s.replace('ADR-1152-ontology-selection-main-integration',ADR.name).replace('ROOT','REPO_ROOT').replace('QUALIFICATION_CODE_REPO_ROOT','QUALIFICATION_CODE_ROOT')
 (T/p.name).write_text(s)
shutil.copyfile(ROOT/'06_TOOLS/EXPERIMENTS/adr_1152/api_fixture_integrated.py',T/'api_fixture_integrated.py')
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1152/check.py').read_text().replace('ADR-1152-ontology-selection-main-integration',ADR.name)
a=s.index("files={'primary'");b=s.index('paths=[',a);s=s[:a]+"files=['test_prompt_integration.py']\n"+s[b:];s=s.replace("if mode=='ontology':paths.append(str(Path(__file__).parent/'test_prompt_integration.py'))",'')
(T/'check.py').write_text(s)
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1152/freeze.py').read_text().replace('newtechnical10+existing216','newtechnical10rerun+216inherited');(T/'freeze.py').write_text(s)
checks=read(P/'artifacts/check-ontology.json');keep=[r for r in checks['rows'] if not any(name in r['test'] for name in ('test_delivered_prompt_and_exact_model_subset_without_forced_pair','test_only_prompt_ast_changed_and_same_input_schema','test_profile_switches_recovery_and_empty_data_are_exact_main109'))]
assert len(keep)==216 and all(r['status']=='passed' for r in keep)
put(DES/'inherited-checks.json',{'path':str((P/'artifacts/check-ontology.json').relative_to(ROOT)),'sha256':sha(P/'artifacts/check-ontology.json'),'passed':216,'rows':keep,'code_files':f['files'],'new_test_count':0,'reason':'Identical product,216unchangedcurrentframeworktests passed;correct onlynewtestROOTconstant'})
print('Same665product;10fixturechecks scheduled,216inherited')
