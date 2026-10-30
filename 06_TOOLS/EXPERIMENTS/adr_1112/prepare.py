from pathlib import Path
import json,hashlib,sys,shutil
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1112-stable-view-identity';ART=ADR/'artifacts';OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1110-stable-review-runtime-binding'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
c=read(OLD/'artifacts/design/criteria.json');c.update(frozen_at=datetime.now(timezone.utc).isoformat(),hypothesis='Exclude host-generated server view IDs from the durable model reference namespace; all152contracts and actual native save/reserve must pass before fresh model.',changes=['Exclude view_id,presentation_id and server envelope only from model alias collection; keep canonical saved view/hash unchanged'])
put(ART/'design/criteria.json',c);m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=c['hypothesis'];m['design'].update(hypothesis=c['hypothesis'],primary_metric='Native saved view and stable model alias binding',success_criteria=c['primary'],failure_criteria='Any native source/ACL/hash/reference/budget guard failure',criteria_frozen_before_run=True);m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None);m['dataset'].update(name='Same152contracts plus one frozen public question',version='v1',frozen_source=str((ART/'design/criteria.json').relative_to(ROOT)),sha256=sha(ART/'design/criteria.json'));m['llm_policy']['llm_calls']=[]
for a in m['design']['arms']:a.update(changes='Completed1110failure' if a['id']=='baseline' else c['changes'],controls='Sources/ACL/model/budgets and allother input/recovery implementation unchanged')
m['runs'].append({'id':'run-002','purpose':'primary','parent_run_id':'run-001','arm_ids':['integrated'],'selection_rule':'One prospectively frozen known public question after contracts pass','status':'planned','artifact_path':'TODO','sha256':'PENDING'});put(ADR/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
f=read(OLD/'artifacts/design/freeze.json');P=ROOT/f['code_root'];new=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('schema_preparation','stable_references','independent_read_recovery')]
C=ac.snapshot(ADR,'stable-view-r1',[n for n in f['files'] if n not in new],experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001','run-002']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(P/n)==h;shutil.copyfile(P/n,S/n)
for n in new:ac.register_file(C,n,upstream_state='absent')
p=S/'02_BACKEND/semantic_runtime/legal_agent/stable_references.py';t=p.read_text();old="if key in (FIELD,'minimal_input_binding'):return";assert t.count(old)==1;t=t.replace(old,"if key in (FIELD,'minimal_input_binding','view_id','presentation_id','source_stage','phase','base_state_revision','evidence_revision','state_version'):return");p.write_text(t)
for name in ('test_preparation.py','test_stable_recovery_isolated.py','test_output_contract_local.py','test_runtime_binding.py','check.py','common.py','live.py','freeze.py'):
 t=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1110'/name).read_text().replace('ADR-1110-stable-review-runtime-binding',ADR.name).replace('adr_1110/stable-runtime-r1','adr_1112/stable-view-r1').replace('adr_1110/check.py','adr_1112/check.py');(Path(__file__).parent/name).write_text(t)
shutil.copyfile(OLD/'artifacts/design/case.json',ART/'design/case.json')
put(ART/'design/baseline.json',{'pointer':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':read(ROOT/'08_DEPLOYMENT/RELEASES/compact-input-20261027-r1/release.json')})
print(S)
