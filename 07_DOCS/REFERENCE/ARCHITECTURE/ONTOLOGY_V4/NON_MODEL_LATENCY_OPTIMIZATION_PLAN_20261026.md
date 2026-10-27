# 모델 밖 처리 시간 상세 측정과 최적화 구현 계획

<!-- MAIN104_SQL_FOLLOWUP -->
**2026-10-27 — MAIN105 반영·실제 서비스 확인 완료:** [전체 반영·실제 실행·온톨로지 후속](MAIN_SQL_AND_ONTOLOGY_FOLLOWUP_20261027.md). 최초211초 원인의 MAIN104 SQL 수정에 반복 원문 확인 재사용과 네 연결 TEMP VIEW의 ID 점조회를 더했다. 보관응답1회 재생의 동일 계측35화면736.500→93.718초(87.275% 감소), 원문·행동·최종 답변 동일, 새 모델 호출0회다. 신규237조건·관측보조1,345조건을 구분한 ADR1081 검증 후 MAIN105 `navigation-validation-20261027-r1`을 선택했고 실제 서비스19확인(HEALTH·모의 HTTP1회·새 모델0회)이 통과했다. 작업 코드 통합에서 새4검사 통과, 기존7실패는 변경 전후 동일하다. 온톨로지는1074 부분실패→1077 상태 전환 수리→MAIN105 결합1079 실모델1셀/10호출을 완료했다. 두 원문의 판단 보존을 확인했지만 근거 연결 보완1회·제한 답변으로 품질 효과는 미인증이다. MAIN105 최종 누적본433파일·첨부4개를 삼성메일 SENT `1a17ae4c6976a0f7`로 발송·확인했다. 설치144명령·SQL18·상태13쌍을 통과했으며 MAIN104 첨부를 대체한다. P0~P4 전체 구현·전체 응답시간 개선·법률 품질·온톨로지 MAIN·GENOS 현장 배포 완료로 확대하지 않는다. 아래 이전 상태 기록과 구분한다.
<!-- /MAIN104_SQL_FOLLOWUP -->

**2026-10-27 — 211초 원인·최적화 확인:** [상세 측정과 결과](NAVIGATION_211S_ROOT_CAUSE_20261027.md). 정의 연결 조회의 전체 참조 VIEW 조립과 권한 ID 목록 반복이 원인이었다. 동일 계측의8개 대응 구간236.744→19.891초(91.598% 감소), 원래 화면·행동·전달 원문8/8 일치, 신규 모델 호출0회. 당시 SQL 두 수정은 작업 코드에 통합했고 선택 MAIN103·GENOS 배포는 유지했다. 이후 MAIN 반영 상태는 문서 상단 최신 기록을 따른다. 초기 준비·전체 응답시간·온톨로지 품질·GENOS 속도와 구분한다. 아래2026-10-26 상태는 선행 단계 기록이다.

2026-10-26 최초 작성은 구현 전 계획이다. 이후 **P0 계측·P1 일부 구현과 부분 실험을 진행했다.** [구현 결과와 실패·미완료 범위](NON_MODEL_LATENCY_IMPLEMENTATION_RESULT_20261026.md)를 현재 상태의 정본으로 읽는다. 아래 전체 P0~P4 설계를 모두 구현한 상태는 아니다. 당시 MAIN·GENOS는 변경하지 않았으며, 이후 MAIN105 반영은 상단 최신 기록을 따른다.

목표는 모델 호출을 제외한 준비·조회·검증·조립·저장 비용을 줄이는 것이다. 먼저 기존 GENOS 함수 계측 R2를 현재 후보까지 연결하고, 동일한 조사 경로에서 반복 검증·직렬화를 줄인 다음, **현재 작업을 먼저 정하고 필요한 화면만 만드는 구조**로 바꾼다. 원문·권한·상태 검증은 유지한다. 모델 호출 수 감소와 서버 연산 감소는 별도 지표로 판정한다.

[MVP](MVP.md) · [구현 에이전트 안내](MVP_AGENT_BRIEF.md) · [기존 입력·조사 계획](MVP_EXECUTION_REPAIR_PLAN_20261026.md) · [실제 실행 상태](MVP_EXECUTION_REPAIR_STATUS_20261026.md) · [GENOS 진입점][genos]

## 1. 현재 근거와 적용 대상을 고정한다

| 대상 | 확인한 상태 | 이 계획에서의 역할 |
|---|---|---|
| ADR1066 로컬 실행 | `action-choice-a2-r1/rev-001` 동결 후보743파일. A0/A1/A2는 같은 코드. 로컬 SQLite 세대 `latest-selection-20261015-r1` | 느린 화면 구성과 온톨로지 상태 충돌의 진단 자료. MAIN 성능으로 부르지 않음 |
| 로컬 MAIN103 | `output-unlimited-20261023-r1`, 활성 manifest SHA256 `b56f4e4fd942eb40fcf2aa9d6bedd37b83f9fb512d610323ad72d760b9df0e79` | 별도 통합·서비스 연결 대상. 후보 기능이 모두 포함된 상태는 아님 |
| GENOS 최신 RAG 발송본 | MAIN102 기반417파일 발송 기록 | 반입·실제 배포 리비전의 증명은 아님 |
| GENOS 10월22일 실행 | 현장 사진 전사에서 총시간·모델시간 확인 | 코드 해시·데이터 세대·DB 모드 미확인. 로컬과 속도 배수 비교 불가 |
| GENOS 함수 계측 R2 | 56개 함수/구간 연결, 스택 표본·CPU·대기·GC 계측, 로컬 검증 완료 | 새로 만들지 않고 확장할 기반. 미발송·현장 미적용 |

