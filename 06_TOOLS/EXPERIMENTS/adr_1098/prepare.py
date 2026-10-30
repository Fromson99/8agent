from pathlib import Path
import hashlib,json,shutil,sys
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
A=R/'04_EXPERIMENTS/ADR/ADR-1098-ontology-assess-pending';OLD=R/'04_EXPERIMENTS/ADR/ADR-1097-ontology-direct-contract'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=json.loads((A/'실험/manifest.json').read_text());old=json.loads((OLD/'실험/manifest.json').read_text())
for k in ('dataset','llm_policy','retrieval_accounting','design'):m[k]=old[k]
criteria=json.loads((OLD/'artifacts/criteria.json').read_text())
criteria.update(hypothesis='Preserve the successful1097 direct/gap flow; when ASSESS omits an acquired fragment, expose ACQUIRED plus NOT_SENT rather than falsely UNACQUIRED. Keep server proofs in canonical journal but remove them from minimal model copy. No response schema change.',failure_record={'path':str((OLD/'artifacts/check-001.json').relative_to(R)),'sha256':sha(OLD/'artifacts/check-001.json')})
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
D=R/'06_TOOLS/EXPERIMENTS/adr_1098'
for name in ('test_direct.py','check.py','freeze.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_1097'/name).read_text().replace('ADR-1097-ontology-direct-contract','ADR-1098-ontology-assess-pending').replace('adr_1097','adr_1098').replace('ADR-1097-experiment-v1','ADR-1098-experiment-v1')
 (D/name).write_text(s)
put(A/'artifacts/reconstruction.json',{'completed_parent':'ADR-1097-experiment-v1/direct','completed_candidate_reference':f,'changes':['Typed source IDs in minimal selection binding use the existing handle map','Prepared handoff resume preserves material receipt; new assessment context consumes it']})
print(S)
