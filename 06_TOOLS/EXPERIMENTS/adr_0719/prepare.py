from pathlib import Path
import json,hashlib,sqlite3,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0719-request-repair-public-qualification';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0718-main50-request-repair-integration'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
base=read(P/'artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256'];put(D/'baseline.json',base)
criteria={'scope':'Unchanged completed ADR0718/repaired v5 implementation: request epochs, source-bound gaps, conservative coverage, exact quote request scope, nested answer content, source projection, accepted outcome and request-window observed RSS.',
 'required':{'all_requests':9,'candidate_primary_supported_min':3,'candidate_repeat_supported_min':3,'no_paired_supported_regression':True,'all_successful_citations_verified':True,'all_candidate_primary_gold_presented':True,'public_scope_only':True,'actual_binding_valid':True,'approved_judgment_and_gap_state_valid':True,'raw_diagnostics_in_public_zero':True,'no_new_contract_regressions':True,'all20_new_contracts_pass':True,'same_code_to_release':True,'unseen_primary_roots':True,'physical_call_accounting':True,'content_preserved':True,'unexpected_http500_zero':True},
 'execution':{'arms':['baseline','repaired'],'order':[['H01','baseline'],['H01','repaired'],['H02','repaired'],['H02','baseline'],['H03','baseline'],['H03','repaired'],['S01','repaired'],['S02','repaired'],['S03','repaired']],
  'model':'qwen/qwen3.8-27b','provider':'Parasail','quantization':'fp8','reasoning':'none','fallback':False,'calls_per_request':40,'output_tokens':6400,'wall_seconds':1800,'fresh_process_per_request':True,'adaptive_reruns':False},
 'stability':'S01/S02/S03 are predeclared identical question repeats of H01/H02/H03 in fresh sessions; excluded from holdout primary counts, reported separately including failures; two repetitions do not certify stability.',
 'semantic_gate':'Independent post-output review of fixed originals. Detailed semantic errors recorded separately, not automatically blocking per 2026-10-07 user instruction; quote, ACL, state, bindings and content loss are blocking.',
 'performance_gate':'Report physical attempts, total/assessment/last-assessment-excluded time, tokens, RSS observation; no ungrounded speed target on3pairs. Preserve total model/deadline limits. No permanent judge.',
 'regression_gate':'All20 new invariant tests passed and zero new failures over current MAIN50 same271 legacy contracts;15 inherited fixture failures retained in parent. Actual source scope/currentness/quote/native publication are also tested in new synthetic and actual requests.',
 'rollback':'Keep MAIN50 on any required failure. On successful local integration preserve MAIN50 manifest+files as rollback target; never claim GENOS deployment.',
 'authorization':'User requested implementation of the reviewed plan; local MAIN integration is included after predeclared verification. Only freshly authored public questions sent externally.'}
put(D/'criteria.json',criteria)
selections=[('H01','article:00b159e6a9abd5d8cdc98dfe','REQUEST_SCOPE_COMPARISON','상장 실무 교육자료를 준비 중입니다. 유가증권시장 상장규정 시행세칙 제14조에서 정한 기준시가총액 산정 방법만 각 호별로 비교해 주세요. 교육과정 설계나 다른 상장요건 검토는 요청하지 않습니다.'),
 ('H02','article:0139762d04cd6e2ba3d7ffe5','NESTED_EXCEPTION_AND_OBLIGATION','소득세법 시행령 제40조의4에 따른 연금계좌 이체의 원칙, 제1항 단서와 제2항의 관계, 일부 금액 이체, 가입일 기준, 계좌취급자의 통보 의무를 구분해 설명해 주세요. 특정 납세자의 사실 판단이 아닌 규정 설명입니다.'),
 ('H03','article:007306eba6c6bca30678ac90','BODY_SEARCH_EXCEPTION','상장지수집합투자기구의 설정이나 설립에 필요한 집합투자증권 최소단위를 정할 때, 수량을 기준으로 하는 원칙과 금액을 기준으로 정할 수 있는 경우는 어떻게 다른가요?')]
