from common import *
import shutil,importlib.util

DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path'])
parent_dir=ROOT/'04_EXPERIMENTS/ADR/ADR-1326-assessment-scope-recovery-contract'
parent=read(parent_dir/'artifacts/design/candidate-integrated.json')
assert all(sha(ROOT/n)==h for n,h in parent['selected_files'].items())
put(DES/'baseline.json',{'pointer':pointer,'release':release,'working_before':parent['selected_files']})
criteria={
 'user_authorization':'계속수정해봐 우리 통테 통과하게 — completed1326 structural repair actual question experiment, fresh isolated requests; no replay of prior UNKNOWN request',
 'hypothesis':'Exact completed1326 per-original scope assessment and typed review recovery can produce supported explanations for a fixed four-turn public conversation without the observed shared-link/empty-claim rejection or accidental goal reset.',
 'success':['Every executed question returns substantive supported claims, not only original excerpts or HTTP200.','Turn1/2 annual regular-meeting rule and timing agree; extra qualifications must match the stored original.','Turn3 resolves the omitted meeting context, explains temporary-meeting timing from the stored original, and maintains the existing goal for this related followup.','Turn4 answers voting rules from commercial law369 without continuing the earlier meeting-timing task; distinguish content completion from goal selection.','Actual final ASSESS uses one original per scope row, no model-owned review_links/link_ref; saved successful assessments use v3-direct; source/ACL/hash/budget/duplicate checks pass. Known review-failure recovery is distinct from missing-source search.'],
 'failure':['Source-only, unadopted explanation, errors or skipped turns are not passes.','No retries after UNKNOWN, no changing frozen product/prompts after viewing results.','No main/GENOS/internal-model or full60-pass inference from this public4turn probe.'],
 'fixed_environment':{'source':'selected140 SQLite generation readonly','state':'isolated SQLite','model':'qwen/qwen3.8-27b','quantization':'fp8','reasoning':'none','provider_policy':'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json','ontology':False,'final_reviews':'default enabled','output_token_cap':None},
 'limits':{'physical_per_request':40,'physical_total':160,'turns':4,'one_live_sequence':True,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128,'available_start_GiB':5,'available_stop_GiB':3,'no_automatic_resend_after_unknown':True},
 'grading':'Read-only stored original and runtime/response audit; no judge model, no answer key in product input. Content success, memory continuity, provider outcome and schema behavior are separate metrics.',
 'prior_observation':'1325: regular1 source-only scope unsupported original; repeated2 same goal but replan thenUNKNOWN; followup/topic skipped. Historical context only, no paired comparison.'}
put(DES/'criteria.json',criteria)
grant=read(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json');allowed=sorted(grant['public_document_ids'])
cases=[{'id':'repeat','arms':['integrated'],'document_ids':allowed,'steps':[
 {'number':1,'question':'상법상 정기주주총회는 언제 소집해야 하나요?','mode':'외규'},
 {'number':2,'question':'상법상 정기주주총회는 언제 소집해야 하나요?','mode':'외규'},
 {'number':3,'question':'그럼 임시총회는 언제 소집하나요?','mode':'외규'},
 {'number':4,'question':'상법 제369조의 의결권 원칙을 알려줘.','mode':'외규'}]}]
put(DES/'live-cases.json',cases)
put(DES/'authorization.json',{'user_request':criteria['user_authorization'],'prior_explicit_authorization':grant['workflow_authorization']['authorization_text'],'public_document_ids':allowed,'cases_sha256':sha(DES/'live-cases.json'),'grant_path':'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','grant_sha256':sha(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'internal_relabeling':False,'quality_certified':False})
put(DES/'source-scope.json',{'public':allowed,'internal':[]})
shutil.copyfile(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Per-turn supported final explanation plus correct continuation/topic transition; source/security/budget integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']='No new product change; prospectively frozen actual model validation of completed1326.'
m['design']['arms'][0].update(changes='Completed1326 reference only; no new baseline model calls',controls='Exact525 source files and selected data generation')
m['design']['arms'][1].update(changes='No code change: completed1326 exact bytes under actual model',controls='Same default reviews, source/ACL/budget/UNKNOWN behavior; no prompts or product modifications during run')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','integrated')}
m['runs'][0].update(arm_ids=['integrated'],selection_rule='One fixed four-turn public session in order, each once; stop on UNKNOWN or non200 parent; saved successful request requery may not send models',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Fixed previous public regular/repeat/temporary/topic-change questions',version='20261104-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['not_applicable_reason']='Observed after run; same original corpus/ranking; no answer-key recall claim'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',list(parent['selected_files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
assert all(sha(can/'snapshot'/n)==h for n,h in parent['selected_files'].items())
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');revision=cm['revisions'][-1];C=can/'revisions'/revision['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':parent['selected_files'],'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}}
put(DES/'candidate-integrated.json',desc)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors,'same_parent525':True})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1319-multiturn-command-assessment-repair/artifacts/transport',ART/'transport')
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*(DES.glob('*.json'))]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'before_model_calls':True,'live_calls_started':False,'same_parent_product_files':525})
print('Frozen new4turn session;same525parent;review defaults enabled;no product changes;selected MAIN',pointer['generation'])