### 수치 원장

| ID | 지표와 종류 | 값과 계산 | 출처·한계 |
|---|---|---|---|
| O1 | 로컬 전체, 관측 | 320.668569초 | ADR1066 A0 첫 문항, 제한 답변까지의 제품 실행. 1건 |
| O2 | 로컬 모델 전송, 관측 | 67.318515초, 11회 | 같은 실행의 물리 전송 구간 합계. 동시 호출 일반화 시 합 대신 구간 합집합 필요 |
| C1 | 로컬 모델 밖, 계산 | O1−O2 = **253.350054초, 전체의 약79.01%** | 실행기 경계에 따른 차이. 아직 모든 구간이 함수에 귀속된 것은 아님 |
| O3 | 선택 화면 구성 관련 간격, 관측 | 8구간 합 **211.333초**, 각23.895~37.467초 | 이벤트 사이 간격이다. 특정 조회·검증 함수의 배타 시간은 아님 |
| C2 | 그 밖의 미분해 시간, 계산 | C1−O3 = **42.017054초** | 초기 준비·나머지 처리 등을 세분해야 함 |
| O4 | GENOS 총시간과 모델, 관측 | 232.284초 / 모델6회131.839초 | 10월22일 사진 전사. `request_finished`·`request_returning`은 다른 경계 |
| C3 | GENOS 모델 밖, 계산 | 232.284−131.839 = **100.445초, 약43.24%** | 두 환경 모두 모델 밖 지연이 크다는 관찰만 가능 |
| O5 | GENOS 최대 호출 간격, 관측 | 호출2→3 **63.540초** | 후보 이벤트→메뉴 필터 완료36.914초도 함수 자체 시간으로 해석하지 않음 |
| O6 | 기존 로컬 R2 프로파일, 관측 | 소형 합성6경로에서 jsonschema가 모델 밖 시간의69~73% | ADR1066·GENOS 원인으로 전용하지 않음 |
| O7 | 기존 계측 부하, 관측 | 소형6경로 전체 실행14.8초 → sample15.4~15.7초, full15.8~16.1초 | fixture 구축 포함. GENOS·현재 후보의 계측 부하는 미확인 |

O1~O3의 원시 수치와 구간 목록은 [읽기 전용 진단 JSON][diag-json], 현장 수치는 [사진 전사 기록][field], O6/O7은 [R2 검증 기록][probe-result]에 있다. 253초와100초를 나누어 환경 성능 차이로 발표하지 않는다.

## 2. 문제별 변경과 완료 조건

| 문제 | 현재 방식과 실제 결과 | 수정 방식 | 같은 입력에서 확인할 결과 |
|---|---|---|---|
| 넓게 만든 뒤 줄임 | `Investigation.view()`가 `build_view()`를 호출한 뒤 전체 상태를 복사하고 작업별로 투영. O3에서211초 관찰. 모든 DB 원문을 매번 읽는다는 뜻은 아님 | 작업 결정과 공급자별 조립을 분리. 필요한 공급자만 실행 | 같은 선택지·원문·필수 상위 조건이 보이고, 불필요한 공급자의 조회·조립 횟수는0 |
| 스키마 준비 반복 | `jsonschema.validate()` 사용 경로는 매번 메타스키마도 검사. O6에서 큰 비중. ADR1066 비중은 미확인 | 동일 스키마의 검사기를 한 번 준비해 재사용 | 같은 객체를 같은 계약으로 검사하고 오류 선택·보완 요청도 보존. 유효 cache 보관 중 메타검사1회. eviction 후 재검사는 별도 집계 |
| 캐시 앞뒤의 반복 작업 | 법령 목록 캐시 적중 전 정렬·범위 hash, 연결 캐시 적중 후 deepcopy·읽기 상태 갱신. 정적 코드로 확인 | 불변 목록·연결과 가변 읽기 상태를 분리. 요청 안에서 재사용 | 적중 때 정적 부분 재계산0. 상태 변경은 해당 부분에 반영 |
| 같은 원문 검증 반복 | `SourceSession.verify`, inventory receipt, 전달 블록 구성에서 동일 bytes를 다시 조회·검증 | 필요한 원문 bytes와 정확한 검증 receipt를 별도로 요청 안에 재사용 | 같은 판본·권한·span에서 중복 조회 감소. 변경된 원문·권한·scope는 여전히 거부 |
| 복사·인코딩·저장 반복 | 동일 actions hash를 여러 번 계산. 전체 frame과 checkpoint를 복사·직렬화 | 동일 불변 객체는 canonical bytes와 hash를 함께 재사용. 불변 frame 분리는 후속 단계 | 저장 bytes·소비자 결과 동일. 재개·동시 수정·예산 선점 보존 |
| 전송 준비 중복 | preview와 실제 호출에서 입력 변환·스키마·요청 표현을 다시 준비하는 경로 | 같은 decision transaction의 준비 결과를 재사용 | 같은 실제 전송 bytes, 같은 전달 원문. 준비 완료와 실제 전달 완료는 구분 |
| 진전 없는 탐색 반복 | A0에서 원문 추가 읽기 없이 연결 목록6회 열기 | 우선 같은 화면의 재조립 비용 제거. 행동 안내·선택 정책 수정은 별도 기능 실험 | 동일 행동 replay에서는 반복 1회당 비용 감소. 선택 개선 효과를 연산 개선으로 섞지 않음 |

