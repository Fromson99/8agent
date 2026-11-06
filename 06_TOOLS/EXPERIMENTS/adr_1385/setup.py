"""Freeze the selected release and three public R4 cases before external calls."""
from common import *
import shutil
import importlib.util
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(exist_ok=False)
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1378-literal-provision-review-scope/artifacts'
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation']==145 and sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
release=read(ROOT/pointer['manifest_path'])
files=release['files'];assert len(files)==528
assert all(sha(ROOT/release['code_root']/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':pointer,'release':release})
ids=['B05-03','B03-12','B03-17']
for name in ('live-cases','grading-only'):
    records={x['id']:x for x in read(prior/'design'/(name+'.json'))}
    put(DES/(name+'.json'),[records[i] for i in ids])
cases=read(DES/'live-cases.json')
grant=read(ROOT/release['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
docs={d for c in cases for d in c['document_ids']}
assert all(c['execution']=='PUBLIC_API' and len(c['steps'])==1 for c in cases) and docs<=set(grant['public_document_ids'])
put(DES/'source-scope.json',{'public':sorted(docs)})
auth={'source':'user_message','text':'잘 못했던 것들 몇개 뽑아서 최신 메인에다가 돌려봐봐 그리고 사용자 답변 퀄리티도 한번 봐줘','session_id':'01a1a6be-d265-7f81-a248-0cb375648beb'}
put(DES/'authorization.json',{**auth,'approved_public_documents':sorted(docs),'questions':ids})
cfg=read(prior/'design/provider-reka.json');cfg['authorization']=auth
put(DES/'provider-reka.json',cfg);put(DES/'providers.json',{'reka':cfg['providers'][0]})
criteria={'hypothesis':'Measure the three historical failures on the exact selected release, including the actual response shown to the user.','success':['A complete committed answer with the expected rule and all required details','Cited sources match expected ranges; no source, ACL, wire, duplicate or budget mismatch'],
'failure':['Original-only, inaccurate, incomplete, timeout, resource stop or missing turn cannot pass. No automatic resend after UNKNOWN.'],
'quality_axes':['질문에 맞는 첫 답과 직접성','원문과 수치·조건·목록의 정확성·누락','답변 주장과 출처 연결','가독성과 실패 시 안내의 유용성'],
'plan':{'cases':ids,'cells':{'reka':ids},'max_calls':120,'provider':'REKA FP8','model':'qwen/qwen3.8-27b','reasoning':'none','model_deadline_seconds':180,'request_deadline_seconds':1800,'repeat':1,'sequential':True}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Delivered answer quality, full validated coverage and source integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Historical R4 observations',controls='Reference only, zero calls')
m['design']['arms'][1].update(changes='Selected MAIN145 exact product bytes',controls='Identical historical questions, independent public sessions, fixed REKA')
stages=read(prior.parent/'실험/manifest.json')['design']['retrieval_stage_plan'];stages['stages_by_arm']['selected']=stages['stages_by_arm'].pop('repaired');m['design']['retrieval_stage_plan']=stages
m['runs'][0].update(arm_ids=['selected'],selection_rule='Risk committee, voting rights, then special resolution. Stop on unknown.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Three previous R4 public failures',version='R4',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
can=ac.snapshot(ADR,'selected',[release['code_root']+'/'+n for n in files],experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
ac.freeze(can);assert not ac.validate(can)
rev=read(can/'candidate.json')['revisions'][-1];code=can/'revisions'/rev['revision_id']/'snapshot'/release['code_root']
assert all(sha(code/n)==h for n,h in files.items())
pin={'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'candidate-selected.json',{'selected_main':145,'code_root':str(code.relative_to(ROOT)),'selected_files':files,'pin':pin})
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))]);put(ADR/'실험/manifest.json',m)
shutil.copytree(prior/'transport',ART/'transport')
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
engines,count,errors=module.check(code);assert not errors
put(ART/'technical-verification.json',{'main':145,'files':528,'release_hash':pointer['release_manifest_sha256'],'engine_count':engines,'checked_files':count,'errors':errors})
print('Frozen MAIN145 exact 528',ids)
