from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0800-workflow-literal-request-quotes';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0799-workflow-handoff-task-context/artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for name in ('baseline.json','working-before.json','data-binding.json'):put(D/name,read(P/name))
criteria=read(P/'criteria.json');criteria['delta']='Request quotes in workflow-only fused INTAKE use exact original literal choices; no freeform concatenation, semantic repair, added model or weakened original verifier. Strictly reject non-object trusted task context.'
criteria['additional_tests']+=['every quote option is a literal original substring and within existing quote length limit','all original characters preserved in anchor partition; no task hint admitted as a quote','schema rejects copied question plus appended task instructions','normal non-workflow schema remains unchanged','task context rejects nonobjects before any child execution']
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');old=read(P.parent.parent/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['delta'];m['design'].update(hypothesis=criteria['delta'],primary_metric='finite technical boundary pass and actual comparison consumer',success_criteria=criteria['success'],failure_criteria=old['design']['failure_criteria'],criteria_frozen_before_run=True)
m['design']['retrieval_stage_plan']=old['design']['retrieval_stage_plan'];m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
for a in m['design']['arms']:a.update(changes='Current selected MAIN73' if a['id']=='baseline' else criteria['delta'],controls=criteria['controls'])
m['runs'][0].update(selection_rule='All finite technical boundary tests; known liquidity observation separately labelled',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=old['llm_policy']['llm_calls'];m['dataset'].update(name='workflow-literal-quote-handoff-contracts',version='20261015-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));put(A/'실험/manifest.json',m)
base=read(D/'baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
cmd=['.venv/bin/python','06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
for n in base['manifest']['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0800/connected/snapshot';prior=R/read(P/'freeze.json')['code_root']
for p in prior.rglob('*'):
 if p.is_file() and '__pycache__' not in p.parts:
  t=C/p.relative_to(prior);t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,t)
for n in ('repin.py','freeze.py','audit_pinned.py','run_tests.py','live.py','replay.py','ledger.py','ui_check.py','test_task_context.py','test_handoff_orchestration.py','test_handoff_restart.py','test_handoff_publication_deadline.py','test_direct_request_handoff.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0799'/n).read_text().replace('0799','0800').replace('workflow-handoff-task-context','workflow-literal-request-quotes')
 (R/'06_TOOLS/EXPERIMENTS/adr_0800'/n).write_text(s)
print('Reserved ADR0800; MAIN73 controls and completed ADR0799 candidate isolated')
