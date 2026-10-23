from common import *
s=read(ART/'stage.json');C=ROOT/s['roots']['candidate'];rows={r['target_path']:r for r in read(C.parent/'candidate.json')['files']}
files=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('connection_scope.py','law_navigation.py','completion_execution.py','completion_contracts.py','gateway.py')]
files+=['05_TESTS/CONTRACTS/'+n for n in ('test_selected_connection_scope_api.py','test_retained_partial_connections.py','test_connection_card_provenance.py','test_truncated_review_source_reply.py')]
assert all(sha(ROOT/n)==sha(C/n) for n in files)
backup=ART/'working-before';pins={};mismatch=[];checked=0
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for n,h in v.get('files',{}).items():
  checked+=1
  if sha(ROOT/n)!=h:mismatch.append({'manifest':str(p.relative_to(ROOT)),'file':n})
  if n in files:assert sha(ROOT/n)==h
 if sha(p)!=sha(backup/p.relative_to(ROOT)):pins[str(p.relative_to(ROOT))]={'before':sha(backup/p.relative_to(ROOT)),'after':sha(p)}
for e in read(ROOT/'00_SYSTEM/PIPELINE.json')['engines'].values():assert sha(ROOT/e['manifest'])==e['sha256']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
save(ART/'working-integration.json',{'changed_files':{n:{'before':rows[n]['upstream_sha256'],'after':sha(ROOT/n),'frozen_candidate_match':True} for n in files},
 'backup_root':str(backup.relative_to(ROOT)),'backup_files':{str(p.relative_to(backup)):sha(p) for p in backup.rglob('*') if p.is_file()},
 'engine_pins':{'changed':pins,'checked':checked,'unrelated_upstream_mismatches':mismatch,'own_pins_verified':True},
 'main_unchanged':True,'genos_changed':False,'rollback':'Restore only changed files and their engine hash entries after checking subsequent edits; do not replace whole manifests. New test may be removed only if unchanged.'})
save(ART/'regression-review.json',{'deterministic_gates_pass':True,'frozen_tests':110,'log':'contracts-frozen.log',
 'development_failures':'Two prior assertions expected the old eight-witness cap; updated to full witnesses and one deduplicated read. Initial nonexistent test path error retained.',
 'frozen_file_count':497,'parent_failure_classification':'parent-failure-replay.json'})
print('Own source/test/pins integrated; unrelated pin mismatches:',sorted({r['file'] for r in mismatch}))
