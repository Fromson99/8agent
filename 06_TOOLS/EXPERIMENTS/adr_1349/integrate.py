from common import *
import shutil,importlib.util

matrix=read(ART/'accepted-test-matrix.json');assert matrix['new_tests_passed']==2 and matrix['baseline_failures_reproduced']
assert (ROOT/'04_EXPERIMENTS/ADR/ADR-1348-ontology-repair-qwen-build-use/artifacts/run-001/result.json').exists(),'Finish prior working-code comparison first'
f=read(DES/'candidate-repaired.json');C=ROOT/f['code_root']
before=read(DES/'working-before.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent working changes: stop instead of overwrite'
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
changes={n:h for n,h in f['selected_files'].items() if before[n]!=h}
products=read(DES/'candidate-path.json')['product_files']
allowed=['00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py',*products]
assert all(n.startswith('02_BACKEND/ENGINES/') or n in allowed for n in changes)
assert all(n in changes for n in products) and len(changes)==32
put(ART/'integration-preflight.json',{'before':{n:before[n] for n in changes},'after':changes,'candidate':f['pin'],'decision':'User-authorized working fix after new contracts and actual API pass; 25 unchanged normalization fixture failures retained; MAIN142 unchanged'})
for n in changes:
    p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in changes:
    p=ROOT/n;temp=p.with_name('.'+p.name+'.adr1349');shutil.copyfile(C/n,temp);os.replace(temp,p)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(ROOT);assert not errors,errors
put(ART/'working-integration.json',{'changed_files':len(changes),'changes':changes,'whole528_matches_candidate':True,'active_pointer_unchanged':True,'engine_preflight':{'engines':engines,'files':count,'errors':errors},'main_generation':142})
put(DES/'candidate-working.json',{'code_root':'.','selected_files':f['selected_files']})
print('Integrated32; working/candidate528 identical; MAIN142 unchanged;',matrix['passed'],'passed,25 prior failures')
