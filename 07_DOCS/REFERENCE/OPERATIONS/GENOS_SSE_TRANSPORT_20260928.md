# GENOS SSE 전송 패치 · 2026-09-28

## 시작 지연 후속 수정: sse-startup-20260928-r1

사진의 `resources.matcher`는 약 51초(스레드 CPU 약 46초), 마지막 단계는
`fulltext.verify` 시작이었다. 사용자는 Run을 `python 08_DEPLOYMENT/GENOS/start_sse.py`로
바꾼 뒤 약 12분간 서빙이 준비되지 않는다고 보고했다. 기존 SSE 앱의 import가
`service.py`의 자동 WARMUP을 즉시 시작하고, GET `/`·`/health`는 404이며,
시작 스크립트가 `WEB_CONCURRENCY`를 상속하는 것을 로컬에서 재현했다.
현장 worker 수·재시작·플랫폼 probe 경로·본문 DB 읽기 상태는 아직 미확인이다.
이 관측만으로 12분의 원인을 하나로 확정하거나 정상 준비 시간으로 판단하지 않는다.

후속 수정은 `stream_app.py`와 `start_sse.py` 두 파일만 변경한다. HTTP 앱 시작과
SSE_CHECK는 backend를 import하지 않으며 GET `/`·`/health`는 HTTP 생존 상태만 반환한다.
응답의 `readiness_scope=http`, `data_readiness=NOT_CHECKED`는 데이터·모델 준비 성공을
뜻하지 않는다. 질문·WARMUP 등 실제 backend 요청에서 기존 `service`를 지연 적재하고
기존 SHA-256·세대·모델 검증을 실행한다. 최초 자료 준비 비용은 남는다.
worker는 1개를 명시하며 한 프로세스의 동시 질문 수 제한은 추가하지 않는다.
워크플로우·데이터·CURRENT·엔진 pin은 변경하지 않는다. Run·Build 값은 유지한다.

인계는 `GENOS_SSE_STARTUP_20260928_R1_APPLY.txt`를 기존 `~/DEV`에서 실행하고,
검증한 두 파일을 commit/push하여 새 코드서빙 리비전을 배포한다. 설치기는 원본 백업,
등록 해시 검사, 재실행 확인과 rollback을 제공한다. `SSE_CHECK`의
`stream_startup_revision=sse-startup-20260928-r1`로 시작 수정의 실제 선택을 확인한다.
그다음 워크플로우 테스트의 `WARMUP`/`WARMUP_STATUS`로 자료 준비를 별도 확인한다.
로컬 회귀·실제 HTTP 기동 검사와 GENOS 현장 배포 성공은 별도다.

현행 인계 설치기 버전은 `sse-transport-20260928-r2`다. 서버·워크플로우 리비전은
`sse-transport-20260928-r1`을 유지한다. R2는 설치기의 checkout 경로 처리만 수정하고
검증한 R1 ZIP의 파일 5개를 그대로 싣는다. 이전 R3 시간/캐시 호환 복구와
HTTP 오류 진단이 적용된 기존 코드에 전송 파일 5개만 추가·교체한다.
최종 답변은 요청한 HTTP 연결에서 받는다. `socketIOClientId`는 채팅 화면 진행
표시에 쓰이며 결과 수신에는 필수가 아니다. 수신 포트는 기존 코드서빙 서버의
시작 설정이며 새 회신 주소나 포트를 만드는 절차가 아니다.

2026-09-28 추가 현장 사진: 코드서빙 701의 `sse2` 커밋에 위 파일 5개가
반영된 것을 사용자 기록으로 확인했다. 앞선 워크플로우 테스트는 새 워크플로우
리비전으로 `/stream`을 요청했으나 `Not Found`, `opened=false`였다.
소스 반영과 실제 HTTP 앱 연결을 구분한다. `stream_app.py`의 `/stream`은 별도
FastAPI 앱의 route이며 기존 `service(config, data)`를 적재하는 것만으로 등록되지
않는다. `start_sse.py`도 파일 반입만으로 실행되지 않는다. 후속 환경 설정 사진에서
코드서빙 701의 Build와 Run이 모두 비어 있고 언어별 기본값을 쓰는 것을 확인했다.
파일 미반영으로 단정하거나 ZIP 재적용을 반복하지 않는다. 이 화면의 Build에
`python -m pip install -r 08_DEPLOYMENT/GENOS/requirements-sse.txt`, Run에
`python 08_DEPLOYMENT/GENOS/start_sse.py`를 저장하고 같은 검증 commit으로 재배포한다.
화면의 `$PORT`는 예시 placeholder이며 실제 포트 숫자나 런타임 변수의 존재까지
사진만으로 확인한 것은 아니다. 포트 누락/충돌 시 시작 로그를 확인해 기존 수신
포트를 사용한다. 새 설정으로 `/stream`이 실제 노출되는지는 SSE_CHECK로 별도 확인한다.
여기서 시작 명령은 GENOS가 실행할 앱을 지정하는 배포 설정이며 코드스페이스에서
별도 서버를 수동으로 켜라는 지시가 아니다. 실제 Run 값과 기존 포트를 확인해 안내한다.

