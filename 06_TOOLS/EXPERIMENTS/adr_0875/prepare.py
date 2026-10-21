from pathlib import Path
import datetime, hashlib, json
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0875-bounded-followup-live';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==83
release=read(R/pointer['manifest_path']);assert sha(R/pointer['manifest_path'])==pointer['release_manifest_sha256']
put(D/'baseline.json',{'pointer':pointer,'manifest':release})
q=read(R/'04_EXPERIMENTS/ADR/ADR-0874-bounded-followup-continuation/artifacts/design/verification-binding.json')
C=R/q['code_root']
cases=[{'id':'committee-comparison','api_type':'WORKFLOW_RUN','workflow_id':'risk_team_compare_workflow','question':'대사: 위험관리위원회운영준칙의 위원회 역할과 심의·의결사항을 관련 외규와 비교하고, 공통사항·차이·확인하지 못한 자료를 알려줘.'}]
put(D/'cases.json',cases)
criteria={'hypothesis':'Frozen0874 candidate completes a real workflow with truthful research receipts and a distinct second acquisition after a no-result first target; original spans and durable consumers remain intact.',
 'primary_metric':'Source handoff, exact acquisition receipts, distinct bounded research, comparison and durable response under exact0874 candidate',
 'success_criteria':['Exact frozen0874 candidate explicitly injected into its own service.py, MAIN83 data and active pointer unchanged','Internal and external source investigation and comparison rows reached; honest partial/missing evidence allowed','Original citation identity/hash and ACL preserved','Saved status and duplicate response match without model calls','No PARTIAL/missing exact receipt labeled COMPLETE; first empty acquisition does not prevent a distinct eligible second target within cap2'],
 'failure_criteria':['Invalid schema or restoration','Unread/foreign/tampered evidence adopted','No durable comparison result','Budget, replay or selected binding regression'],
 'limits':{'new_physical_calls':32,'prior_physical_calls':8,'combined_ceiling':40,'wall_seconds':1800,'rss_gib':8,'address_space_gib':9,'min_available_gib':2,'min_physical_disk_gib':10},
 'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'hidden_retries':0,
 'selection':'Same known committee question as0873, once, fresh isolated state. Not controlled legal-quality comparison. Prior8physicalcalls retained, maximum32new. No retry after outcome.',
 'controls':'Exact frozen0874 code; MAIN83 data/profile/search/grants preserved. Explicit candidate application; physical transport audit only. Prior0873completed request not resumed or charged counters erased.',
 'failure_recovery':'Existing gateway/workflow alone owns retries and persistent budgets. No evaluator/context rewrite, adaptive rerun or product edits.',
 'in_sample':True,'decision_eligible':False,'quality_certified':False,'genos_execution':False}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update({k:criteria[k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria')});m['design']['criteria_frozen_before_run']=True
m['design']['code_isolation']['reason']='Read-only actual-model observation of completed0874 immutable candidate; no new code edits. Shared candidate snapshot and data, no production registry selection.'
m['design']['arms']=[{'id':'observed','role':'baseline','derived_from':['ADR-0874-experiment-v1/qualified'],'changes':'No new code change; explicit frozen0874 candidate app with audited physical sends','controls':criteria['controls']}]
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'child_adopted','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['child_adopted']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'observed':plans}
m['runs'][0].update(arm_ids=['observed'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/committee-comparison/result.json').relative_to(R)))
m['dataset'].update(name='main83-known-committee-and-retained-withdrawal',version='20261018-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':criteria['model'],'repeats':1,'max_calls':32,'temperature':0}]
m['retrieval_accounting']['not_applicable_reason']='Unchanged retrieval; measured native read, child handoff and final cited sets. No legal gold or quality claim.'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
files={}
for n,h in q['serving_files'].items():
 p=C/n;assert sha(p)==h,n;files[str(p.relative_to(R))]=h
paths=[R/'service.py',R/'service/service.py',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/pointer['manifest_path'],R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'06_TOOLS/EXPERIMENTS/resource_guard.py',*Path(__file__).parent.glob('*.py'),*D.glob('*.json')]
paths += [R/release['data_path']/n for n in ('manifest.json','fulltext/manifest.json','navigation/manifest.json')]
for p in paths:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'serving_files':q['serving_files'],'code_root':q['code_root'],'candidate':q['candidate']})
print('FROZEN0874candidate onMAIN83data;32newcalls+8prior; one heavy worker')
