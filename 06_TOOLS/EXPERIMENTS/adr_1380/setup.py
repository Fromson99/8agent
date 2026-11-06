"""Freeze the user's selected MAIN143, with no product modifications."""
from common import *
import shutil, importlib.util

DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation']==143
release=read(ROOT/pointer['manifest_path']);code=ROOT/release['code_root']
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
files=release['files'];assert len(files)==528
assert all(sha(code/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':pointer,'release':release,'working_before':{n:sha(ROOT/n) for n in files if (ROOT/n).exists()}})
criteria={
 'user_authorization':'실제 qwen으로 실험해봐',
 'hypothesis':'The currently selected MAIN143 answers the photographed Article 365(2) question with a source-grounded claim and can honor the photographed review request in the same session. If a recoverable review failure is offered, compare the existing explicit action on a copy of that exact pre-follow-up case.',
 'success':['Turn 1 cites the verified second paragraph and says every accounting period; mere source excerpt is insufficient.', 'Track turn 2 separately: same goal and retained originals, stages executed, public display of internal reasons, and correct cited answer. Prior success allows a continuity observation only, not evidence of failure recovery.', 'When offered on a failed first turn, independently invoke the exact offered REVIEW_AGAIN on a checkpoint with matching case/revision/view hash. Both follows must be compared against the same originating response.', 'Source spans, authority, model wire, physical budget and zero-cost duplicate retrieval verified.'],
 'failure':['No retries after unknown/technical stop. No injected model failures or reference answers. A skipped action is untested.'],
 'fixed_environment':{'code':'MAIN143 release exact 528','source':'local selected SQLite; one public Commercial Act','state':'isolated SQLite','model':'qwen/qwen3.8-27b','quantization':'fp8','reasoning':'none','ontology':False,'final_reviews':'default enabled','provider_policy':'Parasail FP8 primary, known429 only NearAI once','output_token_cap':None},
 'limits':{'physical_per_request':40,'physical_total':120,'planned_chat_turns':2,'conditional_structured_turns':1,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128,'available_start_GiB':5,'available_stop_GiB':3},
 'grading':'Manual source comparison plus mechanically verified traces. No judge model. No field or product changes.'}
put(DES/'criteria.json',criteria)
grant=read(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
allowed=sorted(grant['public_document_ids'])
assert '7bbe815ff43b6635' in allowed
allowed=['7bbe815ff43b6635']
cases=[{'id':'photo','arms':['main143'],'document_ids':allowed,'steps':[
 {'number':1,'question':'상법 제365조 제2항에서 연 2회 이상 결산기를 정한 회사는 언제 총회를 소집하나요?','mode':'외규'},
 {'number':2,'question':'방금 실패한 답변 검토를 이미 확보한 원문을 재사용해서 다시 해줘. 주장과 근거의 연결을 확인하고, 질문에 대한 설명과 남은 미확인을 함께 알려줘.','mode':'외규'}]}]
put(DES/'live-cases.json',cases)
put(DES/'authorization.json',{'user_request':criteria['user_authorization'],'prior_explicit_authorization':grant['workflow_authorization']['authorization_text'],'public_document_ids':allowed,'cases_sha256':sha(DES/'live-cases.json'),'grant_path':str((code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json').relative_to(ROOT)),'grant_sha256':sha(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'internal_relabeling':False,'quality_certified':False})
put(DES/'source-scope.json',{'public':allowed,'internal':[]})
shutil.copyfile(code/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Supported second-paragraph answer, follow-up continuity, and conditional action recovery',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']='User-directed actual two-turn diagnosis on MAIN143, no product changes.'
m['design']['arms'][0].update(changes='Completed 1338 experiment harness reference only; no new baseline model calls',controls='Exact selected528 files')
m['design']['arms'][1].update(changes='No changes: exact selected MAIN143 bytes under actual Qwen',controls='Default reviews and unchanged navigation; isolated state and public original scope')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','main143')}
m['runs'][0].update(arm_ids=['main143'],selection_rule='One frozen photographed chat session with two turns; if turn one returns review failure with offered action, fork exact pre-follow-up checkpoint for one additional action. Global stop on UNKNOWN.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Photo B03-04 and exact provided follow-up',version='20261105-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['not_applicable_reason']='Same original corpus and retrieval; actual acquisition/presentation measured, no answer-key recall claim'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
# Use immutable release paths as upstream, never copy mutable working products.
sources=[release['code_root']+'/'+n for n in files]
can=ac.snapshot(ADR,'main143',sources,experiment_id=m['experiment_id'],arm_id='main143',run_ids=['run-001'])
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');revision=cm['revisions'][-1]
C=can/'revisions'/revision['revision_id']/'snapshot'/release['code_root']
assert all(sha(C/n)==h for n,h in files.items())
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':files,'selected_equivalent':True,'selected_main':143,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}}
put(DES/'candidate-main143.json',desc)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors,'same_selected528':True})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1335-voting-repeat-live/artifacts/transport',ART/'transport')
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='main143',experiment_id=m['experiment_id'],arm_id='main143',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'before_model_calls':True,'live_calls_started':False,'same_selected_product_files':528})
print('Frozen MAIN143 exact528; one photographed case with two turns and conditional structured action; no product changes')
