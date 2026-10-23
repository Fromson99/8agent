from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P=ROOT/'04_EXPERIMENTS/ADR/ADR-0991-bounded-expansion-retry-two/artifacts'
s=read(P/'stage.json');B=ROOT/s['roots']['candidate'];files=read(P/'design-freeze.json')['files']['candidate']
assert all(sha(B/n)==h for n,h in files.items())
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='A shorter role-specific prompt preserves requested scope and necessary dependencies; matching reentry capacity to navigation and carrying verified acquired originals prevents loss at bounded stops without changing legal judgments.',
 primary_metric='Exact prompt character reduction; five paired frozen assessment decisions; one candidate native service result and bounded-stop API contracts.',
 success_criteria='ASSESS system text reduced at least40%, entry/navigation/composition redundant instructions reduced without removing source/permission/scope/conditions. Five paired probes: candidate at least4/5, all formula/comparison/explicit-list material dependencies preserved. Known native question delivers article434 source and both thresholds with original-span integrity within8calls; no all-subjects required gap. Bounded stop preserves verified sources and material gaps without extra model stages; contract integrity failures block adoption.',
 failure_criteria='Keep semantic misses, source/hash/ACL/state failures and partial/failed provider records. Provider error stops all remaining physical requests immediately. No whole-case retry or fallback. This in-sample probe cannot alone qualify MAIN.',
 criteria_frozen_before_run=True,sampling='Original question is in-sample; five newly frozen synthetic decisions for development. Paired identical evidence, alternating arm order, no model judge.',
 execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'max_calls_total':18,'max_calls_per_service':8,'probe_calls':10,'sequential':True,'minimum_available_gib':3,'rss_ceiling_gib':6,'order':'native candidate first, then five alternating baseline/candidate decisions'},
 failure_recovery={'owner':'Existing assessment and navigation bounded repair owners; transport alone handles provider errors, experiment sticky stop forbids subsequent dispatch.','budget':'Same native8/retry0/wall480 as ADR0991; reentry must have the same two-call reserve required by navigation. Preserve counters/deadline.','originals':'Revalidate acquired evidence and current authorization, preserve governing context and excluded/deferred branches; do not fabricate navigation delivery or adoption.','meaning':'LLM still decides adequacy and materiality. No keyword heuristics, forced coverage or hidden deletion of gaps.','final_state':'Limited answer or exact source excerpt when available; explicit incomplete if no verified source. Source corruption/ACL/state still fail.','consumers':'Native service/API, evidence pack, assessment/compose, publication, cached request and audit journal.'})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Exact frozen ADR0991 candidate, same fixed evidence/model; native historical reference only',controls='Unchanged source generation, schemas, authority/claim validators, tool set and native limits')
m['design']['arms'][1].update(changes='Compact active prompt constants, align reentry two-call threshold, verified acquired-original fallback',controls='Same schemas, model/provider, source data, native limits, validators; no new model stage')
save(ADR/'실험/manifest.json',m)
tests=['05_TESTS/CONTRACTS/'+n for n in ('test_assessment_review_continuity.py','test_read_choice_input_preservation.py','test_source_span_norm.py','test_assessment_source_reply.py','test_bounded_delivered_handoff.py')]
D=ac.snapshot(ADR,'candidate',list(files)+tests,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);C=D/'snapshot'
for n in files:shutil.copyfile(B/n,C/n)
old=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0988/candidate/snapshot'
for n in tests:shutil.copyfile(old/n,C/n)
save(ART/'stage.json',{'roots':{'baseline':str(B.relative_to(ROOT)),'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'base_release':s['base_release'],'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':{n:sha(ROOT/n) for n in files},'baseline_files':files})
shutil.copyfile(P/'known-request.json',ART/'known-request.json')
print('Isolated419productfiles+5fixtures; parent, model, criteria and failure contracts bound before edits.')
