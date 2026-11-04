"""Freeze the user's selected MAIN142, with no product modifications."""
from common import *
import shutil, importlib.util

DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation']==142
release=read(ROOT/pointer['manifest_path']);code=ROOT/release['code_root']
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
files=release['files'];assert len(files)==528
assert all(sha(code/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':pointer,'release':release,'working_before':{n:sha(ROOT/n) for n in files if (ROOT/n).exists()}})
criteria={
 'user_authorization':'가장최근 메인 142에서 실험해봐',
 'hypothesis':'Unchanged MAIN142 can find and read the applicable charter-amendment resolution rules and produce a supported final answer; inspect whether a failure occurs before relation presentation, target reading, or final assessment.',
 'success':['One real answer contains both consent thresholds with correct denominators and conjunctive application, supported by acquired original text.','Trace discovery, displayed relation direction and scope, target READ, and final claim evidence independently; direct retrieval of the answer can pass answer quality without proving reverse-link traversal.','Original spans, ACL, actual wire, code hashes and request budgets match; duplicate request causes zero additional model calls.'],
 'failure':['Source-only response, technical error or skipped execution is not a successful answer.','No further physical send after UNKNOWN; no retries added by this runner.','Do not substitute working1332/1337 code, hints, expected article numbers, or answer key into product inputs.'],
 'fixed_environment':{'code':'MAIN142 exact528','source':'selected SQLite readonly','state':'isolated SQLite','model':'qwen/qwen3.8-27b','quantization':'fp8','reasoning':'none','provider_policy':'current Parasail primary; known429-only NearAI switch once','ontology':False,'final_reviews':'default enabled','output_token_cap':None},
 'limits':{'physical_per_request':40,'physical_total':40,'turns':1,'one_live_sequence':True,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128,'available_start_GiB':5,'available_stop_GiB':3,'no_automatic_resend_after_unknown':True},
 'grading':'Offline source-grounded manual comparison and trace audit; no judge model; no paired performance or generalization claim.'}
put(DES/'criteria.json',criteria)
grant=read(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
allowed=sorted(grant['public_document_ids'])
assert '7bbe815ff43b6635' in allowed
allowed=['7bbe815ff43b6635']
cases=[{'id':'charter','arms':['main142'],'document_ids':allowed,'steps':[{'number':1,'question':'정관을 변경할 때 주주총회 결의요건은 무엇인가요?','mode':'외규'}]}]
put(DES/'live-cases.json',cases)
put(DES/'authorization.json',{'user_request':criteria['user_authorization'],'prior_explicit_authorization':grant['workflow_authorization']['authorization_text'],'public_document_ids':allowed,'cases_sha256':sha(DES/'live-cases.json'),'grant_path':str((code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json').relative_to(ROOT)),'grant_sha256':sha(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'internal_relabeling':False,'quality_certified':False})
put(DES/'source-scope.json',{'public':allowed,'internal':[]})
shutil.copyfile(code/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Supported final resolution requirements and separately observed relation navigation',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']='User-directed actual single-question diagnosis on MAIN142, no product changes.'
m['design']['arms'][0].update(changes='Completed MAIN142 technical-validation parent reference only; no new baseline model calls',controls='Exact selected528 files')
m['design']['arms'][1].update(changes='No changes: exact selected MAIN142 bytes under actual Qwen',controls='Default reviews and unchanged navigation; isolated state and public original scope')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','main142')}
m['runs'][0].update(arm_ids=['main142'],selection_rule='One frozen user-described public charter question, once, no article hints; stop after UNKNOWN; successful same-request cache retrieval only',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='User-reported charter-amendment resolution question',version='20261104-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['not_applicable_reason']='Same original corpus and retrieval; actual acquisition/presentation measured, no answer-key recall claim'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
# Use immutable release paths as upstream, never copy mutable working products.
sources=[release['code_root']+'/'+n for n in files]
can=ac.snapshot(ADR,'main142',sources,experiment_id=m['experiment_id'],arm_id='main142',run_ids=['run-001'])
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');revision=cm['revisions'][-1]
C=can/'revisions'/revision['revision_id']/'snapshot'/release['code_root']
assert all(sha(C/n)==h for n,h in files.items())
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':files,'selected_equivalent':True,'selected_main':142,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}}
put(DES/'candidate-main142.json',desc)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors,'same_selected528':True})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1335-voting-repeat-live/artifacts/transport',ART/'transport')
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='main142',experiment_id=m['experiment_id'],arm_id='main142',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'before_model_calls':True,'live_calls_started':False,'same_selected_product_files':528})
print('Frozen MAIN142 exact528; single charter question; no product changes')
