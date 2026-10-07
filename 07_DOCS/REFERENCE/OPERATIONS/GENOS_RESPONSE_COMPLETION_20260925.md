# GENOS 답변 반환과 보고서 저장 분리·리소스 사전 준비

## 2026-09-25 후속: FINAL 답변의 발행 대기 제거

v5 `FINAL` 뒤 `publication.prepare`와 `publication.export`를 동기로 기다리던
경로를 GENOS 선택 환경에서 분리했다. 답변 HTTP body는
`publication_status=PENDING`으로 먼저 반환하고, 별도 daemon worker가 원문
결속 검증과 내구 발행을 완료한다. 원본 답변은 반환 전에 journal의 유효한
`answer` stage artifact에 저장된다. 프로세스가 발행 전에 종료되면 다음
앱 시작 시 `FINAL` control과 이 artifact를 재검증하여 발행을 복구한다.
`publication.prepare/export/completed/failed` 로그로 후속 상태를 확인한다.
발행 전 출처 URL은 아직 열리지 않을 수 있다. 실패 시 답변을 거둬들이지는
않으며 `publication.failed` traceback과 journal 상태를 확인해야 한다.

`Store`가 시작 시 검증한 불변 `store.sqlite`는 동일 파일 상태에서 요청별
전체 SHA-256을 재실행하지 않는다. 파일 상태가 바뀌면 재해시하고 불일치를
거부한다. 선택 원문의 span 검증과 세대 manifest·범위 확인은 발행 worker에
남긴다. Glossary read-only SQLite 연결은 프로세스 안에서 요청별 독점 lease로
재사용하고 요청에서 만든 concept handle은 반환 시 비운다.
관계 탐색의 SQLite progress handler는 lease 반환·재대여 때 해제해 이전
요청의 만료 시각이 다음 질문의 용어집 조회를 중단하지 않게 한다.
일반 label 검색의 별도 3초 제한이 끝나면 요청 전체 SQLite 제한을 복원한다.
1코어 현장의 v5 환경 결속 경로는 `GENOS_RAG_MAX_CONCURRENT_REQUESTS=1`로
프로세스당 동시 조사 요청을 제한할 수 있다. 초과 요청은 대기하지 않고 거절된다.

`GENOS_DEFER_PUBLICATION=1`이 GENOS 세대 선택 시 기본이다. `0`이면 이전
동기 발행 경로로 돌아간다. 코드서빙 리비전 배포와 워크플로우 테스트 화면
검증은 별도다. 첫 질문에서 `rag.started`가 1초 안에 찍혀도 준비가 끝난 뜻은
아니다. `rag.loop.started.elapsed_ms`가 실제 agent 루프 진입 시간이다.
`session.context/journal/sources/gateway`, `glossary.pool.hit`로 앞단 병목을
구분한다. 각 worker가 트래픽을 받기 전에 WARMUP `READY`가 되어야 하지만,
플랫폼의 worker 라우팅·scale-to-zero 동작은 여기서 제어할 수 없으므로
현장 1초 달성은 미확인이다. 현장 시험은 워크플로우 테스트 화면에서만 한다.

## 확인 근거와 범위

2026-09-25 사용자 현장 사진은 내부 `request.finished`가 약 230초에 200을 기록한
뒤 `FINAL RESPONSE / ANSWER`를 마지막 이벤트로 heartbeat가 300초 이후까지
이어지고, 워크플로우에는 코드서빙 HTTP 500이 전달된 모습을 보여준다.
현행 코드에는 그 로그 뒤 전체 원장 수집·NFS JSON/TXT 저장을 await한 뒤
`return result`하는 경로가 있었다. 보고서 완료 대기는 코드로 확인했지만
현장 지연의 세부 I/O와 플랫폼의 300초 제한 적용 위치는 아직 미확인이다.

## 변경된 실행 경로