excluded=set(read(D/'excluded-source-ids.json'));assert not read(D/'exposure-scan.json')['failures'];allowed=set(read(R/base['manifest']['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
db=sqlite3.connect((R/base['manifest']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
cases=[];gold=[]
for cid,sid,kind,question in selections:
 assert sid not in excluded
 source=json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0]);assert source['document_id'] in allowed
 cases.append({'case_id':cid,'kind':kind,'question':question})
 gold.append({'case_id':cid,'source_id':sid,**{k:source[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}})
for i in range(3):cases.append({**cases[i],'case_id':'S0'+str(i+1),'repeat_of':cases[i]['case_id']});gold.append({**gold[i],'case_id':'S0'+str(i+1)})
db.close();put(D/'dataset.json',{'cases':cases,'regression_cases':[],'repeat_cases':['S01','S02','S03'],'product_gold':False,'source_generation':base['manifest']['data_path']});put(D/'gold.json',{'product_visible':False,'version':'Pinned selected public originals','cases':gold})
put(D/'selection-audit.json',{'primary_roots':[x[1] for x in selections],'prior_excluded':len(excluded),'no_overlap':True,'selection_before_results':True,'qualification_scope':'Three unexposed primary article roots, different documents, no CM export. Secondary dependencies may have previous exposure.'})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Source-backed native completion and strict source/state/content invariants',success_criteria=criteria['required'],failure_criteria='Any required invariant fails: keep MAIN50',criteria_frozen_before_run=True,repeats=1)
for arm in m['design']['arms']:
 arm.update(changes='Selected MAIN50 unchanged' if arm['id']=='baseline' else criteria['scope'],controls='Same approved65 sources, dataset generation, model identity, total budgets; fresh process')
 if arm['id']=='repaired':arm['derived_from']=['ADR-0718-experiment-v1/repaired']
 if arm['id']=='baseline':arm.update(derived_from=[],source_binding={'path':str((D/'baseline.json').relative_to(R)),'sha256':sha(D/'baseline.json'),'source_arm':'ADR-0712-experiment-v1/compact','replica_of_selected_release':True})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['dataset'].update(name='Three new public roots plus separately identified identical-question repeats',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Exact9 requests in criteria.execution.order; no adaptive repeats or replacement',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a['id']:stages for a in m['design']['arms']}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
m['questions']=[]
headings=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for n,c in enumerate(cases,1):
 filename=f'질문-{n:03}-{c["case_id"]}.md';p=A/'실험'/filename
 texts=['ADR0719/run-001; '+('predeclared repeated request of '+c['repeat_of'] if c.get('repeat_of') else 'new primary root paired baseline/repaired'),c['question'],'Offline design/gold.json; never read by product runner.', '### 회수·탈락 단계 원장 — run·arm별\n\nNative API, public65 scope, immutable generation; result and ledger hold actual views.', 'Exact provider request/response/usage retained per case; Qwen3.8 Parasail FP8 none no fallback.', 'Same audited client for all phases and at most one decision repair per epoch/presentation; total40.', 'No judge model. Independent saved-original review. Three repeats fixed before results, not adaptive retries.', 'Results not observed at freeze; finalize after all nine requests.']
 p.write_text('# '+c['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headings,texts),1))+'\n');m['questions'].append({'number':n,'case_id':c['case_id'],'file':filename,'sha256':sha(p)})
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','repaired','--experiment-id',m['experiment_id'],'--arm-id','repaired','--run-id','run-001']
for name in sorted(set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0718/repaired';pcm=read(parent/'candidate.json');rev=pcm['revisions'][-1];src=parent/'revisions'/rev['revision_id']/'snapshot';child=R/'02_BACKEND/lawrag/research/candidates/adr_0719/repaired'
for row in pcm['files']:
 name=row['target_path'];target=child/'snapshot'/name;target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src/name,target)
 if name not in set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}:
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(child),'--target',name,'--upstream-state','present' if (R/name).is_file() else 'absent'],check=True,stdout=subprocess.DEVNULL)
put(D/'parent-inheritance.json',{'parent':'ADR-0718-experiment-v1/repaired','manifest_sha256':sha(parent/'candidate.json'),'revision':rev['revision_id'],'serving_code_changes':0,'files':{x['target_path']:sha(src/x['target_path']) for x in pcm['files']}})
for name,v in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,v)
print('Frozen scope selected; copied completed implementation unchanged')
