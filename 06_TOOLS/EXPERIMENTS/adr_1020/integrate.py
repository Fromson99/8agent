from common import *
import shutil,subprocess
s=read(ART/'stage.json');f=read(ART/'design-freeze.json');C=ROOT/s['roots']['candidate'];cm=read(C.parent/'candidate.json')
rows={r['target_path']:r for r in cm['files']}
assert '110 passed' in (ART/'contracts-frozen.log').read_text()
assert all(sha(C/n)==h for n,h in f['files']['candidate'].items())
assert not (ART/'working-integration.json').exists()
files=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('connection_scope.py','law_navigation.py','completion_execution.py','completion_contracts.py','gateway.py')]
files+=['05_TESTS/CONTRACTS/'+n for n in ('test_selected_connection_scope_api.py','test_retained_partial_connections.py','test_connection_card_provenance.py','test_truncated_review_source_reply.py')]
for n in files:
 if rows[n]['upstream_state']=='present':assert sha(ROOT/n)==rows[n]['upstream_sha256'],n
 else:assert not (ROOT/n).exists(),n
backup=ART/'working-before';backup.mkdir(exist_ok=False)
backup_files=[n for n in files if rows[n]['upstream_state']=='present']+['00_SYSTEM/PIPELINE.json']+[str(p.relative_to(ROOT)) for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json')]
for n in backup_files:
 p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in files:shutil.copyfile(C/n,ROOT/n)
subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('repin.py')),str(ROOT)],check=True)
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
save(ART/'working-integration.json',{'changed_files':{n:{'before':rows[n]['upstream_sha256'],'after':sha(ROOT/n),'frozen_candidate_match':sha(ROOT/n)==sha(C/n)} for n in files},
 'backup_root':str(backup.relative_to(ROOT)),'backup_files':{n:sha(backup/n) for n in backup_files},'engine_pins':read(ART/'working-pins.json'),
 'main_unchanged':True,'genos_changed':False,
 'rollback':'Restore only these changed source/test files and their engine file entries from working-before after checking subsequent edits; remove newly added test only if unchanged. Do not replace entire manifests or unrelated Oracle files.'})
save(ART/'regression-review.json',{'deterministic_gates_pass':True,'frozen_tests':110,'log':'contracts-frozen.log',
 'development_failures':'Two old test assertions required the prior eight-witness menu cap; replaced by exact full-witness and one-read-action assertions, all passing. Initial suite path resolution failure retained.',
 'frozen_file_count':len(f['files']['candidate']),'parent_failure_classification':'parent-failure-replay.json'})
print('Integrated five product modules, four tests; MAIN unchanged')
