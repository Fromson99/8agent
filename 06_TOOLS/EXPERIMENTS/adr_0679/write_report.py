"""Describe only completed frozen measurements; never alter their criteria."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read(A/'실험/manifest.json');v=read(A/'artifacts/run-001/result.json');ok=v['strict_success'];assert len(m['questions'])==16 and m['results']['status']=='complete'
assert m['in_sample'] is False and m['decision_eligible'] is True
f=(A/'README.md').read_text().split('---',2)[1]
f=f.replace('decision_eligible: false','decision_eligible: true')
f=f.replace('status: Proposed','status: Accepted' if ok else 'status: Rejected')
lines=[]
for line in f.splitlines():
 if line.startswith('main_wiring:'):line='main_wiring: unchanged'
 lines.append(line)
f='\n'.join(lines)+'\n';row=v['by_arm']['integrated'];u=row['usage'];lat=row['latency'];counts={k:len(x) for k,x in v['semantic_outcomes'].items()}
sections={
'1. 결정 요약':('Accepted. 사전 동결한 계약·응답 완성·무결성 기준을 통과했다. 판단 코드의 검증 결과이며, 나중에 추가된 /chat 변경을 보존한 후속 통합 검증 전에는 이 후보를 MAIN에 직접 적용하지 않는다.' if ok else 'Rejected. 사전 동결 기준을 충족하지 못했다. 원결과와 실패 기록을 보존하며 MAIN을 전환하지 않는다.')+'\n\n'+json.dumps(v['checks'],ensure_ascii=False,indent=2),
'2. 문제와 변경 전 구조':'분석 대상은 generation43 MAIN의 서빙265파일과 동일했다. ADR0678에서 읽기와 채택 분리, 보류 자료 재열람, 진전 없는 반복 종료, 마무리 예산, span 인용, 부족분 재조사, 결정 후 새 문장 생성 방지, 전송/재개/게시/워크플로우 소비자를 구현했다. 17개 개발 요청 후 HTTP200 출력 길이 초과를 전송 오류로 잘못 바꾸는 T10 결함으로 그 후보를 Rejected 처리했다. 완료된 부모를 보존하고 이 후속 후보에서 수정했다.',
'3. 가설과 사전 판정 기준':m['design']['hypothesis']+'\n\n성공: '+m['design']['success_criteria']+'\n\n실패: '+m['design']['failure_criteria']+'\n\n세부 의미 정답을 모두 맞혀야 하는 기준으로 바꾸지 않았다. 인용·권한·해시·상태·게시 무결성과 필수 계약을 유지한다.',
'4. 실험 설계':'기존 부모 실험에서 정답 근거나 실제 원문으로 전달된 조문671개를 제외한 새로운 주 조문16개를 선정했다. 8종 요구 유형을 각2개씩 구성하고, 원문과 질문을 호출 전에 대조했다. 공공기관 정보공개법·중소기업기본법·국세기본법·금융소비자보호법의 동결 원문을 사용한다. 알려진 실패 중심12회귀는 주 평가와 분리했다. 각 질문1회, 제품 코드·질문·모델·채점 지침 동결 후 실행했다. 부모와 같은 질문의 paired A/B가 아니므로 정확도·지연 향상의 인과효과를 주장하지 않는다.',
'5. 데이터·모델·재현성':'동일 term-source-3b667f54bb11d9477888 세대와 공개145문서 승인 범위, Qwen3.8 qwen/qwen3.8-27b / OpenRouter Parasail FP8 / reasoning none / fallback 없음. 요청당40물리호출, 마무리예약3, 형식보정1회, 확인된429 재시도1회, gap 재진입2회, 총1800초. 재시도·보정도 같은 예산이다. 공통 ExperimentClient의 고정 후보에서 형식 오류 표식을 보존하고 Retry-After를 전달했다. 원문·출력·사용량은 해시와 압축 복원 정보로 보존한다. GENOS 내부 실험이 아니다.',
'6. 결과':f"계획한 독립16질문 중 {row['executed_count']}개 실행: 응답 {row['request_success_count']}개, 단일 자동 평가 정답 {row['correct_count']}개, 판단 오류 {counts['judgment_mistake']}개, 미답변 {counts['no_answer']}개. 주 평가6개와 회귀12개는 필수 소비자 계약 실패 후 미실행(NOT_RUN)이며 미답변으로 집계하지 않는다. 직접 /chat 상태 구분3개 계약 실패와 최신 작업 코드 소비자 누락을 확인하여 추가 배정을 중단하고 진행 중 요청만 정상 종료했다.\n\n"+json.dumps(counts,ensure_ascii=False,indent=2)+'\n\n'+json.dumps(v['early_stop'],ensure_ascii=False,indent=2),
'7. 사례별 오류 분석':'정답·판단 오류·미답변은 artifacts/run-001/GENERALIZATION_ERRORS.json과 질문별 원결과에 분리했다. 자동 평가 설명은 원문과 함께 검토할 관찰이며 평가 자체가 완전하다고 보지 않는다. 기존 회귀 질문 답변과 종료 코드는 artifacts/regression에 남긴다. 답변의 COVERED는 구조상 충족 판정이며 법률 의미의 정답 인증이 아니다. 새 문제를 고치거나 재채점할 때에는 새 ADR로 진행한다.',
'8. 비용·지연·회수 규모':f"독립 질문 제품 호출 입력 {u['input_tokens']} tokens, 출력 {u['output_tokens']} tokens, 비용 USD {u['cost_usd']:.6f}. 요청 p50 {lat['request_p50']:.3f}초, 기록 p95 {lat['request_p95']:.3f}초. 회귀·평가 비용은 별도 원기록이다. 회수 단계 전체 원장은 retrieval-ledger.json.gz이고 실제 읽기·전달·채택을 구분한다.",
'9. 해석':'핵심 완료 계약20개와 추가 오류 경계10개가 통과했다. 공통 gateway 테스트는18통과·3실패로 기존 MAIN과 동일한 실패이며 신규 실패는 없다. 부모의 넓은 구 테스트39실패도 숨기지 않고 참조한다. 모든 저장소 테스트 통과를 주장하지 않는다. 동일268서빙파일 패키지·엔진 의존성·서비스 프로필·HEALTH/검색/AD 접근제한 및 실제 워크플로우의 미완료/상류실패 소비를 검사했다. 테스트는 원문 연결과 실행 계약을 검증하며 전체 법률 판단 정확성을 인증하지 않는다.',
'10. 한계와 일반화 가능 범위':'독립 주 조문16개는 네 법률의 공개 규칙 질문이다. 도메인 전체, 개별 사건 판단, 비공개 내부자료, GENOS 모델 품질로 일반화하지 않는다. 원문을 찾았어도 LLM이 주체·예외를 잘못 해석할 수 있다. 별도 의미 평가 모델을 제품의 매 단계에 추가하지 않았으며, COMPOSE는 확정한 판단을 정해진 형식으로 표시한다. 새로운 법률 설명을 덧붙이는 자유도가 줄어드는 대신 판단 이후 문장 변형 위험을 줄인다.',
'11. 운영 결정·롤백 조건':'진행 중 추가된 작업 코드의 /chat·SSE/JSON 변경3파일과 의존성 지문11파일을 별도 보존했다. 이 후보는 그 후속 변경을 포함하지 않으므로 직접 MAIN 적용하지 않는다. 동일 판단 코드를 상속하고 최신 소비자 변경을 보존하는 후속 ADR에서 최종 통합본을 검증해야 한다. Accepted일 때만 검토 파일을 백업하고 현재 작업 코드가 원래 기준과 일치하는지 검사한 뒤 선택적으로 통합한다. 사용자 지시에 따라 stable rag_main_promotion.py의 hash고정 prepare와 apply --confirm-main을 사용한다. 활성 포인터와 새 service.service의 HEALTH/RAG_SEARCH/RAG_ASK에서 코드·프로필·세대·검색 정책·native binding을 확인한다. 불일치 시 MAIN과 작업 코드의 기록된 복원 경로를 사용한다. 기존 요청의 코드 binding이 달라지면 재개를 거부하고 기록을 보존한다. Git main 병합과 GENOS 현장 배포는 별도다.',
'12. 재현 명령':'WSL /home/jin/8-AGENT에서 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0679/run_case.py --arm integrated --case CASE_ID. 완료 결과 덮어쓰기·반복 재실행은 금지하며 새 실험에서 진행한다. adr_structure.py validate --final과 graph로 계보를 검사한다. 전체 그래프의 기존 다른 ADR 결함은 이 후보 결과와 분리해 기록한다.'}
(A/'README.md').write_text('---'+f+'---\n\n# ADR-0679 조사 완료 계약 독립 검증\n\n'+'\n\n'.join('## '+k+'\n\n'+s for k,s in sections.items())+'\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json' and p.suffix in ('.json','.txt','.log','.py','.gz','.md') and not any(x in ('prepared-generations','runtime','setup-check','main-stage') for x in p.relative_to(A/'artifacts').parts)]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input or exact observed product/provider/evaluator/trace artifact'} for p in sorted(files)]})
print('Decision','Accepted' if ok else 'Rejected')
