from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0803-system-owned-workflow-mechanics'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');o=read(A/'artifacts/connected-observation.json');r=read(A/'artifacts/live/result.json');restart=read(A/'artifacts/live/restart-check.json')
assert '183 passed' in (A/'artifacts/frozen-tests.txt').read_text() and restart['status']=='PASS'
result={'status':'complete','technical_contracts_passed':183,'model_calls':r['model_calls'],'elapsed_seconds':r['elapsed_seconds'],
 'actual_status':o['status'],'actual_rows':len(o['rows']),'restart':restart['checks'],'system_seed_events':sum(x['system_seed_events'] for x in o['children']),
 'known_issue':'Child planner still reinterprets combined parent question; internal MISSING_DOCUMENT mistaken for missing regulations; external gaps include internal side. Retain as failure, do not label semantic success.',
 'quality_certified':False,'decision_eligible':False,'main_changed':False,'genos_changed':False}
put(A/'artifacts/run-001/result.json',result)
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Archived completed ADR0802 known-question observation; no fresh model calls'},'connected':{'status':'complete','contracts':183,'actual_status':o['status'],'actual_rows':len(o['rows'])}},usage={'product_model_calls':r['model_calls'],'offline_evaluator_calls':0},latency={'known_live_seconds':r['elapsed_seconds']},error_taxonomy=['CHILD_REINTERPRETS_PARENT_SCOPE','MISSING_DOCUMENT_IS_NOT_ABSENCE','SEMANTIC_TARGET_RETRIEVAL_UNCONFIRMED'])
qh=['1. 실행 메타','2. 사용자 질문 원문','3. 기준답변 — 채점 전용, 제품 입력 비공개','4. 제품 입력을 구성한 원값','5. 제품 모델 호출 — run·arm별 실제 원문','6. 중간 LLM 호출 — router/compiler/verifier/repair','7. 채점 호출과 반복 판정','8. 사례 최종 판정']
qt=['K01, 알려진 질문 1회. in_sample=true, decision_eligible=false.',read(A/'artifacts/design/criteria.json')['known_observation']['question'],'승인된 정답 집합 없음. gold_total=0, recall=null; 법률 정답률을 계산하지 않는다.','실제 원문·정의·최신 선택은 MAIN74와 동일. 코드/입출력 binding은 design/freeze.json 및 live/raw.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json. 정의 우선 읽기→전체 확보→채택→최종 표시. 분모는 두 관측에서 실제 확보한 조문 합집합이며 전체 법률 corpus가 아니다.','../artifacts/live/raw/call-*/request.json, response.json, validation-schema.json, binding.json. 재구성 없이 실제 원값 보존.','단계/횟수/상태: ../artifacts/connected-observation.json. 시스템 이벤트는 child/parent SQLite 원장에 보존.','오프라인 평가 모델0. 동결 코드183검사, 새 프로세스 재사용9검사.',f"실제 {o['status']}, 비교 {len(o['rows'])}행, 모델 {r['model_calls']}호출. 외규 정의 연결 원문 실제 확보·채택 확인, 전체 정답 성공은 미인증."]
p=A/'실험/질문-001-K01.md';p.write_text('\n\n'.join('## '+h+'\n\n'+t for h,t in zip(qh,qt))+'\n');m['questions']=[{'number':1,'case_id':'K01','file':p.name,'sha256':sha(p)}];put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. 시스템 소유 처리 후보183검사 통과. 알려진 실제 질의 관측은 성공/부분 실패를 그대로 보존하며 MAIN 승격 근거와 구분한다.',
 '원문 재복사·고정필드 재작성·자식 문장화·반복 보류 판단을 모델이 수행했다. 뒤쪽 비교 실패가 앞의 통과 행을 최종 결과에서 지웠다.',
 '첫 수정 전 criteria.json, 실제 호출 전 code/design freeze. 원문/ACL/해시/상태 검증 유지, 공유 예산/기존 수정 담당 유지. 내용 차이는 BASIS에서 한 번 판단하고 시스템이 보류를 조립한다.',
 '완료 ADR0802/connected에서 분기. MAIN74 선택338파일 후보(기존336+helper2). 다중 쟁점 연결 보존. 알려진 사례 1회; 새 기준 LLM 호출 없음.',
 'Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음. 공통 ExperimentClient의 후보 transport 분류. 원문 세대와 프롬프트/모델/프로필/코드 해시 design/freeze.json.',
 f"동결 코드183검사 통과. 실제 {r['model_calls']}호출/{r['elapsed_seconds']:.2f}초, {o['status']}, {len(o['rows'])}행. 재시작9검사 통과. 시스템 정의 우선 읽기 이벤트 {result['system_seed_events']}건.",
 '내규 STRUCTURE에 특정 문서가 없다는 MISSING_DOCUMENT를 모델이 규정 부재로 오인했다. 외규는 시스템이 읽은 금융투자업규정 제3-24조의4/시행세칙 제2-8조의3을 채택했지만 초기 자식 목적에 내부 규정 요구도 재삽입되어 불필요한 내규 부족을 생성했다. 사용하지 않는 structure_filter는 기록 후 제거했고 원래 판정·인용 검사 유지. 최종 표 위치 표기도 실제 인용 집합으로 더 좁혀야 함을 후속으로 확인.',
 '실측 usage는 live/result.json, 회수/표시 단계는 run-001/retrieval-ledger.json. 다른 조사 경로와 모델 결과이므로 호출/시간 차이를 일반 성능 향상으로 해석하지 않는다.',
 '기계적 처리는 원문·상태 결속을 가진 시스템 소유가 적절하다. 원래 쟁점/법률 적용·내용 차이 판단은 모델 책임이다. 부모의 의미 계획을 자식이 재생성하는 연결도 후속에서 제거할 필요가 있다.',
 '한 알려진 질문이다. 법률 정답률/일반화 미인증. 정의 위치 확보와 채택은 맞는 전체 답변을 보증하지 않는다. 외부 모델 결과와 GENOS를 구분한다.',
 'MAIN74 선택 포인터 불변, 작업 코드 미반영, GENOS 미반영. 후보 rev-001/실패 로그 불변 보존. 확인된 추가 결함은 새 ADR에서 수정한다.',
 '06_TOOLS/EXPERIMENTS/adr_0803: prepare.py → repin.py → adr_candidate freeze/validate → freeze.py → run_tests.py/live.py → restart_check.py/account.py/close.py. 완료 산출물 재실행 덮어쓰기 금지.']
old=(A/'README.md').read_text();meta=old.split('---',2)[1]
(A/'README.md').write_text('---'+meta+'---\n\n# ADR-0803 시스템 소유 처리\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'실험/README.md').write_text('# 시스템 소유 처리 관측\n\n[K01](질문-001-K01.md): 계약 검증과 실제 알려진 질의 결과를 구분한다.\n')
(A/'RESULT.txt').write_text('\n\n'.join(texts)+'\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0803','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code and actual execution evidence','contains_raw_prompts_and_outputs':'raw' in p.parts or 'runtime' in p.parts} for p in files]})
print('Prepared final records; validate before marking reservation complete')
