from pathlib import Path
from copy import deepcopy
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1061-ontology-mvp-execution-repair';ART=ADR/'artifacts'
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1059-compact-input-guidance-binding'
SOURCE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1059/dense-input-r1'
BASE=ROOT/'04_EXPERIMENTS/ADR/ADR-1054-ontology-mvp-state-binding'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
planpath=ROOT/'07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MVP_EXECUTION_REPAIR_PLAN_20261026.md'
plan={'schema_version':'mvp-execution-repair-plan-v1','before_implementation':True,'plan_path':str(planpath.relative_to(ROOT)),'plan_sha256':sha(planpath),'authorization':'User: 이거 구현대로 만들고 실험해봐','parent':'ADR-1059-experiment-v1/compact-input','candidate_id':'execution-repair-r1','scope':'Implement sections 4–14 of exact plan, V01–V24, then one frozen37×3 matrix, gate after first9cells. No MAIN/GENOS selection.','hypothesis':'Separate candidates, acquisition, delivery, partial review and action dependencies; bounded current packets and one targeted repair preserve valid investigation actions and allow same-information ontology comparison.','input_limits':{'entry':24000,'catalogue':24000,'review':48000,'repair':16000,'assess':64000,'compose':32000,'outer':100000},'first_cases':['fsc-hard-005','cm-023','fsc-hard-008'],'gate':'All plan13.2 safety/control/input/ontology/evidence/answer-control conditions must pass after9cells before102remaining. A1/A2 expected bundle landing and allowed provision delivery required.','stop':'No unknown transport retry or reserved-cell replay. Gate failure preserves results and requires new ADR for code changes. WorkerRSS>5GiB,availableRAM<3GiB,swap increase>512MiB,disk<20GiB stops new calls.','model':'qwen/qwen3.8-27b','max_output_tokens':None,'provider_contract':'Inherit exact user-authorized ADR1059 scoped429-only same-model FP8 chain; no other fallback.','accuracy':'34 reference-answer cases separate from3evidence-only. All37 in_sample true, decision_eligible false. Frozen required article roots, source span delivery primary; full-pair criteria plan13.4.','pending':'Never fabricate DEFER/EXCLUDE or clear gaps. Action source judgments independently validated, whole-request pending retained and prevents COMPLETE.','failure_owner':'output_contract.bounded_decision owns read row repair, shares one repair with JSON recovery; gateway owns known transport retry; same40physical/1024tool/1800s budget/deadline.'}
save(ART/'implementation-plan.json',plan)
m=read(ADR/'실험/manifest.json');old=read(BASE/'실험/manifest.json')
for key in ('dataset','llm_policy','retrieval_accounting','questions'):m[key]=deepcopy(old[key])
m['design']=deepcopy(old['design']);m['design']['code_isolation']['candidates']=[]
m['design'].update(hypothesis=plan['hypothesis'],primary_metric='Per-question required article-root body span delivery, macro average37; accuracy34 and evidence-only3 separately',success_criteria='Exact frozen plan sections13.1 V01–V24,13.2 gate,13.4 criteria; no source/ACL/state loss; partial valid action executes once with pending preserved',failure_criteria=plan['stop'],criteria_frozen_before_run=True,criteria_record={'path':str((ART/'implementation-plan.json').relative_to(ROOT)),'sha256':sha(ART/'implementation-plan.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1059-experiment-v1/compact-input'],'changes':'Immutable parent code reference; no additional live baseline replay','controls':'Historical diagnosis only'}]+[{'id':a,'role':'candidate','derived_from':['baseline'],'changes':d,'controls':'Same execution repair code/data/model/budgets, ontology mode only'} for a,d in [('A0','Ontology off'),('A1','Approved exact source fragments and same metadata, registration order'),('A2','Same approved source/metadata in deterministic compiled order')]]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:deepcopy(old['design']['retrieval_stage_plan']['stages_by_arm']['baseline']) for a in ('baseline','A0','A1','A2')}
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['A0','A1','A2'],'selection_rule':'37 unique cases; first FSC005,CM023,FSC008; counterbalanced A0A1A2,A1A2A0,A2A0A1; first9gate then102same code sequential','status':'not_run','artifact_path':str((ART/'matrix-summary.json').relative_to(ROOT)),'sha256':'PENDING'}]
m['lineage']['hypothesis_delta']=plan['hypothesis']
m['dataset'].update(frozen_source=str((BASE/'artifacts/cases-product.json').relative_to(ROOT)),sha256=sha(BASE/'artifacts/cases-product.json'))
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING')
save(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
rows=read(SOURCE/'candidate.json')['files']
target=c.snapshot(ADR,'execution-repair-r1',[r['target_path'] for r in rows if r['upstream_state']=='present'],experiment_id=m['experiment_id'],arm_id='A2',run_ids=['run-001'])
for r in rows:
 p=target/'snapshot'/r['target_path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/'revisions/rev-001/snapshot'/r['target_path'],p)
 if r['upstream_state']=='absent':c.register_file(target,r['target_path'],upstream_state='absent')
 if p.suffix in ('.py','.json'):
  s=p.read_text()
  if 'ADR-1059-experiment-v1' in s:p.write_text(s.replace('ADR-1059-experiment-v1','ADR-1061-experiment-v1'))
c.refresh(target)
preserved={str(p.relative_to(ROOT)):sha(p) for p in [SOURCE/'candidate.json',PRIOR/'실험/manifest.json',PRIOR/'artifacts/design-freeze.json',ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']}
save(ART/'preservation.json',{'files':preserved,'disk_free_before':shutil.disk_usage(ROOT).free})
for name in ('stage_candidate.py','validate_candidate.py','common.py','run_case.py','run_matrix.py','collect_metrics.py','wire_audit.py','freeze_code.py','freeze_run.py','finish.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1059'/name).read_text().replace('ADR-1059-compact-input-guidance-binding',ADR.name).replace('adr_1059','adr_1061').replace('ADR-1059','ADR-1061').replace('adr1059','adr1061').replace('dense-input-r1','execution-repair-r1')
 (Path(__file__).parent/name).write_text(s)
print(target)
