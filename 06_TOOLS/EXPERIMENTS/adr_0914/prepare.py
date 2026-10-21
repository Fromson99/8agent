from pathlib import Path
import json,hashlib,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0914-answer-first-context-followup';P=R/'04_EXPERIMENTS/ADR/ADR-0912-answer-first-user-followup';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
c={'hypothesis':'Answer-first retains governing ancestor clauses with each acquired read; verified current-question claims are returned without speculative extra research. Same-subject follow-ups prefer an existing goal and preserve prior evidence/history, while genuinely independent questions may start a new goal.',
 'success':['Exact canonical originals and record/source identity preserved, including ancestor context; over-budget bundles defer to existing paginated investigation','Supported partial answer, no-claim bounded reentry, one repair/repeated failure, duplicate and current session contracts pass','CM001 and CM033 return nonempty cited answers with fewer initial calls than frozen ADR0913 baseline; no general speed certification','CM001 exclusion follow-up returns an answer in the same goal, with verified prior evidence reuse and additional investigation if needed'],
 'failure':['Evidence/ACL/hash/state/budget regression','Unknown delivery/adoption represented as verified','Follow-up asks a different topic but host forces old goal','Resource ceiling'],
 'limits':{'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'model_calls_per_request':40,'wall_seconds_per_request':1800,'attempts_per_scenario':1},
 'evaluation':'Finite technical contracts plus two financial_team/public-only scenarios: CM001 with same-session follow-up; separate CM033. All known in-sample. Historical ADR0913 baseline retained, not a contemporaneous paired trial.',
 'failure_owner':'Canonical source verification fails closed, never model-repaired. Existing bounded_decision owns one same-context repair. Existing assessment reentry owner/budget only when no supported claims. No new verifier model. Existing memory resolver and command checker own semantic follow-up selection.',
 'retries':'No adaptive live rerun or product change after first call; preserve failed/partial outcomes in this ADR.','active_main_changed':False,'genos_executed':False}
put(D/'criteria.json',c)
for n in ('baseline.json','cases.json'):shutil.copy2(R/'04_EXPERIMENTS/ADR/ADR-0913-answer-first-financial-scope/artifacts/design'/n,D/n)
b=read(P/'artifacts/design/answer-first-binding.json');C=R/b['code_root'];names=sorted(read(P/'artifacts/design/working-before.json'))
put(D/'working-before.json',{n:sha(R/n) for n in names});put(D/'parent-drift.json',[{'path':n,'parent':sha(C/n),'working':sha(R/n)} for n in names if sha(C/n)!=sha(R/n)])
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['design'].update(hypothesis=c['hypothesis'],primary_metric='governing context continuity and answer-first follow-up',success_criteria=c['success'],failure_criteria=c['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'retained','role':'candidate','derived_from':['ADR-0912-experiment-v1/answer-first'],'changes':c['hypothesis'],'controls':'Same model, public financial team, source generation and resource policy; parent working drift recorded separately.'}]
m['runs'][0].update(arm_ids=['retained'],selection_rule=c['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='cm-answer-first-context-followup',version='20261019-r1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':3,'max_calls':120,'temperature':0}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'retained':[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'selected','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'cited','kind':'present','parent_stage_ids':['selected']}]}
m['retrieval_accounting']['not_applicable_reason']='Acquired/selected/cited accounting; no legal gold or recall evaluation.';m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None);put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','retained','--experiment-id',m['experiment_id'],'--arm-id','retained','--run-id','run-001']
for n in names:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
S=R/'02_BACKEND/lawrag/research/candidates/adr_0914/retained/snapshot'
products=['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json']+['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('law_candidates','law_navigation','evidence_inventory','completion_execution')]
for n in products:
 assert sha(R/n)==read(P/'artifacts/design/working-before.json')[n],'concurrent product edit '+n
 shutil.copy2(C/n,S/n)
put(D/'inherited-products.json',products)
print('Reserved candidate, exact parent answer-first deltas retained; unrelated working changes preserved')
