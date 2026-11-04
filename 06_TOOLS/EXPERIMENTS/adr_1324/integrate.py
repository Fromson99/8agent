from common import *
import shutil,importlib.util,ast
result=read(ART/'contracts-recheck/result.json')
control=read(ART/'baseline-fixture-check/result.json')
wire=read(ART/'provider-wire/result.json')
failed=lambda r:{x['test'] for x in r['rows'] if x['outcome']=='failed'}
assert result['passed']==166 and result['failed']==2
assert control['passed']==0 and control['failed']==2 and failed(result)==failed(control)
assert all('check_unchanged' in x['error'] for r in (result,control) for x in r['rows'] if x['outcome']=='failed')
assert wire['passed']==6 and wire['failed']==0
new_tests={n.name for n in ast.parse((Path(__file__).parent/'test_direct_links.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
assert sum(r['outcome']=='passed' and r['test'].split('::')[-1].split('[')[0] in new_tests for r in result['rows'])==52
f=read(DES/'candidate-integrated.json');C=ROOT/f['code_root']
before=read(DES/'working-before.json');base=read(DES/'baseline.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent working code changed; stop before integration'
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
changes={n:h for n,h in f['selected_files'].items() if before[n]!=h}
products=read(DES/'candidate-path.json')['product_files']
assert all(n.startswith('02_BACKEND/ENGINES/') or n in ['00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py',*products] for n in changes)
put(ART/'integration-preflight.json',{'before':{n:before[n] for n in changes},'after':changes,'candidate':f['pin'],'active_pointer':base['pointer'],'decision':'Integrate validated structural fix into working code only; no MAIN promotion or model-quality certification','known_baseline_fixture_failures':sorted(failed(control))})
for n in changes:
    p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in changes:
    p=ROOT/n;temp=p.with_name('.'+p.name+'.adr1324');shutil.copyfile(C/n,temp);os.replace(temp,p)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(ROOT);assert not errors,errors
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
put(ART/'working-integration.json',{'changed_files':len(changes),'changes':changes,'whole525_matches_candidate':True,'active_main':140,'active_pointer_unchanged':True,'engine_preflight':{'engines':engines,'files':count,'errors':errors},'main_promotion':False,'field_deployment':False})
put(DES/'candidate-working.json',{'code_root':'.','selected_files':f['selected_files']})
print('Integrated',len(changes),'files; selectedMAIN140 unchanged; whole525 candidate/work matches')
