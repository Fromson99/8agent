from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0779-tool-recovery-main';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
criteria={'scope':'Prospective exhaustive fault classification and safe-recovery policy audit of already implemented P1-P3 plus prior subtree/dependency/tool eligibility fixes; no code changes during this ADR.',
 'primary_matrix':{'choices':37,'causes':['AUTH','INTEGRITY','STATE','UNKNOWN','INTERNAL','DEADLINE','BUDGET','PROPOSAL','TRANSIENT'],'wrappers':['direct','explicit','implicit'],'states':['normal','stale','deadline','cancelled','no_budget','alternative'],'expected_total':5994},
 'required':['All 5994 new exhaustive cause/wrapper/state policy contracts pass','All frozen mandatory regressions pass; four independently reproduced old failures remain exact failures, not passes','Actual runtime modules come from the frozen candidate, no working-runtime fallback','Evidence/ACL/source hash/state/replay/read-spend/publication guards preserved','Selected code files exactly equal tested working bytes, original MAIN62 data and model settings preserved'],
 'failure':'Any primary case failure, new regression, missing expected test, source drift or hidden import blocks promotion.',
 'known_development_results':'Prior 842 passed / 4 existing failed is supplementary evidence, not a fresh holdout.',
 'scope_limit':'Exhaustive finite host protocol audit, not unseen legal/model efficacy. Later P4/P7/P5 and output compression remain deferred.',
 'authorization':'메인에 반영하고 삼성으로 메일쏴줘','external_model_calls':0}
put(D/'criteria.json',criteria)
pointer=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=read(pointer);assert active['generation']==62
base=read(R/active['manifest_path']);put(D/'baseline.json',{'pointer':active,'pointer_sha256':sha(pointer),'manifest':base})
files=set(base['files']);files.update('02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('tool_availability','tool_outcome','tool_policy','tool_execution_receipt'))
for n in files:assert (R/n).is_file(),n
changed=[{'path':n,'selected_before':base['files'].get(n),'working_after':sha(R/n)} for n in sorted(files) if base['files'].get(n)!=sha(R/n)]
put(D/'working-delta.json',{'changes':changed,'reason':'Integrates already developed dependency, source subtree and tool eligibility fixes with tool failure P1-P3. Existing transport/stream/profile/model/data policies retained.'})
checks=read(R/'90_RUNTIME/tool_failure_recovery_20261014/checks.json');put(D/'regression-selection.json',{'tests':checks,'expected_passed':842,'expected_failed':4,'known_failure_receipt':read(R/'07_DOCS/REFERENCE/REPORTS/TOOL_FAILURE_RECOVERY_DESIGN_20261014/IMPLEMENTATION_VALIDATION.json')['baseline_failure_causes']})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='5994 finite host protocol cases pass',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['dataset'].update(name='Exhaustive synthetic tool fault/wrapper/state contracts',version='tool-recovery-qualification-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[];m['runs'][0].update(selection_rule='All prospectively frozen 5994 finite policy states; prior known regressions separately reported',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Synthetic host fault audit; no corpus/model ranking or legal accuracy comparison.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No corpus recall measurement.')
for arm in m['design']['arms']:arm.update(changes='Selected MAIN62 protocol availability only' if arm['id']=='baseline' else criteria['scope'],controls='Identical selected data/model/search profiles; no real model calls')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','recovery','--experiment-id',m['experiment_id'],'--arm-id','recovery','--run-id','run-001']
for n in sorted(files):cmd+=['--source',n]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
print('Prepared',len(files),'serving files;',len(changed),'changes; criteria fixed before evaluation')