원문·권한·상태 검사 전체를 끄지 않는다. **동일한 불변 입력의 준비와 계산을 한 번만 수행하는 것**이 첫 최적화이며, 지금 상태에서 유효한지 확인하는 검사는 매 사용·commit 경계에 남긴다.

## 3. 상세 측정 계약

### 기존 R2와 연결 경로

R2의 `scope_call → request_scope → Collector/Sampler`와 `execution_metrics.transport_attempt/capture`, `query_latency.span`을 재사용한다. 현재 R2는 `service._reported_dispatch`를 감싼다. 기존 숫자 이벤트 `timing.probe.started/summary/failed`와 요청 보고서, `extract.py`·`find_reports.py`를 함께 확장한다. 독립 실행기나 두 번째 프로파일러를 만들지 않는다.

R2 설치기는 MAIN99/101/102의 특정 `service.py` 해시에 결속되어 있다. MAIN103·현재 후보의 실제 import·엔진 pin·데코레이터 위치를 확인한 뒤 새 revision으로 확장한다. 기존 R2와 완료 검사 결과를 덮어쓰지 않는다. 소형 API 통합은 기존 Python3.14에서 확인됐고 Python3.11 전체 RAG 통합은 fixture 문제로 미검증이다.

### 총시간과 모델 밖 시간

다음은 새 계측 산출물의 계약 제안이다. 단조 시계를 사용하고 시작·종료 경계를 같이 기록한다.

| 지표 | 경계와 계산 |
|---|---|
| `service_wall_ms` | 서비스 함수 입장부터 반환/실패 확정까지. 프로브 setup·summary와 동기 결과 스냅샷 포함 |
| `model_transport_union_ms` | 실제 모델 전송 시작부터 마지막 바이트/실패까지의 물리 시도 구간 합집합. 네트워크·서버 큐·스트리밍 포함 |
| `non_model_wall_ms` | `service_wall_ms − model_transport_union_ms`. 입력 준비·응답 파싱·검증·도구·재시도 대기 포함 |
| `retry_backoff_ms` | 실제 전송 밖 재시도 대기. 모델 밖의 별도 하위 항목으로 표시 |
| `setup_ms`, `summary_ms` | 계측 자체의 설치·import·결과 가공 비용. 총시간에 포함하고 따로 표시 |
| `report_queue_ms`, `report_finalize_ms` | 보고서 enqueue→worker 시작, worker 시작→cleanup 포함 완료. 반환과 겹칠 수 있으며 사용자 응답 시간에 다시 더하지 않음 |
| `workflow_wall_ms` | GENOS 워크플로우가 관측한 전체시간. 서비스 밖 플랫폼·화면 시간과 구분 |

현재 R2의 경계는 `send_once/send_stream_once` 전체이며 JSON 파싱·hash·스트리밍 `on_content`도 포함한다. `transport.py`와 `execution_metrics.py`에서 실제 송신 시작·마지막 바이트/실패 경계를 연결하고 기존 전체 시도 시간도 별도로 남긴다. 실제 호출·실패·스트리밍 fixture로 두 경계의 차이를 확인한다. 모델 추론만의 순수시간은 현재 관측할 수 없으므로 송수신 구간을 비모델 wall 지표에서 제외한다. 그 안의 로컬 파싱·콜백 CPU도 측정·최적화하되, 겹치는 시간을 비모델 wall에 다시 더하지 않는다. 모델과 다른 처리가 겹치면 겹침과 함수별 CPU를 별도로 설명한다. 호출별 시간을 단순히 더해 전체시간에서 빼지 않는다.

### 반드시 분해할 단계

| 상위 단계 | 세부 계측 대상 | 횟수·크기 지표 |
|---|---|---|
| 시작·결속 | 선택 release/profile, 데이터·scope 결속, 라이브러리 import, 조회 연결 | cold/warm, 연결 횟수, 결속 검사 수 |
| 검색·원문 | 법령 목록/조문 후보, 구조·명시 참조·온톨로지 조회, block/span 읽기 | 조회 수·반환 행/bytes·반복 key 수·batch 크기 |
| 다음 화면 | 작업 결정, provider 조립, actions, 연결 카드, 상위 조건, 원문·이력 투영 | 공급자별 호출, 후보 수, 정적/가변 cache hit/miss |
| 검증 | schema 생성/메타검사/instance 검사, canonical 복원, 필드·근거·ACL·revision 검사 | 서로 다른 schema 수, 검증 수·실패 종류, 재사용 수 |
| 조립·전송 준비 | 정렬, deepcopy, JSON encode, hash, preview·실전송 준비 | 대상 항목/bytes·반복 직렬화 수·준비 재사용 |
| 상태 | frame capture, checkpoint 생성·DB쓰기, reserve/accept/receipt/commit | write 수·bytes·대기·commit, 중복 내용 저장 수 |
| 완료·로그 | 답변 소비자, `DeferredReport.complete`의 동기 복사, 반환, 별도 finalizer | queue 깊이/대기·JSON·fsync·TXT 생성·완료/실패 |

함수별 inclusive/exclusive wall과 thread CPU, 최대값·횟수를 기록한다. 부모+자식 시간을 중복 합산하지 않는다. 스택 표본의 점유율은 추정으로 표시하며 멀티스레드 `sampled_ms` 합을 wall이나 CPU 시간으로 부르지 않는다. `wall−CPU−runqueue`는 I/O·잠금·sleep 등이 섞인 값이므로 NFS·Oracle 원인으로 단정하지 않는다.