`service(config,data)` → 기존 `_dispatch`/RAG → 결과 준비 → NFS live handler 분리
→ `request.finished`/`request.returning` → 기존 결과 dict 반환.
분리된 작업은 마지막 원장 확인 → 최종 답변 블록 → JSON → TXT → live log 종료다.
일반 질문·모델·검색 결과 계약은 유지한다. r2 워크플로우는 명시적 관리 요청만
별도 전달하며, 알려진 질문 필드가 없는 입력에서 임의 문자열/UUID를 추출하지 않는다.

`request.finished`는 호환용 내부 결과 준비 이벤트다. 새 `request.returning`도
함수 반환 직전의 기록이며 게이트웨이·채팅 화면의 수신 확인은 아니다.
`shared_report.started/written/failed`, `shared_trace.started/written/failed`와
`shared_report.journal/json/fsync` 단계로 보고서 I/O를 구분한다.
답변 반환 뒤에는 질문 처리 중이라는 heartbeat를 계속 내보내지 않는다.

완료 I/O는 asyncio 기본 executor 밖의 프로세스별 daemon worker 2개가 담당한다.
live 기록부터 완료까지 최대 8건을 예약하며, 포화 시 새 요청은
`shared_report.skipped reason=report_capacity_reached`를 컨테이너에 남기고
공유 로그 사본 없이 답변한다. 기존 runtime journal은 계속 유지한다.
강제 종료·재배포는 아직 저장 중인 JSON/TXT 사본을 중단할 수 있다.
이는 영속 작업 큐가 아니며 공유 보고서 생성 보장을 뜻하지 않는다.
요청 처리 중 기존 live 로그 생성·flush는 동기 I/O이므로, 이번 수정은
모든 NFS 지연을 제거하는 변경이 아니다.

## 로딩과 캐시

사진의 `index.open`은 약 70초다. 이후 용어집 graph 등 큰 파일 해시 확인이
이어진다. 세부 전체 로그 없이 230초를 전부 로딩이나 모델 시간으로 분류하지 않는다.
navigation 검증·용어집 해시·ReverseMatcher 준비 데이터는 기존에도 프로세스 캐시가
있다. r1은 요청마다 만드는 TermAgent에서도 fulltext 검증 결과를 재사용한다.
r2는 후속 사진에서 `runtime.cache.hit`와 `index.open=210ms` 뒤
`resources.tools`에서 100초 이상 대기한 누락 경로를 수정한다.
검증된 TermIndex에 용어/관계/통계/표현/문서 목록과 문서별 정의 JSON을 한 번
적재하고, 다음 질문에서는 NFS 전체 목록을 다시 읽지 않는다. 일반 질문도 이
캐시를 준비하므로 WARMUP은 필수 선행 조건이 아니다. 질문별 SQLite 연결,
참조/원문 캐시, 정의 범위와 변경 가능한 객체는 분리한다. 프로세스당 한 navigation
세대만 보존하며 교체 시 목록 캐시도 교체한다.
`tools.cache.ready/hit`, `tools.catalog/stats/documents/surfaces/definition_catalog/copy/definitions`로
실제 준비 구간을 구분한다. `request.started.worker_id`로 같은 프로세스인지 비교한다.
첫 질문의 cold 준비와 메모리 복사 비용은 남으며 현장 시간을 숫자로 보장하지 않는다.

캐시는 선택 경로, manifest·SQLite의 파일 상태(dev/inode/size/mtime/ctime),
기대 manifest 해시, navigation·source 해시와 tokenizer 버전에 결속한다.
변경 시 재검증하며 요청별 SQLite 연결과 팀/문서 범위는 공유하지 않는다.
배포 E2E와 `verify_assets`는 기존 직접 전체 검증을 유지한다.
기존 generation, glossary compiler, 데이터 manifest를 수정하거나 재색인하지 않는다.

## 현장 사용 순서

1. 기존 `~/DEV`에 이번 코드·엔진 manifest·PIPELINE pin을 함께 반영한다.
   동일 코드 ZIP과 clean 배포 commit을 `genos_release_gate.py`로 검증한다.
   기존 PeCab generation을 그대로 선택한다. 설치 의존성 추가는 없다.
