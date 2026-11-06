"""Freeze the user's selected MAIN145, with no product modifications."""
from common import *
import shutil, importlib.util

DES.mkdir(exist_ok=False)
pointer=read(ART/'activation-at-request.json')
assert pointer['generation']==145 and pointer['release_manifest_sha256']=='2c8f5f6d58abde41469566088bf9ca7a94cf5926df3c844ed1d54c962fff5d24'
release=read(ROOT/pointer['manifest_path']);code=ROOT/release['code_root']
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
files=release['files'];assert len(files)==528
assert all(sha(code/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':pointer,'release':release,'working_before':{n:sha(ROOT/n) for n in files if (ROOT/n).exists()}})
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1383-main145-ontology-usage/artifacts/usage-live/legacy365-on1-ontology-on'
record=read(parent/'turn-1/response.json.gz')['body']; agent=record['assembly']['term_agent']
assert agent['stop_reason']=='ASSESSMENT_CONTRACT_UNRESOLVED' and not record['answer']['claims']
view=agent['review_explanation']
offered=next(a for a in view['actions'] if a['enabled'] and a['kind']=='REVIEW_AGAIN')
req=read(parent/'turn-1/request.json')
archive=read(parent/'runtime-archive.json')
assert sha(parent/'runtime.tar.gz')==archive['archive']['sha256']
assert sha(parent/'runtime-inventory.json.gz')==archive['inventory']['stored_sha256']
assert all(sha(ROOT/read(parent/'binding.json')['code_root']/n)==h for n,h in files.items())
seed=ART/'action-seed'
put(seed/'origin.json',{'parent_dir':str(parent.relative_to(ROOT)),'sent_question':req['question'],'session_id':req['session_id'],'case_id':record['question_id'],'revision':record['revision'],'owner':'adr1383','request_sha256':sha(parent/'turn-1/request.json'),'response_sha256':sha(parent/'turn-1/response.json.gz'),'archive':archive['archive'],'inventory_sha256':archive['inventory']['stored_sha256']})
put(seed/'action-request.json',{'label':offered['label'],'review_action':{'schema_version':'review-action-v1','case_id':view['case']['question_id'],'revision':view['case']['revision'],'action_id':offered['id'],'view_hash':view['content_sha256'],'operation_id':'adr1387-structured','input':{}}})
prior_profile=read(parent/'binding.json')['profile']
put(DES/'parent-profile.json',prior_profile)
criteria={
 'user_authorization':'스왑 늘ㄹ릴수 있겠나? 그리고 실패했던거 다시 실험해봐',
 'hypothesis':'A direct offered action on an actual stored failed 365 assessment starts review of the existing evidence; compare the exact photo sentence from an independently restored copy of the same starting case.',
 'success':['Both runs open a separately SHA-verified copy of the identical source-failure archive and preserve scope, source generation and principal.','For each turn report accepted command, entry stage, goal identity, source and claim coverage, wire, duplicate model calls and user-visible content.','A full answer states all three requested timing rules and cites the matching source for each. Partial coverage is reported explicitly.'],
 'failure':['Run only if 1384 first turn succeeds, does not reproduce eligible failure and has no UNKNOWN. Any UNKNOWN or technical stop on this comparison prevents further physical sends.','Do not change previous records, source, stored assessment, authorization or model binding. No clue or answer key injections.'],
 'fixed_environment':{'code':'MAIN145 exact528','model':'qwen/qwen3.8-27b','reasoning':'none','ontology':'original authorized 1383 legacy365-on1 ON snapshot','source':'public Commercial Act SQLite1','turns':'one explicit action then one free-text request in independent clones','limits':'40 per request, 80 total, 1GiB swap growth, >=3GiB RAM and >=1GiB swap free, maximum5GiB worker'},
 'grading':'Manual comparison to exact stored 365 text; 1383 original question also asks paragraphs1 and3, unlike the photo. Order fixed. No speed/causal or population claim.'}
from resource_guard import self_test, sample
assert self_test()==11
put(DES/'resource-criteria.json',{'test_cases':11,'preparation':sample(),'before':(ART/'swap-before.txt').read_text(),'after':(ART/'swap-after.txt').read_text(),'filesystem':'ext4','persistent_fstab_entry':'/var/lib/wsl-local-swap/extra-4g.swap none swap sw,nofail 0 0','restart_tested':False})
put(DES/'criteria.json',criteria)
grant=read(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
allowed=sorted(grant['public_document_ids'])
assert '7bbe815ff43b6635' in allowed
allowed=['7bbe815ff43b6635']
cases=[{'id':'recovery','arms':['selected'],'document_ids':allowed,'steps':[{'number':2,'question':'방금 실패한 답변 검토를 이미 확보한 원문을 재사용해서 다시 해줘. 주장과 근거의 연결을 확인하고, 질문에 대한 설명과 남은 미확인을 함께 알려줘.','mode':'외규'}]}]
put(DES/'live-cases.json',cases)
put(DES/'authorization.json',{'user_request':criteria['user_authorization'],'prior_explicit_authorization':grant['workflow_authorization']['authorization_text'],'public_document_ids':allowed,'cases_sha256':sha(DES/'live-cases.json'),'grant_path':str((code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json').relative_to(ROOT)),'grant_sha256':sha(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'internal_relabeling':False,'quality_certified':False})
put(DES/'source-scope.json',{'public':allowed,'internal':[]})
shutil.copyfile(code/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Correct three-paragraph answer and same-goal review for explicit versus free-text continuation',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']='User-authorized repeat after WSL swap expansion, isolated fresh two-turn session on MAIN145, no product changes.'
m['design']['arms'][0].update(changes='Completed 1383 paired arm actual 365 ON failure reference only; no new baseline model calls',controls='Exact selected528 files')
m['design']['arms'][1].update(changes='No changes: exact selected MAIN145 bytes under actual Qwen',controls='Default reviews and unchanged navigation; isolated state and public original scope')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','selected')}
m['runs'][0].update(arm_ids=['selected'],selection_rule='Use two independent clones of the identical finalized failed case, structured first; stop after UNKNOWN.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Existing actual 1383 three-part question and two user-triggered recovery actions',version='20261105-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['not_applicable_reason']='Same original corpus and retrieval; actual acquisition/presentation measured, no answer-key recall claim'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
# Use immutable release paths as upstream, never copy mutable working products.
sources=[release['code_root']+'/'+n for n in files]
can=ac.snapshot(ADR,'selected',sources,experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');revision=cm['revisions'][-1]
C=can/'revisions'/revision['revision_id']/'snapshot'/release['code_root']
assert all(sha(C/n)==h for n,h in files.items())
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':files,'selected_equivalent':True,'selected_main':145,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors,'same_selected528':True})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1335-voting-repeat-live/artifacts/transport',ART/'transport')
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json'),*seed.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'before_model_calls':True,'live_calls_started':False,'same_selected_product_files':528})
print('Frozen MAIN145 exact528; one photographed case with two turns and conditional structured action; no product changes')
