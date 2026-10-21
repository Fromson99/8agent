"""Freeze one unchanged MAIN87 public question before the first model call."""
from pathlib import Path
import datetime, hashlib, json

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0899-main87-charter-call-trace';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

assert not (D/'freeze.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==87
release=read(R/pointer['manifest_path']);assert sha(R/pointer['manifest_path'])==pointer['release_manifest_sha256']
put(D/'baseline.json',{'pointer':pointer,'manifest':release})
cases=[{'id':'charter-quorum','api_type':'RAG_ASK','question':'정관을 변경할때 주주총회 결의 요건은 무엇인가요?'}]
put(D/'cases.json',cases)
criteria={
 'hypothesis':'The unchanged MAIN87 can batch multiple article reads and reference decisions, while serial navigation turns may still increase physical calls. One known question observes which occurs; no performance improvement claim.',
 'primary_metric':'Physical model attempt count and elapsed time, with exact per-call source-card counts and selected read targets',
 'success_criteria':['Actual service selects unchanged MAIN87 code/data/profile and approved public source scope',
  'One exact user question reaches an answer or honestly recorded partial/failure result',
  'Every physical model call has raw input/output or failure receipt and phase identity',
  'Article read target counts and reference decision batch sizes are measurable from preserved inputs/outputs',
  'Existing evidence identity, ACL and persistent budgets remain enforced; product pointer unchanged'],
 'failure_criteria':['Binding/source authorization drift','Unrecorded physical model call','Resource guard stop','Unauditable input/output'],
 'limits':{'physical_calls':40,'wall_seconds':1800,'rss_gib':6,'address_space_gib':8,'min_available_gib':4,'min_physical_disk_gib':10},
 'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'hidden_retries':0,
 'selection':'Exactly one user-provided known question, one run, no adaptive retry or alternate arm.',
 'controls':'Use immutable selected MAIN87 via service.application and service.service RAG_ASK; no product edits. Existing grant narrows external model source scope to approved public documents. GENOS internal model/corpus differ.',
 'failure_recovery':'Gateway alone owns existing bounded retries. Resource stop is preserved; do not rerun silently. Existing global heavy-worker lock forbids overlap.',
 'low_memory':'One worker; resident cache and warmup off; allocator limits and post-call gc/malloc_trim; no duplicated source generation.',
 'in_sample':True,'decision_eligible':False,'quality_certified':False,'genos_execution':False,
 'gold':'No approved answer/gold or model grader. Original span checks are technical integrity only.'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update({k:criteria[k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria')})
m['design']['criteria_frozen_before_run']=True
m['design']['code_isolation']['reason']='Read-only observation of already immutable selected MAIN87. No product candidate; selected code hashes are shared and verified rather than copying all files.'
m['design']['arms']=[{'id':'observed','role':'baseline','derived_from':['ADR-0896-experiment-v1/qualified'],'changes':'No product behavior change; raw transport and call/batch observation only','controls':criteria['controls']}]
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'selected','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'cited','kind':'present','parent_stage_ids':['selected']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'observed':plans}
m['runs'][0].update(arm_ids=['observed'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='user-charter-quorum',version='20261019-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'native_rag','class':'product','model':criteria['model'],'repeats':1,'max_calls':40,'temperature':0}]
m['retrieval_accounting']['not_applicable_reason']='Read/adopt/cited accounting only; search is unchanged and there is no approved legal gold.'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
files={}
for n,h in release['files'].items():
    p=R/release['code_root']/n;assert sha(p)==h,n;files[str(p.relative_to(R))]=h
paths=[R/'service.py',R/'service/service.py',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/pointer['manifest_path'],R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'06_TOOLS/EXPERIMENTS/resource_guard.py',*Path(__file__).parent.glob('*.py'),*D.glob('*.json')]
paths += [R/release['data_path']/n for n in ('manifest.json','fulltext/manifest.json','navigation/manifest.json')]
for p in paths:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'serving_files':release['files']})
print('Frozen one MAIN87 public RAG request; RSS 6GiB / AS 8GiB / available floor 4GiB; global heavy-worker lock required.')
