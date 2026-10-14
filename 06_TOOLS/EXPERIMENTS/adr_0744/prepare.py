from pathlib import Path
import json,hashlib,sqlite3,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0744-focused-rules-final-qualification';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0743-direct-request-provenance'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
base=read(P/'artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256'];put(D/'baseline.json',base)
criteria={'scope': 'Unchanged completed743 four fixes: reversible short IDs and lossless cards, request-grounded exploration, scoped heading failure, source-quoted v7 modal labels, compact condition display, single-authoritative content, direct request authority and completed-search progress. No cache changes.', 'required': {'candidate_primary_supported': 2, 'successful_pairs_min': 1, 'input_ratio_max': 0.9, 'calls_delta_max': 2, 'request_seconds_ratio_max': 1.5, 'all_source_acl_state_content_binding': True, 'required_modal_distinctions': True}, 'execution': {'cases': 2, 'requests': 4, 'order': [['H01', 'baseline'], ['H01', 'integrated'], ['H02', 'integrated'], ['H02', 'baseline']], 'no_adaptive_reruns': True, 'model_calls_per_request_max': 40}, 'regression_gate': '104 critical contracts pass; full375 no new failure vs inherited15. Parent frozen identical316 files.', 'performance': 'Only both-arm source-supported pairs count towards input/calls/latency gate. All failures retain costs; no provider fallback or replacing questions.', 'semantic_gate': 'Explicit required permissions/obligations must not be reversed; exceptions maintained. Other semantic omissions recorded separately and do not automatically block promotion. Offline review reads fixed source gold and saved answers only; never changes product context or outputs.', 'rollback': 'Keep MAIN52 if any required gate fails; preserve exact prior pointer, code/data and install backups.', 'authorization': 'User explicitly authorized items1-4 implementation and local MAIN; earlier small external experiments authorized. Only authored public questions and approved65 original documents. Cache excluded.'}
put(D/'criteria.json',criteria)
selections=[('H01', 'article:065714f13b48243249d75e69', 'EXACT_OPTIONAL_EXPENSE_DUTY', '소득세법 제31조에 적힌 범위에서 보험차익으로 취득·개량한 자산의 필요경비 산입이 의무인지 선택인지, 보험금을 받은 과세기간에 취득·개량할 수 없을 때의 기한, 사용계획서 제출 의무와 제출처, 총수입금액에 다시 산입하는 두 사유를 설명해 주세요. 대통령령의 세부 절차까지는 확장하지 말아 주세요.'), ('H02', 'article:06d92d992dc11de471e42028', 'HEADING_BODY_DUTY_PERMISSION_PROHIBITION', '교육자료를 준비 중입니다. 자본시장과 금융투자업에 관한 법률의 의결권 대리행사 권유 규정에서 상대방에게 교부할 서류, 위임장 용지에 표시할 수 있어야 하는 사항, 공공적 법인의 주식에 대해 권유할 수 있는 주체, 그리고 상대방 의사에 반한 의결권 행사 가능 여부를 설명해 주세요. 교부 의무·권유 가능 주체의 제한·반대 의사 행사 금지를 구분하고, 권유 행위의 유형이나 대통령령 세부 사항은 추가로 열거하지 말아 주세요.')]

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
 if arm['id']=='integrated':arm['derived_from']=['ADR-0743-experiment-v1/integrated']
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
 texts=['ADR0744/run-001; '+('predeclared repeated request of '+c['repeat_of'] if c.get('repeat_of') else 'new primary root paired MAIN52/compact'),c['question'],'Offline design/gold.json; never read by product runner.', '### 회수·탈락 단계 원장 — run·arm별\n\nNative API, public65 scope, immutable generation; result and ledger hold actual views.', 'Exact provider request/response/usage retained per case; Qwen3.8 Parasail FP8 none no fallback.', 'Same audited client for all phases and at most one decision repair per epoch/presentation; total40.', 'No judge model. Independent saved-original review. No adaptive retries or repeated sessions.', 'Results not observed at freeze; finalize after all four requests.']
 p.write_text('# '+c['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headings,texts),1))+'\n');m['questions'].append({'number':n,'case_id':c['case_id'],'file':filename,'sha256':sha(p)})
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for name in sorted(set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0743/integrated';pcm=read(parent/'candidate.json');rev=pcm['revisions'][-1];src=parent/'revisions'/rev['revision_id']/'snapshot';child=R/'02_BACKEND/lawrag/research/candidates/adr_0744/integrated'
for row in pcm['files']:
 name=row['target_path'];target=child/'snapshot'/name;target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src/name,target)
 if name not in set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}:
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(child),'--target',name,'--upstream-state','present' if (R/name).is_file() else 'absent'],check=True,stdout=subprocess.DEVNULL)
put(D/'parent-inheritance.json',{'parent':'ADR-0743-experiment-v1/integrated','manifest_sha256':sha(parent/'candidate.json'),'revision':rev['revision_id'],'serving_code_changes':0,'files':{x['target_path']:sha(src/x['target_path']) for x in pcm['files']}})
for name,v in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,v)
print('Frozen scope selected; copied completed implementation unchanged')

shutil.copy2(P/'artifacts/contract-result.json',A/'artifacts/contract-result.json')
assert read(A/'artifacts/contract-result.json')['strict_success']
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(child)],check=True,stdout=subprocess.DEVNULL)
put(D/'semantic-review-contract.json',{'cases':{x[0]:{'source_id':x[1],'question':x[3]} for x in selections},'required':'Review explicit requested permissions/duties and exception polarity against immutable gold; semantic detail errors separate; product context and output never changed','review_output':'artifacts/run-001/semantic-review.json','gold_product_visible':False})
