"""Freeze the user's selected MAIN145, with no product modifications."""
from common import *
import shutil, importlib.util

DES.mkdir(exist_ok=False)
pointer=read(ART/'activation-at-request.json')
assert pointer['generation']==145 and pointer['release_manifest_sha256']=='2c8f5f6d58abde41469566088bf9ca7a94cf5926df3c844ed1d54c962fff5d24'
release=read(ROOT/pointer['manifest_path']);code=ROOT/release['code_root']
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1388-bound-chat-review-repair/artifacts/design/candidate-repaired.json')
code=ROOT/parent['code_root']
files=parent['selected_files'];assert len(files)==528
assert all(sha(code/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':pointer,'release':release,'working_before':{n:sha(ROOT/n) for n in files if (ROOT/n).exists()}})
criteria={'user_authorization':'수정해봐; 직전 실제 Qwen 실험을 이어 검증','hypothesis':'Fresh cases born under the verified 1388 candidate bind literal photo review to the immediately preceding goal without command resolution.','success':['Photo and wider three-clause questions run first, then identical external-prefixed legacy follow-up; report both the initial legal correctness and actual second-turn behavior.','If the final-review action is offered, re-enter at verified restart stage on same goal; if already complete, report absence of retry without model calls. Neither exact command uses source-request-route/memory-resolve.','Full source/ACL/wire/idempotence checks. No post-UNKNOWN sends.'],'failure':['Any UNKNOWN or failed prior HTTP response halts subsequent sends; stopped cells remain unobserved. No selected release changes.'],'limits':{'physical_per_request':40,'physical_total':160,'heavy_workers':1,'swap_growth_MiB':1024,'ram_floor_GiB':3},'grading':'Offline manual comparison against source texts. No judge model or answer key in product input.'}
from resource_guard import self_test, sample
assert self_test()==11
put(DES/'resource-criteria.json',{'test_cases':11,'preparation':sample(),'before':(ART/'swap-before.txt').read_text(),'after':(ART/'swap-after.txt').read_text(),'filesystem':'ext4','persistent_fstab_entry':'/var/lib/wsl-local-swap/extra-4g.swap none swap sw,nofail 0 0','restart_tested':False})
put(DES/'criteria.json',criteria)
grant=read(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
allowed=sorted(grant['public_document_ids'])
assert '7bbe815ff43b6635' in allowed
allowed=['7bbe815ff43b6635']
cases=[{'id':'photo','arms':['repaired'],'document_ids':allowed,'steps':[
 {'number':1,'question':'상법 제365조 제2항에서 연 2회 이상 결산기를 정한 회사는 언제 총회를 소집하나요?','mode':'외규'},
 {'number':2,'question':'방금 실패한 답변 검토를 이미 확보한 원문을 재사용해서 다시 해줘. 주장과 근거의 연결을 확인하고, 질문에 대한 설명과 남은 미확인을 함께 알려줘.','mode':'외규'}]}]
import copy
full=copy.deepcopy(cases[0]);full['id']='full365';full['steps'][0]['question']='상법 제365조에 따른 정기총회, 연 2회 이상 결산기를 정한 회사의 총회, 임시총회의 소집 시기를 각각 알려주세요.\n연 2회 이상'
cases.append(full)
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1383-main145-ontology-usage/artifacts'
put(DES/'legacy-context.json',read(prior/'design/legacy365-context.json'))
put(DES/'live-cases.json',cases)
put(DES/'authorization.json',{'user_request':criteria['user_authorization'],'prior_explicit_authorization':grant['workflow_authorization']['authorization_text'],'public_document_ids':allowed,'cases_sha256':sha(DES/'live-cases.json'),'grant_path':str((code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json').relative_to(ROOT)),'grant_sha256':sha(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'internal_relabeling':False,'quality_certified':False})
put(DES/'source-scope.json',{'public':allowed,'internal':[]})
shutil.copyfile(code/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Supported second-paragraph answer, follow-up continuity, and conditional action recovery',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']='Fresh two-turn verification of frozen candidate1388 in separate sessions with same-version state on MAIN145, no product changes.'
m['design']['arms'][0].update(changes='Completed1384 original photo timeout, reference only; no new baseline model calls',controls='Exact selected528 files')
m['design']['arms'][1].update(changes='Frozen candidate 1388 exact528; photo OFF, wider legacy365 ON',controls='Default reviews and unchanged navigation; isolated state and public original scope')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','repaired')}
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Two fresh sessions, photo OFF then full365 ON, literal photo follow-up for both. Sequential; stop after UNKNOWN or failed transport.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Photo B03-04 and exact provided follow-up',version='20261105-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['not_applicable_reason']='Same original corpus and retrieval; actual acquisition/presentation measured, no answer-key recall claim'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
# Use immutable release paths as upstream, never copy mutable working products.
sources=[parent['code_root']+'/'+n for n in files]
can=ac.snapshot(ADR,'repaired',sources,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');revision=cm['revisions'][-1]
C=can/'revisions'/revision['revision_id']/'snapshot'/parent['code_root']
assert all(sha(C/n)==h for n,h in files.items())
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':files,'selected_equivalent':False,'selected_main':145,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}}
put(DES/'candidate-repaired.json',desc)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors,'same_selected528':True})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1335-voting-repeat-live/artifacts/transport',ART/'transport')
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='repaired',experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'before_model_calls':True,'live_calls_started':False,'same_selected_product_files':528})
print('Frozen MAIN145 exact528; one photographed case with two turns and conditional structured action; no product changes')
