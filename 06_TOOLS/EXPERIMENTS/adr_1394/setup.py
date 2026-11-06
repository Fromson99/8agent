"""Freeze the user's selected MAIN146, with no product modifications."""
from common import *
import shutil, importlib.util

DES.mkdir(exist_ok=False)
pointer=read(ART/'activation-at-request.json')
assert pointer['generation']==146 and pointer['release_manifest_sha256']=='556980059817606002d3db1004e213ed3d62a79a24dff26ee836ea9630e8fc23'
release=read(ROOT/pointer['manifest_path']);code=ROOT/release['code_root']
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==pointer
files=release['files'];assert len(files)==528
assert all(sha(code/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':pointer,'release':release,'working_before':{n:sha(ROOT/n) for n in files if (ROOT/n).exists()}})
criteria={
 'user_authorization':'우리 멀티턴도 다시 한번 봐봐 문제없나',
 'hypothesis':'An unchanged selected MAIN146 retains context across repeated questions and related follow-ups, starts a new goal for an unrelated legal question, and executes review commands only against the correct immediately preceding state.',
 'success':['T1: supported every-accounting-period answer citing Commercial Act 365(2). T2: same text as a new request: if original was answered, keep goal, answer and verified original; no unnecessary new source search. Distinguish this from an identical request-ID requery.', 'T3: resolve implicit meeting context and explain the necessary/as-needed rule for extraordinary meetings from 365(3). Report topic continuity, actual scope and any goal or issue loss separately.', 'T4: independently answer one vote per share under 369(1), start a distinct goal, do not cite prior meeting evidence as support for votes.', 'T5: exact short review command acts on T4 only; no model on a complete T4, or direct bounded source selection/review if a retry was actually offered. No general command resolver on this operation.', 'Source text/scope/ACL/wire/budget checks and zero new model calls on duplicate request IDs. Complementary native ports test history, scope changes and session isolation with fixture models.'],
 'failure':['Stop subsequent live turns after indeterminate call or HTTP failure; preserve all receipts, no resend. Source-only or unjustified CLARIFY is not a substantive answer; partial path is not a full pass.'],
 'limits':{'physical_per_request':40,'physical_total':200,'heavy_workers':1,'rss_cap_gib':5,'swap_growth_MiB':1024,'available_floor_gib':3},
 'grading':'One fixed native conversation via actual public Qwen/Parasail default (configured known-429 switch only). Score offline against stored originals and actual stage and goal records; no grader model, no new mutable product paths.'}
from resource_guard import self_test,sample
assert self_test()==11
put(DES/'resource-criteria.json',{'before':sample(),'limits':criteria['limits']})
put(DES/'criteria.json',criteria)
grant=read(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
allowed=sorted(grant['public_document_ids'])
assert '7bbe815ff43b6635' in allowed
allowed=['7bbe815ff43b6635']
first='상법 제365조 제2항에서 연 2회 이상 결산기를 정한 회사는 언제 총회를 소집하나요?'
questions=[first,first,'그럼 임시총회는 언제 소집하나요?','상법 제369조 제1항에 따르면 주식 1주당 의결권은 몇 개인가요?','검토 다시 하기']
cases=[{'id':'conversation','arms':['selected'],'document_ids':allowed,'steps':[{'number':i,'question':q,'mode':'외규'} for i,q in enumerate(questions,1)]}]
put(DES/'live-cases.json',cases)
put(DES/'authorization.json',{'user_request':criteria['user_authorization'],'prior_explicit_authorization':grant['workflow_authorization']['authorization_text'],'public_document_ids':allowed,'cases_sha256':sha(DES/'live-cases.json'),'grant_path':str((code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json').relative_to(ROOT)),'grant_sha256':sha(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'internal_relabeling':False,'quality_certified':False})
put(DES/'source-scope.json',{'public':allowed,'internal':[]})
shutil.copyfile(code/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Per-turn answer/source correctness, goal continuity and isolation, duplicate idempotence and review dispatch',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']='One five-turn public conversation on selected MAIN146, without product changes.'
m['design']['arms'][0].update(changes='Completed1392 technical activation reference only; no new baseline model calls',controls='Exact selected528 files')
m['design']['arms'][1].update(changes='Unchanged selected MAIN146 release 528 files, default ontology OFF',controls='Default reviews and unchanged navigation; isolated state and public original scope')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','selected')}
m['runs'][0].update(arm_ids=['selected'],selection_rule='Five fixed fresh messages, one authenticated chat. Stop on UNKNOWN or HTTP failure.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Public Commercial Act native five-turn conversation',version='20261105-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
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
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':files,'selected_equivalent':True,'selected_main':146,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors,'same_selected528':True})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1335-voting-repeat-live/artifacts/transport',ART/'transport')
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'before_model_calls':True,'live_calls_started':False,'same_selected_product_files':528})
print('Frozen selected MAIN146, 5 turns, no product changes')