후속 사용자 요구는 Build/Run을 비운 언어별 기본값 유지다. 기존
`service(config, data) -> dict` 질문·답변 경로는 그 방식으로 사용해 왔지만,
현재 `/stream`은 별도 앱에만 등록되어 기본 로더에서는 404가 관측됐다.
위 명시 시작 명령은 현재 제공한 SSE 앱을 선택하는 방법이며, GENOS에서 SSE를
구현하는 유일한 방법으로 확정하지 않는다. 기본값을 유지하는 SSE 변경에는
현장 기본 로더의 앱 적재·route 확장 계약 확인이 필요하다. 실제 기본 로더
`main.py` 원본과 확장 계약은 현재 반입 자료에서 확인되지 않았다. 화면의 회색
`uvicorn main:app ...` 예시를 실제 기본 실행 명령으로 간주하거나, 저장소 루트에
`main.py`를 추가하면 자동 선택된다고 추정하지 않는다. 이 확인 없이 기본 로더의
앱을 임의로 변경하는 코드나 기본값 SSE 지원 완료를 인계하지 않는다.

## 실행 경로와 범위

`워크플로우 service → _stream_code_serving → /stream → stream_app → 기존 service.service`
로 연결한다. LEGAL_AGENT의 검색·모델·세대 선택·최종 답변 계약은 기존 service가 담당한다.
워크플로우는 소켓 ID가 없어도, 진행 표시가 off여도 SSE를 읽는다.
서버는 `: connected`를 먼저 전송하고 조용한 동안 10초마다 heartbeat를 보낸다.
`result`는 기존 service의 결과 한 개다. 응답의 `code_serving_transport`에
실제 경로·서버 리비전·heartbeat 수를 남긴다.

`/stream` HTTP 404/405에서만 기존 `/json`으로 한 번 전환한다.
500·읽기 오류·중간 연결 끊김에는 작업을 다시 요청하지 않는다.
SSE_CHECK는 이 JSON 전환 없이 실제 스트림 경로를 확인하며 모델을 호출하지 않는다.

수정 파일은 `workflow/genos_rag_chat.py`, `stream_app.py`, `start_sse.py`,
`requirements-sse.txt`, `workflow/workflow.env.example`다. 모두
`08_DEPLOYMENT/GENOS/` 아래에 있다. RAG 전체 예산 1800초와 워크플로우 소켓
대기 2100초는 유지한다. 이 패치는 40분 계산을 허용하는 요청 예산 변경이 아니다.
데이터·CURRENT·용어집 compiler·engine pin은 변경하지 않는다.

## 현장 적용

첨부 `GENOS_SSE_20260928_R2_APPLY.txt`는 ZIP 바이트를 내장한 실행 가능한 Bash다.
ZIP과 TXT 중 어느 파일을 받을지에 따른 경로 오류를 피하며 다음처럼 실행한다.

```bash
bash ~/DEV/TRANSFER/GENOS_SSE_20260928_R2_APPLY.txt
```

기본 적용 대상은 기존 Git checkout `~/DEV`다. 실행 로그·해시 영수증·원복용 원본을
`~/DEV/TRANSFER/sse-transport-20260928-r2/`에 남긴다. `~/DEV`가 `/workspace` 등을
가리키는 checkout 링크면 실제 Git root를 확인해 적용한다. 영수증의 root는 실제 경로,
requested_root는 사용자가 지정한 경로다. 파일 내부 링크는 계속 거부한다.
사진의 R1 오류는 코드 쓰기 전 중단했으며 R2로 재실행할 수 있다. 알려진 R3/HTTP 진단 파일
바이트만 교체하며 다른 코드가 발견되면 보존하고 실패 상태를 기록한다.
같은 TXT를 재실행하면 이미 적용된 파일을 확인한다.

코드 커밋 후 같은 TXT를 `MODE=gate`로 실행하면 push할 checkout의 기존
`genos_release_gate.py`를 호출한다. 기존 설정/CURRENT에서 자동 선택한 generation과
해시를 기록하고 그 checkout의 E2E와 verify_assets를 검사한다. 데이터는 새로 만들지 않는다.
그 설정이 코드서빙 리비전의 generation 설정과 같은지는 배포 화면에서 확인한다.
세대 설정이 없는 코드를 임의의 최신 NFS 폴더에 연결하지 않는다.

Git commit/push와 리비전 배포는 적용과 별도 단계다. 다른 작업 파일을 함께
커밋하지 않도록 첨부 README의 5개 경로만 지정한다. gate PASS 이후 통과한 commit을
push하고, 코드서빙에서 같은 commit과 기존 generation으로 새 리비전을 만든다.

## 코드서빙 시작 설정

