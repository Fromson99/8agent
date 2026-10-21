from pathlib import Path
import datetime, hashlib, json
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0919-financial-private-bond-definition';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==88
release=read(R/pointer['manifest_path']);assert sha(R/pointer['manifest_path'])==pointer['release_manifest_sha256']
put(D/'baseline.json',{'pointer':pointer,'manifest':release})
cases=[{'id':'private-bond-definition','api_type':'RAG_ASK','question':'사모사채 정의 알려줘'}]
put(D/'cases.json',cases)
criteria={'hypothesis':'Selected MAIN88 can answer the exact private-bond definition request using authorized Financial team original sources; observe answerability, evidence fidelity and remaining gaps.',
 'primary_metric':'Grounded definition answer through actual selected MAIN88 RAG_ASK with Financial team scope',
 'success_criteria':['Exact actual service MAIN88 binding, no application injection','Actual answer defines the requested term from acquired originals; limited explanation or explicit shortage distinguished from unsupported definition','Original citation identity/hash and ACL preserved','Duplicate response and run match without additional model calls','Partial semantic result distinguished from infrastructure failure; no perfect legal answer requirement'],
 'failure_criteria':['Invalid schema or restoration','Unread/foreign/tampered evidence adopted','No durable answer','Budget, replay or selected binding regression'],
 'limits':{'physical_calls':40,'wall_seconds':1800,'rss_gib':6,'address_space_gib':8,'min_available_gib':4,'min_physical_disk_gib':10},
 'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'hidden_retries':0, 'low_memory':{'resident_data':'off','allocator':'MALLOC_ARENA_MAX=1 MALLOC_TRIM_THRESHOLD_=65536 MALLOC_MMAP_THRESHOLD_=131072','instrumentation':'gc.collect and malloc_trim after each generation; no input/output changes'},
 'selection':'User supplied definition question exactly once. No hints or expected answer injected; no adaptive re-execution.',
 'controls':'Actual selected MAIN88 service, code/data/profile/search/grants unchanged. Only physical transport and observation instrumentation. Fresh isolated request for this new test; prior completed experiments retained and not resumed.',
 'failure_recovery':'Existing gateway/workflow alone owns retries and persistent budgets. No evaluator/context rewrite, adaptive rerun or product edits.',
 'answer_first_scope':'Existing MAIN88 ordinary RAG policy; no task_context override.', 'scope':'Selected financial_team documents intersected with frozen public model grant. Independently inspect relevant local financial sources after product selection; no gold or evidence hints injected.', 'in_sample':True,'decision_eligible':False,'quality_certified':False,'genos_execution':False}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update({k:criteria[k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria')});m['design']['criteria_frozen_before_run']=True
m['design']['code_isolation']['reason']='Read-only observation of immutable already selected MAIN88 release; no product candidate or product edits. Existing release files hash-bound and shared without duplicate snapshot.'
m['design']['arms']=[{'id':'observed','role':'baseline','derived_from':['ADR-0917-experiment-v1/qualified'],'changes':'No code change; actual selected service with audited physical sends','controls':criteria['controls']}]
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'selected','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'cited','kind':'present','parent_stage_ids':['selected']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'observed':plans}
m['runs'][0].update(arm_ids=['observed'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/private-bond-definition/result.json').relative_to(R)))
m['dataset'].update(name='main88-financial-private-bond-definition',version='20261019-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'native_rag','class':'product','model':criteria['model'],'repeats':1,'max_calls':40,'temperature':0}]
m['retrieval_accounting']['not_applicable_reason']='Unchanged retrieval; measured native read, committed selection and final cited sets. No legal gold or quality claim.'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
files={}
for n,h in release['files'].items():
 p=R/release['code_root']/n;assert sha(p)==h,n;files[str(p.relative_to(R))]=h
paths=[R/'service.py',R/'service/service.py',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/pointer['manifest_path'],R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'06_TOOLS/EXPERIMENTS/resource_guard.py',*Path(__file__).parent.glob('*.py'),*D.glob('*.json')]
paths += [R/release['data_path']/n for n in ('manifest.json','fulltext/manifest.json','navigation/manifest.json')]
for p in paths:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'serving_files':release['files']})
print('FROZEN MAIN88 actual service;40calls1800seconds; one heavy worker; no product or pointer changes')
