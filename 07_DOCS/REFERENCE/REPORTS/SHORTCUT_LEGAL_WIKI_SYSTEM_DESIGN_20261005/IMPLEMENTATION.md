# 구현·이행·검증 계획

[전체 설계](README.md) · [데이터 계약](CONTRACTS.md) · 아래 작업은 설계이며 아직 실행하지 않았다.

## 1. 실제 실행 경로와 변경 경계

현재 작업 v6의 법률 질문은 `service/service.py → service.py → semantic_runtime.app → Pipeline → coordinator.run_case → unified_runtime.run/execute → CaseRepository + NativeRag`를 따른다. 선택 프로필에 따른 분기가 있으며 인사·목록 등 모든 요청이 일곱 조사 단계를 거치는 것은 아니다. native WorkRepository와 사건 DB·publication이 연결된다.

이 진입점을 유지한다. v6 밖의 기존 memory-v2·action-memory·query-shortcut·Markdown 위키는 명시적 import adapter로 연결하고 각각을 새로운 온라인 정본으로 병렬 운영하지 않는다. 이행 기간의 조회 범위와 source 우선순위는 manifest로 고정한다.

다음 표의 경로는 저장소 기준이다. 신규 모듈 이름은 제안이며 실제 파일을 만든 상태가 아니다.

| 파일·함수 | 변경 책임 | 입력 → 출력·소비자 |
|---|---|---|
| `service.py`, `service/service.py`, `semantic_runtime/app.py` | 기존 인증·요청 계약 보존, 사건 ref·상태 노출 | 신뢰된 principal/요청 → pipeline; 결과 → 기존 UI |
| `semantic_runtime/pipeline.py`, `legal_agent/coordinator.py` | 공통 memory context를 먼저 취득하고 단일 실행 진입 유지 | 요청 → 수신 receipt/현재 사건 → run_case |
| `legal_agent/unified_runtime.py::open_cases/execute` | v4 repository 선택, 저장·조사·게시 커밋 조정, 재개 | run/사건 revision → 답변·outbox |
| `legal_agent/case_repository.py` | v3 호환 adapter와 v4 사건·발언·정정·잠금·outbox 계약 | 모든 기록 생산자 → shortcut authority |
| 제안 `legal_agent/shortcut_repository.py` | 추가 테이블·상태·CAS·cursor·이행 공통 repository 인터페이스 | DB → 사건/기록/지식 현재 상태 |
| 제안 `legal_agent/conversation_linker.py` | 세션 간 사건 연결·갈래/쟁점 배정 제안 | 명시 참조·후보·발언 → 근거 있는 연결 proposal |
| `legal_agent/corrected_memory.py`, `memory_methods.py` | 단일 goal 중심 resolver를 새 사건 명령으로 변환; FINALIZE는 확인 이벤트 | 사용자 정정 → typed fact revision·영향 계산 |
| `legal_agent/repository.py::record_observation`, `journal-v6.sql` | 실제 도구 목적·계약·원결과·판단 연결 보완 | 실행 → trace refs; 기존 불변 journal 호환 |
| `legal_agent/unified_rag.py::rebind`, `memory_rag.py` | 사용 모드별 부분 재사용·durable source 재결속 | reuse plan → 기존 조사 단계와 신규 native 판단 |
| `legal_agent/domain_control.py` | 도구·방법의 승인 계약 및 호환성 검사; 새 법률 개념 자동 승인 금지 | 현재 catalogue·정책 → 실행 허용 결과 |
| 제안 `legal_agent/reuse_policy.py` | 조건·현재성·권한·검증·예산 검사, 사용 영수증 | knowledge revision → HINT/PROCEDURE/JUDGMENT/REJECT |
| `legal_agent/knowledge_repository.py` | 경험 목록 투영에서 지식 단위·revision·조건 조회로 확장 | scoped query → 정본 지식과 출처 |
| 제안 `lawrag/pipeline/legal_wiki_compiler.py` | 분절·결합·완결성·근거 검사 및 새 revision 구성 | shortcut watermark → draft/published build |
| `lawrag/pipeline/action_memory.py::build/main` | 기존 스케줄·lock·시간 예산 안에서 새 compiler mode 호출 | 큐 → 제한된 작업 receipt |
| `lawrag/pipeline/legal_llm_wiki.py` | 불변 raw·index/log·철회 overlay 패턴 재사용; 새 renderer adapter | wiki revision → Markdown/JSON projection |
| `lawrag/pipeline/unified_memory.py::migrate/main` | 새 스키마·레거시 종류별 이행·복구·재구축 진입 | 명시 snapshot → import mapping/receipt |
| `00_SYSTEM/PIPELINE.json`, 새 스키마·v6 profile 후보 | 선언·실제 dispatch 일치, feature config·producer/consumer 연결 | 명세 → 검증 가능한 실행 경로 |

