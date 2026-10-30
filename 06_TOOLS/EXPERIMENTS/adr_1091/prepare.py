from pathlib import Path
import hashlib,json,sys,shutil
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
A=R/'04_EXPERIMENTS/ADR/ADR-1091-ontology-a1-merge-repair';OLD=R/'04_EXPERIMENTS/ADR/ADR-1088-ontology-a1-compact-integration'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=json.loads((A/'실험/manifest.json').read_text());old=json.loads((OLD/'실험/manifest.json').read_text())
for key in ('dataset','retrieval_accounting','llm_policy','design'):
 m[key]=old[key]
m['integration'].update({k:v for k,v in old['integration'].items() if k not in ('merge_id','planned_at')})
m['design']['hypothesis']='Fix the 1088 merge NameError while preserving exact parent composition and all prospectively declared contracts. No substantive effect or policy change.'
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
criteria={'hypothesis':m['design']['hypothesis'],'inherited_criteria':str((OLD/'artifacts/criteria.json').relative_to(R)), 'inherited_sha256':sha(OLD/'artifacts/criteria.json'),'success_criteria':m['design']['success_criteria'], 'failure_origin':{'path':str((OLD/'artifacts/check-001.json').relative_to(R)),'sha256':sha(OLD/'artifacts/check-001.json'),'passed':189,'failed':4,'error':'catalogue_choice_prompt formal active_schema, body schema NameError'},'new_model_calls':0}
put(A/'artifacts/criteria.json',criteria)
m['design']['criteria_record']={'path':str((A/'artifacts/criteria.json').relative_to(R)),'sha256':sha(A/'artifacts/criteria.json')};m['design']['code_isolation']['candidates']=[]
m['dataset'].update(frozen_source=m['design']['criteria_record']['path'],sha256=m['design']['criteria_record']['sha256'])
put(A/'실험/manifest.json',m)
f=json.loads((OLD/'artifacts/freeze.json').read_text());B=R/f['code_root'];cm=json.loads((R/f['binding']['manifest_path']).read_text());rev=cm['revisions'][-1]
files=[str((R/r['frozen_path']).relative_to(B)) for r in rev['files']]
C=ac.snapshot(A,'a1-combined-r1',[n for n in files if (R/n).is_file()],experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n in files:
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(B/n,p)
 if not (R/n).exists():ac.register_file(C,n,upstream_state='absent')
p=S/'02_BACKEND/semantic_runtime/legal_agent/decision_projection.py';s=p.read_text();a='def catalogue_choice_prompt(payload, active_schema, *, grouped_fulltext=False):';assert s.count(a)==1;p.write_text(s.replace(a,'def catalogue_choice_prompt(payload, schema, *, grouped_fulltext=False):'))
D=R/'06_TOOLS/EXPERIMENTS/adr_1091'
for n in ('test_combined.py','test_ontology_optimization.py','check.py','freeze.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_1088'/n).read_text().replace('ADR-1088-ontology-a1-compact-integration','ADR-1091-ontology-a1-merge-repair').replace('adr_1088/','adr_1091/').replace('ADR-1088-experiment-v1','ADR-1091-experiment-v1')
 (D/n).write_text(s)
put(A/'artifacts/merge-repair.json',{'reconstructed_composition':f,'change':{'path':str(p.relative_to(S)),'before':sha(B/p.relative_to(S)),'after':sha(p),'reason':'Restore catalogue function parameter name; no semantic change'},'completed_parents':m['lineage']['parents'],'failed1088_is_completed_parent':False})
print(S)