응답 전 비모델 구간을 서로 겹치지 않는 상위 구간으로 분할하고 `unattributed_ms`를 보존한다. 목표는 비모델 시간의95% 이상을 **이름 있는 상위 단계**에 귀속하는 것이다. 이 수치는 목표이며 세부 원인이95% 밝혀졌다는 뜻은 아니다. 남은5%가 절대시간으로 크면 추가 분해한다.

### 저장·부하·실패

- `DeferredReport.__exit__`는 현재 bounded queue에 넣고, `finalize()`가 별도 스레드에서 JSON·fsync·읽기용 TXT를 만든다. worker는 enqueue 직후 서비스 반환 전에 시작할 수도 있다. `enqueued/worker_started/worker_finished` 단조시각과 응답 경로와의 겹침을 별도 수명 구간으로 기록한다. 응답 경로에 동기 저장을 새로 넣거나, finalizer를 끝난 Collector에 붙여 수집기를 계속 살려두지 않는다.
- 현재 `shared_report.written` 뒤에도 trace·TXT·context cleanup이 남는다. 전체 finalizer 완료 이벤트는 cleanup까지 끝난 뒤 worker의 finally에서 완료/실패/중단 상태와 함께 추가한다. 최종 보고서 자신의 저장 시간은 그 보고서 안에 사후 삽입할 수 없으므로 로그/분석 소비자가 이 숫자 집계를 결합한다. 상세 보고서를 계측 수치 때문에 다시 전체 쓰기하지 않는다.
- 새 숫자 집계에는 별도 계측 schema version을 부여하고 기존 R1/R2 기록을 읽는 `extract`의 호환성을 유지한다. 기존 요청 보고서 형식은 additive 필드만 허용한다. finalizer 수명 이벤트는 같은 request 상관 ID로 결합하며 누락은0초가 아닌 미확인으로 표시한다.
- 본문·질문·답변·SQL·bind·문서/블록 ID·인자·지역변수·예외 메시지를 프로브에 추가하지 않는다. 중복 key 집계는 요청 메모리에서만 수행하고 숫자로 내보낸다. 코드/설정/데이터 버전 지문은 기존 접근 통제된 실행 binding을 참조한다.
- 기본 상세 계측은 끔. 간단한 상위 구간·카운터 모드와 진단용 함수/표본 모드를 구분한다. 기존 R2 부하가 있으므로 모든 요청에10ms 스택 수집을 켜지 않는다.
- 기존1900초 제한은 함수 진입 계측에만 적용되고 샘플러에는 같은 deadline 검사가 없다. 확장 시 elapsed·표본·GC event·key 수의 제한을 모든 수집 경로에 적용하고, 한도 도달은 계측만 중단한다. 제품 시간·호출 예산을 늘리거나 줄이지 않는다.
- GC 콜백은 잠금·로그·보고서 생성 없이 제한된 append만 한다. 기존 잠금 교착 회귀를 유지한다. 별도 스레드의 context 전파·동시 요청 간 분리도 검사한다.
- 계측 실패는 업무 결과·예외를 바꾸지 않고 `incomplete`로 남긴다. summary 누락·미계측 경계를 성공 측정으로 계산하지 않는다. 제품의 필수 상태 저장 실패는 기존 실패 계약을 그대로 따른다.

## 4. 최적화 구현 순서와 파일 변경 지도

아래 `legal_agent/*`는 `02_BACKEND/semantic_runtime/legal_agent/` 기준이다. 후보 전용 모듈은 [ADR1066 snapshot][snapshot]에서 실제 연결을 확인했다. 작업 코드에 없는 기능은 최신 작업 변경과 대조해 필요한 부분만 통합한다. snapshot 전체를 덮어쓰지 않는다. 새 함수·타입 이름은 제안이다.

### P0 상세 측정과 기준선

`service.py`, `request_report.py`, `execution_metrics.py`, `legal_agent/transport.py`·`gateway.py`, R2 `genos_timing_probe.py`·`extract.py`, 기존 `query_latency.span`을 확장한다. 신규 ontology/review/action/projection/gateway 경계는 기존56개 명시 목록에 없으므로 연결 검사를 추가한다. 무작정 모든 함수를 감싸기보다 3절의 상위 구간과 반복 카운터를 먼저 연결하고, 큰 구간만 상세 측정한다.

산출물은 요청 전체 요약, 비모델 상위 단계, 비싼 배타시간 상위 함수, 반복 작업 수, 계측 누락·부하를 가진 한 보고서다. **이 단계가 끝나면211초 중 화면 조립·스키마·원문·저장의 몫을 같은 실행에서 설명할 수 있어야 한다.**

### P1 반복 검증과 직렬화 제거

| 변경 지점 | 구현 | 보존할 소비자 계약 |
|---|---|---|
| `law_navigation.validate`, `decision_projection.expand`, 공통 schema helper | 동일 스키마에서 `validator_for/check_schema` 한 번, 검사기 재사용 | 기존 `best_match(iter_errors)` 오류 선택 유지. output 계약의 최대16개 오류·순서도 유지 |
| `action_choice_contract`, `output_contract` | 기존 직접 `Draft202012Validator` 사용은 별도 분석. 필요 시 객체 재사용만 | 이 경로가 메타검사를 반복한다고 잘못 가정하지 않음 |
| `navigation_tasks.project`, `repository.save_view` | 동일 actions digest 한 번. 동일 canonical bytes를 hash와 저장에 공유 | 배열 순서·형식·hash·오류 경로 동일 |
| `bounded_source_session.structured`, `gateway.prepare_input` | 결정 transaction 안에서 `PreparedInput` 재사용 | 같은 논리적 decision·presentation·복구 담당·profile/transport binding에 한정. view/schema/prompt/source/ACL/state 또는 보완 입력이 달라지면 폐기. 실제 전송 직전 예산·revision 재확인 |