표의 backend 상대 경로는 `02_BACKEND/` 아래다. `CaseRepository`를 즉시 제거하지 않는다. 기존 public 인터페이스를 adapter로 유지하며 새 repository에 책임을 이전한다. 기존 메서드와 테이블을 한 번에 중복 구현하는 대형 교체를 피한다.

## 2. 작업 패키지와 완료 조건

| 단계 | 산출물 | 선행 조건 | 종료 조건 |
|---|---|---|---|
| P0 기준 고정 | 실제 실행 명령·profile·source 세대·store 위치·기능 flags manifest, 데이터 보존 정책 | 현행 코드 조사 | 후보가 운영 경로에서 자동 선택되지 않음 |
| P1 지속 기록 | v4 schema, intake, artifact 참조, outbox, reconciliation | P0, 단일 writer·내구 저장 확인 | 분류 실패·중단·재시도에도 수신 기록과 원본 참조 유지 |
| P2 사건·정정 | investigation/branch/issue, typed facts, cross-session linking, dependency | P1 | 새 세션 계속·갈래 분리·정정 취소·충돌 처리 검증 |
| P3 지식 구성 | compiler, claim/procedure 계약, 완결성·검증 receipt, draft index | P2 | 원기록 추적 가능한 분절·결합; 비공개 범위 유지 |
| P4 조회·힌트 | KnowledgeRepository 변경, exact lookup, source currentness, 사용자 설명 | P3 | wiki 미존재·실패 시 기존 조사 완료, 힌트와 판단 혼동 없음 |
| P5 절차·판단 재사용 | reuse policy, typed tool executor, 부분 재계산·재결속 | P4, 계약·품질 평가 | 오적용 차단 및 효과 기준 통과; 사용 모드별 승인 |
| P6 운영·현장 | 증분 배치, 모니터링, 백업/복구·이행/원복, GENOS 인계 | P1~P5의 해당 활성 범위 | 실제 workflow 화면 검증·receipt 확보 |

핵심은 P1~P3이다. 지식이 만들어지는 기반을 완성한 뒤 P4~P5를 켠다. user_wiki 전용 서비스, 그래프 DB, 별도 vector DB, 새 독립 실행기, 전 대화 전수 LLM 재해석은 첫 구축의 필수 항목으로 두지 않는다.

## 3. 단계별 검증 계약

