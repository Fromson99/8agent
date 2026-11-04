from common import *
import shutil,importlib.util
DES.mkdir(exist_ok=False)
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1353-ontology-acquisition-norm-link-boundary/artifacts'
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1352-ontology-content-review-contract/artifacts'
f=read(P/'design/candidate-repaired.json');assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
put(DES/'working-before.json',f['selected_files'])
for name in ('baseline.json','live-cases.json','source-scope.json','provider-policy.json','ontology-365-r1-context.json','ontology-365-r2-context.json','package-origin.json','records.json','originals.json','originals-origin.json'):
 shutil.copyfile(OLD/'design'/name,DES/name)
shutil.copytree(OLD/'transport',ART/'transport')
assert sha(DES/'provider-policy.json')==sha(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')
put(DES/'authorization.json',{'user_request':'다시 진행해봐','meaning':'New independent build and365 tests on completed1353 final code, following explicit user request to resume','old_unknown_record':str((OLD/'STOP_EXTERNAL.json').relative_to(ROOT)),'old_unknown_sha256':sha(OLD/'STOP_EXTERNAL.json'),'old_remote_completion_still_unknown':True,'old_calls_or_results_rewritten':False,'new_session_prefix':'adr1354-','public_document_ids':read(DES/'source-scope.json')['public'],'isolated_test_only':True,'main_and_production_publication_changes':0})
criteria={'hypothesis':'Final1353 content selection, unique original review, excluded acquisition facts and EFFECT-local norm choice support correct construction and complete365 answers.',
 'build_success':['No administrative statements or free metadata synthesis','All generated statements selected without trimming; existing normalize/source-analysis/project compiler succeeds','Compiled original coordinates and semantics reviewed; no automatic legal approval or production publication'],
 'use_success':['Two independent365 ON answers contain the three correct source-grounded timing rules','No excluded-acquisition or duplicate-original final review errors; default review preserved','Actual COMPLETE approved365 context reaches model; source/ACL/wire errors0; budgets match; duplicate adds0 calls'],
 'failure':['Stop all remaining new sends after any new UNKNOWN; do not replay that request','Preserve any incomplete answer or newly exposed compiler/review failure; do not count raw-source reply as completed','No adaptive retry or code/prompt changes within this frozen ADR'],
 'order':['one build','365 ON independent1','365 ON independent2'],
 'limits':{'build_calls':9,'use_calls_per_cell':40,'use_calls_total':80,'heavy_workers':1,'rss_GiB':5,'available_start_GiB':5,'available_stop_GiB':3,'swap_growth_MiB':128},
 'fixed':'Exact completed1353 working528, same public Commercial Act SQLite and approved365 package; Qwen3.8 FP8 reasoning none; declared provider routing; no output cap; MAIN142 separate.',
 'inference_limits':'Development/in-sample one build and one question repeated twice. No OFF control, no causal speed or broad quality claim. Old1352 UNKNOWN retained; fresh execution authorized by current user request.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Compiler completion and two correct complete365 answers with preserved source validation',success_criteria=criteria['build_success']+criteria['use_success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed1353 technical reference; old1352 observed failures retained',controls='Reference only, no new baseline calls')
m['design']['arms'][1].update(changes='No product change: run completed1353 frozen528 on fresh isolated requests',controls='Same data, Qwen, provider routing, review and approved context')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','repaired')}
m['dataset'].update(name='Archived charter judgment and twice-independent explicit365 question',version='20261104-final-repeat-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Fixed build then365 ON twice, stop any UNKNOWN; no adaptive repeats',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'repaired',list(f['selected_files']),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001']);ac.freeze(can);assert not ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in f['selected_files']},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
assert desc['selected_files']==f['selected_files'];put(DES/'candidate.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='repaired',experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'live_public.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'live_public.py'))]);put(ADR/'실험/manifest.json',m)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
e,n,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':e,'files':n,'errors':errors,'same_as_completed1353':True,'technical_tests_inherited':{'path':str((P/'accepted-test-matrix.json').relative_to(ROOT)),'sha256':sha(P/'accepted-test-matrix.json')}})
print('Fresh frozen528 matches completed1353 and working; engine',e,n,'product changes0')
