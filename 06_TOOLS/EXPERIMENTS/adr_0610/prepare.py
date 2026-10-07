"""Predeclare new synthetic turns, register an unchanged completed candidate."""
import copy,hashlib,json,shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
P=R/'04_EXPERIMENTS/ADR/ADR-0609-native-memory-reuse-purpose-separation'
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tool(*args):subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),'adr_candidate.py',*args],cwd=R,check=True,capture_output=True)
def turn(s,q):return {'session_id':s,'question':q,'document_ids':['d']}
inputs=[{'case_id':'mixed-corrections','turns':[
turn('M1','모의승인규정 제1조의 승인 절차를 알려줘. 대상은 국내야.'),
turn('M1','별도의 두 번째 질문이야. 모의승인규정 제1조에서 해외 대상의 승인 절차를 알려줘.'),
turn('M1','첫 번째 질문만 정정할게. 대상은 국내가 아니라 해외야. 두 번째 질문은 유지해.'),
turn('M1','첫 번째 질문의 첫 정정이 잘못됐어. 그 질문을 최초에 말했던 대상 조건으로 되돌려 판단해줘.'),
turn('M1','방금 한 두 번째 정정도 잘못됐어. 첫 번째 질문에서 첫 정정 직후의 대상 조건으로 다시 돌아가줘.'),
turn('M1','최종적으로 첫 번째 질문의 대상은 최초 질문 때 조건이 맞아. 정정들을 거슬러 최초 대상 조건으로 복원해줘. 두 번째 질문은 그대로야.'),
turn('M1','두 번째 질문의 조건과 결론은 그대로 두고 최종 답변만 표로 써줘.'),
turn('M1','첫 번째 질문은 지금 최종 답이 맞아. 이 질문의 최종 정답 루트를 저장해줘.'),
turn('M1','첫 번째 질문에서 왜 그 결론이 됐는지, 어떤 정정을 거쳐 어떤 근거를 채택했는지 설명해줘.'),
turn('M2','모의승인규정 제1조 승인 절차를 알려줘. 대상은 국내야. 이전 대화에서 내가 최종 확인한 경험을 활용해줘.'),
turn('M2','방금 질문의 대상은 해외가 맞아. 국내로 들고 온 것은 잘못됐으니 해외로 다시 판단해줘.'),
turn('M2','지금 해외 대상의 최종 답이 맞아. 이 질문의 정답 루트를 저장해줘.'),
turn('M3','새 대화야. 모의승인규정 제1조 국내 대상의 승인 절차를 이전에 최종 확인한 경험으로 알려줘.')
]}, {'case_id':'stage-reentry','turns':[
turn('S1','모의승인규정 제1조의 국내 대상 승인 절차를 알려줘.'),
turn('S1','그 질문에 조건을 추가해줘. 대상은 국내이고 긴급 사건이야. 긴급 사건의 예외까지 고려해 다시 판단해줘.'),
turn('S1','현재 국내·긴급 사건 조건은 유지해. 검색계획을 고쳐서 검색어를 "승인 절차"와 "긴급 사건 별도 예외" 두 개로 바꾸고 원문을 찾아 다시 판단해줘.'),
turn('S1','현재 검색 결과의 원문을 다시 읽는 단계부터 재검토해줘. 목적과 국내·긴급 조건, 검색계획은 유지해.'),
turn('S1','현재 읽은 원문 중 근거를 선정하는 단계부터 다시 해줘. 목적과 국내·긴급 조건, 검색계획은 유지해.'),
turn('S1','긴급 조건을 추가한 정정이 잘못됐어. 첫 질문 최초의 대상 조건으로 돌아가고 긴급 조건은 제거해줘. 지금 검색계획은 유지해.'),
turn('S1','이 질문을 최초부터 어떻게 고쳤고 현재 왜 이 결론인지 근거와 함께 설명해줘.'),
turn('S1','현재 조건과 결론을 그대로 두고 최종 답변만 표로 써줘.'),
turn('S1','이 질문은 지금 최종 답이 맞아. 최종 정답 루트를 저장해줘.')
]}]
put(D/'inputs.json',inputs)
# Offline expectations are deliberately not passed to the application/model.
status=['READY','READY','READY','READY','READY','READY','READY','STORED','READY','REUSED','READY','STORED','REUSED']
gold={
'mixed-corrections':{'statuses':status,'procedure':['A','B','B','A','B','A','B',None,None,'A','B',None,'A'],'executed':{'3':['ASSESS','COMPOSE'],'4':['ASSESS','COMPOSE'],'5':['ASSESS','COMPOSE'],'6':['ASSESS','COMPOSE'],'7':['COMPOSE'],'10':['COMPOSE'],'11':['ASSESS','COMPOSE'],'13':['COMPOSE']},'targets':{str(i):['M1',2 if i in (2,7) else 1] for i in range(1,10)},'inspect_turns':[9], 'isolation_turns':[3,4,5,6,7], 'restore_turns':{'4':1,'5':3,'6':1},'unconfirmed_turns':[1,2,3,4,5,6,7]},
'stage-reentry':{'statuses':[['READY','REUSED'],'READY','READY','READY','READY','READY','READY','READY','STORED'],'procedure':['A',None,None,None,None,'A',None,'A',None],'executed':{'2':['ASSESS','COMPOSE'],'3':['PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE'],'4':['READ','SELECT','ASSESS','COMPOSE'],'5':['SELECT','ASSESS','COMPOSE'],'6':['ASSESS','COMPOSE'],'8':['COMPOSE']},'targets':{str(i):['S1',1] for i in range(1,10)},'inspect_turns':[7], 'restore_turns':{'6':1},'table_turns':[8]}
}
gold['mixed-corrections']['targets'].update({'10':['M2',1],'11':['M2',1],'12':['M2',1],'13':['M3',1]});gold['mixed-corrections']['table_turns']=[7]
put(D/'gold.json',gold)
m=json.loads((A/'실험/manifest.json').read_text());p=json.loads((P/'실험/manifest.json').read_text())
m['lineage']['hypothesis_delta']='Unchanged completed candidate: force interleaved goals, correction-of-correction, exact origin restoration, multiple RAG entry stages and saved-route reuse; observe domain-control gaps.'
m['design'].update(hypothesis='The existing prototype maintains correct goal and original-event identity across mixed multi-turn corrections, preserves unaffected goals and reuses only confirmed current bundles. Natural explanation and domain-path enforcement are separately checked and may fail.',primary_metric='Predeclared status, procedure token, exact stage, target, isolation, origin and confirmation checkpoints; not legal semantic accuracy',success_criteria='All 22 turns complete and all frozen checkpoints pass. Explanation turns require nonempty natural answer. Strict domain-control claim additionally requires offered domain path IDs and host receipts, currently absent.',failure_criteria='Any target/origin/state/confirmation/stage mismatch, missing requested explanation, provider abort; absent domain IDs means design not demonstrated',criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'REPLAY','role':'candidate','derived_from':['ADR-0609-experiment-v1/REPAIRED'],'changes':'No product code changes; new synthetic forced-turn inputs, DB snapshots and offline checks','controls':'Exact nine frozen parent candidate files, same synthetic source generation, same pinned model/provider'}]
m['design']['transport']=p['design']['transport'];m['design']['retrieval_stage_plan']=copy.deepcopy(p['design']['retrieval_stage_plan']);m['design']['retrieval_stage_plan']['stages_by_arm']={'REPLAY':p['design']['retrieval_stage_plan']['stages_by_arm']['REPAIRED']}
m['design']['limits']=['Synthetic two-article corpus; in-sample exploratory examples, no improvement or generalization claim.','No implementation of domain-control-v1 proposed catalogue/method/proof gate. Existing reason/concept fields are free text.','No second live baseline arm: byte-identical parent candidate reused on new inputs.','INSPECT answer rendering is a known gap and counted against requested natural explanation, not excused.','Procedure letter checks are not complete semantic legal evaluation.','Current condition changes invalidate ASSESS onward by field mapping; guard-dependency applicability discovery is not implemented.','No MAIN/GENOS deployment.']
m['llm_policy']=copy.deepcopy(p['llm_policy']);m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':'provider default'}]
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['REPLAY'],'selection_rule':'All 22 frozen turns in order; continue model-level failures to observe recovery; abort persistent provider failure','status':'planned','artifact_path':str((A/'artifacts/run-001/result.json').relative_to(R)),'sha256':'PENDING'}]
m['dataset'].update(name='synthetic-forced-multiturn-examples',version='v1',frozen_source=str((D/'inputs.json').relative_to(R)),sha256=sha(D/'inputs.json'),legal_version_checked=True,reference_version_checked=True)
m['retrieval_accounting']=copy.deepcopy(p['retrieval_accounting']);m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((A/'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)),sha256='PENDING')
for k in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]={'REPLAY':None}
put(A/'실험/manifest.json',m)
# Scoped hypothesis is now written; snapshot/register before freezing unchanged bytes.
old=R/'02_BACKEND/lawrag/research/candidates/adr_0609/pure-purpose-memory/candidate.json';c=json.loads(old.read_text())
args=['snapshot','--adr',str(A.relative_to(R)),'--experiment-id','ADR-0610-experiment-v1','--candidate-id','forced-turn-memory','--arm-id','REPLAY','--run-id','run-001']
for f in c['files']:
 if f['upstream_state']=='present':args.extend(['--source',f['target_path']])
tool(*args)
base=R/'02_BACKEND/lawrag/research/candidates/adr_0610/forced-turn-memory';cp=base/'candidate.json'
for f in c['revisions'][-1]['files']:
 target=f['snapshot_path'].split('/snapshot/',1)[1];dest=base/'snapshot'/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['frozen_path'],dest)
 if not (R/target).exists():tool('register',str(cp.relative_to(R)),'--target',target,'--upstream-state','absent')
tool('freeze',str(cp.relative_to(R)));tool('validate',str(cp.relative_to(R)))
print('Prepared 22 frozen-intent turns and unchanged registered candidate; runner freeze follows.')
