"""Freeze the working serving file set, grading boundaries, and prior failed questions."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
from genos_codespace_engine_preflight import check

DES.mkdir(exist_ok=False)
prior=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1378-*'))
charter=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1346-*'))
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256'] and pointer['generation']==145
release=read(ROOT/pointer['manifest_path'])
put(DES/'baseline.json',{'pointer':pointer,'release':release})
files={n:sha(ROOT/n) for n in release['files']}
assert len(files)==528 and 'def same_dispatch(' in (ROOT/'02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py').read_text()
put(DES/'work-vs-main.json',{n:{'working':h,'main':release['files'][n]} for n,h in files.items() if h!=release['files'][n]})
r4={c['id']:c for c in read(prior/'artifacts/design/live-cases.json')}
old=read(charter/'artifacts/design/live-cases.json')[0]
cases=[{**r4['B03-17'],'id':'charter','title':'조문 번호 없는 정관 변경 결의요건','steps':old['steps'],'document_ids':old['document_ids']},r4['B03-03'],r4['B05-03']]
grades={c['id']:c for c in read(prior/'artifacts/design/grading-only.json')}
ids=[c['id'] for c in cases]
put(DES/'live-cases.json',cases)
put(DES/'grading-only.json',[{**grades['B03-17'],'id':'charter','expected':'정관 변경은 주주총회 결의이며 출석 주주 의결권 3분의 2 이상과 발행주식총수 3분의 1 이상을 모두 충족한다.'},grades['B03-03'],grades['B05-03']])
docs=sorted({d for c in cases for d in c['document_ids']})
grant=read(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
assert set(docs)<=set(grant['public_document_ids']) and all(c['execution']=='PUBLIC_API' for c in cases)
put(DES/'source-scope.json',{'public':docs})
auth={'source':'user_message','text':'qwen으로 테스트 몇개해봐 이전에 실패했던거','session_id':read(ADR/'claim.json')['session_id']}
put(DES/'authorization.json',{**auth,'approved_public_documents':docs,'questions':ids})
cfg=read(prior/'artifacts/design/provider-reka.json')
cfg.update(authorization=auth,reason='Freeze the REKA FP8 route used in prior R4/ontology comparisons, one authorized provider.')
put(DES/'provider-reka.json',cfg);put(DES/'providers.json',{'reka':cfg['providers'][0]})
criteria={'hypothesis':'The reviewed working pipeline can answer prior failures and honor any supervisor correction before executing a tool.',
 'success':['A returned explanatory answer with accurate complete content and exact cited provision. A missing numbered paragraph must not be invented.',
 'Measure supervisor exercise separately. Only a real review followed by matching tool, or a documented no-dispatch terminal, counts. A redirect is proven only if old/new differ and the next executed action/arguments match. Never count an unexercised branch.',
 'Original spans, ACL, provider wire, request budget and duplicate lookup agree. No answer key in product input.'],
 'failure':['Uncertain transport/resource outcome stops further physical sends. A semantic failure alone does not cancel the next independent case. No automatic resend, no code or prompt tuning during these tests.'],
 'plan':{'cases':ids,'cells':{'reka':ids},'max_calls':120,'provider':'REKA FP8','model':'qwen/qwen3.8-27b','reasoning':'none','per_request':40,'model_deadline_seconds':180,'request_deadline_seconds':1800,'repeat':1,'sequential':True,'limits':'single worker, free RAM 5/3GiB, RSS 5GiB, swap growth 128MiB, free disk 20GiB'}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Per-question grounded answer, with separate supervisor-to-execution verification',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Historical observations only',controls='No new baseline calls')
m['design']['arms'][1].update(changes='Exact current working tree serving set with the reviewed decision gate',controls='Frozen case, provider and inputs, 3 independent sessions')
st=read(prior/'실험/manifest.json')['design']['retrieval_stage_plan'];st['stages_by_arm']['reviewed']=st['stages_by_arm'].pop('repaired');m['design']['retrieval_stage_plan']=st
m['runs'][0].update(arm_ids=['reviewed'],selection_rule='Three prior public failures: charter then meeting timing then risk committee; fixed order; one attempt per case.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Previously failed charter and R4 questions',version='20261105',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
can=ac.snapshot(ADR,'reviewed',list(files),experiment_id=m['experiment_id'],arm_id='reviewed',run_ids=['run-001'])
ac.freeze(can);assert not ac.validate(can)
rev=read(can/'candidate.json')['revisions'][-1];code=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(code/n)==h for n,h in files.items())
pin={'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'candidate-reviewed.json',{'code_root':str(code.relative_to(ROOT)),'selected_files':files,'pin':pin})
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='reviewed',experiment_id=m['experiment_id'],arm_id='reviewed',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
shutil.copytree(prior/'artifacts/transport',ART/'transport')
eng,count,errors=check(code);assert not errors,errors
put(ART/'technical-verification.json',{'files':len(files),'engine_count':eng,'checked_files':count,'errors':errors,'same_working_code':True,'reference_main':145,'different_from_main':len(read(DES/'work-vs-main.json'))})
print('Frozen',ids,eng,count,len(files))
