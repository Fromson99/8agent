from pathlib import Path
import json,hashlib,sqlite3,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0730-compact-choice-public-qualification';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0729-compact-branch-choice-contract'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
base=read(P/'artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256'];put(D/'baseline.json',base)
criteria={'scope': 'Unchanged completed729 compact branch-choice external grammar with unchanged original local validation, corrected scoped-heading failure, and inherited727 navigation projection and constraints.', 'required': {'all_requests': 4, 'candidate_primary_supported_min': 2, 'no_paired_supported_regression': True, 'citations_acl_state_binding_content_valid': True, 'all_candidate_primary_gold_presented': True, 'all68_critical_contracts_pass': True, 'zero_new_contract_regressions': True, 'successful_pairs_min': 1, 'input_ratio_max': 0.9, 'calls_delta_max': 1, 'request_seconds_ratio_max': 1.3}, 'execution': {'arms': ['baseline', 'integrated'], 'order': [['H01', 'baseline'], ['H01', 'integrated'], ['H02', 'integrated'], ['H02', 'baseline']], 'model': 'qwen/qwen3.8-27b', 'provider': 'Parasail', 'quantization': 'fp8', 'reasoning': 'none', 'fallback': False, 'calls_per_request': 40, 'output_tokens': 6400, 'wall_seconds': 1800, 'fresh_process_per_request': True, 'adaptive_reruns': False}, 'stability': 'Two paired questions, no repeats; no statistical speed claim', 'semantic_gate': 'Record detailed semantic mistakes separately; exact citation/ACL/state/content/binding failures block. No grade-driven answer edits or retries.', 'performance_gate': 'At least one pair supported in both arms; ONLY these successful pairs aggregated for input<=90%, calls<=baseline+1, time<=130%. Failed-baseline completion recovery and cost reported separately.', 'regression_gate': 'All68 critical tests pass, no new failures across339 vs inherited15.', 'rollback': 'Keep MAIN51 on any required failure. Preserve prior pointer/code/data and working backups.', 'authorization': 'Current user proceed plus earlier explicit MAIN and external data authorization; only public authored questions and approved65 originals.'}
put(D/'criteria.json',criteria)
selections=[('H01', 'article:0b92df4d11a249f8122bbe58', 'EXACT_OR_THRESHOLD_EXCEPTION', '외국환거래규정 제9-35조에 따라 외국기업 국내지점이 결산순이익금을 대외송금할 때 이용할 은행, 신청서와 첨부서류, 감사증명서가 필요한 두 조건의 관계, 장관에게 설치신고한 지점의 서류 갈음 특례를 이 조문에 적힌 범위에서 설명해 주세요.'), ('H02', 'article:0ec030b92ab16dc6dd7c5ce8', 'BODY_MULTI_BRANCH_DISCRETION', '금융투자회사의 영업 및 업무에 관한 규정상 협회가 징계내역 열람신청을 받았을 때 통보하는 절차와 징계·책임자 범위를 알려 주세요. 통보대상에서 제외할 수 있는 사유를 징계별 경과기간, 감독당국의 조치, 금융투자업 관련성으로 나누어 설명하고 제외가 의무인지도 구분해 주세요.')]

excluded=set(read(D/'excluded-source-ids.json'));assert not read(D/'exposure-scan.json')['failures'];allowed=set(read(R/base['manifest']['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
db=sqlite3.connect((R/base['manifest']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
cases=[];gold=[]
for cid,sid,kind,question in selections:
 assert sid not in excluded
 source=json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0]);assert source['document_id'] in allowed
 cases.append({'case_id':cid,'kind':kind,'question':question})
 gold.append({'case_id':cid,'source_id':sid,**{k:source[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}})

db.close();put(D/'dataset.json',{'cases':cases,'regression_cases':[],'repeat_cases':[],'product_gold':False,'source_generation':base['manifest']['data_path']});put(D/'gold.json',{'product_visible':False,'version':'Pinned selected public originals','cases':gold})
put(D/'selection-audit.json',{'primary_roots':[x[1] for x in selections],'prior_excluded':len(excluded),'no_overlap':True,'selection_before_results':True,'qualification_scope':'Two unexposed primary article roots, different documents, no CM export. Secondary dependencies may have previous exposure.'})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Source-backed native completion and strict source/state/content invariants',success_criteria=criteria['required'],failure_criteria='Any required invariant fails: keep MAIN51',criteria_frozen_before_run=True,repeats=1)
for arm in m['design']['arms']:
 arm.update(changes='Selected MAIN51 unchanged' if arm['id']=='baseline' else criteria['scope'],controls='Same approved65 sources, dataset generation, model identity, total budgets; fresh process; final same-epoch recovery fix inherited')
 if arm['id']=='integrated':arm['derived_from']=['ADR-0729-experiment-v1/compact']
 if arm['id']=='baseline':arm.update(derived_from=[],source_binding={'path':str((D/'baseline.json').relative_to(R)),'sha256':sha(D/'baseline.json'),'source_arm':'ADR-0725-experiment-v1/integrated','replica_of_selected_release':True})
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
 texts=['ADR0730/run-001; '+('predeclared repeated request of '+c['repeat_of'] if c.get('repeat_of') else 'new primary root paired MAIN51/compact'),c['question'],'Offline design/gold.json; never read by product runner.', '### 회수·탈락 단계 원장 — run·arm별\n\nNative API, public65 scope, immutable generation; result and ledger hold actual views.', 'Exact provider request/response/usage retained per case; Qwen3.8 Parasail FP8 none no fallback.', 'Same audited client for all phases and at most one decision repair per epoch/presentation; total40.', 'No judge model. Independent saved-original review. No adaptive retries or repeated sessions.', 'Results not observed at freeze; finalize after all four requests.']
 p.write_text('# '+c['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headings,texts),1))+'\n');m['questions'].append({'number':n,'case_id':c['case_id'],'file':filename,'sha256':sha(p)})
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for name in sorted(set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0729/compact';pcm=read(parent/'candidate.json');rev=pcm['revisions'][-1];src=parent/'revisions'/rev['revision_id']/'snapshot';child=R/'02_BACKEND/lawrag/research/candidates/adr_0730/integrated'
for row in pcm['files']:
 name=row['target_path'];target=child/'snapshot'/name;target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src/name,target)
 if name not in set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}:
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(child),'--target',name,'--upstream-state','present' if (R/name).is_file() else 'absent'],check=True,stdout=subprocess.DEVNULL)
put(D/'parent-inheritance.json',{'parent':'ADR-0729-experiment-v1/compact','manifest_sha256':sha(parent/'candidate.json'),'revision':rev['revision_id'],'serving_code_changes':0,'files':{x['target_path']:sha(src/x['target_path']) for x in pcm['files']}})
for name,v in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,v)
print('Frozen scope selected; copied completed implementation unchanged')
