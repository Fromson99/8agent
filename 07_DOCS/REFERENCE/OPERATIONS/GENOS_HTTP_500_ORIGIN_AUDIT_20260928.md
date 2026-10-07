# 300초 HTTP 500 발생 경로 재검사

## 확인된 현장 기록

같은 request_id `39aaf4093d2247c9888fb2dfd63ce47c`에서 워크플로우는
`failure_kind=http_error`, `http_status=500`, `tm_total=300.016`을 반환했다.
NFS 완료 기록을 읽는 진단 TXT의 현장 출력은 `SERVER_STATUS=200`,
`runtime.request.finished.http_status=200`, `request.finished.duration_ms=385943`,
`request.returning.duration_ms=385970`이다. 모델 호출 대기값도 약 1513~1796초였다.
이는 우리 service가 준비한 결과와 호출자가 받은 HTTP 응답이 다름을 입증하지만,
특정 GENOS 게이트웨이 설정이나 제품 결함을 확인한 것은 아니다. 사용자는
운영 측에서 플랫폼 제한이 없다는 답변을 받았다고 전달했다.

## 실제 호출 경로와 500 생성 조건

워크플로우 `_run_once` → `call_code_serving`/`_post_code_serving` →
`POST /api/gateway/code_serving/{id}/json` → 플랫폼이 적재한 `service.service` →
`_normalize(LEGAL_AGENT)` → `_call(POST /v1/rag/ask)` → ASGI 앱의 `ask` → v5.
소켓 ID가 없는 현장 테스트는 `/json` 경로다.

|지점|500을 만드는 조건|이번 요청 기록과의 관계|
|---|---|---|
|`service.py:_call`|ASGI 요청/응답 처리 예외를 `RUNTIME_REQUEST_ERROR`와 status 500으로 반환|실패 시 runtime.request.failed가 남는다. 현장 완료는 runtime.request.finished 200|
|`service.py:_reported_dispatch`|미처리 예외를 `CODE_SERVING_ERROR`와 status 500으로 반환|실패 시 request.crashed/finished 500이 남는다. 현장 완료는 finished 200|
|`semantic_runtime/app.py` + `legal_agent/errors.py`|ContractError, ToolExecutionError, BudgetExhausted 등 계약·도구·예산 오류의 http_status=500|ask.failed와 구조화된 code/detail로 기록. 이번 완료 요청은 200|
|`DeadlineExceeded`|전체 deadline 초과|500이 아니라 504이며 기본 v5 요청 예산은 1800초|
|`TransportError`|내부 모델 HTTP/연결/대기 오류|직접 매핑은 502. model_http.failed/attempt.failed 기록이 필요|
|`service.py:_pipeline`|구축 result.ok=false 또는 구축 예외|PIPELINE_* 전용. LEGAL_AGENT 정규화 경로에서 호출되지 않음|
|`stream_app.py:worker`|스트림 worker의 미처리 예외를 status 500 결과 frame으로 반환|별도 커스텀 앱 /stream 경로이며 이번 /json 테스트와 구분|
|워크플로우 `_run_once`|urllib HTTPError의 exc.code를 화면에 표시|“코드서빙 응답 500”은 수신한 HTTP 500의 표시다. 300초를 판단해 500을 생성하는 코드가 아님|

워크플로우 자체 TimeoutError는 `failure_kind=client_exception`으로 기록된다.
우리 v5 모델 전송은 `context.remaining()`을 asyncio.timeout/httpx.Timeout에 전달한다.
`service._call`의 ASGI 내부 호출에는 별도 300초 wait_for/timeout 래퍼가 없다.

## 남은 300과 확인하지 못한 범위

현재 작업 코드의 숫자형 시간 설정을 다시 검사했다. 현재 source/config 977개를
읽었고 2MB 초과/읽기 불가 1개는 제외했다. 별도 확대 기록에는 완료된 릴리스·
설계 예제·테스트의 300초가 포함되며 이것을 현재 실행 설정으로 보지 않는다.
현재 코드에서는 `lawrag/core/embedding.py`의 `requests.post(timeout=(15,300))`가
남아 있다. 이는 임베딩 한 번의 읽기 대기이며 v5 모델 호출의 전체 deadline을
대신하지 않는다. 단순 숫자 일치만으로 이번 500의 원인으로 확정하지 않는다.

사용자 사진의 ~/DEV 목록에는 `runtime/`이 있다. 저장소 .gitignore와 genosIgnore는
이를 제외하고, R3 ZIP에도 runtime/·실행기/게이트웨이 설정 파일은 없다.
현재 로컬에는 해당 runtime/이 없어 내용을 확인할 수 없다. 이 폴더가 실행 래퍼인지
데이터 상태인지도 현장 파일 확인 전에는 미확인이다. .env와 CodeSpace 환경값은
코드서빙/워크플로우 프로세스 환경과 자동으로 공유되지 않는다.

## 현장 읽기 전용 검사

`GENOS_500_TIMEOUT_AUDIT_20260928.txt`는 ~/DEV에서 bash로 실행한다.
현재 코드/config, 숨긴 .env 시간 값, Git에서 제외된 runtime/의 코드/config를
읽고 파일/행/시간 값/HTTP 500 생성 위치와 HTTP ClientSession의 명시 timeout
유무를 출력한다. 비밀값·원문·질문·답변·프록시 주소는 출력하지 않는다.
서비스 import, 네트워크 호출, 코드/데이터/환경 수정이 없다.
runtime/은 symlink를 따라가지 않으며 2MB 초과 파일은 제외 수로 표시한다.
R3 주요 파일 SHA 대조는 해당 checkout의 확인이며 배포 프로세스의 바이트 인증이 아니다.
출력된 후보의 호출 여부·실제 serving 리비전은 다음 단계에서 대조해야 한다.

55개 관련 계약/회귀 검사와 모의 runtime/숨긴 .env/300초 산술식/HTTP 500/비밀 제외/
서비스 미실행/읽기 전용 사례를 확인했다. 실제 현장 원인은 아직 미확인이다.
이번 작업에서 서빙 코드, 프로필 pin, 데이터 manifest/CURRENT, 리비전은 변경하지 않았다.