스키마 cache key는 정확한 내용·배열 순서·`properties` 등 오류 열거에 영향을 주는 키 삽입 순서·draft·format checker·참조 registry 버전이다. 키를 정렬한 hash 하나로 오류 순서가 다른 스키마를 합치지 않는다. 요청별 동적 enum이 포함된 스키마는 요청 안에서만 크기 제한을 두고 보관한다. 불변 코드 전용 스키마만 프로세스 수명을 검토한다. 스키마 hash를 계산하는 비용도 계측하며, 이미 결속된 schema 객체의 bytes/hash를 재사용한다. 매 화면의 schema가 모두 다르면 재사용 이득이 작으므로 실제 적중률로 판단한다. wire 검사·복원 후 검사·현재 상태 검사는 서로 다른 경계다.

### P2 현재 작업부터 정하는 화면 구성

현행 `review_packets.project`가 pending·blocked·오래된 미검토 원문·정확한 출발 원문을 정하고, `navigation_tasks.project`가 그 결과로 작업을 결정한다. 이 의존성을 보존하면서 **작은 검토 대상 계획 → 제안 함수 `resolve_task` → 필요한 provider → 계획에 따른 정확한 원문·온톨로지 조립 → 현재 화면**으로 분리한다. 검토 대상 계획은 현재 receipt·상태 metadata로 작성하며 원문 확보·판단·전달 receipt를 새로 만들지 않는다. 계획과 조립 사이 revision/source binding이 바뀌면 같은 확정 상태에서 재계획한다. 공급자는 법령/조문 후보, 구조, 연결, 검토 원문, 이력으로 나눈다.

현재 화면 밖 작업의 전환 가능 여부·정확한 행동 집합은 작은 action manifest와 불변 fragment로 유지한다. 전체 행동의 결속을 현재 화면 hash로 대체하지 않는다. manifest를 만들기 위해 다시 전체 본문을 조립하는 것도 금지한다. provider 의존성과 명시적 반환 계약을 두어 상호 호출로 광범위 구성이 재발하지 않게 한다.

**법령 결과 전체, 조문 후보20개와 더 보기, 직접 READ 대상, 복귀, 선택 범위와 필수 상위 조건은 보존한다.** 이는 화면·탐색 계약이며 입력 문자 상한을 되살리는 정책이 아니다. 입력 문자 차단 해제·출력 토큰 상한 없음은 유지한다. 선택 가능한 의미 정보가 바뀌면 행동 보존 최적화가 아니라 별도 기능 변경으로 분류한다.

초기 cache 무효화는 state revision 단위로 보수적으로 한다. 정확성 확인 후 search/evidence/delivery/review revision별로 좁힌다. 과거 frame을 현재 상태로 재생성하지 않는다. 과거 frame은 불변이며 새 형식 도입 시 schema version과 기존 frame reader를 함께 둔다.

### P3 요청 내 원문과 연결 재사용

`SourceSession.verify`, `evidence_inventory.check_page/expected/receipt`, `unit_relations.delivered_blocks`, `unit_reading.blocks`, `law_overview.directory`, `connection_scope.inspect_directory/offer_choices`를 함께 변경한다. 이미 있는 `store.sources()` batch API로 현재 선택에 필요한 block만 묶는다.

| 재사용 대상 | 필수 key와 수명 | 무효화·재검사 |
|---|---|---|
| 원문 bytes | generation/Oracle snapshot, 문서 판본, artifact hash, block. 요청 종료까지 bounded LRU | 판본·원문 결속 변경 시 폐기. 변경 감지 방식은 실제 store 계약 유지 |
| 검증 receipt | 위 key + ACL/scope, 정확한 span·내용 hash, source binding, 검증 계약 | 권한·scope·내용·계약 변경 시 사용 금지. 현재 권한·state·commit 검사는 유지 |
| 법령 목록·목차 | index/generation, ACL, 검색 scope·검색식·정책·페이지 | 새 검색·권한·데이터 변경 시 재계산 |
| 연결의 정적 카드 | 실제 endpoint/witness, 판본·scope·조회 receipt | 확보/전달 상태는 별도 revision의 가변 부분으로 갱신 |
| 승인 온톨로지 | 승인 묶음 ID·버전·membership hash, 허용 scope, 실제 전달 span | A1/A2 정보 동일성, 묶음 밖 연결·미확보 상태 보존 |

실패·부분 조회·부재를 검증 성공으로 캐시하지 않는다. `evidence_id` 또는 `verified=True` 하나만으로 재사용하지 않는다. 기존 `check_unchanged()`의 파일 stat 비교를 매번 전체 파일 hash 계산이라고 설명하지 않으며, 이를 성급하게 제거하지 않는다.

GENOS에서는 필요한 자료만 Oracle/조회 API에서 받아 요청 중 사용한다. 전체 원문·색인 로컬 복제, 영속 SQLite 캐시, 요청 간 원문 캐시는 도입하지 않는다. DB 내부 cache·색인은 별도 계층이며 SQL별 시간/행수/실행 계획을 확인한 뒤 DB 관리 절차로 제안한다. Oracle 연결 pool도 현재 구현과 권한 분리·연결 비용 관측을 확인한 뒤 별도 변경한다.

