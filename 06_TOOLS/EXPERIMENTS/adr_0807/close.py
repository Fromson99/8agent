from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0807-nonblank-generation-grammar'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');o=read(A/'artifacts/connected-observation.json');r=read(A/'artifacts/live/result.json');restart=read(A/'artifacts/live/restart-check.json');assert restart['status']=='PASS'
count=sum(int(re.findall(r'(\d+) passed', (A/'artifacts'/n).read_text())[-1]) for n in ('frozen-tests.txt',))
result={'status':'complete','technical_contracts_passed':count,'model_calls':r['model_calls'],'elapsed_seconds':r['elapsed_seconds'],
 'actual_status':o['status'],'actual_rows':len(o['rows']),'restart':restart['checks'],
 'known_issue':'Known-case source completeness and legal correctness remain observational. Exact child failures and gaps in connected-observation.json; no legal quality certification.',
 'quality_certified':False,'decision_eligible':False,'main_changed':False,'genos_changed':False}
put(A/'artifacts/run-001/result.json',result);m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['design']['arms'][0]['changes']='Completed ADR0806/connected archived diagnostic observation; not a successful final response'
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Archived completed ADR0806 diagnostic; no fresh model calls'},'connected':{'status':'complete','contracts':count,'actual_status':o['status'],'actual_rows':len(o['rows'])}},usage={'product_model_calls':r['model_calls'],'offline_evaluator_calls':0},latency={'known_live_seconds':r['elapsed_seconds']},error_taxonomy=['OBSERVED_COMPLETENESS_LIMITATIONS'])
qh=['1. 실행 메타','2. 사용자 질문 원문','3. 기준답변 — 채점 전용, 제품 입력 비공개','4. 제품 입력을 구성한 원값','5. 제품 모델 호출 — run·arm별 실제 원문','6. 중간 LLM 호출 — router/compiler/verifier/repair','7. 채점 호출과 반복 판정','8. 사례 최종 판정']
qt=['K01 알려진 질문 1회. in_sample=true, decision_eligible=false.',read(A/'artifacts/design/criteria.json')['known_observation']['question'],'승인된 정답 없음: gold_total=0, recall=null. 법률 정답률로 평가하지 않는다.','MAIN74 원문·정의·최신 선택 유지. 입력/해시 design/freeze.json, live/binding.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json. 분모는 두 관측에서 실제 읽은 조문 합집합이며 전체 corpus가 아니다.','../artifacts/live/raw/call-*/request.json, response.json, validation-schema.json에 실제 입력과 출력 보존.','자식 진입·문장화 호출, 시스템 정의 읽기, 부모 인용 투영은 parent-task-observation.json 및 connected-observation.json.',f'평가 모델0. 동결 코드{count}검사. 새 프로세스 재시작9검사 통과.',f"실제 상태 {o['status']}, 비교 {len(o['rows'])}행, 호출 {r['model_calls']}회. 의미 정답 성공으로 바꾸지 않는다."]
p=A/'실험/질문-001-K01.md';p.write_text('\n\n'.join('## '+h+'\n\n'+t for h,t in zip(qh,qt))+'\n');m['questions']=[{'number':1,'case_id':'K01','file':p.name,'sha256':sha(p)}];put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[f'Proposed. 시스템 소유 처리 {count}검사와 실제 서비스 재시작 검증. 알려진 질문은 별도 관측이며 직접 승격 근거가 아니다.',
 '모델이 원문을 복사하고 상태/식별자를 재작성했다. 자식이 부모 계획을 재해석하고 재문장화했으며 보류 판단도 반복 호출했다. 뒤 비교 실패가 앞 행을 지웠다.',
 'criteria.json을 수정 전에 동결했다. 생성 형식에서 시스템 소유 선택 필드를 제외하고 정본에서 다시 결속한다. 원문·권한·해시·상태 검증과 단일 복구 담당/총예산은 유지한다.',
 '완료 ADR0806/connected에서 분기. 비공백 문자가 있어야 한다는 조건을 전체 문자열 언어로 명시했다. 정본 JSON Schema 검증의 허용 언어는 유지하며, 공급자 grammar가 full-match하더라도 한 글자만 강제하지 않는다. 부모의 시스템 이관 기능 및1..12개 쟁점 보존.',
 'Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음. 공통 ExperimentClient 사용. 검증 대상338파일과 공유 원문 세대는 design/freeze.json.',
 f"동결 코드 {count}검사 통과. 실제 {r['model_calls']}호출/{r['elapsed_seconds']:.2f}초, {o['status']}, 비교{len(o['rows'])}행. 실제 최종 결과의 새 프로세스 재시작9검사와 동일 요청 추가 호출0 확인.",
 '실제 남은 부족·실패는 connected-observation.json에 기록한다. 이전 ADR0804의 필수 검색 선택 누락과 ADR0806의 시스템 소유 인용 재작성 오류는 별도 역사로 보존한다. 스키마 통과를 정답으로 취급하지 않는다.',
 '실측 토큰/모델/provider/출력은 live/raw. 호출수·시간은 관측이며 다른 의미 조사 경로 간 인과적 성능 개선으로 주장하지 않는다.',
 '시스템: 부모 쟁점 전달, 정확 인용 복원, 식별자/상태 결속, 정의·명시 참조 읽기, 구조적 문장화, 판정 불가 게이트, 행 저장/재개, 표시할 인용 필터. 모델: 쟁점 의미·검색 선택·원문 해석·내용 차이·조건 충족 판정.',
 '한 알려진 질문이다. 법률 정답률·일반화 미인증. 여러 쟁점은 보존하지만 필요한 근거를 모두 찾았다는 보증은 아니다. 외부 모델과 GENOS 현장은 구분한다.',
 '이 관측은 MAIN74를 바꾸지 않는다. 작업 코드 통합과 실제 MAIN 반영은 새 기술 경계 자격검증을 거쳐 기록한다. 실패 원문 및 후보 rev-001 불변 보존. GENOS 미반영.',
 '06_TOOLS/EXPERIMENTS/adr_0807: prepare.py → repin.py → adr_candidate freeze/validate → freeze.py → run_tests.py/live.py → restart_check.py/account.py/inspect_parent_task.py/close.py. 완료 기록 덮어쓰기 금지.']
meta=(A/'README.md').read_text().split('---',2)[1];(A/'README.md').write_text('---'+meta+'---\n\n# ADR-0807 시스템 소유 필드 생성 제거\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'실험/README.md').write_text('# 알려진 질문 관측\n\n[K01](질문-001-K01.md): 기능 계약과 실제 정답 성공을 구분한다.\n');(A/'RESULT.txt').write_text('\n\n'.join(texts)+'\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0807','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code and actual execution evidence','contains_raw_prompts_and_outputs':'raw' in p.parts or 'runtime' in p.parts} for p in files]})
print('Prepared final records',count)
