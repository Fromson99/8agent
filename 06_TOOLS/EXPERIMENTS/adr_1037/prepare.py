"""One preregistered uncapped rerun; working/MAIN/GENOS remain unchanged."""
from common import *
from copy import deepcopy
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1036-judgment-keep-live-retry'
pm=read(parent/'실험/manifest.json');pf=read(parent/'artifacts/design-freeze.json')
assert pm['results']['status']=='complete' and pm['reservation']['status']=='completed'
old=pf['files']['candidate'];files={n:sha(ROOT/n) for n in old}
maintenance=ROOT/'09_ARTIFACTS/AUDITS/20261023-output-unlimited-main'
allowed=set(read(maintenance/'source-binding.json')['working_modified'])
delta=[n for n in files if files[n]!=old[n]];assert len(files)==513 and set(delta)<=allowed
assert read(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['max_output_tokens'] is None
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/pointer['manifest_path'])
assert pointer['generation']==103 and base['data_path']==read(parent/'artifacts/stage.json')['base_release']['data_path']
m=read(ADR/'실험/manifest.json');d=deepcopy(pm['design'])
d['code_isolation']=m['design']['code_isolation'];d['arms']=m['design']['arms']
d.update(hypothesis='Removing application output caps from the existing read-judgment implementation allows a complete READ/KEEP proposal, acquisition of97 and a validated final answer; it may instead expose continuing whitespace repetition, provider limits, timeouts or reasoning failures.',
 primary_metric='Wire cap absence; complete READ/KEEP execution,97/163 original acquisition, retained judgments/needs and final review, duplicate actions, physical calls/tokens/latency, exact source integrity.',
 success_criteria='All wire requests omit max_tokens/max_completion_tokens/max_output_tokens. Same question65public documents/model/provider and14call1800s budget as1036. Read97 without KEEP rejection and return answer or explicit limited answer; preserve previous judgments/needs/conflicts and validate final review of accumulated heads. Zero equivalent directory loops, unsupported coordinates, hash/ACL violations.163 reach observed without product target injection.',
 failure_criteria='Any output cap transmitted, lost judgment/need/conflict, unsupported coordinate, hash/ACL mismatch, failed97 acquisition or missing validated final answer. Provider429/transport stops once without fresh retry; server length remains incomplete and cannot be repaired by raising an application cap. Unexercised paths unverified.',
 sampling='One candidate run-001 on the exposed known-query from1036, same65public documents. Historical1036 six-call failed result only; no new capped baseline/no judge/no legal gold. No adaptive retry after observed result.',
 working_integration='No product changes. Frozen current513file working candidate differs from1036 only in31 authorized output-policy/adapter/profile/pin files. The separately hash-bound current ExperimentClient implements the same no-app-cap policy. Selected MAIN103 and GENOS unchanged.',
 historical_comparison={'parent':'ADR-1036-experiment-v1/candidate','calls':6,'failure':'Two6400-token incomplete READ outputs, invalid final review, then429','paired':False},
 output_policy={'max_output_tokens':None,'policy_sha256':sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'legacy_override':'ignored by current ExperimentClient','server_limits':'unknown, not disabled','failure_parity':'Audited adapter preserves current LocalGemmaTransport OUTPUT_INCOMPLETE classification with allow_length_repair=False, instead of previous generic ProposalError.'})
d['arms'][0].update(changes='Completed1036 failed capped run, reused as historical context only.',controls='No fresh capped baseline model calls; single exposed question, unpaired comparison.')
d['arms'][1].update(changes='Authorized output-cap removal and matching uncapped incomplete-response classification; no navigation/prompt/data/model changes.',controls='Same working read-judgment implementation, exact question65public documents,Qwen3.8/ParasailFP8/none/no fallback,14calls/1800s.')
d['budgets'].update(max_output_tokens=None)
d['failure_recovery']['uncapped_output']='Provider length preserves incomplete error; no cap-expansion regeneration. Existing schema/decision budgets unchanged.'
m['design']=d;m['lineage']['hypothesis_delta']=d['hypothesis'];m['llm_policy']=deepcopy(pm['llm_policy']);m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING')
m['runs'][0].update(arm_ids=['candidate'],selection_rule=d['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',d)
cd=ac.snapshot(ADR,'candidate',sorted(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);c=cd/'snapshot'
shutil.copyfile(parent/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':base,'roots':{'candidate':str(c.relative_to(ROOT))},'root':str(c.relative_to(ROOT)),
 'candidate_dirs':{'candidate':str(cd.relative_to(ROOT))},'candidate_dir':str(cd.relative_to(ROOT)),
 'working_before':files,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],
 'parent':str(parent.relative_to(ROOT)),'parent_files':len(files),'changed_files':delta,
 'inherited_tests':{'artifact':str((maintenance/'validation.json').relative_to(ROOT)),'sha256':sha(maintenance/'validation.json'),
 'working_cap_contracts':58,'main_cap_contracts':56,'note':'Prior cap-removal tests; new isolated candidate tests separately recorded.'}})
save(ART/'graph-before.json',{'validation_errors':read(ROOT/'04_EXPERIMENTS/ADR/EXPERIMENT_GRAPH.json')['validation_errors']})
print('Prepared513files; authorized31cap/pin deltas; selectedMAIN103 retained')
