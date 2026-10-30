from pathlib import Path
import json,hashlib,sys,shutil
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];H=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-1138-scope-final-recovery-integration';D=A/'artifacts/design'
P=R/'04_EXPERIMENTS/ADR/ADR-1129-catalog-recovery-serving'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json')
criteria={'frozen_at':datetime.now(timezone.utc).isoformat(),'hypothesis':'Stored body coordinates resolve unqualified article references without conflating addenda; a rejected final review cannot block independently validated, bounded source gaps. Preserve all1129 performance/reference contracts.',
 'primary':['Scope contracts: body/addendum, missing-body, duplicate-body, explicit addendum, ACL and typed selection','Final rejected review: one correction, then independently valid source gap only; no rejected claims/review committed; exact target/progress/budget/restart checks','Existing1129 technical checks retain source/ACL/hash/state contracts; intentional new final schema checked independently','Known privacy question reaches original reading and final answer; known difficult question retained as diagnostic, legal correctness not certified'],
 'failure_contract':{'owner':'completion_execution after its single correction','eligible':'FINAL_READ_REVIEW_INVALID only, core claim/evidence validation remains mandatory','recovery':'existing ASSESS_GAP_REENTRY with claims empty and final review INCOMPLETE; no invented legal opinion','guards':'actual missing exact source target, same ACL/generation, source-progress fingerprint, existing counters/deadline','final':'valid final answer or explicitly preserved bounded failure'},
 'budgets':{'model_attempts':40,'tools':1024,'wall_seconds':1800,'max_output_tokens':None},'resource_guard':{'rss_gib':4,'available_ram_gib':3,'swap_mib':512,'free_disk_gib':20},'main_promotion':'Separate prospective integration qualification after this known-case probe; concurrent ontology1137 preserved.'}
put(D/'criteria.json',criteria)
m['in_sample']=True;m['decision_eligible']=False;m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Protected source and recovery contracts',success_criteria=criteria['primary'],failure_criteria='Any protected invariant regression; live failures preserved',criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']=criteria['hypothesis']
for a in m['design']['arms']:a.update(changes='1138 body-coordinate resolution and independent final-assessment recovery over1129',controls='Same data/model/budgets; historical failure inputs are in-sample')
m['runs'][0].update(selection_rule='All frozen new scope/recovery contracts and observed1129 regressions',arm_ids=['repaired'])
m['runs'].append({'id':'run-002','purpose':'probe','parent_run_id':'run-001','arm_ids':['repaired'],'selection_rule':'Known public privacy question once, after contracts pass; no answer key in model input','status':'planned','artifact_path':'TODO','sha256':'PENDING'})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
put(A/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
absent=[n for n in f['files'] if not (R/n).exists()]
C=ac.snapshot(A,'repaired-r1',[n for n in f['files'] if n not in absent],experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001','run-002']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,S/n)
for n in absent:ac.register_file(C,n,upstream_state='absent')
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1129').glob('*.py'):
 if p.name in ('prepare.py','qualify.py','finish_incomplete.py','stage.py'):continue
 text=p.read_text().replace(P.name,A.name).replace('adr_1129','adr_1138').replace("arm='integrated'","arm='repaired'").replace("'integrated-r1'","'repaired-r1'").replace("arm_id='integrated'","arm_id='repaired'")
 (H/p.name).write_text(text)
for p in (P/'artifacts/design').glob('*.json'):
 if p.name not in ('freeze.json','criteria.json','staging.json'):shutil.copyfile(p,D/p.name)
m['dataset'].update(name='Known body/addendum failure and final-review recovery probe',version='v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
put(A/'실험/manifest.json',m)
print(S)