### P4 상태와 이력 저장

먼저 `corrected_memory.save_selection_progress`, `Investigation.save`, `investigation_chain.capture`, `repository.save_view`에서 encode/hash 중복만 없앤다. counters 병합 후 내용이 같으면 상태 row 재쓰기를 생략할 수 있으나, goal revision·소유권·감사 이벤트는 보존한다. “내용이 같음”을 “상태 확인 불필요”로 바꾸지 않는다.

그다음 불변 원문·action fragment와 가변 상태를 분리하여 copy-on-write를 적용한다. 기존 checkpoint/frame reader와 새 version 이행을 한 변경으로 다룬다. 새 frame만 참조 방식으로 저장하고 완료된 기록은 재작성하지 않는다.

모델·도구 예산 선점, ACCEPTED, 실행 전 의도, 실행 후 receipt, pending/실패·복구 횟수, 최종 발행은 즉시 보존해야 한다. 네트워크 호출을 넘겨 transaction을 묶거나 fsync를 일괄 제거하지 않는다. 응답 후 finalizer의 I/O도 CPU·메모리·공유 저장소 경쟁을 만들 수 있으므로 별도 비용으로 측정한다.

## 5. 온톨로지 실패와 선택 문제의 처리 순서

ADR1066 A2의 `ontology delivery receipt changed`는 동일 원문의 표시 ID 변경을 내용 변경으로 취급한 상태 결속 오류다. 승인 묶음 확보·모델 전달은 관찰됐지만 전체 효과 검증은 끝나지 않았다.

상세 계측 P0는 이 실패 이전 구간까지 그대로 측정할 수 있다. 성공까지의 전후 비교를 위해서는 **원문 내용의 불변 identity와 표시 이력의 identity를 분리하는 기능 수정**이 선행되어야 한다. `ontology_review.reconcile`, `evidence_inventory.confirmed_pages`, `decision_projection.retain_requested`와 저장 소비자를 같이 다룬다. 실제 원문·좌표·판본·권한이 바뀐 경우에는 계속 거부해야 한다.

별도 gate의 `WIRE_DOCUMENT_ID_MISSING`은 evidence-ID 기반 소유권을 읽지 못한 감사 호환 문제다. 기존 native receipt의 소유권 검증에 맞춰 소비자를 연결하며 문서 ID를 추측해 채우거나 gate를 끄지 않는다. 과거1066 결과·점수는 수정하지 않는다.

두 기능 수정과 “원문 대신 연결 목록만 반복 선택”의 안내/행동 수정은 성능 최적화 arm과 분리한다. 먼저 동일 동작의 계산비 절감을 측정하고, 이후 필요한 읽기까지의 총 비용을 별도로 비교한다. 탐색을 일찍 끊어 빨라진 요청은 성능 개선 성공으로 계산하지 않는다.

## 6. 검증과 실험 계획

### 작은 계약 검사부터

| 상황 | 통과 조건 |
|---|---|
| 정상·잘못된 schema | 같은 검증 결과·오류 선택·보완 책임. 새 모델 재시도 없음 |
| 표시 ID만 변경 / 실제 원문 변경 | 전자는 정상 이력 갱신, 후자는 기존 무결성 차단 |
| ACL·scope·판본·revision 변경 | cache hit여도 잘못된 자료 전달/commit 차단 |
| 중단·재개·중복 요청 | 최초 deadline·사용량·확정 receipt·pending 유지, 부작용 중복0 |
| 동일 상태·다른 상태 | 동일 상태에서는 반복 계산 감소, 변경된 상태는 정확히 반영 |
| 계측 off/on·실패·취소·한도 | 업무 결과/예외 동일. 누락·계측 부하는 명시 |
| GC·별도 스레드·동시 요청 | 교착 없음, 요청 간 원문/수치 섞임 탐지. 공유 자원 수치는 격리 불가 표시 |
| 실제 소비자 | 같은 코드·pin의 `/v1/rag/ask` 또는 service 진입점에서 답변·상태·계측 보고서 연결 |
| finalizer 지연·queue 포화 | 응답 전/후 지연을 구분. 계측 때문에 새 동기 대기나 숨은 성공 처리 없음 |

기존 관련 계약/API와 위 변경에 해당하는 실패 검사만 먼저 실행한다. 이미 통과한 대형 검사를 매 작은 수정마다 반복하지 않는다. 통합 후 같은 코드의 관련 회귀를 한 번 실행하고, 새 실패·변경이 있을 때만 범위를 넓힌다. 반복되는 의미 불확실성 때문에 정상 원문 전달을 막는 새 검사도 넣지 않는다.

### 성능 비교는 새 ADR로 동결한다

실험용 구현·첫 비교 전 [실험 프롬프트][experiment-prompt]·[표준][standard]을 끝까지 읽고 동일 scope reservation 확인 후 새 ADR을 선점한다. 이 계획 작성 자체는 예약·실험이 아니다. 결과를 확인한 뒤 추가하는 후보는 후속 ADR로 분리한다.

ADR1066은 부분 중단 상태이므로 완료 parent로 가장하지 않는다. 완료된 기준 arm의 정확한 ID를 확인해 부모로 정하고1066은 코드·실패 진단의 `relationships`로 연결한다. 수정된 기준군·후보의 전체 코드/데이터/설정/프롬프트/스키마를 새로 결속한다.

