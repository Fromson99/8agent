from pathlib import Path
import json,hashlib,sqlite3,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0755-scoped-gap-public-qualification';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0754-excluded-reference-gap-guidance'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
base=read(P/'artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256'];put(D/'baseline.json',base)
criteria={'scope': 'Unchanged completed754 four fixes: reversible short IDs and lossless cards, request-grounded exploration, scoped heading failure, v8 source-ID bound exact quotations and recorded explicit label correction, compact condition display, single-authoritative content, direct request authority and completed-search progress; gap reentry precedes presentation preference and duplicate proof includes effect/context. Finite offered identity sets bound output lists before reversible transport. Excluded detail is not a missing requested source; required gaps and strict validation retained. No cache changes.', 'required': {'candidate_primary_supported': 2, 'successful_pairs_min': 1, 'input_ratio_max': 0.9, 'calls_delta_max': 2, 'request_seconds_ratio_max': 1.5, 'all_source_acl_state_content_binding': True, 'required_modal_distinctions': True}, 'execution': {'cases': 2, 'requests': 4, 'order': [['H01', 'baseline'], ['H01', 'integrated'], ['H02', 'integrated'], ['H02', 'baseline']], 'no_adaptive_reruns': True, 'model_calls_per_request_max': 40}, 'regression_gate': '145 critical contracts pass; full416 no new failure vs inherited15. Parent frozen identical318 files.', 'performance': 'Only both-arm source-supported pairs count towards input/calls/latency gate. All failures retain costs; no provider fallback or replacing questions.', 'semantic_gate': 'Explicit required permissions/obligations must not be reversed; exceptions maintained. Other semantic omissions recorded separately and do not automatically block promotion. Offline review reads fixed source gold and saved answers only; never changes product context or outputs.', 'rollback': 'Keep MAIN52 if any required gate fails; preserve exact prior pointer, code/data and install backups.', 'authorization': 'User explicitly authorized items1-4 implementation and local MAIN; earlier small external experiments authorized. Only authored public questions and approved65 original documents. Cache excluded.'}
put(D/'criteria.json',criteria)
selections=[('H01', 'article:11dee66e409c225e04dc134e', 'EXACT_DEPOSIT_PROHIBITION_DISCRETION', '금융투자회사의 영업 및 업무에 관한 규정 제3-29조 제3항과 제4항만 기준으로 설명해 주세요. 유사해외통화선물거래의 거래단위당 위탁증거금 최저액과 그 사용 제한, 투자자 예탁자산평가액이 유지증거금에 미달할 때 회사가 할 수 있는 거래, 유지증거금의 최저 기준을 구분해 주세요. 의무·금지와 선택 가능한 조치를 구별하고, 인용된 다른 법령의 예치·신탁 세부 용도는 확장하지 말아 주세요.'), ('H02', 'article:156659ad50c11f9d4d562f52', 'HEADING_COMPANY_INSPECTOR', '상법의 회사의 업무·재산상태 검사 규정에서, 주주가 법원에 검사인 선임을 청구할 수 있는 요건, 검사인의 조사 후 보고 의무, 법원이 주주총회 소집을 명할 수 있는 경우, 이사와 감사의 조사·보고 의무를 설명해 주세요. 청구·명령의 허용과 보고 의무를 구분하고, 준용된 제310조의 세부 내용은 추가로 다루지 말아 주세요.')]

