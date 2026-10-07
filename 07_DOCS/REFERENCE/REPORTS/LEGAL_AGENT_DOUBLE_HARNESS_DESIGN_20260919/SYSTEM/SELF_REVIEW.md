# 시스템 상세 설계 자체 검토

작성자와 같은 에이전트가 코드·계약과 다시 대조했다. 독립 검토, 품질 인증, 배포 승인이 아니다. 대상은 [시스템 상세 설계](SYSTEM_DESIGN.md)와 이 폴더의 부속물이다.

| 항목 | 발견한 구현상 문제 | 반영한 설계 |
|---|---|---|
| schema 배선 | pipeline-v1 contract에 schema_id를 추가하면 additionalProperties 위반 | hash 검증한 schema_path 파일의 `$id`를 캐시하여 validate_port에서 사용 |
| 전송 횟수 | genos.request_json의 max_retries는 실제로 총 시도 수 | 한 번 전송은 값 1. 신규 transport에는 숨은 재시도 없음 |
| 시간 제한 | read timeout이 총 시간 제한을 보장하지 않음 | 요청별 async transport에 total deadline, 원격 취소/청구 한계 표시 |
| revision | 전송 예약 로그 때문에 정상 모델 응답이 stale이 될 수 있음 | event.seq와 state_revision 분리 |
| 철회 | 근거의 전역 adopted 플래그로는 issue별 판단 철회 불가 | assessment version과 역방향 dependency 무효화 |
| 판단 원자성 | 일부 updates만 적용하면 의존 관계가 깨짐 | batch 전체 검증/임시 ID 해소/CAS/transaction |
| 읽기/채택 | 아직 실행하지 않은 tool의 예상 결과를 채택할 위험 | updates commit 뒤 reads, 새 observation은 다음 view에서 판단 |
| 문장 검증 | free-form text가 구조화 claim 밖의 주장을 포함할 수 있음 | 전체 답변 문장을 paragraph claims로 등록 |
| 쟁점 제외 | NOT_APPLICABLE로 중요 쟁점을 검토 없이 제거할 수 있음 | coverage purpose claim으로 검토 전 종료 제외 금지 |
| 질문 사실 | 사용자가 말하지 않은 사실을 모델이 채워 넣을 수 있음 | stated는 질문 exact span, unknown은 명시적 미확인 |
| 기존 endpoint | ask만 바꾸면 search/links/health에서 adapter 호출이 깨짐 | get_index/config/retrieve(source-only) 유지 |
| 단계 재실행 | retrieve 재실행마다 query_id가 바뀜 | RequestContext에 query 고정 |
| 출력 포트 | answer에 control 추가하면 첫 포트 기반 로그가 잘못됨 | result/control slot 선언과 명시적인 result 소비 |
| 응답 저장 | journal 완료와 기존 run JSON 저장 사이의 crash | publication outbox와 동일 hash의 idempotent export |
| 파일 원자성 | os.replace만으로 no-clobber를 보장할 수 없음 | durable 임시 파일+원자적 no-clobber 설치+hash 충돌 검사 |
| 다중 worker 복구 | boot ID가 다르다고 실행 중 요청을 중단 처리할 위험 | 요청 lifetime owner lock, scanner는 lock 획득한 run만 처리 |
| 오류 분류 | 모델 JSON 오류가 전역 ValidationError handler에서 422가 됨 | 입력/모델/내부 계약 오류를 typed exception으로 분리 |
| 검증 범위 | DDL 실행이나 schema 검사가 제품 동작 검증으로 오인될 수 있음 | 검사 결과에 product controller/model/GENOS 실행 0 명시 |

미완료·미확인 사항:

- repository, controller, tool adapters, gateway, publisher 제품 구현과 통합 검사는 아직 없다. `interfaces.py`는 Protocol 선언, `wiring-plan.json`은 배포 불가능한 blueprint다.
- SQL CHECK/FK/trigger는 hash 실제 일치, span 원문 일치, dependency의 다단계 cycle, 모델 가시성, 의미적 지지 관계를 검증하지 않는다. repository와 source adapter 구현 책임으로 명시했다.
- JSON Schema는 메시지 모양을 검사한다. FINAL과 gate의 조합, 사실 span의 의미, claim과 finding의 관계, stale 처리 등 교차 상태 검사는 별도 코드가 필요하다.
- SQLite의 fsync/lock, publication의 crash 복구, async 취소, 다중 요청 격리는 설계했지만 실제 환경에서 검증하지 않았다. in-memory SQLite 검사로 이를 통과했다고 선언하지 않는다.
- 물리 모델 시도 상한과 provider 청구 횟수는 같지 않다. timeout은 usage unknown일 수 있고 원격 생성은 계속될 수 있다.
- context 문자 상한은 model token 한도가 아니다. 배포 모델별 tokenizer/serving 상한과 한국어 입력의 실제 token 수 검사가 필요하다.
- 수치 profile은 초기 배선 가정이다. 정확도·p95·비용·구현 일정 개선을 예측한 값이 아니다.
- 동일 모델 reviewer는 독립 정답 판정자가 아니다. 근거를 찾아도 해석을 틀릴 수 있으며 별도 평가가 남는다.

자료 갱신: 작성 중 기존 `FINAL/sources.json`의 S26(ADR-0473 README)이 바뀐 것을 감지했다. 새 README는 작업 완료 및 기본 미채택 결론을 기술한다. 기존 FINAL 문서의 당시 snapshot을 덮어쓰지 않고 SYSTEM/sources.json에 이번 읽기 시점 hash를 기록했다. 이 상세 설계는 새 점수를 성능 근거로 전용하지 않는다. 새 ADR의 원시 결과 전체를 이번에 재집계한 것은 아니다.

검사 결과는 [validation.json](validation.json)에 기록한다. 문서/SQL/프로토콜 수준의 통과이며 제품 연결 완료나 MAIN 승격을 뜻하지 않는다.