2. 검증한 commit을 push하고 코드서빙 새 리비전을 배포한다.
   `GENOS_GENERATION`, 내부 모델 설정, `GENOS_SHARED_LOG_DIR`를 유지한다.
3. `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py` **전체**를 기존 워크플로우
   Python 단계에 교체하고 저장·배포한다. 현재 현장은 워크플로우 테스트만 가능하다.
   이전 r1 안내의 코드서빙 직접 테스트 지시는 폐기한다. 코드 ZIP만 반영하면
   기존 워크플로우의 WARMUP→일반 질문 변환이 남으므로 별도 교체가 필요하다.
   **워크플로우 테스트 입력**으로 다음을 보낸다. 사전 준비가 필요 없으면
   바로 일반 질문부터 실행해도 같은 프로세스 캐시가 준비된다.

```json
{"API_TYPE":"WARMUP"}
```

시작 시 코드서빙은 `status:202`, `body.state:RUNNING`을 반환하고
워크플로우에는 `answer_status:warmup`, `warmup.state:RUNNING`이 표시된다. 같은 프로세스의
중복 시작은 합쳐진다. 별도 질문·생성 호출 없이 기존 resources 경로로
navigation·용어집·matcher·fulltext·PeCab을 준비한다. 앱 최초 구성 시
기존 내부 모델 ID 확인(`/models`)은 실행될 수 있다.

4. 같은 **워크플로우 테스트 입력**에서 아래 요청으로 상태를 조회한다.

```json
{"API_TYPE":"WARMUP_STATUS"}
```

`warmup.state=READY`와 `warmup.generation_path`, `warmup.worker_id`를 확인한 뒤
`{"question":"실제 근거 질문"}`을 보낸다. 준비 요청에서 일반 답변이나 UUID 검색이
나오면 워크플로우 코드가 아직 교체되지 않았거나 다른 단계가 입력을 바꾼 것이다.
실패 시 `FAILED/error_type`과 컨테이너 `warmup.failed`를 확인한다.
상태 조회는 준비를 새로 시작하지 않는다. 두 관리 요청은 NFS 공유 로그를
열지 않으며 컨테이너 로그에 기록한다.

캐시는 **worker_id로 식별되는 프로세스별**이다. 여러 worker/replica 또는
요청마다 새 프로세스를 만드는 플랫폼에서는 한 번의 READY가 전체 인스턴스의
준비를 보장하지 않는다. 재시작 후에는 다시 준비해야 한다. 첫 로딩 비용을
질문 전에 이동하는 기능이며 전체 cold 준비 시간이 단축됐다는 주장은 아니다.

5. 서로 다른 실제 질문 두 건으로 `tools.cache.hit`와 `resources.tools` 소요 시간을
   확인한다. 질문마다 worker_id가 달라지면 프로세스별 준비 상태를 구분한다.
   짧은 실제 근거 질문으로 워크플로우 수신과 답변을 확인한다. 같은 request_id로
   `request.returning`과 워크플로우 수신 시각을 대조한다. JSON/TXT는 나중에 생길 수 있다.
   기존 300초 플랫폼 제한과 agent 예산은 변경하지 않았으므로 오래 걸리는 모델
   요청까지 무조건 성공한다는 보장은 없다.

## 검증·복구

로컬 모의 회귀 검사는 JSON/TXT/로그 close 지연 중 asyncio 호출 종료,
보고서 실패·포화·요청 취소, 요청 간 로그 잠금 분리, 실제 resource 경로의 캐시 재사용,
fulltext 파일·기대 pin·tokenizer 변경 거부를 확인한다. 현장 성능 실측이나
질문 품질 비교 실험은 수행하지 않았다.

실패 시 기존 코드서빙 리비전과 그 환경변수로 복귀한다. 적용 스크립트가 남긴
`BACKUP/previous`와 `previous.txt`/`added.txt`는 DEV 파일 복구 근거다.
기존 NFS generation과 runtime journal은 삭제하지 않는다.
