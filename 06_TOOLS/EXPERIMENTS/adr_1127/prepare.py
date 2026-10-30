from pathlib import Path
import json,hashlib,sys,shutil
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1127-stable-document-catalog';ART=ADR/'artifacts';OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1126-stable-review-serving-qualification';HERE=Path(__file__).parent

def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
c=read(OLD/'artifacts/design/criteria.json');c.update(frozen_at=datetime.now(timezone.utc).isoformat(),hypothesis='Encode existing final adoption requirements in full generation alternatives: adopted judgment needs nonempty claim_refs; unresolved/unused needs none. Preserve canonical detailed validation and legal choice. One model correction of preserved1120screen.',new_holdout_is_engineering_only=False,observed_conditions_are_regression=True)
c['hypothesis']='Bind document IDs to already loaded authoritative catalogue names; presentation labels cannot redefine identity. Preserve full-generation names, source/ACL/hash and stable alias guards.';c['primary']=['All344observed conditions and6catalogue-state conditions pass','Known privacy question completes native HTTP without document identity implementation failure; protected guards pass; legal quality uncertified'];put(ART/'design/criteria.json',c)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=c['hypothesis'];m['design'].update(hypothesis=c['hypothesis'],primary_metric='Actual native source/review/recovery integration',success_criteria=c['primary'],failure_criteria='Any source/ACL/hash/state/budget guard or required test failure',criteria_frozen_before_run=True);m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None);m['dataset'].update(name='Observed engineering matrix and corrected synthetic source HTTP fixtures',version='v2',frozen_source=str((ART/'design/criteria.json').relative_to(ROOT)),sha256=sha(ART/'design/criteria.json'));m['llm_policy']['llm_calls']=[]
for a in m['design']['arms']:a.update(changes='Read-judgment prompt and diagnostics only; A-F and MAIN107 preserve protected contracts',controls='Same sources/model/profile/budgets; fixture errors repaired')
m['runs'][0]['selection_rule']='Same48/157/51regression plus5actual native HTTP cases; every gate before model'
m['runs'].append({'id':'run-002','purpose':'audit','parent_run_id':'run-001','arm_ids':['integrated'],'selection_rule':'One known public question after gates;65sprovider interval within1800s','status':'planned','artifact_path':'TODO','sha256':'PENDING'});put(ADR/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
f=read(OLD/'artifacts/design/freeze.json');P=ROOT/f['code_root'];new=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('schema_preparation','stable_references','independent_read_recovery')]
C=ac.snapshot(ADR,'integrated-r1',[n for n in f['files'] if n not in new],experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001','run-002']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(P/n)==h;shutil.copyfile(P/n,S/n)
for n in new:ac.register_file(C,n,upstream_state='absent')
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1126').glob('*.py'):
 if p.name in ('prepare.py','finish.py','patch.py','probe_final.py','probe_native_transport.py','finish_component.py'):continue
 t=p.read_text().replace('ADR-1126-stable-review-serving-qualification',ADR.name).replace('adr_1126','adr_1127');(HERE/p.name).write_text(t)
for name in ('case.json','baseline.json','matrix.json','regression-matrix.json','test-support.json','merge.json','observed-schema-fixture.json','final-probe-inputs.json'):shutil.copyfile(OLD/'artifacts/design'/name,ART/'design'/name)
print(S)
