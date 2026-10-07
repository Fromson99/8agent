"""Combine completed provider probes without treating them as a new performance arm."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe';B=R/'04_EXPERIMENTS/ADR/ADR-0524-gemma-fp8-scoped-retrieval'
def read(p):return json.loads(p.read_text())
a,b=read(A/'artifacts/summary.json'),read(B/'artifacts/summary.json')
rows=[]
for provider,s in [('DeepInfra FP8',a),('Parasail FP8',b)]:
 for arm,label in [('baseline','기존 r3'),('guarded','수정 후보')]:
  t=s['totals'][arm];rows.append(f"| {provider} | {label} | {t['physical_calls']} | {t['provider_429_responses']} | {t['gold_by_stage']['read']}/{t['gold_total']} | {t['gold_obtained']}/{t['gold_total']} | {t['gold_by_stage']['answer']}/{t['gold_total']} | {t['partial_graphs']} |")
large=[]
for provider,s in [('DeepInfra',a),('Parasail',b)]:
 for row in s['rows']:
  g=row.get('graph')
  if row['arm']=='guarded' and g and g['roots']:
   large.append(f"| {provider} | {row['case_id']} | {g['roots']} | {g['sources']:,} | {g['states']:,} | {g['pending']:,} | {g['status']} |")
calls=a['usage']['physical_calls']+b['usage']['physical_calls'];cost=a['usage']['cost_usd']+b['usage']['cost_usd'];overload=sum(t['provider_429_responses'] for s in (a,b) for t in s['totals'].values())
report=f'''# Gemma 실제 탐색 실험 결과 — 2026-09-22

## 결론

**현재 수정안은 회수 성능 유지와 탐색 폭발 해결을 통과한 상태가 아니다.** Gemma 호출과 경로 실행은 수행했지만 공급자 과부하가 반복되어 정상 조건의 품질 비교는 보류한다. 동시에 실제 채택 시작점에서 원문 묶음이 크게 확장되는 문제와 시간 초과 후 정리 오류를 재현했다. MAIN·활성 DB·GENOS는 변경하지 않았다.

## 실험 조건

- 공개 질문 6개: fsc-hard-009, cm-025, cm-015, cm-040, cm-009, cm-013. 이전 ADR0521에서 해시로 정한 표본을 유지했다.
- 공개 문서145개. 원문 store가 동일한 기존/수정 DB를 사용했다. 질문·법령 외 내부자료와 기준답변은 모델 입력에서 제외했다.
- Gemma `google/gemma-4-31b-it`, FP8, thinking off, temperature0. 질문당 최대14회, 요청300초. 각 실험3작업자, 외부420초 감시. 기준은 선택된 r3 전체 실행 경로, 후보는 ADR0522 rev002와 수정 DB이다.
- DeepInfra의 반복429 이후 별도 ADR0524에서 Parasail만 고정했다. 실행 중 공급자나 모델 자동 대체는 없다. 두 공급자 실험은 일부 시간 동안 같은 WSL 호스트에서 겹쳤으므로 지연은 독립 비교 지표로 사용하지 않는다.
- 과거 후보 풀을 넣지 않고 모델이 질문 계획·검색·읽기·시작점 판단·관계 탐색·답변 단계를 수행했다. 과거90/90의 대량 회수 루프와 동일한 평가가 아니다.
- 총 실제 요청 **{calls}회**,429 응답 **{overload}회**. 응답에 기록된 비용 합계 **${cost:.5f}**. 실패·시간 초과의 누락 사용량은 별도 확인 필요하다.

## 실제 관측값

아래 기준 근거는 질문별 필요한 **조 원문10건**이다. 항·호의 필요한 구절이 전부 전달됐다는 점수나 답변의 법률적 정답 점수가 아니다. 공급자 장애가 섞인 관측값이므로 수정 전후의 인과적 성능 차이로 해석하면 안 된다.

| 공급자 | 조건 | 호출 |429| 서버가 읽은 기준 원문 | 성공 응답 호출에 제시된 기준 원문 | 답변 인용 기준 원문 | 미완료 연결 묶음 |
|---|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## 실제로 커진 연결 묶음

| 공급자 | 질문 | 채택 시작점 | 보존 원문 | 범위·경로 상태 | 남은 상태 | 상태 |
|---|---|---:|---:|---:|---:|---|
{chr(10).join(large)}

DeepInfra cm-009의 시작점 두 개는 각각 원문23블록/10블록 전체를 진입 범위로 사용했다. DB source의 전체 블록 수와도 같다. 5,188개의 기록된 이동은 모두 DB_REFERENCE였으며 정방향2,909·역방향2,279였다. 동일 관계 왕복 차단도354회 동작했지만1,027개 원문까지 확장됐다. 따라서 이름 유사도로 새 연결을 만든 것만의 문제가 아니며, 진입 범위가 넓을 때 DB의 재귀 연결 자체도 커질 수 있다. 각 연결 원문의 쟁점상 필요성은 이 수치만으로 확인되지 않는다.

## DB 수정 상태 재확인

수정 DB가 실험에 실제 사용된 것은 기존/후보 runtime binding과 navigation manifest 해시로 확인했다. 기존 해시는92b972df…이며 후보는c2a765f6…이다. 관계 행은146,994→133,727개로 바뀌었다. 다만 이 사실은 관계 의미가 모두 검증됐다는 뜻이 아니다.

추가 읽기 전용 감사에서 공개 관계133,116건 중 대상 좌표가 연결됐지만 관계 종류UNKNOWN인 행43,363건, 블록 단위 '준용 단서' 표시와 현재 참조의 역할이 일치하지 않는 행7,213건을 확인했다. 이 수치는 오류 정답 건수가 아니라 검토가 필요한 상태/표시의 집계다. UNKNOWN을 이유로 연결을 일괄 제거해서도 안 된다.

실제 예에서 원문은 '제13조제9항에 따라 … 이 경우 제6항 단서를 준용한다'인데 제13조제9항 행에도 '준용 단서'가 남아 있었다. 해당 행의 reference_role은UNKNOWN이며, DB가 제13조제9항을 확정된 준용 관계로 저장했다고 단정할 수는 없다. 참조 좌표 정확도, 관계 종류/표시 정확도, 질문에 필요한 탐색 범위는 각각 검증해야 한다. 따라서 **DB 수정 완료를 전제로 탐색 로직만 원인이라고 결론 내릴 수 없다.**

감사 자료: [실행 DB와 관계 상태]({B/'artifacts/db-loaded-and-role-audit.json'}).

## 추가로 확인한 결함과 다음 수정 기준

| 항목 | 확인한 근거 | 수정 기준 |
|---|---|---|
| 전문검색 색인 연결 누락 | 새 관계 DB에서도 전문검색 설정이 이전 navigation 해시에 묶여 있어 matcher.fulltext가None | 세대 생성 시 관계·전문검색·서비스 설정의 연결 해시를 함께 검증. 이번 실험에서는33,443건의 색인 입력이 완전히 같음을 확인하고 새 실험용 세대에 연결 정보를 수정했다. |
| 시작점 범위가 너무 넓음 | 채택은 조 원문 단위이며 protected_graph에 실제 읽은 전체 블록이 전달됨 | 시작점의 담당 쟁점과 탐색 진입 항·호·목을 명시하고, 조 전체 원문 보존과 분리. 근거가 필요한 다른 범위는 명시적 확장 판단을 기록. |
| 유효한 DB 연결도 큰 묶음 형성 |2개 시작점에서1,000개 이상 원문 및 PARTIAL frontier | 사용자가 요구한 하위 정·역참조 탐색은 유지. 범위 전달·참조 원문·관계 상태를 감사하고, 미완료 frontier를 완결된 근거로 표시하지 않는다. 임의 개수 제한으로 회수 성공을 만들지 않는다. |
| 질문 계획이 도구 실행 전 거절됨 | 답변 쟁점과 문맥에 같은 question_ref 배정 | 모델의 계획 오류를 원문 범위 손실 없이 수정하도록 피드백 계약을 검증. DB 회수 실패와 분리 집계. |
| 시간 초과 후 정리도 중단됨 | relations_session.metadata → covers → store.source에서 SQLite interrupted | 시간 종료 시 이미 확보한 근거·미완료 범위를 안전하게 반환하도록 정리 경로 개선. deadline 이후 재조회가 계속 필요한 구조를 검토. |
| 필수 관계 검토가 모델 입력에 안 들어감 | required relation review does not fit view 오류 | 큰 원문 묶음의 서버 보존과 모델의 검토 페이지를 분리하되, 미검토·보류 상태와 실제 전달 증거를 남김. |

현재 실험은 위 결함을 확인한 기록이며, 이 후속 수정의 구현·성능 검증까지 완료했다는 의미가 아니다. 회수90/90을 강제하지 않으며 실제 놓친 근거·놓친 단계·추가 탐색 필요성을 설명할 수 있어야 한다.

## 재현 자료

- [DeepInfra 실행 기록]({A/'README.md'})
- [Parasail 실행 기록]({B/'README.md'})
- [시작점2개→1,027개 진단]({A/'artifacts/large-closure-diagnosis.json'})
- [전문검색 연결 수정 근거]({A/'artifacts/fulltext-rebinding.json'})
- [최종 관측값]({B/'artifacts/summary.json'})

원시 요청·응답·스키마·usage·SQLite journal과 오프라인 회수 원장은 각 ADR artifacts에 보존했다. 큰 graph는 별도 gzip 파일로 분리되며 재조립하면 원래 묶음 hash를 복원할 수 있다. 두 ADR은 in-sample probe이고 decision_eligible=false다. MAIN 승격이나 GENOS 현장 성능 인증 근거가 아니다.
'''
p=R/'07_DOCS/REFERENCE/REPORTS/GEMMA_SCOPED_EXPLORATION_RESULT_20260922.md';p.write_text(report);print(p)
