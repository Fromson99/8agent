from common import *
import shutil,importlib.util
result=read(ART/'contracts-final/result.json');scope=read(ART/'scope-modes/result.json')
assert result['failed']==scope['failed']==0 and result['exit_code']==scope['exit_code']==0
f=read(DES/'candidate-integrated.json');C=ROOT/f['code_root'];before=read(DES/'working-before.json');base=read(DES/'baseline.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent serving code changed; do not overwrite'
changes={n:h for n,h in f['selected_files'].items() if before[n]!=h}
assert all(n.startswith('02_BACKEND/ENGINES/') or n in ['00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py',*read(DES/'candidate-path.json')['product_files']] for n in changes)
put(ART/'integration-preflight.json',{'before':{n:before[n] for n in changes},'after':changes,'candidate':f['pin'],'active_pointer':base['pointer'],'no_main_change':True})
for n in changes:
 p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in changes:
 p=ROOT/n;temp=p.with_name('.'+p.name+'.adr1321');shutil.copyfile(C/n,temp);os.replace(temp,p)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf);engines,count,errors=pf.check(ROOT);assert not errors,errors
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
put(ART/'working-integration.json',{'changed_files':len(changes),'changes':changes,'whole525_matches_candidate':True,'active_main':base['pointer']['generation'],'active_pointer_unchanged':True,'parallel_embedding_changes_preserved':all(sha(ROOT/n)==base['release']['files'][n] for n in ('02_BACKEND/semantic_runtime/genos.py','02_BACKEND/semantic_runtime/oracle_query_service.py','02_BACKEND/semantic_runtime/oracle_query_vector.py')),'engine_preflight':{'engines':engines,'files':count,'errors':errors},'main_promotion':False,'field_deployment':False})
put(DES/'candidate-working.json',{'code_root':'.','selected_files':f['selected_files']})
print('Integrated',len(changes),'files;6product+1nativecatalogue+31pins. MAIN',base['pointer']['generation'],'unchanged')
