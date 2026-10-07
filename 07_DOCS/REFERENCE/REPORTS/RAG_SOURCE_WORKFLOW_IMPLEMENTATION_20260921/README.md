# 원문 선택 흐름 구현·Qwen 실험 결과

## 현재 결론

구현과 중간 검사를5개 독립 후보 실험으로 진행했다. 최신 후보는28개 계약을 수정본/frozen revision에서 통과했다. 최신 CM018은 발견240→읽기1→모델전달1→선택1→게시원문1, 기준답 일치1/1이다. 전체 재설계를 완성하거나 운영 MAIN으로 승격한 상태는 아니다.

## 구현한 것

- 모델은 전달된 원문의 source와 KEEP_CORE/KEEP_SUPPLEMENTAL/DEFER/REJECT를 고른다. 정확 span·좌표·원문 해시는 서버가 결속하고 독립 검토 전 REVIEWED를 허용하지 않는다.
- 한 요청의 잘못된 도구 동작 때문에 정상 원문 선택까지 잃지 않게 했다. 구조화 오류와 실제 도구 ERROR를 수정 재시도로 연결했다.
- 발견한 새 후보를 진행으로 세고, 읽기0 상태에서 후보를 남긴 채 초안으로 넘어가는 것을 거부했다.
- 입력 크기를 마지막 metadata/cursor까지 계산하고, 주장 ID와 내용을 같은 검토 카드로 제공했다.
- immutable 원본 반출 속성과 실험별 공개 전송 승인을 분리해 기존 게시 검사와 결속했다. 원본 속성은 바꾸지 않았다.
- 일부 문단을 가리키는 ID라도 article 읽기 요청이면 canonical 조 전체 범위를 읽는다. 남은 페이지가 있으면 미완료로 표시한다.
- 서버가 원래 대상·범위·cursor를 묶은 다음 페이지 동작을 제공하고, cursor를 target으로 사용한 오류에 실행 가능한 수정 동작을 돌려준다.

## 실제 실험 결과

| 단계 | 계약 검사 | 신규 제품 실행 | 출처 있는 결과 | 검토 답변 | 기준답 일치 | 신규 제품/평가 호출 |
|---|---:|---:|---:|---:|---|---:|
| [ADR-0489](../../../../04_EXPERIMENTS/ADR/ADR-0489-source-workflow-recovery-qwen/README.md) | 16 | 12 | 5/6 | 0/6 | 0/6 (원평가2건 오인) | 91/6 |
| [ADR-0490](../../../../04_EXPERIMENTS/ADR/ADR-0490-source-workflow-packing-review-repair/README.md) | 19 | 3 | 2/3 | 2/3 | 1/3 | 20/6 |
| [ADR-0491](../../../../04_EXPERIMENTS/ADR/ADR-0491-source-tool-error-repair-cm018/README.md) | 21 | 1 | 1/1 | 0/1 | 0/1 | 14/2 |
| [ADR-0492](../../../../04_EXPERIMENTS/ADR/ADR-0492-source-article-read-scope/README.md) | 25 | 1 | 1/1 | 0/1 | 0/1 | 10/2 |
| [ADR-0493](../../../../04_EXPERIMENTS/ADR/ADR-0493-source-continuation-repair/README.md) | 28 | 1 | 1/1 | 1/1 | 1/1 | 14/2 |

출처 있는 결과·검토 답변·정답은 후보 기준이다. ADR0489의 신규 제품12회는 기준6+후보6이고 이후 기준은 과거 실행을 상속했으므로 새 호출로 중복 계산하지 않았다. 게시 JSON 성공에는 빈 결과도 포함될 수 있어 위 표는 출처가 실제 있는 결과를 별도로 센다. ADR0489의 원시 평가 정답2건은 출처카드를 답변으로 오인한 false positive이며 원시 지표를 덮어쓰지 않고 감사에서 분리했다. 이후는 답변/출처 평가를 분리했다.

## 중간 확인에서 찾아낸 추가 문제

