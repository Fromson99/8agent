from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-0999-original-context-inline-live-rerun/artifacts'
f=read(prior/'design-freeze.json');s=read(prior/'stage.json')
assert not (ART/'stage.json').exists()
assert all(sha(ROOT/n)==h for n,h in f['working_files'].items())
files={n:sha(ROOT/n) for n in sorted(set(f['working_files'])|{'05_TESTS/CONTRACTS/test_decision_original_context.py'})}
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='A single validated reference endpoint extent and exact acquired coverage shared by link cards, scope grants, pending checks and READ offers removes article-only unread contradictions without legal-coordinate special cases.',
 primary_metric='Canonical scope and coverage invariants, no duplicate READ offered after acquisition, native route and original context through decree163, final publication.',
 success_criteria='Regression reproduces empty-block article endpoint defect before correction; same canonical blocks drive displayed endpoint, grant, obligation and already_read. Full source, structural subtree and explicit child ranges respect exact acquired codepoints; partial reads stay unread; corrupt/out-of-scope targets fail closed. Native API chain reads root→linked target→next target without redisplaying completed READ, preserves original question/bodies, and duplicate request has no extra calls. One natural known-question run observes92→97 connection and no acquired97 READ recurrence, reaches163 and publishes answer. Legal correctness remains unscored without approved gold.',
 failure_criteria='Any scope/ACL/hash broadening, partial read marked complete, duplicate completed READ, altered source or unbounded recovery blocks integration. Record independent semantic expansion/provider/output failures without changing frozen candidate or rerunning the whole question.',criteria_frozen_before_run=True,
 sampling='Deterministic data/contract/API regressions plus one identical public question through native service/API. Historical ADR0999 only; no baseline live rerun, no coordinate/gold injection.',
 execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'max_calls_total':40,'max_model_attempts':40,'max_output_tokens':6400,'wall_seconds':1800,'max_transport_retries':0,'concurrency':1,'rss_ceiling_gib':6,'minimum_available_gib':3},
 failure_recovery={'coverage_owner':'unit_relations canonical endpoint and acquired block coverage; existing evidence_inventory codepoint validation','classification':'Empty list on article endpoint is source-wide representation, not missing original. Missing/corrupt non-root structural extent is contract failure, not broadening. Partial evidence stays incomplete.','duplicate':'Do not offer completed linked READ; existing action duplicate guard and one repair remain backstop','semantic':'Model chooses relevance, sufficiency and remaining links; no97/163 or question-specific branch','provider':'Sticky stop; zero transport retry; one existing native schema/assessment repair','state':'Existing request/source/generation/scope bindings and journal, original bodies and failed attempts preserved','final':'Publish only accepted claims; preserve explicit failure when model output cannot validate'},
 retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{a:[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}] for a in ['baseline','candidate']}})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Completed ADR0999 native failure, historical only',controls='Same public question/data/model/budgets; no causal speed comparison')
m['design']['arms'][1].update(changes='Shared canonical endpoint extent and codepoint acquisition, consistent link menus and native API regression',controls='Question and legal decisions remain model-owned; same reader, source/generation/hash/ACL and repair limits; no new legal routing heuristics')
save(ADR/'실험/manifest.json',m)
save(ART/'design-before-implementation.json',{'design':m['design'],'manifest_sha256':sha(ADR/'실험/manifest.json')})
D=ac.snapshot(ADR,'candidate',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
save(ART/'stage.json',{'base_release':s['base_release'],'roots':{'candidate':str((D/'snapshot').relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_before':files})
print('Prepared candidate',len(files),'files')
