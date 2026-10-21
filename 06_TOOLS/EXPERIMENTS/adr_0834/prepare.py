"""Freeze unchanged MAIN78 and a single prospective diagnostic request."""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys
from datetime import datetime, timezone

R = Path(__file__).resolve().parents[3]
T = Path(__file__).parent
A = R/'04_EXPERIMENTS/ADR/ADR-0834-comparison-main78-live-check'
D = A/'artifacts/design'
D.mkdir(exist_ok=True)
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')

pointer = read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation'] == 78
release = read(R/pointer['manifest_path'])
selected = R/release['code_root']
assert all(sha(selected/n) == h for n,h in release['files'].items())
put(D/'baseline.json', {'pointer':pointer, 'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'), 'manifest':release})
put(D/'data-binding.json', {'path':release['data_path'], 'manifest_sha256':release['data_manifest_sha256']})
cases = [{'id':'public-liquidity-01', 'registered_id':None,
    'question':'금융투자업자의 유동성비율에 관해 외규의 대상, 비율 정의, 산정 기간, 예외를 확인하고 대응하는 내부 기준과 관리 절차를 비교해 주세요. 내규를 확보하지 못한 항목은 외규에서 확인한 내용과 구분해서 표시해 주세요.',
    'api_type':'WORKFLOW_RUN', 'workflow_id':'risk_team_compare_workflow',
    'stage':'synthetic_diagnostic', 'origin':'Exactly the known synthetic831 question reused for one fresh diagnosis after receipt fix; no registered original question, annotations or gold'}]
put(D/'cases.json', cases)
criteria = {
    'hypothesis':'Unchanged MAIN78 can return durable field-level comparison or explicitly limited partial results with own-side original sources through actual active service bootstrap.',
    'success':['terminal durable response', 'field results identify unconfirmed items', 'all published evidence matches original spans and own-side provenance', 'successful sources survive later failures', 'saved status and duplicate return identical answer without new model calls'],
    'failure':['wrong code/data/model binding', 'lost acquired evidence', 'unsupported side substitution', 'duplicate model calls', 'no grounded final output after successful source acquisition'],
    'limits':{'physical_calls':40, 'wall_seconds':1800, 'outer_timeout':1920},
    'selection':'One known831 synthetic query repeated after code fix; no adaptive rerun or statistical improvement rate. Different model draws prevent deterministic paired attribution',
    'semantic_rubric':'Inspect whether selected sources actually concern the requested ratio, whether missing internal evidence stays missing, and whether comparison conclusions are supported. No approved gold or numerical accuracy claim.',
    'model':'qwen/qwen3.8-27b', 'provider':'Parasail', 'quantization':'fp8', 'reasoning':'none', 'fallback':False,
    'fault_injection':None, 'in_sample':True, 'decision_eligible':False, 'quality_certified':False,
    'entry':'Workspace service.application active-pointer bootstrap. No app injection. Single-send transport instrumentation uses ExperimentClient with original authorization and gateway.',
    'failure_owner':'Existing runtime gateway and workflow; the runner adds no retries or repairs. Existing request budget/deadline covers failures.',
    'promotion':'No new product code or promotion. Active MAIN78 remains selected.'}
put(D/'criteria.json', criteria)
# Keep an isolated, validated byte-identical witness. The actual service must
# select the existing release with the same files, never discover this witness.
cmd = [str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','observed','--experiment-id','ADR-0834-experiment-v1','--arm-id','observed','--run-id','run-001']
for n in release['files']:
    if (R/n).exists(): cmd += ['--source', n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C = R/'02_BACKEND/lawrag/research/candidates/adr_0834/observed'
for n,h in release['files'].items():
    target = C/'snapshot'/n
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(selected/n,target)
    if not (R/n).exists():
        subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'))
import adr_candidate
adr_candidate.refresh(C)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json'); rev=cm['revisions'][-1]
code=C/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(code/n)==h for n,h in release['files'].items())
m=read(A/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Actual active service grounded partial/comparison result and durable consumer integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:
    arm.update(changes='Completed0833 technical context only; no new baseline calls' if arm['id']=='baseline' else 'No product change; actual active MAIN78 with audited physical sends',controls=['same selected code/data/profile/authorization', '40call/1800second budget', 'one predeclared request'])
m['runs'][0].update(artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),arm_ids=['observed'],selection_rule=criteria['selection'])
m['dataset'].update(name='synthetic-liquidity-known-topic',version='20261016-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'observed','arm_id':'observed','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}])
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':criteria['model'],'repeats':1,'temperature':'selected runtime value'}]
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'child_adopted','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['child_adopted']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':plans,'observed':plans}
m['retrieval_accounting'].update(changed=False,not_applicable_reason='No retrieval implementation change; native runtime read/adopted/final stages are newly observed under the unchanged MAIN78 policy.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
files={str((code/n).relative_to(R)):h for n,h in release['files'].items()}
files.update({str(p.relative_to(R)):sha(p) for p in list(T.glob('*.py'))+list(D.glob('*.json'))+[R/'service.py',R/'service/service.py',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'files':files,'code_root':str(code.relative_to(R)),'serving_files':release['files']})
print('Frozen unchanged MAIN78; one request; no fault injection or adaptive rerun')
