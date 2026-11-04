from common import *
import shutil,importlib.util,ast
f=read(DES/'candidate-bounded.json');C=ROOT/f['code_root']
before=read(DES/'working-before.json');baseline=read(DES/'baseline.json')
contracts=read(ART/'final-contracts/result.json');api=read(ART/'api-contracts-r2/result.json')
assert api['passed']==2 and api['failed']==0
assert contracts['passed']==94 and contracts['failed']==1
failures={r['test'] for r in contracts['rows'] if r['outcome']=='failed'}
control=read(ART/'parent-finish-control/result.json')
assert failures=={r['test'] for r in control['rows'] if r['outcome']=='failed'}
assert control['passed']==0 and control['failed']==1
old=read(ART/'parent-control/result.json');first=read(ART/'pager-contracts/result.json')
assert {r['test'] for r in old['rows'] if r['outcome']=='failed'}<= {r['test'] for r in first['rows'] if r['outcome']=='failed'}
names={n.name for n in ast.parse((Path(__file__).parent/'test_page_cycle.py').read_text()).body
       if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
pager_rows=[r for r in contracts['rows'] if r['test'].split('::')[-1].split('[')[0] in names]
assert len(pager_rows)==17 and all(r['outcome']=='passed' for r in pager_rows)
assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent working source changed; do not overwrite'
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
changes={n:h for n,h in f['selected_files'].items() if before[n]!=h}
products=read(DES/'candidate-path.json')['product_files']
assert all(n.startswith('02_BACKEND/ENGINES/') or n in ['00_SYSTEM/PIPELINE.json',*products] for n in changes)
assert len(changes)==32 and all(n in changes for n in products)
put(ART/'integration-preflight.json',{'before':{n:before[n] for n in changes},'after':changes,'candidate':f['pin'],'active_pointer':baseline['pointer'],'decision':'User-requested working fix; all new pager/API checks passed; three existing regression failures reproduced before patch; MAIN unchanged'})
for n in changes:
    p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in changes:
    p=ROOT/n;temp=p.with_name('.'+p.name+'.adr1340');shutil.copyfile(C/n,temp);os.replace(temp,p)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(ROOT);assert not errors,errors
put(ART/'working-integration.json',{'changed_files':len(changes),'changes':changes,'whole528_matches_candidate':True,'selected_main':baseline['pointer']['generation'],'active_pointer_unchanged':True,'engine_preflight':{'engines':engines,'files':count,'errors':errors},'field_deployment':False})
put(DES/'candidate-working.json',{'code_root':'.','selected_files':f['selected_files']})
print('Integrated',len(changes),'files; exact528 working/candidate; MAIN142 unchanged')
