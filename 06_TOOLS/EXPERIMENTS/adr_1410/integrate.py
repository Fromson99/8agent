from common import *
import shutil
baseline=read(DES/'baseline.json');candidate=read(DES/'candidate-selected.json');C=ROOT/candidate['code_root']
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer'],'MAIN changed'
assert all(sha(C/n)==h for n,h in candidate['selected_files'].items())
working=read(DES/'working-before.json')
for n,h in baseline['release']['files'].items():assert sha(ROOT/n)==working.get(n,h),n
changed=[n for n,h in candidate['selected_files'].items() if not (ROOT/n).exists() or sha(ROOT/n)!=h]
put(DES/'working-copy-decision.json',{'authority':'User requests remove condition/exception final review and use dialogue/ontology; working implementation only, no MAIN promotion',
 'actual_model_quality_pass':False,'reason':'Actual final explanation/followup is observed but exceptions still omitted; no general or legal quality certification',
 'files':changed,'candidate':candidate['pin']})
for n in changed:
 p=ROOT/n;backup=ART/'working-before'/n
 if p.exists() and not backup.exists():backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,backup)
 p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
assert all(sha(ROOT/n)==h for n,h in candidate['selected_files'].items())
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from genos_codespace_engine_preflight import check
engines,files,errors=check(ROOT);assert not errors,errors
put(DES/'candidate-working.json',{'code_root':'.','selected_files':candidate['selected_files'],'pin':candidate['pin']})
put(ART/'working-copy.json',{'files':changed,'changed_count':len(changed),'candidate_all_files_match':True,'engine_count':engines,'engine_files':files,'errors':errors,'main_unchanged':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']})
print('Working copy',len(changed),'changes; exact candidate531; MAIN150 unchanged')
