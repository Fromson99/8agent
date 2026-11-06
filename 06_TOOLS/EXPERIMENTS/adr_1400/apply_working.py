from common import *
import ast,shutil
f=read(DES/'candidate-working.json');C=ROOT/f['code_root'];b=read(DES/'working-before.json')
assert read(ART/'integrated-unit/result.json')['exit_code']==0
assert read(ART/'native-state-boundary-r3/result.json')['exit_code']==0
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
assert all(sha(ROOT/n)==h for n,h in b['files'].items()),'Concurrent working changes; refuse before any write'
def plans(p):
 for node in ast.parse(p.read_text()).body:
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PLANS' for t in node.targets):return ast.literal_eval(node.value)
a=plans(ROOT/'02_BACKEND/semantic_runtime/oracle_query_plans.py');z=plans(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py')
assert a.keys()==z.keys() and all({k:v for k,v in value.items() if k!='sources'}=={k:v for k,v in z[n].items() if k!='sources'} for n,value in a.items())
changed=[n for n,h in b['files'].items() if f['selected_files'][n]!=h];backup=ART/'working-before-bytes'
for n in changed:
 dest=backup/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
for n in changed:
 path=ROOT/n;temp=path.with_name('.'+path.name+'.adr1400');temp.write_bytes((C/n).read_bytes());os.replace(temp,path)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));from genos_codespace_engine_preflight import check
engines,count,errors=check(ROOT);assert not errors,errors
put(ART/'working-integration.json',{'code_root':f['code_root'],'all530_exact':True,'files':len(f['selected_files']),'changed':changed,'changed_count':len(changed),'native_executables_identical':len(z),'engines':engines,'engine_files':count,'errors':errors,'selected_MAIN_unchanged':b['pointer'],'common_reason_review_preserved':True,'backup':str(backup.relative_to(ROOT))})
print('Working integration exact530; changed',len(changed),'files, SQL',len(z),'unchanged, MAIN147 unchanged')
