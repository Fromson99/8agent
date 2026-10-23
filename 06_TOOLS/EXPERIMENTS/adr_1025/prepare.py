from common import *
from copy import deepcopy
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1024-connection-cycle-retest'
pm=read(prior/'실험/manifest.json');pf=read(prior/'artifacts/design-freeze.json');ps=read(prior/'artifacts/stage.json');parent=ROOT/ps['roots']['candidate']
assert pm['reservation']['status']=='completed' and pm['results']['status']=='complete'
assert all(sha(parent/n)==h for n,h in pf['files']['candidate'].items())
assert sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')==pf['client_sha256']
m=read(ADR/'실험/manifest.json');m['design']=deepcopy(pm['design'])
m['design'].update(sampling='User-requested repeat after first-call provider429. Unchanged final ADR1023 candidate501files, same known public question/data/model/budgets, candidate once. ADR1024 historical parent; completed ADR1022 provides unpaired performance context only. No adaptive rerun or legal quality certification.',working_integration='No product changes. Exact ADR1023 final501files imported into a new isolated candidate. Working tree, MAIN102 and GENOS unchanged.')
m['design']['arms'][0].update(derived_from=['ADR-1024-experiment-v1/candidate'],changes='Completed ADR1024 candidate, first-call provider429; historical only, no baseline calls.',controls='Exact unchanged implementation, same request/data/model/budget; separate time/run.')
m['design']['arms'][1].update(changes='No code or prompt change from final ADR1023/candidate. User-authorized fresh run after provider429.',controls='Exact parent501hashes including tests, same data/model/question,14physical calls/1800s,transport retry0, no fallback.')
m['design']['code_isolation']['candidates']=[]
m['lineage']['hypothesis_delta']='Unchanged parent candidate; obtain a native trace after first-call provider429 prevented previous measurement.'
m['llm_policy']=deepcopy(pm['llm_policy']);m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',m['design'])
files=set(pf['files']['candidate']);present={n for n in files if (ROOT/n).is_file()}
d=ac.snapshot(ADR,'candidate',sorted(present),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);c=d/'snapshot'
# Explicit whole candidate reproduction for an unchanged retest, never copied into working product.
for n in files:
 (c/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(parent/n,c/n)
 if n not in present:ac.register_file(d,n,upstream_state='absent')
assert all(sha(c/n)==h for n,h in pf['files']['candidate'].items())
shutil.copyfile(prior/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':{'candidate':str(c.relative_to(ROOT))},'candidate_dirs':{'candidate':str(d.relative_to(ROOT))},'working_before':{n:sha(ROOT/n) for n in present},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],'parent':str(prior.relative_to(ROOT)),'same_parent_files':len(files)})
save(ART/'inherited-contract-verification.json',{'parent_manifest_sha256':sha(prior/'실험/manifest.json'),'parent_freeze_sha256':sha(prior/'artifacts/design-freeze.json'),'equal_parent_file_hashes':True,'file_count':len(files),'tests_passed_in_parent':107,'tests_rerun_here':False,'reason':'Exact unchanged parent code/tests, no new unresolved contract concern. Run native experiment as requested.','original_test_adr':'ADR-1023','test_log':read(prior/'artifacts/inherited-contract-verification.json')['test_log'],'test_log_sha256':read(prior/'artifacts/inherited-contract-verification.json')['test_log_sha256']})
print('Prepared unchanged candidate',len(files),'files')