- 모의 계약 통과가 실제 질의 성공을 보장하지 않았다. 실제 실행을 단계별로 추적하면서 입력 포장, review ID, READ 범위, 페이지 토큰 문제를 추가로 확인했다.
- ADR0491의 제49조 전체 READ는30블록4,602자 중 제4항1블록307자만 반환하면서 완료로 표시했다. ADR0492에서 서버 범위를 수정했다.
- ADR0492는 원문20개를 전달했지만 cursor를 target에 넣는 오류를 복구하지 못했다. ADR0493은 전달 계약과 복구 안내를 수정했다.
- 법률 검토 모델이 승인한 주장도 기준답과 틀릴 수 있다. ADR0490 CM003이 해당하며 검토 성공을 법률 정답으로 취급하지 않았다.
- source ID 단위 gold hit는 관련 문단 확보와 다르다. 항·호 수준 정답 범위 평가는 추가로 필요하다.

## 남은 설계와 확인 범위

원래 설계48개 시나리오 전체를 통과한 상태가 아니다. 질문의 법령명/약칭과 조 좌표를 안정적으로 찾는 경로, 이미 제시했다가 화면에서 빠진 handle 복구, canonical 조 단위 evidence/page 병합, 미완료 탐색 목록과 종료조건, 모든 큰 입력의 재분할, 오류 resolved/exhausted 생명주기, 인증된 resume·feedback·service bridge는 남았다. 기존 “원문 미평가” 상태표시와 새 source_selection의 연결도 완전하지 않다. 조 전체 범위·cursor 복구의 모의 검사와 실제 Qwen에서 해당 경로를 사용한 횟수는 각 audit에서 구분했다.

후보는 기존 session→outbox→publication 경로를 연구 runner로 실행했다. HTTP/Open 연결은 모의 검사이며 실제 GENOS 화면·내부 모델·권한은 검증하지 않았다. Qwen 소표본 인샘플 결과를 일반 성능으로 추정하지 않는다.

## 비용과 재현성

신규 Qwen 호출 시도는 제품149+평가18=167회, 반환된 provider usage 합계 비용은 $1.16422540이다. 상속 기준 비용은 제외했다. 최신 제품14회 중 연결 실패1회는 usage가 없고 이 합계는 확인된 usage만 센 것이다. 원문은 공개145문서 승인 범위, Qwen3.5-122B FP8 thinking off, 자동 fallback 없음. 실제 request/response·모델/provider·토큰·비용·시간·hash·실패원본은 ADR별 보존했다.

다른 작업의 공통 코드변경으로 막힌 첫 전송 전 시도2회는 모델0호출이었다. 공통 runtime/config도 별도로 고정해 계속 실행했고 다른 작업자의 파일을 덮어쓰지 않았다. 최신 후보와 부모들의 계보·실행 hash를 고정했으며 운영 활성 포인터를 이 작업으로 변경하지 않았다.

## 찾아볼 파일

- [최신 구현과 검사](../../../../04_EXPERIMENTS/ADR/ADR-0493-source-continuation-repair/IMPLEMENTATION.md)
- [최신 실험 결과](../../../../04_EXPERIMENTS/ADR/ADR-0493-source-continuation-repair/README.md)
- [페이지 안내·사용 감사](../../../../04_EXPERIMENTS/ADR/ADR-0493-source-continuation-repair/artifacts/continuation-audit.json)
- [조 전체 범위 감사](../../../../04_EXPERIMENTS/ADR/ADR-0493-source-continuation-repair/artifacts/article-scope-audit.json)
- [원래 설계](../RAG_SOURCE_WORKFLOW_REDESIGN_20260921/DESIGN.md)
- [초기48개 시나리오 구현범위 감사](../../../../04_EXPERIMENTS/ADR/ADR-0489-source-workflow-recovery-qwen/artifacts/coverage-map.json)

ADR별 최종 구조검사를 수행했다. 전체 graph 검사에는 이 작업 전부터 있던 ADR0305 run-purpose, ADR0444 parent, ADR0158 missing-source3개 오류가 남는다. unrelated 과거 실험을 수정해 숨기지 않았다.

후속 실행: [동일 최신 코드의 CM003·CM038 결과](OTHER_CM_RESULTS.md) — CM003 실패, CM038 통과. 이전5개 실험 집계와 분리했다.

- [후속: 소량 연결 자동 전달 CM3 실행](RELATION_DELIVERY_RESULTS.md) — 자동 읽기7건 전달, 답변0/3.
