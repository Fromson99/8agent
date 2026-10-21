from pathlib import Path
import hashlib,json,subprocess,sys,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0912-answer-first-user-followup';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
criteria={'hypothesis':'Hand acquired verified originals directly to the existing ASSESS before optional navigation; publish supported current-question claims with explicit gaps, deferring extra investigation to user follow-up. Investigate bounded concrete gaps if no supported current-question claims exist.',
 'success':['Contract/API checks preserve exact source, ACL, hash, state, retry, duplicate and follow-up behavior','Known initial CM questions return nonempty cited answers without speculative assessment reentry when supported claims exist','Same-session follow-up is judged against its new question and can acquire additional sources; prior originals/history remain available','Candidate aggregate initial-request call count is lower than paired baseline; report time without causal certification'],
 'failure':['Fabricated delivery/adoption or sufficiency','Evidence/ACL/hash/state/budget regression','No supported claims published as a successful answer','Resource ceiling breached'],
 'contract':'Opt-in answer_first flag, modern ordinary RAG only; workflow child source-return unchanged. After a complete selected read, verify canonical evidence and hand a character-bounded original pack to ASSESS, without pretending navigator received it. Persist material/question hash to avoid same-pack repeated assessment within an investigation. ASSESS owns at most one schema repair; existing SELECT reentry owner and budget only when no supported claims. Preserve all unresolved gaps and partial status.',
 'evaluation':'Known CM001 and CM033 in-sample; CM001 follow-up asks exclusions without gold. Baseline then candidate, each with the same two scenarios. One run per scenario. Synthetic contracts use actual ASGI API.',
 'limits':{'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'min_disk_gib':10,'model_calls_per_request':40,'wall_seconds_per_request':1800,'max_live_attempts_per_scenario':1},
 'order':['baseline','answer-first'],'reruns':'No adaptive rerun or product change after first live execution; a new candidate requires new ADR.','active_main_changed':False,'genos_access':False}
put(D/'criteria.json',criteria)
f=read(R/'04_EXPERIMENTS/ADR/ADR-0908-reference-context-continuity/artifacts/design/freeze.json');cm=read(R/f['candidate']['manifest_path']);names=[x['target_path'] for x in cm['files']]
names+=['02_BACKEND/semantic_runtime/preparation_progress.py','02_BACKEND/semantic_runtime/process_trace.py'];names=sorted(set(names))
put(D/'working-before.json',{n:sha(R/n) for n in names})
drift=[n for n in names if not (R/f['code_root']/n).exists() or sha(R/n)!=sha(R/f['code_root']/n)]
old=read(R/'04_EXPERIMENTS/ADR/ADR-0909-reference-context-charter-trace/artifacts/design/baseline.json');put(D/'baseline.json',{'pointer':old['pointer'],'active_release':old['active_release'],'manifest':old['active_release'],'parent_code_root':f['code_root'],'current_drift_from_parent':drift,'controls':'Both arms include the same current unrelated Oracle/warmup logging changes; only compact decision/return semantics differ.'})
cases=read(R/'04_EXPERIMENTS/ADR/ADR-0895-committed-answer-consistency/artifacts/design/cases.json')
cases=[c for c in cases if c['id'] in ('cm-001','cm-033')]
for c in cases:
 c['turns']=[{'id':c['id'],'question':c['question']}]
 if c['id']=='cm-001':c['turns'].append({'id':'cm-001-followup','question':'그럼 이 의무보유에서 제외되는 경우는 무엇인가요?'})
put(D/'cases.json',cases)
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='initial request model calls and supported limited-answer follow-up contract',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'baseline','role':'candidate','derived_from':['ADR-0908-experiment-v1/retained'],'changes':'Current working code, plus independently recorded logging drift from parent. No new navigation change.','controls':'Same source generation/profile/model and single-worker instrumentation.'},{'id':'answer-first','role':'candidate','derived_from':['baseline'],'changes':criteria['hypothesis'],'controls':'All other baseline code and data frozen identically.'}]
m['runs'][0].update(arm_ids=['baseline','answer-first'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='cm-answer-first-followup',version='20261019-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':6,'max_calls':240,'temperature':0}]
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'selected','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'cited','kind':'present','parent_stage_ids':['selected']}];m['design']['retrieval_stage_plan']['stages_by_arm']={a:plans for a in criteria['order']}
m['retrieval_accounting']['not_applicable_reason']='Acquired/selected/cited accounting; approved legal gold and search recall are not measured.';m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
for arm in criteria['order']:
 cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
 for n in names:cmd+=['--source',n]
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
print('Prospective criteria frozen, two isolated 714-file snapshots, shared data; drift:',drift)
