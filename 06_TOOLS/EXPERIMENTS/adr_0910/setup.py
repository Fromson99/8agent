from pathlib import Path
import hashlib,json,subprocess,sys,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0910-explicit-navigation-intent';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
criteria={'hypothesis':'Explicit CONTINUE/FINALIZE intent in the existing single compact decision and a concrete resume_action on RETURN_TO reduce explanation/action drift; content-based return receipts prevent unchanged-state return chains without adjudicating sufficiency.',
 'success':['Finite contracts pass for explicit intent/action conflict, one repair, persistent repeat failure, legitimate continued research and partial FINISH, return plan, no-progress return filtering, new-evidence reopening, ACL/hash/state and real API consumers', 'Known public candidate request returns a nonempty answer with exact original spans and no repeated RETURN_TO without content progress', 'No new always-on model call; investigate sufficiency and legal relevance remain model judgments'],
 'failure':['Any evidence/ACL/hash/state/budget regression','Returning deletes originals, marks gaps resolved, or claims sufficiency without model judgment','Resource ceiling breached'],
 'performance':'Prospectively fixed current baseline then candidate, one request each. Record call counts and wall/model/gc times; target candidate <= baseline calls and wall time, but stochastic n=1 is exploratory not a speed certification.',
 'contract':'intent is an explicit independently generated enum, validated against choice; never derive intent from reason keywords. RETURN_TO requires an offered resume_action. Successful return records content progress facts; a subsequent unchanged return is unavailable and rejected if forged. Existing output.bounded_decision owns at most one repair with the same view; existing finalization handles exhaustion.',
 'evaluation':'Known charter question, in-sample probe; no legal gold or independent evaluator. Synthetic software checks also use a real API entry with scripted transport.',
 'limits':{'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'min_disk_gib':10,'model_calls_per_arm':40,'wall_seconds_per_arm':1800,'max_live_attempts_per_arm':1},
 'order':['baseline','intent'],'reruns':'No adaptive live rerun or product edits after first execution. Failures preserved; follow-up requires new ADR.', 'active_main_changed':False,'genos_access':False}
put(D/'criteria.json',criteria)
f=read(R/'04_EXPERIMENTS/ADR/ADR-0908-reference-context-continuity/artifacts/design/freeze.json');cm=read(R/f['candidate']['manifest_path']);names=[x['target_path'] for x in cm['files']]
names+=['02_BACKEND/semantic_runtime/preparation_progress.py','02_BACKEND/semantic_runtime/process_trace.py'];names=sorted(set(names))
put(D/'working-before.json',{n:sha(R/n) for n in names})
drift=[n for n in names if not (R/f['code_root']/n).exists() or sha(R/n)!=sha(R/f['code_root']/n)]
old=read(R/'04_EXPERIMENTS/ADR/ADR-0909-reference-context-charter-trace/artifacts/design/baseline.json');put(D/'baseline.json',{'pointer':old['pointer'],'active_release':old['active_release'],'manifest':old['active_release'],'parent_code_root':f['code_root'],'current_drift_from_parent':drift,'controls':'Both arms include the same current unrelated Oracle/warmup logging changes; only compact decision/return semantics differ.'})
put(D/'cases.json',read(R/'04_EXPERIMENTS/ADR/ADR-0909-reference-context-charter-trace/artifacts/design/cases.json'))
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='unchanged-state return repetitions and intent/action contract',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0908-experiment-v1/retained'],'changes':'Current working code, plus independently recorded logging drift from parent. No new navigation change.','controls':'Same source generation/profile/model and single-worker instrumentation.'},{'id':'intent','role':'candidate','derived_from':['baseline'],'changes':criteria['hypothesis'],'controls':'All other baseline code and data frozen identically.'}]
m['runs'][0].update(arm_ids=['baseline','intent'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='user-charter-quorum-intent',version='20261019-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':2,'max_calls':80,'temperature':0}]
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'selected','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'cited','kind':'present','parent_stage_ids':['selected']}];m['design']['retrieval_stage_plan']['stages_by_arm']={a:plans for a in criteria['order']}
m['retrieval_accounting']['not_applicable_reason']='Acquired/selected/cited accounting; approved legal gold and search recall are not measured.';m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
for arm in criteria['order']:
 cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
 for n in names:cmd+=['--source',n]
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
print('Prospective criteria frozen, two isolated 714-file snapshots, shared data; drift:',drift)
