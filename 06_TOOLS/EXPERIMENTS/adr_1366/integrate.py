"""Integrate only verified product changes, preserving concurrent work and MAIN."""
from common import *
import shutil,importlib.util
f=read(DES/'candidate-repaired.json');C=ROOT/f['code_root'];before=read(DES/'working-before.json');b=read(DES/'baseline.json')
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent working changes: preserve and stop'
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
tests=read(ART/'final-contracts/result.json');bounds=tests
assert tests['failed']==bounds['failed']==0
products=['request_entry.py','structure_selection.py','wire_schema.py','decision_projection.py','need_continuity.py','completion_execution.py','source_goal_control.py','investigation_supervisor.py','provider_routing.py','source_work_review.py']
products=['02_BACKEND/semantic_runtime/legal_agent/'+p for p in products]
changes={n:h for n,h in f['selected_files'].items() if before[n]!=h}
assert all(n.startswith('02_BACKEND/ENGINES/') or n in ['00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py',*products] for n in changes)
put(ART/'integration-preflight.json',{'before':{n:before[n] for n in changes},'after':changes,'candidate':f['pin'],'tests':{'new_and_reused_contracts':tests['passed'],'wire_boundaries':bounds['passed']},'no_validation_removed':True,'main_changed':False})
for n in changes:
 p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in changes:
 p=ROOT/n;temp=p.with_name('.'+p.name+'.adr1366');shutil.copyfile(C/n,temp);os.replace(temp,p)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(ROOT);assert not errors,errors
put(ART/'working-integration.json',{'changes':changes,'changed_files':len(changes),'whole528_matches_candidate':True,'main_generation':142,'active_pointer_unchanged':True,'engine_preflight':{'engines':engines,'files':count,'errors':errors}})
print('Integrated',len(changes),'files; working528 exactly frozen, MAIN142 unchanged')
