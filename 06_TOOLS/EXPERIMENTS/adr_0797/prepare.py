"""Reserve first, freeze technical scope, then isolate the selected MAIN73 code."""
from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0797-workflow-adopted-evidence';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);base=read(R/pointer['manifest_path'])
assert pointer['generation']==73
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(p),'manifest':base})
criteria={'scope':'Prospectively fixed finite technical boundary audit, not semantic answer quality certification',
 'design':{'path':'07_DOCS/REFERENCE/REPORTS/WORKFLOW_EVIDENCE_HANDOFF_20261015/DESIGN.md','sha256':sha(R/'07_DOCS/REFERENCE/REPORTS/WORKFLOW_EVIDENCE_HANDOFF_20261015/DESIGN.md')},
 'controls':['MAIN73 immutable source/navigation/fulltext/latest selection','definition-first retrieval','one existing INTAKE and child RAG, no added selector model','40 total model attempts and original 1800-second deadline'],
 'success':['exact committed ASSESS receipts only; no all-read evidence export','dedup identical coordinates while retaining origin and condition/exception dependencies','hash, scope, unread, stale, foreign-ID rejection; no invented version','active bundle replaces prior revision; historical records remain auditable','delivered evidence ledger equals actual bounded sources and validator allowlist','bounded issue/pair packets; incomplete dependency closure never authorizes conformance','targeted source context, existing followup budget, no reset or unknown resend','report and selected UI show only cited necessary sources','real service uses same frozen code; duplicate and restart preserve result without model recall','all targeted technical contracts pass with no new regression'],
 'failure_owner':{'integrity':'workflow_evidence: stop without model repair','proposal':'workflow ModelAdapter: initial plus one correction','research':'existing recovery: maximum two, same global budget','oversize':'packet planner: deterministic explicit incomplete scope, no top-k truncation','unknown_delivery':'existing durable model journal: never resend'},
 'qualification':'Complete finite synthetic contract matrix; known ADR0795 liquidity question is separate observational regression, never holdout or semantic qualification',
 'known_observation':{'question':'대사: 유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?','repeats':1,'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'maximum_calls':40},
 'limitations':['Current corpus lacks verified applicability dates; content comparison may remain DEFERRED','GENOS inaccessible and not deployed','No claim of legal correctness or latency generalization']}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']='Deliver verified adopted spans with active revision and bounded comparison packets'
m['design'].update(hypothesis='Exact committed claims can be handed to comparison without full child exploration, while preserving provenance and failure boundaries',primary_metric='finite technical contracts and actual consumer connection',success_criteria=criteria['success'],failure_criteria='Any wrong source, missing explicit condition, scope/hash bypass, stale active evidence or unbounded/repeated call',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason='Isolated MAIN73 extension; qualification is finite technical audit')
for arm in m['design']['arms']:arm.update(changes='MAIN73 unchanged' if arm['id']=='baseline' else 'Verified claim bundle, bounded presentation, targeted context and cited report',controls=criteria['controls'])
m['runs'][0].update(selection_rule='All predeclared technical boundaries; known live observation separately labeled',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='workflow-handoff-finite-contracts',version='20261015-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
for arm in ('baseline','optimized'):
 m['design']['retrieval_stage_plan']['stages_by_arm'][arm]=[{'stage_id':s,'kind':k,'parent_stage_ids':[] if i==0 else [['read','adopted','present'][i-1]]} for i,(s,k) in enumerate([('read','source'),('adopted','select'),('present','present')])]
put(A/'실험/manifest.json',m)
sources=sorted(base['files'])
cmd=['.venv/bin/python','06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','optimized','--experiment-id',m['experiment_id'],'--arm-id','optimized','--run-id','run-001']
for s in sources:cmd+=['--source',s]
subprocess.run(cmd,check=True)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0797/optimized/snapshot'
for s in sources:shutil.copyfile(R/base['code_root']/s,C/s)
put(D/'working-before.json',{s:sha(R/s) for s in sources})
put(D/'data-binding.json',{'path':base['data_path'],'manifest_sha256':base['data_manifest_sha256']})
print('MAIN73 isolated',len(sources),'files')
