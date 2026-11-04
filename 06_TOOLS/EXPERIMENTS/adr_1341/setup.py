from common import *
import shutil,importlib.util,ast
DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path'])
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1340-candidate-page-cycle-handoff/artifacts/design/candidate-bounded.json')
assert len(parent['selected_files'])==528 and all(sha(ROOT/n)==h for n,h in parent['selected_files'].items())
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
assert all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
put(DES/'baseline.json',{'pointer':pointer,'release':release,'working_before':parent['selected_files'],'parent':parent['pin']})
criteria={
 'user_authorization':'실험해봐 — preceding turn fixed candidate-page-cycle control in ADR1340; run the same charter question on that verified code.',
 'hypothesis':'The completed1340 working candidate can answer the charter amendment resolution question using stored sources without consuming the entire investigation reserve in unchanged candidate-page cycles.',
 'success':['Final supported explanation includes both consent thresholds with correct denominators and conjunctive application, with the required source actually acquired.',
 'If a same-menu no-new-page cycle occurs, the pager yields to the existing assessment path; no investigation-budget exhaustion caused by repeated pages. If no cycle occurs, record the guard as not exercised rather than runtime-proven.',
 'Original spans, ACL, actual provider wire, frozen code and request budgets match; same-request cache requery adds zero model calls.'],
 'failure':['Original-only/errors/skipped are not successful final answers.','Stop on UNKNOWN; no resend or adaptive product/prompt changes.','No article hints, answer key or observed earlier response injected into live product input.'],
 'fixed_environment':{'code':'Completed1340 exact528, includes earlier1332/1337 working changes; selectedMAIN142 remains unchanged','source':'Same selected public commercial-law SQLite','state':'isolated SQLite','model':'qwen/qwen3.8-27b','quantization':'fp8','reasoning':'none','temperature':0,'provider_policy':'Parasail primary; known429-only NearAI once','ontology':False,'final_reviews':'default enabled','output_token_cap':None},
 'limits':{'physical_per_request':40,'physical_total':40,'turns':1,'one_live_sequence':True,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128,'available_start_GiB':5,'available_stop_GiB':3,'no_automatic_resend_after_unknown':True},
 'grading':'Stored-source/manual semantics and recorded trace; no judge models. Earlier1338 is a historical observation, not a simultaneous controlled comparison. Other working changes preclude attribution of all differences to the pager.'}
put(DES/'criteria.json',criteria)
grant=read(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json');allowed=['7bbe815ff43b6635'];assert set(allowed)<=set(grant['public_document_ids'])
cases=[{'id':'charter','arms':['bounded'],'document_ids':allowed,'steps':[{'number':1,'question':'정관을 변경할 때 주주총회 결의요건은 무엇인가요?','mode':'외규'}]}]
put(DES/'live-cases.json',cases)
put(DES/'authorization.json',{'user_request':criteria['user_authorization'],'prior_explicit_authorization':grant['workflow_authorization']['authorization_text'],'public_document_ids':allowed,'cases_sha256':sha(DES/'live-cases.json'),'grant_path':'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','grant_sha256':sha(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'internal_relabeling':False,'quality_certified':False})
put(DES/'source-scope.json',{'public':allowed,'internal':[]})
shutil.copyfile(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Supported final answer and bounded candidate paging; independently observed guard exercise',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']='No new product changes; actual single-question validation of completed1340 bounded pager working code.'
m['design']['arms'][0].update(changes='Completed1340 contract reference only; previous1338 actual outcome remains historical',controls='No new baseline model calls')
m['design']['arms'][1].update(changes='No changes to completed1340 exact528; real model evaluation',controls='Same question/data/default reviews/routing/budgets, isolated state')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','bounded')}
m['runs'][0].update(arm_ids=['bounded'],selection_rule='Single public charter question once; no article hint; stop on UNKNOWN; successful identical request requery only',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Same user-reported charter amendment resolution question',version='20261104-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['not_applicable_reason']='Unchanged retrieval; actual acquisition/presentation measured without approved gold recall'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'bounded',list(parent['selected_files']),experiment_id=m['experiment_id'],arm_id='bounded',run_ids=['run-001'])
assert all(sha(can/'snapshot'/n)==h for n,h in parent['selected_files'].items())
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':parent['selected_files'],'selected_equivalent':False,'parent_adr':'ADR-1340','same_parent528':True,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-bounded.json',desc)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors,'same_parent528':True})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1338-main142-charter-resolution-live/artifacts/transport',ART/'transport')
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='bounded',experiment_id=m['experiment_id'],arm_id='bounded',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text())
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'before_model_calls':True,'live_calls_started':False,'same_parent_product_files':528})
print('Frozen1340 exact528; one charter question; no product changes; selected MAIN142 unchanged')
