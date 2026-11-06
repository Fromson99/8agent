from common import *
import shutil,importlib.util
plan=read(DES/'integration-plan.json');f=read(DES/'candidate-working.json');C=ROOT/f['code_root']
tests=read(ART/'final-contracts/result.json')
control=read(ART/'parent-settings-control/result.json')
known='test_selected_local_release_receives_settings_without_rewriting_frozen_files'
failed=[r for r in tests['rows'] if r['outcome']=='failed']
assert tests['code_unchanged'] and tests['passed']==106 and len(failed)==1 and known in failed[0]['test']
assert control['failed']==1 and known in control['rows'][0]['test']
assert 'FileNotFoundError' in failed[0]['error'] and 'FileNotFoundError' in control['rows'][0]['error']
assert '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json' in failed[0]['error'] and '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json' in control['rows'][0]['error']
assert tests['code_root']==str(C)
assert all(sha(C/n)==h for n,h in plan['after'].items())
assert all(sha(ROOT/n)==h for n,h in plan['before'].items()),'Concurrent working bytes changed. Stop before first write.'
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
backup=ART/'working-before';backup.mkdir(exist_ok=False)
for n in plan['changes']:
 p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
applied=[]
try:
 for n,h in plan['changes'].items():
  p=ROOT/n
  assert sha(p)==plan['before'][n]
  tmp=p.with_name('.'+p.name+'.adr1395');shutil.copyfile(C/n,tmp)
  assert sha(tmp)==h and sha(p)==plan['before'][n]
  os.replace(tmp,p);applied.append(n)
 assert all(sha(ROOT/n)==h for n,h in plan['after'].items())
 spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
 engines,count,errors=pf.check(ROOT);assert not errors,errors
 assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==active
except BaseException:
 for n in reversed(applied):
  if sha(ROOT/n)==plan['after'][n]:
   tmp=(ROOT/n).with_name('.'+Path(n).name+'.adr1395-restore');shutil.copyfile(backup/n,tmp);os.replace(tmp,ROOT/n)
 raise
put(ART/'working-integration.json',{'products':plan['products'],'changed':plan['changes'],'changed_count':len(plan['changes']),
 'exact528_matches_tested':True,'preserved_concurrent':plan['preserved_concurrent'],'selected_main':active,
 'engine':{'engines':engines,'files':count,'errors':errors},'native_executable_count':plan['native_executables'],
 'model_calls':0})
put(DES/'candidate-checkout.json',dict(code_root='.',selected_files=plan['after']))
print('Integrated six products and pins; working528 exact tested integration; concurrent2 preserved.')
