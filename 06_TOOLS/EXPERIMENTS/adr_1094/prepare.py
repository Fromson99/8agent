"""Freeze scope before implementation; inherit the completed ontology candidate."""
from pathlib import Path
import hashlib,json,shutil,sys
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
A=R/'04_EXPERIMENTS/ADR/ADR-1094-ontology-direct-assessment'
P=R/'04_EXPERIMENTS/ADR/ADR-1091-ontology-a1-merge-repair'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=json.loads((A/'실험/manifest.json').read_text());parent=json.loads((P/'실험/manifest.json').read_text())
assert parent['results']['by_arm']['integrated']['status']=='complete'
criteria={
 'hypothesis':'An opt-in ontology acquisition handoff can deliver verified assembled knowledge and exact originals directly to the existing ASSESS owner, without an additional navigation review or connection choice. ASSESS still decides sufficiency and uses existing gap re-entry.',
 'primary_metric':'Synthetic actual HTTP and exact compact wire contracts; no legal quality or latency measurement.',
 'success_criteria':[
  'A1 and A2 with an acquired approved bundle reach ASSESS immediately after READ; full/partial ontology meaning, current evidence references and original text survive compact wire.',
  'ASSESS emits answer content and sufficiency in its existing single decision; structured COMPOSE renders it. Existing narrative COMPOSE remains a presentation call when configured.',
  'Material source gap uses existing SELECT re-entry; same-material handoff cannot loop; pending opinions stay pending until explicit ASSESS review.',
  'No approved bundle or disabled switch retains the old route. Incomplete bundle/original omission cannot become complete or prove absence.',
  'Snapshot/plan/anchor/source/ACL/extent/content tampering rejected; current evidence refs only. Same request reuse consumes no additional calls.',
  'Inherited ontology, minimal-input and task-local contracts pass on the same frozen revision. No change to deferred schema, gap materiality or judgment-link repair modules.'
 ],
 'failure_contract':{
  'input_consumer':'Explicit approved snapshot + acquisition checkpoint + verified selected originals -> existing completion_execution ASSESS -> existing COMPOSE/publication.',
  'classification':'Incomplete acquisition is pending, not integrity failure. Snapshot/plan/ACL/source/hash mismatch is contract failure. Model schema/evidence/review failures retain existing classification.',
  'owner':'LawInvestigation owns one handoff per material signature. completion_execution owns ASSESS correction (one) and gap re-entry (profile limit); gateway retains transport ownership. No added retry runner.',
  'allowed_mutation':'Only routing and ontology model-context projection; never infer judgment, sufficiency, claim, source absence, authorization or repair a source reference.',
  'budget':'Same request counters/deadline/tool and model budgets, finalization reserve, correction and re-entry limits. Handoff itself makes no model call or new source read.',
  'state':'Acquisition plans/receipts, evidence, pending reviews, handoff signature, assessment basis and exact saved model view retained in existing journal/checkpoint.',
  'termination':'Existing answer/limited answer/fact request/pending/failure; no automatic ANSWER on ontology completeness.',
  'tests':'Full and partial HTTP, missing-source re-entry, exact refs, duplicate request, same material, absent bundle, snapshot/plan/content/ACL/extent rejection, inherited source/repair/budget contracts.'
 },
 'deferred':'User item1 schema and judgment-link/gap repair; inspect after other work completes. MAIN106 and GENOS unchanged.',
 'models':{'new_calls':0,'output_cap':None},'resources':{'sequential':True,'max_rss_gib':1,'min_available_gib':3},
 'parent':'ADR-1091-experiment-v1/integrated'}
assert not (A/'artifacts/criteria.json').exists();put(A/'artifacts/criteria.json',criteria)
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update({k:criteria[k] for k in ('hypothesis','primary_metric','success_criteria','failure_contract')},criteria_frozen_before_run=True,failure_criteria='Any required synthetic contract failure; no generalization/quality claim.')
m['design']['criteria_record']={'path':str((A/'artifacts/criteria.json').relative_to(R)),'sha256':sha(A/'artifacts/criteria.json')}
m['dataset'].update(name='Synthetic approved ontology and two source articles; no real question/gold',version='v1',frozen_source=m['design']['criteria_record']['path'],sha256=m['design']['criteria_record']['sha256'])
m['llm_policy']['llm_calls']=[]
reason='No real corpus or retrieval-effect evaluation; synthetic routing and source-contract validation only.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
for arm in m['design']['arms']:
 arm.update(changes='Inherited completed1091; opt-in direct ontology handoff/context for direct arm only',controls='Same original/source/ACL/assessment-schema/repair contracts and shared budgets.')
m['runs'][0].update(arm_ids=['direct'],selection_rule='Prospectively declared synthetic contracts and inherited regressions',artifact_path=str((A/'artifacts/check-001.json').relative_to(R)))
put(A/'실험/manifest.json',m)
f=json.loads((P/'artifacts/freeze.json').read_text());B=R/f['code_root'];cm=json.loads((R/f['binding']['manifest_path']).read_text());rev=cm['revisions'][-1]
assert rev['revision_sha256']==f['binding']['revision_sha256']
assert all(sha(R/r['frozen_path'])==r['snapshot_sha256'] for r in rev['files'])
files=[str((R/r['frozen_path']).relative_to(B)) for r in rev['files']]
C=ac.snapshot(A,'direct-r1',[n for n in files if (R/n).is_file()],experiment_id=m['experiment_id'],arm_id='direct',run_ids=['run-001']);S=C/'snapshot'
for n in files:
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(B/n,p)
 if not (R/n).exists():ac.register_file(C,n,upstream_state='absent')
put(A/'artifacts/parent.json',{'binding':f['binding'],'code_root':str(B.relative_to(R)),'active_release_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_code_overwritten':False})
print(S)