1. **측정 기반 확인:** 기존 저장된 응답을 사용하는 격리 진단 fixture를 만든다. 무거운 원문 로딩은 한 프로세스씩 수행한다. 기록된 모델 응답은 성능 재현용이며 새로운 품질·holdout 결과가 아니다. 표시 ID가 달라지는 경우 검증을 우회해 끼워 넣지 않고 동일 canonical 상태 재현 가능 여부를 먼저 확인한다.
2. **단계별 동작 보존 비교:** 계측만 있는 기준군과 P1→P2→P3→P4 후보를 같은 입력·선택·읽기 범위·모델 응답으로 비교한다. 응답 내용, 실제 wire 의미, canonical 행동, 원문/span, 상태·예산을 대조한다. 시각·진단 필드처럼 달라질 수 있는 항목은 사전 allowlist로만 제외한다.
3. **작은 반복 측정:** 최초 제안은 대상 경로별 cold1회와 warm5회, 기준/후보 순서를 교대하고 단일 worker로 실행한다. cold는 프로세스·애플리케이션 cache 상태를 명시하며 OS/DB cache까지 비웠다고 가정하지 않는다. median·최대·각 회차를 보고하고5회로 안정적인 p95를 주장하지 않는다. 변동이 크면 원인을 확인하고 추가 표본·예산을 후속 계획에 고정한다.
4. **계측 부하 분리:** 같은 경로에서 off/상위 구간만/sample/full을 구분한다. 최적화 전후 최종 속도는 최소 계측 또는 off에서도 확인한다. 계측 시간을 임의로 빼서 개선률을 만들지 않는다.
5. **통합 모델 확인:** 기능 오류와 감사 소비자가 해결된 뒤 승인된 질문·자료·현행 외부 모델 정책으로 새 통합 실행을 동결한다. A0/A1/A2의 원문 확보·전달·판단·답변을 연결하고 부분 종료와 완주를 따로 집계한다. 모델시간은 기록하되 최적화 성과 분자에서 제외한다.

### GENOS 비교 절차

현재 세션에서는 GENOS에 접속할 수 없다. 다음은 현장 인계와 결과 수집 절차다.

1. 실제 코드 리비전·release/profile/pin·데이터 generation·조회 모드·Python·CPU quota·메모리·동시 요청 수를 기록한다. 최신 발송본을 실제 배포본으로 가정하지 않는다.
2. 같은 계측 계약과 분석기를 로컬·GENOS에 연결한다. 우선 **각 환경 내부**의 수정 전후를 비교한다. 서로 다른 실제 모델 결정 경로끼리의 총시간 비교와 고정 동작의 계산비 비교를 분리한다.
3. NFS/SQLite 경로와 Oracle 요청별 조회 경로를 별도로 표기한다. 조회 수·bytes·wall/CPU·대기·스키마·조립·저장을 같은 항목으로 비교하되 backend가 다르면 환경 효과와 코드 효과를 분리한다.
4. 현장 질의·warmup은 **워크플로우 테스트 화면에서만** 한 건씩 실행한다. 서비스와 워크플로우 전체시간을 함께 기록한다. 서버 밖 화면·플랫폼 구간은 관측 자료가 없으면 미확인으로 남긴다.
5. 신규 인계본은 기존 checkout `~/DEV`에 해시 고정 백업/적용/복구한다. 실행은 사용자가 업로드한 `TRANSFER`를 현재 위치로 하여 정확한 ZIP/TXT의 상대경로와 `python3`를 사용한다. ZIP 적용·commit/push·코드서빙 리비전·환경변수·워크플로우 편집기 반영을 각각 확인한다.
6. 보고서 원본과 binding을 확보해 분석한다. 사진의 일부 시간만으로 함수별 절감률을 확정하지 않는다. 상세 계측을 끈 경로에서도 기능과 지연을 확인한 뒤 운영 사용 여부를 정한다.

## 7. 목표와 자원 및 도입 기준

**목표는 동일 동작에서 비모델 시간50% 이상 절감, 추가 목표80% 절감이다.** 이는 사용자의 강한 최적화 요구를 작업 목표로 수치화한 것이며 달성 예측이 아니다. 실제 채택 여부는 같은 작업량·원문·상태를 유지했는지와 단계별 관측으로 판단한다.

| ID | 종류와 조건 | 계산 | 의미 |
|---|---|---|---|
| T1 | 1차 목표, C1과 같은 경로 | 253.350054×0.5 = **126.675027초 이하** | 비모델50% 절감 목표 |
| T2 | 추가 목표, 같은 조건 | 253.350054×0.2 = **50.670011초 이하** | 비모델80% 절감 목표 |
| S1 | 계산 예시, O2가 고정이라는 가정 | O2+T1 =193.993542초 / O2+T2 =117.988526초 | 전체시간 예측이 아님. 모델시간·조사 경로가 달라지면 성립하지 않음 |
| S2 | 민감도 예시, O3만 절반으로 줄고 나머지 고정 | C1−211.333×0.5 =147.683554초 | 비모델 약41.71% 절감. 화면 구간만 절반으로 줄여서는 T1 미달 |

개별 후보는 동일 경로 median이 개선되고 새로운 큰 지연·메모리·정확성 회귀가 없을 때 채택한다. 효과가0이거나 계측/캐시 관리 비용이 절감보다 크면 해당 변경은 제외한다. O6의70%를 근거로 T1/T2 달성을 보장하지 않는다. 저비용 계측 모드의 추가 지연 목표는 동일 fixture median3% 이하로 두고, 초과하면 기본 비활성·진단용으로 유지한다. sample/full은 별도로 실측해 비용을 공개한다.

