from common import *
put(ART/'working-copy-preflight-import-failure.json',{'error':'ModuleNotFoundError: genos_codespace_engine_preflight','stage':'after all candidate files copied and SHA checked, before preflight','product_recopy':False,'external_calls':0})
baseline=read(DES/'baseline.json');candidate=read(DES/'candidate-selected.json');decision=read(DES/'working-copy-decision.json')
assert all(sha(ROOT/n)==h for n,h in candidate['selected_files'].items())
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from genos_codespace_engine_preflight import check
engines,files,errors=check(ROOT);assert not errors,errors
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
put(DES/'candidate-working.json',{'code_root':'.','selected_files':candidate['selected_files'],'pin':candidate['pin']})
put(ART/'working-copy.json',{'files':decision['files'],'changed_count':len(decision['files']),'candidate_all_files_match':True,'engine_count':engines,'engine_files':files,'errors':errors,'main_unchanged':True})
print('Working copy',len(decision['files']),'changes; candidate531 exact; MAIN150 unchanged')
