from pathlib import Path
import hashlib,json,shutil,sys
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
A=R/'04_EXPERIMENTS/ADR/ADR-1095-ontology-assess-wire';OLD=R/'04_EXPERIMENTS/ADR/ADR-1094-ontology-direct-assessment'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=json.loads((A/'실험/manifest.json').read_text());old=json.loads((OLD/'실험/manifest.json').read_text())
for k in ('dataset','llm_policy','retrieval_accounting','design'):m[k]=deepcopy=old[k]
criteria=json.loads((OLD/'artifacts/criteria.json').read_text())
criteria.update(hypothesis='Complete1091 plus the preserved1094 direct handoff: retain ontology fields through the ASSESS input allowlist and test corruption on an actual ontology-bound option. No output-schema/gap/judgment-repair changes.',failure_record={'path':str((OLD/'artifacts/check-001.json').relative_to(R)),'sha256':sha(OLD/'artifacts/check-001.json')})
put(A/'artifacts/criteria.json',criteria)
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design']['hypothesis']=criteria['hypothesis']
m['design']['criteria_record']={'path':str((A/'artifacts/criteria.json').relative_to(R)),'sha256':sha(A/'artifacts/criteria.json')}
m['dataset'].update(frozen_source=m['design']['criteria_record']['path'],sha256=m['design']['criteria_record']['sha256']);m['design']['code_isolation']['candidates']=[]
m['runs'][0].update(arm_ids=['direct'],selection_rule='All prospectively declared direct handoff and inherited contracts',artifact_path=str((A/'artifacts/check-001.json').relative_to(R)))
put(A/'실험/manifest.json',m)
f=json.loads((OLD/'artifacts/freeze.json').read_text());B=R/f['code_root'];cm=json.loads((R/f['binding']['manifest_path']).read_text());rev=cm['revisions'][-1]
assert all(sha(R/r['frozen_path'])==r['snapshot_sha256'] for r in rev['files'])
files=[str((R/r['frozen_path']).relative_to(B)) for r in rev['files']]
C=ac.snapshot(A,'direct-r1',[n for n in files if (R/n).is_file()],experiment_id=m['experiment_id'],arm_id='direct',run_ids=['run-001']);S=C/'snapshot'
for n in files:
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(B/n,p)
 if not (R/n).exists():ac.register_file(C,n,upstream_state='absent')
p=S/'02_BACKEND/semantic_runtime/legal_agent/input_modes.py';s=p.read_text();a="'assessment_scope','partial_issue_assessments','integration_task'))"
assert a in s;p.write_text(s.replace(a,"'assessment_scope','partial_issue_assessments','integration_task','ontology_bundles','ontology_assessment'))"))
D=R/'06_TOOLS/EXPERIMENTS/adr_1095'
for name in ('test_direct.py','check.py','freeze.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_1094'/name).read_text().replace('ADR-1094-ontology-direct-assessment','ADR-1095-ontology-assess-wire').replace('adr_1094','adr_1095').replace('ADR-1094-experiment-v1','ADR-1095-experiment-v1')
 if name=='test_direct.py':
  s=s.replace("elif change=='option_text':options[0]['text']='X'+options[0]['text'][1:]", "elif change=='option_text':\n        option=next(o for o in options if o['evidence_id'] in row['evidence_ids'])\n        option['text']='X'+option['text'][1:]")
 (D/name).write_text(s)
put(A/'artifacts/reconstruction.json',{'completed_parent':'ADR-1091-experiment-v1/integrated','failed_candidate_reference':f,'failed_candidate_is_parent':False,'changes':['ASSESS input allowlist adds ontology context','corruption fixture targets bound fragment option']})
print(S)
