from common import *
import shutil,importlib.util
matrix=read(ART/'accepted-test-matrix.json');assert matrix['passed']==136 and matrix['new_tests_passed']==26 and matrix['parent_same_two_failures']
f=read(DES/'candidate-repaired.json');C=ROOT/f['code_root'];before=read(DES/'working-before.json');b=read(DES/'baseline.json')
assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent working changes: stop'
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
changes={n:h for n,h in f['selected_files'].items() if before[n]!=h};products=read(DES/'candidate-path.json')['product_files']
assert all(n.startswith('02_BACKEND/ENGINES/') or n in ['00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py',*products] for n in changes)
put(ART/'integration-preflight.json',{'before':{n:before[n] for n in changes},'after':changes,'candidate':f['pin'],'decision':'User-authorized working repair after136 checked contracts including3 reused API wrappers; parent1352 actual failures and UNKNOWN retained; this follow-up model0, no overall quality pass'})
for n in changes:
 p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in changes:
 p=ROOT/n;temp=p.with_name('.'+p.name+'.adr1353');shutil.copyfile(C/n,temp);os.replace(temp,p)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(ROOT);assert not errors,errors
put(ART/'working-integration.json',{'changed_files':len(changes),'changes':changes,'whole528_matches_candidate':True,'active_pointer_unchanged':True,'engine_preflight':{'engines':engines,'files':count,'errors':errors},'main_generation':142})
print('Integrated',len(changes),'candidate528 equals working; MAIN142 unchanged')