| ID | 검증 상황 | 기대 결과·검사 대상 |
|---|---|---|
| C01 | 동일 요청 재전송 / 같은 키의 다른 본문 | 이벤트·모델 실행 중복 없음 / 충돌 반환 |
| C02 | 수신 저장 뒤 분류 모델 실패 | 원발언 유지, 미배정 상태로 재개 |
| C03 | 세션 A·B에서 같은 사건 계속 | 명시 연결에만 같은 investigation, 각각 session provenance |
| C04 | 비슷한 회사·동일 개념의 별개 사건 | 사실·권한·정정 상속 없음 |
| C05 | 한 발언에 여러 질문·정정 | 정확한 span별 배정, 공통 근거 참조 가능 |
| C06 | 같은 사실 동시 정정, 오래 걸린 답변 도착 | CAS 충돌, 최신 revision 덮어쓰기·잘못된 게시 없음 |
| C07 | 정정 철회 및 최초 발언 복원 | 새 복원 이벤트, 원기록·이전 판단 보존, 필요한 부분 재계산 |
| C08 | 잘못 합친 사건·지식 분리 | 연결 철회와 lineage 유지, 파생 head 재생성 |
| C09 | 위키 생성 중 새 정정 | 오래된 build의 현재본 게시 거부; 최신 입력 재큐잉 |
| C10 | 원문 변경·참조 삭제·권한 철회 | 관련 주장만 STALE/차단; 조회·게시 시 확인 |
| C11 | 사용자 확인했지만 법령명 오류 | confirmation 유지, source verification 실패, 판단 재사용 차단 |
| C12 | 과거 이유·source binding 누락 | NOT_RECORDED/LEGACY_UNBOUND 유지, 정답 승격 없음 |
| C13 | 저장된 tool name·입력 조작 또는 구 schema | 도구 실행 전 거부, 현재 PLAN으로 재진입 |
| C14 | 중단 위치별 장애 주입 | journal 전/후, DB commit 전/후, 게시 전/후 각각 정확한 복구 |
| C15 | projection 삭제·실패, 색인 지연 | 정본 보존, 증분/전체 재생성, stale 조회 방지 |
| C16 | 긴 이력·명시된 예전 정정 참조 | 페이지/cursor·정확한 이벤트 조회, 요약만으로 원문 대체 안 함 |
| C17 | tenant/사용자/팀/문서 범위 교차 | 검색·exact ID·artifact·오류 응답 모두 접근 차단 |
| C18 | 백업·복구·writer 재시작 | DB+artifact+cursor 일관성 검증, 유실·중복 이벤트 탐지 |
| C19 | 배치 중 반복 실패·예산 소진 | 재시도 상한·격리 큐, 다음 작업 진행, 실패를 완료로 처리 안 함 |
| C20 | 위키 없이 또는 feature off 상태 | 기존 RAG 경로 정상; 새 기록의 자동 폐기 없음 |

이 검사는 구현 계약·회귀 확인이다. 법률 정답률이나 속도 개선을 증명하려면 아래 별도 실험이 필요하다. 이번 문서 작성에서는 검사 코드를 구현하거나 런타임 검사를 실행하지 않았다.

## 4. 법률 품질·속도 평가 설계

실제 비교를 시작할 때는 저장소 실험 표준 두 문서를 끝까지 읽고 ADR을 선점한다. 부모 pipeline/arm, 코드·데이터·모델·프롬프트·정책·평가 기준을 결과 전에 동결한다. 새 실험의 외부 모델은 당시 정본 정책을 다시 확인하고 공통 ExperimentClient를 사용한다. 현재 사용자 정책은 Qwen3.8/Parasail FP8/reasoning none/fallback 없음이다. 비공개 대화·내부 자료는 해당 외부 승인에 포함되지 않는다.

비교 arm 제안: 기준 v6, 지속 기록만, 기록+wiki 힌트, 기록+wiki 절차, 검증 판단 재사용. 여러 기능을 한꺼번에 넣고 어느 변화가 효과를 냈는지 모르는 비교를 피한다. 후보와 기준에 같은 자료·질문·실행 환경·예산을 사용한다.

독립 평가 단위는 사건·쟁점·근거 문서군이다. 같은 사례의 표현 변경·멀티턴 변형은 한 family로 묶고 train/build와 holdout에 나누어 넣지 않는다. 평가 질문의 정답·후속 가이드를 wiki compiler 입력으로 먼저 주는 누출을 막는다. 원문 시점·예외·정답 조건을 검토한 별도 평가 계약을 둔다.

