from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3]; A=R/'04_EXPERIMENTS/ADR/ADR-0694-structure-first-read-plan'
P=R/'02_BACKEND/lawrag/research/candidates/adr_0693/consistent-judgment';C=R/'02_BACKEND/lawrag/research/candidates/adr_0694/structured-reading'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');p=read(P/'candidate.json');rev=p['revisions'][-1]
criteria={'scope':'Structure metadata before explicitly scoped fulltext; idempotent model-selected read plans with acquired/delivered/adopted separation.',
 'required':['No body FTS in initial discover or initial menu','Structure miss never silently widens to corpus fulltext','Explicit document/subtree selection constrains SQL before ranking and cursor identity','Read plan binding preserves selected source ranges and completed substeps across interruption','Batch acquisition deduplicates identical targets without adopting them','v4 judgment and public-display contracts remain valid'],
 'qualification':'Synthetic probe only, in_sample true, decision_eligible false; later frozen public paired holdout measures physical calls, tokens, elapsed time and evidence omissions.'}
put(A/'artifacts/design/criteria.json',criteria)
m['design'].update(hypothesis=criteria['scope'],primary_metric='Contract violations',success_criteria=criteria['required'],failure_criteria='Any invariant failure',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'structured-reading','experiment_id':m['experiment_id'],'arm_id':'structured-reading','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':'PENDING','revision_id':'PENDING','revision_sha256':'PENDING','runner_path':'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py')}])
m['dataset'].update(name='Synthetic structural trees and interrupted read plans',version='structure-first-v1',frozen_source=str((A/'artifacts/design/criteria.json').relative_to(R)),sha256=sha(A/'artifacts/design/criteria.json'),legal_version_checked=True,reference_version_checked=True)
for arm in m['design']['arms']:arm.update(changes='Completed v4 parent' if arm['id']=='baseline' else criteria['scope'],controls='Same synthetic sources and pinned MAIN46 source generation')
m['runs'][0].update(selection_rule='All structure, scope, interruption and inherited critical contracts',artifact_path=str((A/'artifacts/contracts/result.json').relative_to(R)))
m['lineage']['hypothesis_delta']=criteria['scope']
m['retrieval_accounting']['not_applicable_reason']='Synthetic contract checks; no measured corpus retrieval or real model effect'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','structured-reading','--experiment-id',m['experiment_id'],'--arm-id','structured-reading','--run-id','run-001']
for f in p['files']:cmd+=['--source',f['target_path']]
subprocess.run(cmd,cwd=R,check=True)
for f in p['files']:shutil.copy2(P/'revisions'/rev['revision_id']/'snapshot'/f['target_path'],C/'snapshot'/f['target_path'])
put(A/'artifacts/design/parent-code.json',{'manifest_path':str((P/'candidate.json').relative_to(R)),'manifest_sha256':sha(P/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']})
