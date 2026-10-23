from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
assert not (ART/'stage.json').exists()
release=read(ROOT/'08_DEPLOYMENT/RELEASES/selected-connection-coverage-20261022-r1/release.json')
base=ROOT/release['code_root']
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1001-main102-connection-live-audit/artifacts'
files=sorted(read(prior/'design-freeze.json')['files']['candidate'])
assert all(sha(base/n)==h for n,h in release['files'].items())
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='An explicit answer-progress review in the existing navigation call improves termination without a separate monitor model: assess current answer, material missing source and expected answer change, preserve original-based judgment and hand off after two model-reported no-change steps.',
 primary_metric='Counterfactual stop/continue correctness; native public request completion within14physicalcalls, required source coverage and exact source/ACL integrity.',
 success_criteria='Candidate passes all deterministic state/recovery/API contracts. Candidate scores3of3 on frozen synthetic stage probes (enough→FINISH; missing delegated original→READ; narrowed unresolved chain→READ), with no regression versus paired baseline. One native public question returns200 within14physicalcalls, acquires income-tax97 and decree163, and all original spans match scope/hash. No source/ACL/state regression or fabricated completion. No legal-answer accuracy certification.',
 failure_criteria='Premature FINISH on missing/chain, candidate stage regression, native unfinished by14physicalcalls, required source missing, semantic/grammar repair exhausted, source/ACL/state breach or added monitor calls fails criteria. First provider/transport failure stops all remaining model cases. Preserve all outcomes; no adaptive reruns.',
 criteria_frozen_before_run=True,
 sampling='Three synthetic decision scenarios paired baseline→candidate sequentially, then one previously exposed public capital-gains question on candidate only. MAIN102 native baseline is independently recorded in ADR1001; historical whole-run comparison is descriptive, not randomized causal proof. No gold supplied to product.',
 execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'stage_probe_calls':6,'native_physical_call_ceiling':14,'max_calls_total':20,'native_profile_model_attempts':40,'max_transport_retries':0,'concurrency':1,'rss_ceiling_gib':6,'minimum_available_gib':3},
 failure_recovery={'classification':'Answer sufficiency/progress are model judgments; repeated operation/outcome is system observation; neither certifies legal truth','owner':'Existing read-choice bounded decision owns one schema repair; existing native ASSESS/COMPOSE owns final claims. Progress handoff after two accepted model NO_CHANGE/FAILED reviews with originals, or model NO_PROGRESS. No extra monitor invocation.','preservation':'Persist request-bound progress receipts and exact proposal before handoff; presentation/restart cannot reset streak; no source/ACL/hash relaxation','limits':'Existing native deadlines/call counters retained; research outer ceiling14 records stopped failure and does not manufacture answer','final':'Progress stop enters existing bounded original handoff and assessment, not a hard error or automatic successful answer'},
 retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{a:[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}] for a in ('baseline','candidate')}})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Exact immutable MAIN102 for paired stage probes; ADR1001 native audit separate historical reference',controls='Same synthetic input, model/provider/output limits; no product change')
m['design']['arms'][1].update(changes='Opt-in answer-progress review and persisted bounded handoff in existing navigation choice; no extra LLM stage',controls='Source/read/link/ACL/hash/assessment/composition contracts unchanged; source judgments remain model-owned; no question or legal-coordinate heuristic')
m['runs'][0].update(selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'stage-probe-and-native','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
save(ADR/'실험/manifest.json',m)
save(ART/'design-before-implementation.json',{'design':m['design'],'selected_release_id':release['release_id'],'references':[
 {'url':'https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/loopDetectionService.ts','lesson':'Separate exact repetitive actions/content from optional periodic semantic loop diagnosis; different target collection is not by itself a repeated-action loop.'},
 {'url':'https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/stuck_detector.py','lesson':'Compare both action and observation, including alternating patterns; preserve useful work with changed outcomes.'},
 {'url':'https://arxiv.org/abs/2510.08517','lesson':'Counterfactual evidence-present/evidence-missing termination pairs; paper uses fine-tuning in medical/math tasks, not evidence that prompting alone solves RAG termination.'}]})
D=ac.snapshot(ADR,'candidate',files,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);C=D/'snapshot'
for n in release['files']:shutil.copyfile(base/n,C/n)
save(ART/'stage.json',{'base_release':release,'roots':{'baseline':str(base.relative_to(ROOT)),'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_before':{n:sha(ROOT/n) for n in files}})
save(ART/'known-request.json',read(prior/'known-request.json'))
print('Design and selected baseline fixed; isolated candidate ready for implementation')