| 영역 | 지표·분모 | 반드시 분리할 항목 |
|---|---|---|
| 분절·연결 | 검토된 쟁점 경계·사건 연결 중 정확한 비율, 빠진 필수 맥락 수 | 잘못 합침과 과도한 분리 |
| 지식 구성 | 주장별 원문·이유 추적률, 조건·예외 누락, 상충 탐지 | 실제 검증과 형식 필드 존재 |
| 재사용 | 허용 가능한 후보 recall, 잘못된 조건 승인율, 오래된 주장 채택 | HINT/PROCEDURE/JUDGMENT 각 모드 |
| 법률 답변 | 독립 사례별 전체 성공, 주장 정확도, 잘못된 법령명·예외·인용 | 핵심 결론 맞음과 전체 답변 맞음 |
| 지연 | 수신~완료 wall time의 분포, stage latency, 첫 표시 시간 | miss/hit, 초기/반복, 로컬/GENOS |
| 비용 | 실제 모델 입출력 토큰·호출별 금액, 저장·배치 자원, 검토 시간 | online과 compiler·재검증 운영 비용 |
| 운영 | 유실/중복/권한 위반, 큐 지연, 복구 성공, DB lock 대기 | 단일 writer와 다중 인스턴스 |

수신 유실·권한 교차·중복 효과·알려진 stale 판단 채택은 필수 사례에서 허용하지 않는 설계 목표다. 유한한 검사에서 오류가 없었다고 실제 오류 확률을 0으로 선언하지 않는다. 법률 품질 허용 회귀, 지연 목표, 평가 표본 규모는 기준 측정과 업무 위험을 보고 실험 전에 수치로 확정한다. 이번에는 근거 없는 수치를 제시하지 않는다.

ADR-0619의 공개 두 사례는 이미 알려진 회귀 사례로만 포함한다. 새 holdout 성능으로 계산하지 않는다. ADR-0575의 야간 action-memory 온라인 연결이 속도 기준을 통과하지 못했던 이력을 고려해, 후보 탐색·context 크기·추가 모델 호출을 각각 계측한다.

## 5. 성능·비용·규모의 조건부 계산

아래는 설계 계산식이다. 아직 입력값이 없어 기대 절감률·개발 인일·월 비용은 미산정이다.

| ID | 변수·단위 | 종류·측정 방법 |
|---|---|---|
| F01 | N: 기간 내 요청 수, request/기간 | 미확인; 실제 입구 집계 |
| F02 | h: 안전하게 재사용된 비율, 적용 요청/전체 요청 | 미확인; reuse receipt와 평가 대조 |
| F03 | B: 기준 평균 online 비용, 금액/request | 미확인; 같은 요청 분포의 기준 측정 |
| F04 | S: 재사용 요청에서 줄어든 원래 작업 비용, 금액/적용 request | 미확인; 제거한 단계 실제 호출 비교 |
| F05 | V: 재사용 요청의 추가 적용 검사 비용, 금액/적용 request | 미확인; source/condition/verifier 비용 |
| F06 | O: 모든 요청의 새 기록·후보 탐색 비용, 금액/request | 미확인; miss에도 드는 비용 포함 |
| F07 | C: 지식 구성·색인·재검증·운영·검토 비용, 금액/기간 | 미확인; 별도 자원·검토 시간 집계 후 단가 적용 |

`새 총비용 = N × [B + O − h × (S − V)] + C`

`순절감 = N × [h × (S − V) − O] − C`

`S > V`일 때 손익분기 적용률은 `h > (O + C/N) / (S − V)`다. `S ≤ V`면 이 가정 아래 재사용으로 비용이 줄지 않는다. source 변경이 잦으면 C와 V가 커지고, 새 사건이 많으면 h가 낮아진다. compiler가 한 번 만든 단위를 여러 요청에서 쓰면 C/N은 줄지만 접근권한과 조건이 맞아야 한다.

금액 대신 모델 호출 수를 넣으려면 모든 항을 호출 단위로 별도 계산한다. 호출별 토큰·가격이 다르므로 호출 절감률을 금액 절감률로 바꾸지 않는다. 지연도 별도로 측정하며 비동기 compiler 시간을 online 요청에 합산하지 않는다. 평균 비용 식으로 p95 지연을 추정하지 않는다.

