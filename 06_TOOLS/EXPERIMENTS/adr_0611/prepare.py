import copy,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def put(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tool(*args):
 p=subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),'adr_candidate.py',*args],cwd=R,capture_output=True,text=True)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
cm=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0494-source-workflow-other-cm/product-cases.json').read_text());q={c['case_id']:c['question'] for c in cm['cases']}
def turns(session,texts):return [{'session_id':session,'question':t} for t in texts]
cases=[{'case_id':'cm-038-chain','base_case_id':'cm-038','turns':turns('CM38',[
q['cm-038'],
'방금 질문은 주주총회에 대한 보고를 뜻했어. 보고받는 기관을 주주총회로 정정해서 다시 판단해줘.',
'첫 정정도 잘못됐어. 이사회 및 감사에 대한 보고로 정정해서 다시 판단해줘.',
'두 번째 정정이 틀렸어. 첫 번째 정정 직후의 보고 대상 조건으로 돌아가줘.',
'이제 최초 질문 때의 범위로 돌아가줘. 정정 때 추가한 보고 대상 조건을 없애고 최초 질문 전체에 답해줘.',
'지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘.',
'이 질문을 최초부터 어떤 정정을 거쳐 고쳤는지, 현재 왜 이 결론인지 실제 기록과 근거를 설명해줘.',
'현재 조건과 결론은 유지하고 최종 답변만 표로 써줘.'
])+[{'session_id':'CM38-NEW','question':q['cm-038']+' 이전 대화에서 내가 최종 확인한 경험을 활용해줘.'}]+turns('CM38-NEW',[
'방금 질문에서 보고받는 기관을 이사회 및 감사로 정정해줘.',
'방금 정정이 잘못됐어. 이 대화의 최초 질문 때 범위로 복원해줘.',
'지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘.'
])}, {'case_id':'cm-003-chain','base_case_id':'cm-003','turns':turns('CM03',[
q['cm-003'],
'방금 질문의 재무적투자자는 벤처금융 또는 전문투자자에 해당하는 경우야. 그 자격 조건을 추가해서 다시 판단해줘.',
'그 정정이 잘못됐어. 최초 질문에 없던 자격 조건을 추가하지 말고 최초 질문 때 조건으로 되돌려줘.',
'지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘.',
'이 질문의 최초 조건과 정정, 다시 최초로 복원한 과정을 실제 기록에 근거해 설명해줘.',
'지금 조건과 결론을 유지하고 최종 답변만 표로 써줘.'
])+[{'session_id':'CM03-NEW','question':q['cm-003']+' 이전 대화에서 내가 최종 확인한 경험을 활용해줘.'}]}]
put(D/'inputs.json',cases)
gold0=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0494-source-workflow-other-cm/gold-cases.json').read_text())
gold={'cm-038-chain':{'history_turns':[7],'presentation_turns':[8],'confirm_turns':[6,12],'reuse_turns':[9],'restore_pairs':[[4,2],[5,1],[11,9]],'legal_turns':{'1':'original','2':'shareholder','3':'board_auditor','4':'shareholder','5':'original','9':'original','10':'board_auditor','11':'original'},'references':{'original':gold0['cases'][1]['reference_answer'],'shareholder':'주주총회에 대한 보고는 대표자가 해야 하며 내부회계관리자에 대한 위임 단서의 대상이 아니다.','board_auditor':'대표자가 필요하다고 판단하는 경우 이사회 및 감사에 대한 보고는 내부회계관리자가 하도록 할 수 있다.'},'decisive_source_ids':gold0['cases'][1]['decisive_source_ids']},'cm-003-chain':{'history_turns':[5],'presentation_turns':[6],'confirm_turns':[4],'reuse_turns':[7],'restore_pairs':[[3,1]],'legal_turns':{'1':'original','2':'qualified','3':'original','7':'original'},'references':{'original':gold0['cases'][0]['reference_answer'],'qualified':gold0['cases'][0]['reference_answer']},'decisive_source_ids':gold0['cases'][0]['decisive_source_ids']}}
put(D/'gold.json',gold)
m=json.loads((A/'실험/manifest.json').read_text());parent=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/실험/manifest.json').read_text())
m['lineage']['hypothesis_delta']='Fix typed method admission, semantic invalidation and source-bound history explanation; compare unchanged parent and repaired candidate on real CM questions and public source corpus.'
m['design'].update(hypothesis='Registered memory methods restrict presentation/explanation authority; changes in actual state or upstream judgments control retirement, and history is rendered from immutable events. This prevents explanation from destroying confirmed experience while preserving correction/reuse.',primary_metric='Per-turn completion, confirmation retention after explanation/presentation, exact restore facts, immutable history references, reuse and source-supported CM answer agreement',success_criteria='All candidate turns complete; confirmation remains active through history/presentation; all four restorations and three reuse requests succeed; no history mutation/fabricated event; legal agreement no worse than baseline; <=350 calls/arm and one transport retry per transient failure.',failure_criteria='Any unauthorized mutation, missing preserved confirmation, bad origin, reuse failure, unrepaired product error or legal regression. Report engine/data/source failures separately.',criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'BASELINE','role':'candidate','derived_from':['ADR-0610-experiment-v1/REPLAY'],'changes':'None; exact completed nine-file candidate','controls':'Same nineteen CM-based turns, public scope, source generation, model and transport as GUARDED'},{'id':'GUARDED','role':'candidate','derived_from':['BASELINE'],'changes':'Typed memory method admission; state-based knowledge retirement; immutable event history answer; history-aware compose/check; bounded correction stage validation','controls':'Same retrieval implementation and public source generation'}]
m['design']['transport']=copy.deepcopy(parent['design']['transport']);m['design']['limits']=['Nineteen forced turns derived from two existing CM golden questions; not all61 CM, not held-out.','User correction utterances are experiment-authored; base questions and law sources are actual stored CM data.','Only public145 document scope; internal documents excluded, immutable export flag retained.','Memory method catalogue is a scoped control layer, not full legal concept/relationship ontology enforcement.','Same model performs answer and offline judgment; automated evaluation is not human legal certification.','Order BASELINE then GUARDED, case order CM038 then CM003; no randomization; histories and model calls isolated by arm.','MAIN and GENOS unchanged.']
plan=parent['design']['retrieval_stage_plan']['stages_by_arm']['REPLAY'];m['design']['retrieval_stage_plan']={**parent['design']['retrieval_stage_plan'],'stages_by_arm':{a:plan for a in ('BASELINE','GUARDED')}}
m['llm_policy']=copy.deepcopy(parent['llm_policy']);m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0},{'role':'judge','class':'offline_evaluator','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['BASELINE','GUARDED'],'selection_rule':'All19 frozen turns per arm, BASELINE then GUARDED. Offline answers judged only after both product arms finish.','status':'planned','artifact_path':str((A/'artifacts/run-001/result.json').relative_to(R)),'sha256':'PENDING'}]
m['dataset'].update(name='real-cm003-cm038-memory-corrections',version='v1',frozen_source=str((D/'inputs.json').relative_to(R)),sha256=sha(D/'inputs.json'),legal_version_checked=True,reference_version_checked=True)
m['retrieval_accounting']=copy.deepcopy(parent['retrieval_accounting']);m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((A/'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)),sha256='PENDING');m['retrieval_accounting']['not_applicable_reason']='Retrieval implementation unchanged; actual final consumption is measured in both arms.'
for k in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]={a:None for a in ('BASELINE','GUARDED')}
put(A/'실험/manifest.json',m)
old=R/'02_BACKEND/lawrag/research/candidates/adr_0610/forced-turn-memory/candidate.json';c=json.loads(old.read_text())
for arm,ident in [('BASELINE','baseline-memory'),('GUARDED','method-guarded-memory')]:
 args=['snapshot','--adr',str(A.relative_to(R)),'--experiment-id',m['experiment_id'],'--candidate-id',ident,'--arm-id',arm,'--run-id','run-001']
 for f in c['files']:
  if f['upstream_state']=='present':args.extend(['--source',f['target_path']])
 tool(*args);base=R/'02_BACKEND/lawrag/research/candidates/adr_0611'/ident;cp=base/'candidate.json'
 for f in c['revisions'][-1]['files']:
  target=f['snapshot_path'].split('/snapshot/',1)[1];dest=base/'snapshot'/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['frozen_path'],dest)
  if not (R/target).exists():tool('register',str(cp.relative_to(R)),'--target',target,'--upstream-state','absent')
 if arm=='BASELINE':tool('freeze',str(cp.relative_to(R)))
print('Prepared19 turns, two arms, isolated candidates. Candidate implementation and final freeze follow.')
