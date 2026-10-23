"""Prospective one-question execution of unchanged integrated ADR1033 code."""
from common import *
from copy import deepcopy
import sys, shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1033-read-judgment-continuity'
historical=ROOT/'04_EXPERIMENTS/ADR/ADR-1032-small-connections-live-question'
pm=read(parent/'실험/manifest.json'); pf=read(parent/'artifacts/design-rev-005.json')
hm=read(historical/'실험/manifest.json'); hs=read(historical/'artifacts/stage.json')
assert pm['reservation']['status']=='completed' and pm['results']['status']=='complete'
assert all(sha(ROOT/n)==h for n,h in pf['files'].items())
m=read(ADR/'실험/manifest.json'); d=m['design']
d.update(
 hypothesis='The integrated read_judgment mode records source-specific relevance, reasons and missing information within existing next-action calls, retains earlier opinions and unresolved needs, and explicitly reviews all retained judgments before final publication without repeated equivalent connection actions.',
 primary_metric='Source judgment continuity, complete final review, grounded next-action and repeated-directory audit; physical calls, token usage and latency.',
 success_criteria='One real service request issues an answer or explicitly limited answer; all newly presented source bundles receive validated judgments in an existing next-action call, earlier opinions and open needs/conflicts remain available until explicitly revised with evidence/reason, final assessment covers every retained judgment/need/conflict, no invented source coordinate executed and zero source/hash/ACL violations. No repeated identical connection scope with unchanged state; no dedicated judgment-only model call. At most14 physical calls/1800s. Unexercised revision/conflict branches remain unverified live. Decree163 reach is reported, not a gold answer or injected target.',
 failure_criteria='Schema/review failure preventing final publication, silent loss/overwrite of judgment or unresolved need/conflict, incomplete final review, repeated equivalent connection directory, unsupported coordinate execution, or source/hash/ACL failure. Provider429/transport failure terminates without rerun and is not semantic failure proof. Budget-limited outcome preserves known originals and missing scope.',
 criteria_frozen_before_run=True,
 retrieval_stage_plan=deepcopy(hm['design']['retrieval_stage_plan']),
 sampling='One unchanged exposed public capital-gains question, candidate only; no fresh baseline model call. Exact complete ADR1033 implementation parent. ADR1032 is historical context only, not a paired causal comparison. No target/gold injected into product, no judge call, no adaptive rerun.',
 failure_recovery=deepcopy(pm['design']['failure_recovery']),
 budgets={'per_arm_calls':14,'total_calls':14,'wall_seconds':1800,'rss_limit_gib':6,'minimum_available_gib':4},
 working_integration='No product edits. Exact511 integrated working files equal ADR1033 rev005; frozen candidate and isolated runtime. Selected MAIN102 and GENOS unchanged.',
 historical_comparison={'adr1032_calls':12,'adr1032_input_tokens':574742,'adr1032_seconds':274.69,'paired':False,'profile_difference':'read_judgment true now; this mode disables small-connection automatic reads. Existing next-action and final-assessment payloads contain judgments.'})
d['failure_recovery']['live_limits']='14 physical calls/1800s; provider/transport retries0 and sticky stop; existing schema repair only, no new retry owner; RSS6GiB and minimum available4GiB. Preserve raw failures and retained state.'
d['arms'][0].update(changes='Completed ADR1033 implementation and182 related contracts; no baseline model calls in this probe.',controls='Unchanged integrated working code, exact parent frozen revision; historical ADR1032 is unpaired.')
d['arms'][1].update(changes='No implementation changes. Execute read_judgment=true through actual service.py with frozen code and isolated runtime.',controls='Same known request and65 public documents; Qwen3.8/ParasailFP8/reasoningnone/no fallback;14calls/1800s.')
m['lineage']['hypothesis_delta']='Actual-question probe of exact integrated read-judgment parent code; no product implementation changes.'
m['llm_policy']=deepcopy(hm['llm_policy'])
m['retrieval_accounting']=deepcopy(hm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['runs'][0].update(arm_ids=['candidate'],selection_rule=d['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m)
files=sorted(pf['files'])
candidate_dir=ac.snapshot(ADR,'candidate',files,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
c=candidate_dir/'snapshot'
assert all(sha(c/n)==h for n,h in pf['files'].items())
shutil.copyfile(historical/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':hs['base_release'],'roots':{'candidate':str(c.relative_to(ROOT))},'candidate_dirs':{'candidate':str(candidate_dir.relative_to(ROOT))},'working_before':pf['files'],'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],'parent':str(parent.relative_to(ROOT)),'same_parent_files':len(files),'parent_revision':'rev-005'})
save(ART/'design-before-snapshot.json',d)
print('Prepared exact working/parent candidate',len(files),'files; no product change')