저장량은 `기간 내 신규 이벤트 수 × 평균 payload 크기 + 신규 artifact 바이트 + index·복제·백업 증가량`으로 측정한다. content hash 중복 제거율은 가정하지 않고 관측한다. 장기 기록량·문서 개정 빈도·동시 요청 수가 없으므로 SQLite 처리량 및 필요 장비 수는 미확인이다.

작업 일정은 P0~P6별 구현·계약 검사·이행·검토·현장 확인 시간의 실제 추정치를 합산한다. 현장 DB/디스크 결정과 내부 모델 검증이 선행되기 전 달력 일정을 확정하지 않는다.

## 6. 실패 대응·운영 책임

| 위험 | 탐지·전파 | 대응·담당 |
|---|---|---|
| 잘못된 사건 연결 | 서로 다른 subject/조건·수정 범위 충돌 | linker가 후보로 제한; 사건 관리자/사용자 정정으로 분리 |
| 잘못된 해석의 지식화 | claim·예외 검토 실패, 사용자 이의 | 해당 revision DISPUTED, reuse 차단, compiler 재검토 |
| 대규모 원문 개정 | source manifest/hash 변경 | 변경 의존만 invalidation 큐; serving은 매 요청 현재성 재검사 |
| compiler 지연·실패 | outbox lag·오류·예산 소진 | worker 재시도/격리; agent는 원문 조사 지속 |
| 저장 불가 | DB/artifact durable commit 실패 | 성공 저장으로 표시하지 않음; 원요청 키로 재시도 가능하게 실패 반환 |
| 다중 writer·잠금 | lease/CAS 충돌, lock timeout | 한 writer로 제한; 확장 필요 시 DB 서비스 이행 |
| 사용 권한·반출 변경 | query/publish 시 scope 검사 | 원자료부터 projection까지 차단·재생성; 저장관리 담당 |
| 로그의 비밀값 | tool adapter 허용 필드·민감정보 정책 | 인증키·토큰 원문 미저장; 내용과 오류 로그 모두 동일 정책 |

운영 화면은 `미처리 기록 수`, `wiki 갱신 지연`, `재사용 허용/거부 이유`, `미해결 쟁점`, `검증 실패`, `복구 상태`를 제공한다. 사용자에게는 “이전 A 사건의 조건을 이어받음”, “취득일 정정으로 이 판단을 다시 확인함”, “이전 자료가 바뀌어 원문을 다시 조사함”처럼 결과에 필요한 설명을 보여 준다.

수신·실행·compiler·답변 전체에 request/run/investigation/build ID를 연결한다. 운영 로그에 원문 대화 전체를 반복 복제하지 않고 권한 있는 trace 조회로 연결한다. 보존 기간은 원발언·도구 payload·projection·백업별로 정책화한다. 접근 제한·삭제 요청이 발생하면 파생 색인·artifact·백업까지 범위를 추적하고 승인된 보존/삭제 정책에 따른다. append-only는 정상 갱신 방식이지 무기한 개인정보 보존 명령이 아니다.

## 7. 기존 데이터 이행