빌드 의존성 파일을 `08_DEPLOYMENT/GENOS/requirements-sse.txt`로 설정한다.
기존 serving 의존성과 SSE 서버용 uvicorn을 설치한다. 기존 service 함수 로더만
실행하는 현재 배포 경로에는 `/stream`이 등록되지 않는다. 제공한 별도 SSE 앱을
사용하려면 아래 시작 설정으로 연결한다. 기본값 유지 방식은 위 후속 요구와 같이
기본 로더의 확장 계약을 먼저 확인해야 한다.

기존 플랫폼이 PORT / UVICORN_PORT / SERVER_PORT / GENOS_PORT 중 하나를 제공하면
시작 명령은 다음과 같다.

```bash
python 08_DEPLOYMENT/GENOS/start_sse.py
```

포트 환경변수가 없으면 **기존 코드서빙 시작 명령의 --port 값을 그대로** 붙인다.
이 문서에서는 GENOS의 실제 포트가 확인되지 않아 값을 추정하지 않는다.
포트는 새로운 결과 수신 설정이 아니다. 서로 다른 포트 환경변수가 있으면 명시된
기존 --port 값을 사용한다. 기타 GENOS 주소·인증키·팀·generation 설정은 재사용한다.

## 워크플로우 교체와 테스트

`GENOS_SSE_20260928_R2_WORKFLOW_PASTE_ALL.txt` 전체를 각 대상 워크플로우 Python
단계에 붙여넣고 저장·배포한다. Git push만으로 워크플로우 편집기의 Python은 바뀌지 않는다.
기존 코드서빙 ID·토큰·BASE_URL·TEAM_ID와 대기 설정은 그대로 사용한다.

진행 표시를 켜려면 **워크플로우 환경 설정**의 `GENOS_RAG_PROGRESS_UI`를 `socketio`로
저장·배포한다. `socketio-final`은 최종 답변만 표시한다. 소켓 ID는 실제 GENOS 채팅이
전달하는 값을 사용하며 직접 생성하지 않는다. 단계별 상태와 조용한 동안의 경과 시간을
표시한다. 서버 heartbeat는 10초마다, 화면 경과 시간 갱신은 최대 30초마다다.
워크플로우 테스트는 소켓 ID가 없을 수 있어 진행 표시는 실제 채팅에서 확인한다.
V1.8.6의 조기 표시·최종 답변 중복은 아직 현장 미확인이다. 표시가 실패해도 SSE 수신을 계속한다.

현장 검증은 워크플로우 테스트 화면에서만 한다. 입력 JSON:

```json
{"question":"SSE_CHECK"}
```

`sse_check.sse_ready=true`, `transport.route=/stream`, `transport.opened=true`,
`stream_server_revision=sse-transport-20260928-r1`이어야 한다.
404/405나 false면 코드서빙의 시작 앱/새 리비전/워크플로우가 선택한 코드서빙 ID를
확인한다. 이 진단은 검색·모델·데이터 캐시를 실행하지 않는다.
그다음 같은 화면에서 실제 질문을 실행하고 300초 이후 최종 답변과
`code_serving_transport.route=/stream`, heartbeat 수, request_id를 기록한다.
빠른 SSE_CHECK 통과만으로 긴 요청 성공을 보고하지 않는다.

## 원복

실행 출력의 `BACKUP_READY` 경로를 지정해 같은 TXT를 실행한다.

```bash
MODE=rollback ROLLBACK_FROM='<출력된 BACKUP_READY 경로>' bash ~/DEV/TRANSFER/GENOS_SSE_20260928_R2_APPLY.txt
```

원복 뒤 변경 전 Git commit/코드서빙 리비전/시작 명령과 백업한 워크플로우 Python으로
각각 복귀한다. 원복 후에 수정한 파일은 자동 덮어쓰지 않는다. 데이터 generation은 유지한다.

## 검증과 미확인

진행 표시·소켓 ID 조합, 404/405 전환, 500 단일 호출, heartbeat와 최종 결과,
SSE_CHECK의 모델 미호출, 기존 답변 출력·service 진입 계약을 로컬에서 검사했다.
WSL에서 실제 새 시작 명령과 HTTP `/stream` SSE_CHECK도 통과했다.
R2 설치 검사는 실제 R1 TXT의 checkout 링크 거부를 재현한 뒤 같은 fixture에
R2 적용·재실행·확인·링크 경로 원복과 실제 경로 영수증을 검증했다.
R3/오류 진단 원본 적용·쓰기 실패 원복·후속 변경 보존·payload 링크 거부·
R1/R2 payload 바이트 동일성·커밋 코드 gate도 검증했다.
이 결과는 GENOS 현장 배포나 300초 이후 결과 수신의 증명이 아니다.
플랫폼의 절대 실행 제한은 SSE heartbeat로 해제된다고 가정하지 않는다.

코드 ZIP/파일 SHA·코드 루트·기준 commit·검사 결과는 인계 디렉터리의
HANDOFF_RECEIPT.json에 남긴다. 실제 push commit·GENOS generation·리비전·현장 요청 결과는
미확인이며 적용/게이트 영수증과 현장 화면 결과로 별도 확인한다.
