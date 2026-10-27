from pathlib import Path
from copy import deepcopy
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1059-compact-input-guidance-binding';ART=ADR/'artifacts'
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1058-bounded-navigation-input-dedup'
SOURCE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1058/dense-input-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
plan=read(PRIOR/'artifacts/implementation-plan.json')
plan.update(hypothesis='Keep1058 exact input compression and validate shared guidance against canonical metadata; the CM023 saved failure and original4oversized views must prepare successfully.',
    change='Only fix the instruction consumer: projected codec feature layout and canonical shared-value integrity header are separate inputs. Do not disable validation or change data, source content, decisions, ACL, state or budgets.',
    scope='Completed1057 baseline,1058 failed implementation dependency; same3cases under a fresh frozen run, old12calls and all failures retained.')
plan['success'].append('Saved1058 CM023 failure prepares losslessly, and shared+expanded format regression runs through actual repository reservation')
save(ART/'implementation-plan.json',plan)
m=read(ADR/'실험/manifest.json');old=read(PRIOR/'실험/manifest.json')
m['design']=deepcopy(old['design']);m['design']['code_isolation']['candidates']=[]
m['design'].update(hypothesis=plan['hypothesis'],success_criteria='; '.join(plan['success']),failure_criteria=plan['stop'])
m['design']['criteria_record']={'path':str((ART/'implementation-plan.json').relative_to(ROOT)),'sha256':sha(ART/'implementation-plan.json')}
m['design']['arms'][1]['changes']=plan['change'];m['lineage']['hypothesis_delta']=plan['hypothesis']
m['relationships']=[{'adr_id':'ADR-1058','relation':'informed_by','record_path':str((PRIOR/'artifacts/failure-summary.json').relative_to(ROOT)),
    'record_sha256':sha(PRIOR/'artifacts/failure-summary.json'),'note':'Immutable failed code dependency and exact runtime reproduction; not a completed parent arm.'}]
m['runs'][0].update(purpose='audit',arm_ids=['compact-input'],selection_rule='Same3cases chosen before this correction; failed1058 cells never overwritten',artifact_path=str((ART/'live-result.json').relative_to(ROOT)))
m['retrieval_accounting']=deepcopy(old['retrieval_accounting']);m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING')
m['dataset']=deepcopy(old['dataset']);m['dataset'].update(frozen_source=str((ART/'implementation-plan.json').relative_to(ROOT)),sha256=sha(ART/'implementation-plan.json'))
m['llm_policy']=deepcopy(old['llm_policy']);save(ADR/'실험/manifest.json',m)
live=read(PRIOR/'artifacts/live-probe-plan.json');live['success']=plan['success'];save(ART/'live-probe-plan.json',live)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
rows=read(SOURCE/'candidate.json')['files']
target=c.snapshot(ADR,'dense-input-r1',[r['target_path'] for r in rows if r['upstream_state']=='present'],experiment_id=m['experiment_id'],arm_id='compact-input',run_ids=['run-001'])
for r in rows:
    p=target/'snapshot'/r['target_path'];p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(SOURCE/'revisions/rev-001/snapshot'/r['target_path'],p)
    if r['upstream_state']=='absent':c.register_file(target,r['target_path'],upstream_state='absent')
    if p.suffix in ('.py','.json'):
        s=p.read_text()
        if 'ADR-1058-experiment-v1' in s:p.write_text(s.replace('ADR-1058-experiment-v1','ADR-1059-experiment-v1'))
c.refresh(target)
preserved=read(PRIOR/'artifacts/preservation.json')['files']
for p in [SOURCE/'candidate.json',PRIOR/'실험/manifest.json',PRIOR/'artifacts/design-freeze.json',PRIOR/'artifacts/failure-summary.json']:
    preserved[str(p.relative_to(ROOT))]=sha(p)
save(ART/'preservation.json',{'files':preserved,'disk_free_before':shutil.disk_usage(ROOT).free})
for name in ('stage_candidate.py','validate_candidate.py','common.py','run_case.py','run_matrix.py','collect_metrics.py','wire_audit.py','freeze_code.py','freeze_run.py','replay_saved_inputs.py','finish.py'):
    s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1058'/name).read_text()
    s=s.replace('ADR-1058-bounded-navigation-input-dedup',ADR.name).replace('adr_1058','adr_1059').replace('ADR-1058','ADR-1059').replace('adr1058','adr1059')
    (Path(__file__).parent/name).write_text(s)
print(target)
