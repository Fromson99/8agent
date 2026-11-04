from common import *
import shutil,importlib.util,ast
r=read(ART/'contracts/result.json')
assert r['failed']==0 and r['passed']>=106
names={n.name for n in ast.parse((Path(__file__).parent/'test_repeat_scope.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
assert sum(x['outcome']=='passed' and x['test'].split('::')[-1].split('[')[0] in names for x in r['rows'])==39
f=read(DES/'candidate-integrated.json');C=ROOT/f['code_root'];before=read(DES/'working-before.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent working code changed'
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
changes={n:h for n,h in f['selected_files'].items() if before[n]!=h}
products=read(DES/'candidate-path.json')['product_files']
assert all(n.startswith('02_BACKEND/ENGINES/') or n in ['00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py',*products] for n in changes)
put(ART/'integration-preflight.json',{'before':{n:before[n] for n in changes},'after':changes,'candidate':f['pin'],'active_pointer':baseline['pointer'],'decision':'User-directed working fix after all structural/API contracts; selected MAIN unchanged; no model quality certification'})
for n in changes:
    p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in changes:
    p=ROOT/n;temp=p.with_name('.'+p.name+'.adr1331');shutil.copyfile(C/n,temp);os.replace(temp,p)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(ROOT);assert not errors,errors
put(ART/'working-integration.json',{'changed_files':len(changes),'changes':changes,'whole525_matches_candidate':True,'selected_main':140,'active_pointer_unchanged':True,'engine_preflight':{'engines':engines,'files':count,'errors':errors},'field_deployment':False})
put(DES/'candidate-working.json',{'code_root':'.','selected_files':f['selected_files']})
print('Integrated',len(changes),'files;525working/candidate identical;MAIN140 unchanged')