excluded=set(read(D/'excluded-source-ids.json'));assert not read(D/'exposure-scan.json')['failures'];allowed=set(read(R/base['manifest']['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
db=sqlite3.connect((R/base['manifest']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
cases=[];gold=[]
for cid,sid,kind,question in selections:
 assert sid not in excluded
 source=json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0]);assert source['document_id'] in allowed
 cases.append({'case_id':cid,'kind':kind,'question':question})
 gold.append({'case_id':cid,'source_id':sid,**{k:source[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}})

db.close();put(D/'dataset.json',{'cases':cases,'regression_cases':[],'repeat_cases':[],'product_gold':False,'source_generation':base['manifest']['data_path']});put(D/'gold.json',{'product_visible':False,'version':'Pinned selected public originals','cases':gold})
put(D/'selection-audit.json',{'primary_roots':[x[1] for x in selections],'prior_excluded':len(excluded),'no_overlap':True,'selection_before_results':True,'qualification_scope':'Two unexposed primary article roots, two different documents, no CM export. Secondary dependencies may have previous exposure.'})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Source-backed native completion and strict source/state/content invariants',success_criteria=criteria['required'],failure_criteria='Any required invariant fails: keep MAIN52',criteria_frozen_before_run=True,repeats=1)
for arm in m['design']['arms']:
 arm.update(changes='Selected MAIN52 unchanged' if arm['id']=='baseline' else criteria['scope'],controls='Same approved65 sources, dataset generation, model identity, total budgets; fresh process; final same-epoch recovery fix inherited')
 if arm['id']=='integrated':arm['derived_from']=['ADR-0754-experiment-v1/integrated']
 if arm['id']=='baseline':arm.update(derived_from=[],source_binding={'path':str((D/'baseline.json').relative_to(R)),'sha256':sha(D/'baseline.json'),'source_arm':'ADR-0728-experiment-v1/integrated','replica_of_selected_release':True})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['dataset'].update(name='Two new public primary roots',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Exact4 requests in criteria.execution.order; no adaptive repeats or replacement',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a['id']:stages for a in m['design']['arms']}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
m['questions']=[]
headings=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for n,c in enumerate(cases,1):
 filename=f'질문-{n:03}-{c["case_id"]}.md';p=A/'실험'/filename
 texts=['ADR0755/run-001; '+('predeclared repeated request of '+c['repeat_of'] if c.get('repeat_of') else 'new primary root paired MAIN52/compact'),c['question'],'Offline design/gold.json; never read by product runner.', '### 회수·탈락 단계 원장 — run·arm별\n\nNative API, public65 scope, immutable generation; result and ledger hold actual views.', 'Exact provider request/response/usage retained per case; Qwen3.8 Parasail FP8 none no fallback.', 'Same audited client for all phases and at most one decision repair per epoch/presentation; total40.', 'No judge model. Independent saved-original review. No adaptive retries or repeated sessions.', 'Results not observed at freeze; finalize after all four requests.']
 p.write_text('# '+c['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headings,texts),1))+'\n');m['questions'].append({'number':n,'case_id':c['case_id'],'file':filename,'sha256':sha(p)})
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for name in sorted(set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0754/integrated';pcm=read(parent/'candidate.json');rev=pcm['revisions'][-1];src=parent/'revisions'/rev['revision_id']/'snapshot';child=R/'02_BACKEND/lawrag/research/candidates/adr_0755/integrated'
for row in pcm['files']:
 name=row['target_path'];target=child/'snapshot'/name;target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src/name,target)
 if name not in set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}:
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(child),'--target',name,'--upstream-state','present' if (R/name).is_file() else 'absent'],check=True,stdout=subprocess.DEVNULL)
put(D/'parent-inheritance.json',{'parent':'ADR-0754-experiment-v1/integrated','manifest_sha256':sha(parent/'candidate.json'),'revision':rev['revision_id'],'serving_code_changes':0,'files':{x['target_path']:sha(src/x['target_path']) for x in pcm['files']}})
for name,v in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,v)
print('Frozen scope selected; copied completed implementation unchanged')

shutil.copy2(P/'artifacts/contract-result.json',A/'artifacts/contract-result.json')
assert read(A/'artifacts/contract-result.json')['strict_success']
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(child)],check=True,stdout=subprocess.DEVNULL)
put(D/'semantic-review-contract.json',{'cases':{x[0]:{'source_id':x[1],'question':x[3]} for x in selections},'required':'Review explicit requested permissions/duties and exception polarity against immutable gold; semantic detail errors separate; product context and output never changed','review_output':'artifacts/run-001/semantic-review.json','gold_product_visible':False})
