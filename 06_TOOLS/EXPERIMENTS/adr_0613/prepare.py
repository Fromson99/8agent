import copy,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0613-cm-memory-current-state-authority';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True);P=R/'04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery'
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
for name in ['inputs.json','gold.json','source-binding.json','source-coordinates.json']:shutil.copyfile(P/'artifacts/design'/name,D/name)
m=json.loads((A/'실험/manifest.json').read_text());p=json.loads((P/'실험/manifest.json').read_text())
m['lineage']['hypothesis_delta']='Repair duplicate source choices without bypassing scope/limits; use current facts exclusively for current legal review; expose the actual restart-to-COMPOSE execution contract to command checker.'
m['design']=copy.deepcopy(p['design']);m['design'].pop('code_isolation',None)
m['design'].update(hypothesis='Safe duplicate coalescing and explicit current-state/execution authority eliminate source-selection aborts and verifier confusion about prior corrections and entry stages.',success_criteria='All19 REPAIRED turns meet expected statuses; all4 restore pairs and both reuse turns succeed; both histories are exact and read only; both table turns preserve current confirmed experience; legal agreement no worse than fresh BASELINE; <=350 physical requests per arm; no scope or generation escapes.',criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'BASELINE','role':'candidate','derived_from':['ADR-0612-experiment-v1/RECOVERED'],'changes':'Exact completed ADR0612 RECOVERED ten-file code and format-recovery wrapper','controls':'Same19 turns/public145 source generation/model/format retry and grading'},{'id':'REPAIRED','role':'candidate','derived_from':['BASELINE'],'changes':'Duplicate valid source ID coalescing; current-fact-only answer/check payload; current-state and general-rule vs applied-fact semantics; explicit restart continuation contract to command checker','controls':'No gold or CM-specific source ID injected, source retrieval unchanged'}]
m['design']['limits']=[x.replace('RECOVERED','REPAIRED') for x in p['design']['limits']]
m['design']['limits']=[x for x in m['design']['limits'] if not x.startswith('Products use isolated')]+['Concurrent isolated arms with sequential19 turns per arm. Both inherit one format repair and one transient transport retry; max4 physical requests per logical invoke. No retry after frozen outcomes.','Four restoration comparisons use response state exactly as ADR0612. Separate post-run DB diagnosis never replaces frozen scores.']
plan=p['design']['retrieval_stage_plan']['stages_by_arm']['RECOVERED'];m['design']['retrieval_stage_plan']['stages_by_arm']={a:plan for a in ['BASELINE','REPAIRED']}
m['llm_policy']=copy.deepcopy(p['llm_policy']);m['dataset']=copy.deepcopy(p['dataset']);m['dataset']['frozen_source']=str((D/'inputs.json').relative_to(R));m['dataset']['version']='v3-current-state-authority-same-inputs'
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['BASELINE','REPAIRED'],'selection_rule':'Concurrent isolated same19 turns; offline gold only after both products complete','status':'planned','artifact_path':str((A/'artifacts/run-001/result.json').relative_to(R)),'sha256':'PENDING'}]
m['retrieval_accounting']=copy.deepcopy(p['retrieval_accounting']);m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((A/'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)),sha256='PENDING')
for k in ['before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']:m['retrieval_accounting'][k]={a:None for a in ['BASELINE','REPAIRED']}
put(A/'실험/manifest.json',m)
cp=R/'02_BACKEND/lawrag/research/candidates/adr_0612/bounded-memory/candidate.json';c=json.loads(cp.read_text())
def tool(*args):
 x=subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),'adr_candidate.py',*args],capture_output=True,text=True);assert x.returncode==0,x.stdout+x.stderr
for arm,ident in [('BASELINE','baseline-memory'),('REPAIRED','current-state-memory')]:
 args=['snapshot','--adr',str(A.relative_to(R)),'--experiment-id',m['experiment_id'],'--candidate-id',ident,'--arm-id',arm,'--run-id','run-001']
 for f in c['files']:
  if f['upstream_state']=='present':args+=['--source',f['target_path']]
 if arm=='REPAIRED':args+=['--source','02_BACKEND/semantic_runtime/legal_agent/source_selection.py']
 tool(*args);base=R/'02_BACKEND/lawrag/research/candidates/adr_0613'/ident
 for f in c['revisions'][-1]['files']:
  target=f['snapshot_path'].split('/snapshot/',1)[1];dest=base/'snapshot'/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['frozen_path'],dest)
  if not (R/target).exists():tool('register',str((base/'candidate.json').relative_to(R)),'--target',target,'--upstream-state','absent')
 if arm=='BASELINE':tool('freeze',str((base/'candidate.json').relative_to(R)))
for name in ['binding.py','run.py','grade.py','contracts.py','native_contracts.py','format_recovery.py','freeze.py','finalize.py','report.py','audit.py','state_audit.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0612'/name).read_text().replace('0612','0613').replace('cm-memory-bounded-recovery','cm-memory-current-state-authority').replace('RECOVERED','REPAIRED').replace('bounded-memory','current-state-memory').replace('LEGAL_AGENT_CM_MEMORY_RECOVERY_20261002','LEGAL_AGENT_CM_MEMORY_FINAL_20261002')
 if name=='run.py':
  s=s.replace("if arm=='REPAIRED':return bounded_generate", "if arm in ('BASELINE','REPAIRED'):return bounded_generate")
  s=s.replace("    native=load(","    if arm=='REPAIRED':load('semantic_runtime.legal_agent.source_selection',paths['02_BACKEND/semantic_runtime/legal_agent/source_selection.py'])\n    native=load(")
 (R/'06_TOOLS/EXPERIMENTS/adr_0613'/name).write_text(s)
print('ADR613 prepared; no calls yet.')