1. 대상 runtime·v3 DB·native journals·legacy 종류를 사용자가 선택한 환경의 명시 manifest로 고정한다. 날짜상 최신 폴더를 자동 선택하지 않는다.
2. 쓰기와 일관된 snapshot을 만들고 원본 hash·행 수·artifact 존재·권한을 확인한다. 진행 중 journal은 live 파일 복사 대신 지원되는 snapshot/checkpoint 절차를 사용한다.
3. 새 v4 DB에 원문 기록부터 import한다. 모든 원 ID→신규 ID mapping과 source snapshot hash를 보존한다. 동일 snapshot의 재import는 멱등이다.
4. v3 session/goal은 독립 사건으로 우선 이관한다. 세션 간 같은 사건이라고 소급 추측하지 않는다. knowledge는 기존 USER_CONFIRMED 사실을 보존하되 새 source/interpretation 검증을 통과한 것으로 승격하지 않는다.
5. native journal은 trace·judgment ref로 연결한다. action-memory·옛 query-shortcut은 provenance 있는 legacy record/hint 후보로 이관한다. 기존 `LEGACY_UNBOUND`를 자동 사용 가능으로 바꾸지 않는다.
6. 같은 해석을 발견해도 원래 사건 기록은 보존하고 legal_wiki 후보 관계만 만든다. 이유가 없는 기록은 NOT_RECORDED로 남긴다.
7. 새 위키·검색 projection만 재구축한다. 문서 구조화·용어집·원문 generation을 이 작업 때문에 재생성하지 않는다. 용어 정본 수정이 필요한 경우 별도 기존 MAIN 절차로 처리한다.
8. 이행 검사와 원복 snapshot이 준비되면 writer를 잠시 정지하고 최종 delta를 이관·대조한 뒤 store pointer를 전환한다. 장기 dual write로 두 정본을 만들지 않는다.

현재 `unified-memory migrate`는 memory-v2/action-memory 입력만 지원하므로 위 절차를 그대로 실행할 수 없다. v3·native·query-shortcut importer와 차분 이행 receipt 구현이 먼저 필요하다.

## 8. 활성화와 롤백

코드가 구현됐다는 이유로 MAIN 승격하지 않는다. capture → draft compile → hint → procedure → judgment reuse를 별도 flags와 receipt로 전환한다. 동일 질문의 단계별 상태·품질·시간을 확인한다. PIPELINE 선언과 실제 요청 경로를 대조한다.

문제가 생기면 먼저 judgment/procedure 사용을 끄고 기존 RAG를 유지한다. 기록과 draft compiler는 원인에 따라 유지하거나 중지한다. DB 이행 자체를 되돌릴 때는 신규 기록을 export·검사하고 읽기 가능한 보존본을 확보한다. v3가 이해하지 못하는 v4 기록을 억지로 덮어쓰지 않는다. 호환 변환할 수 없는 새 기록은 read-only archive와 mapping으로 유지하고, 최신 정정을 잃은 과거 답변의 자동 재사용을 차단한다.

GENOS 인계에는 정확한 코드 리비전·설정·DB schema·source generation·단일 writer 조건·입출력 계약·백업·재개·원복 절차를 넣는다. 현장 명령은 `python3`를 사용하고 검증은 워크플로우 테스트 화면에서 한다. 코드 ZIP 적용, runtime store 이행, Git push, 코드서빙 리비전 배포, 실제 질문 성공은 각각 별도 receipt다.

## 9. 자체 검토와 완료 보고 기준

| 항목 | 이번 문서 상태 |
|---|---|
| 최신 사용자 정의 반영 | shortcut 지속 기록 선행, legal_wiki 후속 지식 구성, user_wiki 유보 |
| 코드·설계 차이 명시 | v3 동일 경험 투영과 새 지식 compiler 구분 |
| 저장·권한·정정·동시성 | CAS, 불변 참조, outbox, 부분 커밋 복구 명시 |
| 기존 기능과 연결 | 기존 service/pipeline/야간 작업·이행 진입점 확장 |
| 수치 근거 | 실측 없는 속도·정확도·인일 약속 없음; 조건부 산식 제공 |
| 검토 방식 | 작성자의 자체 검토; 독립 감독 검토 아님 |
| 이번 검증 범위 | 문서 링크·JSON 예시·근거 파일·수식·구조 일관성 확인 |
| 미실행 | 구현, 품질·속도 실험, DB 이행, 스케줄 생성, MAIN/GENOS 활성화 |

미래 구현 완료 보고는 저장 성공, 지식 구성 성공, 온라인 사용 성공, 법률 품질, 성능, 현장 배포를 따로 명시해야 한다. 하나가 성공했다고 나머지까지 완료 처리하지 않는다.
