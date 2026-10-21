from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0917-answer-first-release-closure';Q=R/'04_EXPERIMENTS/ADR/ADR-0916-answer-first-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-0915-answer-first-followup-provenance';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'binding.json');base=read(D/'baseline.json');prior=read(Q/'artifacts/run-001/result.json');preview=read(A/'artifacts/packager-preview.json');staged=dict(base['manifest']['files'])
for row in preview['changes']:
 if row['after'] is None:staged.pop(row['path'],None)
 else:staged[row['path']]=row['after']
r=read(A/'artifacts/resource-preview.json');integration=read(D/'integration.json');known=read(P/'artifacts/run-001/result.json')
checks={'exact_frozen_inputs':all(sha(R/n)==h for n,h in f['files'].items()),'actual_packager_complete_inventory':staged==b['serving_files'],'exact_declared_deltas':[{k:v for k,v in x.items() if k!='reason'} for x in preview['changes']]==[{k:v for k,v in x.items() if k!='reason'} for x in integration['changes']],'all_372_files_match_candidate_and_working':len(staged)==372 and all(sha(R/n)==sha(R/b['code_root']/n)==h for n,h in staged.items()),'parent_132_and_service_checks':prior['strict_success'] and prior['technical_tests']==132 and all(prior['checks'].values()),'known_live_replies_and_followup':known['strict_success'] and known['followup_continuity_passed'],'pointer_unchanged':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer'],'preview_within_budget':r['returncode']==0 and r['stop_reason'] is None}
assert all(checks.values()),checks
result={**prior,'checks':checks,'strict_success':True,'new_finite_tests':0,'retained_tests':132,'qualification_kind':'finite actual release packager census; no product change/model rerun','serving_files':372,'preparation_failure_preserved':str((Q/'artifacts/main-prepare.log').relative_to(R))};put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={'qualified':{'status':'complete','strict_success':True,'checks':checks}},usage={'product_model_calls':0,'offline_evaluator_calls':0},error_taxonomy=[{'kind':'inherited_limitations','details':prior['remaining']}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 p=A/'실험'/q['file'];parts=['run-001 / qualified; packaging-only successor to completed0916.','불필요한 조사 축소와 멀티턴 후속 조사 기능을 실제 로컬 실행에 연결한다.','Finite packaging inventory census; no legal gold.','design/binding.json and freeze.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nNo retrieval evaluation. Parent known-question ledger unchanged.','No model calls. Parent0915 has three known live responses.','No new inference/evaluator calls or product source changes.','Actual stable packager preview and exact candidate/working hashes; parent132tests and16consumer checks retained.',json.dumps(result,ensure_ascii=False)]
 p.write_text('# 릴리스 파일 연결\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
meta=(A/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:
 if re.search(r'(?m)^'+k+':',meta):meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
 else:meta+='\n'+k+': '+v+'\n'
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=['Accepted exact release closure. No product changes after completed parent live validation.','Parent declared371files but actual packager produced an additional existing session_identity.py. Fail-closed preparation stopped before activation.',json.dumps(read(D/'criteria.json'),ensure_ascii=False),'Read-only actual packager preview of immutable714-file candidate; compare all372serving files with declaration and working tree.','Same code/profile/data as parents0915/0916; no new model calls.',json.dumps(result,ensure_ascii=False),'session_identity.py existed in frozen candidate and current API tests. This corrects serving inventory only.','132 parent technical tests; parent22actualcalls vs historical71; no extra model calls.','Actual package contents, selected pointer and consumer binding must all agree.','\n'.join(prior['remaining']),'Prepare and activate exact qualified local release; preserve MAIN87 rollback. Verify active service uses372hash-bound files. GENOS remains separate.','prepare.py; guarded stable packager preview; report.py; final validate/graph; promote.py prepare; stableapply; consumer.py active; promote.py finish.']
(A/'README.md').write_text('---'+meta+'---\n\n# 답변 우선 실제 릴리스 파일 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n')
(A/'실험/README.md').write_text('# 검증 인덱스\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0917','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Actual release closure qualification','contains_raw_prompts_and_outputs':False} for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json']})
print('Qualified actual372-file closure; parent132checks retained')