무거운 실행 전 가용 RAM·swap·디스크·기존 프로세스를 확인한다. 최초 로컬 실행 제안은 worker RSS4GiB, 가용 RAM3GiB 미만 또는 지속 swap 증가 시 추가 실행 중단이며, 실제 기준선과 환경을 확인해 **실행 전** 동결한다. 현재 기준선이 이를 넘으면 중단 이력을 남기고 실행 범위/정책을 새로 정한다. 이 값은 제품 입력·출력 한도가 아니다. 원문 캐시는 크기 제한·eviction으로 메모리를 돌려주며 원문/권한 검증을 생략하지 않는다. 로그·snapshot은 같은 hash의 불변 자료를 공유하고 실패 원장은 보존한다.

일정은 작업 패키지 P0→P1→P2→P3→P4→통합→GENOS 순서로 관리한다. 현재는 병목 분해·후보와 작업 코드의 통합 차이·현장 대기 시간이 미확인이므로 달력 완료일을 제시하지 않는다. P0 종료 때 실제 큰 구간과 변경 파일을 기준으로 후속 작업량을 다시 산정한다. 큰 기여가 없는 P3/P4의 구조 변경은 절감 효과 확인 전 진행하지 않는다.

## 8. 배선과 완료 기록

완료는 다음을 구분해서 남긴다.

1. **작업 코드:** 기존 최신 수정 위에 통합, 코드/스키마/프로필 지문, 실패 계약과 테스트 결과.
2. **동결 후보:** 같은 코드로 측정·기능 검증, 계측 부하·작업량·결과·회귀·원시 기록.
3. **선택 MAIN:** 승격 요건과 명시적 절차 충족 시에만 활성 pointer·release manifest·실제 로컬 service binding 확인. 의미적 판단 미스는 별도 기록하되 인용/권한/해시/재개/서빙 연결의 심각한 결함은 차단.
4. **GENOS:** 코드 인계, 반입, 리비전, 워크플로우 확인, 현장 측정을 각각 기록. 로컬 통과를 현장 통과로 쓰지 않음.

롤백은 계측 설정 off → 해당 변경의 code/profile/pin 복구 → 활성 release pointer/receipt 복구 순서로 대상별 준비한다. 새 checkpoint 형식이 생기면 구 reader 지원 또는 해당 버전의 재개 경로를 함께 보존한다. 모델 호출·도구 사용량과 최초 deadline을 초기화하는 롤백은 허용하지 않는다. 완료 실험·과거 R2·원문을 덮어쓰지 않는다.

이 문서의 최초 작성 완료 범위는 문서와 연결이었다. 이후 구현·측정 상태는 위 결과 문서를 따르며 전체 단계 완료·승격·GENOS 적용으로 확대하지 않는다.

교차 검토에서 모델 전송 경계 안의 파싱 비용, finalizer와 서비스 반환의 겹침·전체 완료 이벤트 부재, 검토 대상 계획과 작업 결정의 의존성, 스키마 오류 순서 보존을 확인해 위 계약에 반영했다. 이는 설계 검토이며 구현·속도 검증 결과는 아니다.

## 근거와 읽기 순서

- [ADR1066 원인과 원시 수치][diag-json] 및 [설명][diag] — 이벤트 간격, 원문 재표시 충돌, 선택 문제. 파일 hash와 관찰 범위 포함.
- [실제 후보 snapshot][snapshot] — `law_navigation.view/build_view`, 작업 투영, 원문·상태 소비자. 현재 작업 코드와 구분.
- [R2 구현][probe] · [검증과 한계][probe-result] · [프로브 수집 계약][probe-contract] — 기존56개 연결, GC 교착 수정, 계측 부하.
- [GENOS 사진 전사][field] · [최신 MAIN102 발송본][sent] · [MAIN103 서비스 확인 기록][main-binding] — 발송·선택·실제 현장 상태 구분.
- [전체 아키텍처][architecture] · [실패 복구 정책][recovery] · [실험 표준][standard] — Oracle 요청별 조회, 무결성·상태·예산, 비교·승격 절차.

[genos]: ../../../../GENOS.md
[architecture]: ../../../../00_SYSTEM/ARCHITECTURE.md
[recovery]: ../../OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md
[experiment-prompt]: ../../../../04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md
[standard]: ../../../../04_EXPERIMENTS/LEGACY_ADR/STANDARD.md
[diag-json]: ../../../../04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/POST_RUN_DIAGNOSIS.json
[diag]: ../../../../04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/POST_RUN_DIAGNOSIS.md
[snapshot]: ../../../../02_BACKEND/lawrag/research/candidates/adr_1066/action-choice-a2-r1/revisions/rev-001/snapshot
[probe]: ../../../../08_DEPLOYMENT/GENOS/handoffs/function_timing_20261024_r2/payload/genos_timing_probe.py
[probe-result]: ../../../../09_ARTIFACTS/AUDITS/20261024-function-timing-r2/RESULT.txt
[probe-contract]: ../../../../09_ARTIFACTS/AUDITS/20261024-function-timing-r2/CONTRACT.txt
[field]: ../../../../09_ARTIFACTS/AUDITS/20261022-request-timing-r2/FIELD_OBSERVATION_20261022.json
[sent]: ../../../../08_DEPLOYMENT/GENOS/handoffs/reference_coverage_20261022_r1/SEALED.json
[main-binding]: ../../../../09_ARTIFACTS/AUDITS/20261023-output-unlimited-main/consumer-active.json
