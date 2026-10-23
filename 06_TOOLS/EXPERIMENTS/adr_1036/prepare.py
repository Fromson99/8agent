"""Freeze one authorized retry of the identical verified working implementation."""
from common import *
from copy import deepcopy
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1035-judgment-keep-retry-recovery'
pm=read(parent/'실험/manifest.json');pf=read(parent/'artifacts/design-freeze.json');ps=read(parent/'artifacts/stage.json')
assert pm['results']['status']=='complete' and pm['reservation']['status']=='completed'
files=pf['files']['candidate'];assert all(sha(ROOT/n)==h for n,h in files.items())
m=read(ADR/'실험/manifest.json'); d=deepcopy(pm['design'])
d['code_isolation']=m['design']['code_isolation'];d['arms']=m['design']['arms']
d.update(hypothesis='The unchanged verified ADR1035 KEEP/WITHDRAW delta and retained same-evidence correction budget permit the actual public question to progress to97 and answer when provider calls return; this is a user-requested fresh isolated rerun after provider429, not an automatic replay of a reserved decision.',
    primary_metric='97 acquisition without KEEP rejection, retained judgments/needs/final review, duplicate actions, physical calls/tokens/latency and exact source integrity.',
    success_criteria='Exact513files/data/question/model match parent. Actual question reads97 without KEEP rejection and returns answer or explicit limited answer, preserves prior judgment/need/conflict identities and reviews all accumulated heads at final assessment, executes no equivalent duplicate directory or unsupported coordinate. Zero hash/ACL violations;14physicalcalls/1800s.163 reach is observed, never forced or injected. Parent deterministic tests are inherited, not newly claimed.',
    failure_criteria='Changed source binding or input, failed hash/ACL, KEEP rejection blocking97, no97 acquisition, lost prior judgment/need/conflict or missing final review. Provider429/transport stops once with no further run; incomplete provider execution cannot establish model quality. Unexercised paths remain unverified.',
    sampling='One candidate run-001, exact known-query from1035 and same65public documents. No new baseline call, no judge or legal gold. Parent1035 was provider-blocked,1034 is historical unpaired context. No adaptive retries after observing this run.',
    working_integration='No product implementation changes or working integration in this rerun. Working513files, selected MAIN102 and GENOS remain unchanged.',
    historical_comparison={'parent':'ADR-1035-experiment-v1/candidate','calls':2,'normal_responses':1,'failure':'Parasail upstream429 on first read-choice','paired':False,'older_failed_execution':'ADR-1034-experiment-v1/candidate'})
d['arms'][0].update(changes='Completed parent1035 provider-blocked run with verified deterministic fixes.',controls='Historical unpaired result; no fresh baseline model call.')
d['arms'][1].update(changes='No code/prompt/model/data change. New explicitly authorized full question execution after parent provider429.',controls='Same513files, question,65public documents,Qwen3.8/ParasailFP8/none/no fallback,14calls/1800s.')
m['design']=d;m['lineage']['hypothesis_delta']=d['hypothesis'];m['llm_policy']=deepcopy(pm['llm_policy'])
m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING')
m['runs'][0].update(arm_ids=['candidate'],selection_rule=d['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',d)
cd=ac.snapshot(ADR,'candidate',sorted(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);c=cd/'snapshot'
shutil.copyfile(parent/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':{'candidate':str(c.relative_to(ROOT))},'root':str(c.relative_to(ROOT)),
    'candidate_dirs':{'candidate':str(cd.relative_to(ROOT))},'candidate_dir':str(cd.relative_to(ROOT)),
    'working_before':files,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],
    'parent':str(parent.relative_to(ROOT)),'same_parent_files':len(files),
    'inherited_tests':{'artifact':str((parent/'artifacts/result.json').relative_to(ROOT)),'sha256':sha(parent/'artifacts/result.json'),
        'candidate_passed':155,'same_parent_failures':6,'working_target_passed':60,'new_tests_run':0}})
save(ART/'graph-before.json',{'validation_errors':read(ROOT/'04_EXPERIMENTS/ADR/EXPERIMENT_GRAPH.json')['validation_errors']})
print('Prepared unchanged parent/working snapshot:',len(files))
