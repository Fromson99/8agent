from common import *
import shutil,subprocess
s=read(ART/'stage.json');f=read(ART/'design-freeze.json');C=ROOT/s['roots']['candidate'];rows={r['target_path']:r for r in read(C.parent/'candidate.json')['files']}
assert '89 passed' in (ART/'contracts-frozen.log').read_text()
assert not (ART/'working-integration.json').exists()
files=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('connection_scope.py','decision_projection.py')]
files+=['05_TESTS/CONTRACTS/'+n for n in ('test_selected_connection_scope_api.py','test_answer_progress_api.py','test_answer_progress.py','test_connection_scope_refresh.py')]
for n in files:
 assert sha(C/n)==f['files']['candidate'][n]
 if rows[n]['upstream_state']=='present':assert sha(ROOT/n)==rows[n]['upstream_sha256'],n
 else:assert not (ROOT/n).exists(),n
profile='00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'
assert sha(ROOT/profile)==s['working_before'][profile]
assert not read(ROOT/profile)['candidate_navigation'].get('answer_progress_control',False)
backup=ART/'working-before';backup.mkdir(exist_ok=False)
backup_files=[n for n in files if rows[n]['upstream_state']=='present']+[profile,'00_SYSTEM/PIPELINE.json']+[str(p.relative_to(ROOT)) for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json')]
for n in backup_files:
 p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in files:shutil.copyfile(C/n,ROOT/n)
subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('repin.py')),str(ROOT)],check=True)
assert sha(ROOT/profile)==s['working_before'][profile]
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
save(ART/'working-integration.json',{'changed_files':{n:{'before':rows[n]['upstream_sha256'],'after':sha(ROOT/n),'frozen_candidate_match':True} for n in files},
 'excluded_candidate_profile':{'path':profile,'candidate_enabled_answer_progress_control':True,'working_enabled_answer_progress_control':False,'reason':'Native candidate prematurely finished at97, then investigated model-invented155; final attempt429. Do not activate the unsuccessful semantic stopping policy.'},
 'backup_root':str(backup.relative_to(ROOT)),'backup_files':{n:sha(backup/n) for n in backup_files},'engine_pins':read(ART/'working-pins.json'),'main_unchanged':True,'genos_changed':False,
 'rollback':'Restore only changed files and their pin entries after checking subsequent edits. Profile and MAIN were not switched.'})
save(ART/'regression-review.json',{'deterministic_gates_pass':True,'frozen_tests':89,'log':'contracts-frozen.log','initial_failure':'Old budget test expected fallback with two calls left; now asserts fallback with one call left, and new test verifies narrow contract with two.', 'working_policy':'answer_progress_control remains false'})
print('Integrated scope/selector fixes and tests; unsuccessful progress profile remains off')
