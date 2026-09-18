"""User-steered implementation audit, before any model calls or frozen candidate run."""
from runtime import *
m=read(D/'실험/manifest.json')
new(A/'pre-amendment-manifest.json',m)
m['phase']='audit';m['in_sample']=False;m['decision_eligible']=False;m['questions']=[];m['llm_policy']['llm_calls']=[]
m['design'].update(primary_metric='Ordinary contract and pipeline wiring checks; no accuracy or retrieval-effect comparison',success_criteria='All scoped folder/title/tree/coordinate and multi-entry contract checks pass; source generation unchanged',failure_criteria='Any contract failure; never sufficient with unreviewed candidates or unresolved required links',implementation_scope='Existing multi-entry union plus folder-origin projection, title-only catalogue, server-owned narrowed conversation contexts, stored outline and exact coordinate block reads',controls='Frozen parent0448 and selected source generation unchanged',order='No live model comparison. Original six-case proposal preserved, not executed.',criteria_frozen_before_run=True)
m['design']['retrieval_stage_plan']={'not_applicable_reason':'Only ordinary unit/connection tests and read-only metadata inspection, not a retrieval effect evaluation','stages_by_arm':{}}
m['runs']=[{'id':'run-001','purpose':'audit','parent_run_id':None,'arm_ids':['multi'],'selection_rule':'Ordinary contract tests and read-only current source metadata connection checks; no baseline replay or model calls','status':'planned','artifact_path':str((A/'verification.json').relative_to(R)),'sha256':'PENDING'}]
a=read(R/'04_EXPERIMENTS/ADR/ADR-0448-inherited-structure-coordinate-binding/실험/manifest.json')['retrieval_accounting'];m['retrieval_accounting']=a
m['design']['protocol_deviations']=['Initial unchanged parent snapshot was created before successful design serialization due to setup command failure. All candidate implementation edits occurred after initial design save. No model calls or effect measurements occurred. This audit is not decision eligible.']
m['design']['user_amendment']='2026-09-17: internal path -> 내규; preserve folders; external/kofia/title-only filters; scoped followup article paragraph and outline.'
(D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');new(A/'amended-design-before-implementation.json',m)
p=D/'README.md';s=p.read_text();s=s.replace('phase: probe','phase: audit').replace('in_sample: true','in_sample: false');p.write_text(s)
print('audit amendment saved; original planned comparison preserved; models0')
