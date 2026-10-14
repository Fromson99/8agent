# 통합 Socket.IO / 기존 Python 워크플로우 SSE 선택 R2

사용자가 원한 선택은 RAG 실행 방식이다. R1은 직접 HTTP `/chat`과 직접 Socket.IO
`/chat`만 선택했고, 별도 Python 워크플로우 선택은 구현하지 않았다.
R2는 `python3 main_router.py`에서 `GENOS_MAIN_MODE`로 두 백엔드 앱을 선택한다.
기존 MAIN generation 44 RAG·AD·기억·조사 완료 계약과 워크플로우 코드는 보존한다.
작업 코드와 로컬 모의 검증 결과이며 GENOS 플랫폼 배포·연결 완료 증거는 아니다.

| 값 | 실행 경로 | 답변 스트림 |
|---|---|---|
| `workflow` (미설정 기본값) | GENOS의 별도 Python `run(data)` → 게이트웨이 → 코드서빙 `/stream` → RAG | 코드서빙 → Python 워크플로우는 HTTP SSE |
| `integrated` | 코드서빙 `/chat` → 같은 프로세스 RAG | 코드서빙 → 연결된 플랫폼 SID로 Socket.IO `token` / `end` |
| `existing` | R1 설정 이름의 호환 별칭으로 `workflow` 선택 | HTTP SSE |

통합 모드의 Socket.IO는 SSE와 다른 전송 프로토콜이다. 사용자가 원하는 실시간
답변 스트림을 Socket.IO 이벤트로 보낸다는 뜻이며, HTTP `text/event-stream`을
Socket.IO 소켓에 그대로 쓰지 않는다. 통합 방식에는 별도 GENOS Python 단계가 필요 없다.
워크플로우 방식은 기존처럼 `/stream`의 `progress` / `answer_delta` / `result`를 읽는다.
기존 워크플로우의 화면 전송 helper가 플랫폼의 `main_socketio`를 쓰는 기능도 보존한다.
이는 코드서빙이 소켓 서버를 제공하는 통합 모드와 별개의 기존 화면 기능이다.

## 설정과 플랫폼 연결

코드서빙 Run은 두 모드 모두 `python3 main_router.py`다.
변수는 부팅 시 적용되므로 환경변수를 변경한 뒤 리비전을 재배포하거나 재시작한다.
`python3 main.py`는 기존 직접 HTTP 채팅 진입점으로 남으며 이 선택 변수를 적용하지 않는다.

| 설정 대상 | `workflow` | `integrated` |
|---|---|---|
| 코드서빙 환경변수 | `GENOS_MAIN_MODE=workflow` | `GENOS_MAIN_MODE=integrated` |
| Build | 기존 SSE 의존성 또는 두 모드 공용 `requirements-socketio.txt` | `python3 -m pip install -r 08_DEPLOYMENT/GENOS/requirements-socketio.txt` |
| 채팅앱 연결 | 기존 별도 Python 워크플로우를 선택 | 새 코드서빙 `/chat`을 선택 |
| 코드서빙 Socket.IO 옵션 | 끔, 이 앱은 소켓 서버를 띄우지 않음 | `socket.io 실시간 스트리밍 사용` 켬 |
| 별도 Python 단계 | 기존 `genos_rag_chat.py:run`과 게이트웨이 설정 유지 | 사용하지 않음 |
| 코드서빙 인증/소켓 | 기존 게이트웨이 인증 | 연결된 SID, `GENOS_CHAT_TRUST_PLATFORM_IDENTITY=1`, 전달되는 Bearer와 `GENOS_CHAT_GATEWAY_TOKEN` 일치 |

**서버 환경변수는 GENOS에 저장된 채팅앱 연결 대상이나 워크플로우 정의·소켓 옵션을
자동으로 수정하지 않는다.** 현재 제공된 플랫폼 API 계약이 없어 이 변경을 실행할 수 없다.
두 연결을 미리 구성하고 선택하거나, 모드 전환 때 위 플랫폼 설정도 함께 맞춘다.
변수 하나만 바꾸면 플랫폼의 별도 워크플로우 사용 여부까지 바뀐다고 설명하지 않는다.

통합 모드의 `GENOS_SOCKETIO_PATH`는 기본 `socket.io`, namespace는 `/`다.
게이트웨이 인증이 서버에 전달되지 않거나 SID가 이 서버에 연결되지 않았으면
기존 최종 JSON은 보존하고 토큰 전송 상태에 미연결 이유를 남긴다.
키·토큰 값은 문서·로그·Git에 남기지 않는다.

## 경로 계약

`main_workflow.py`는 독립 FastAPI 앱으로 `/json`과 `/stream`을 기존 구현에 연결한다.
일반 `/chat` 요청을 409 `wrong_entrypoint`로 거부한다. 별도 워크플로우가 연결되지
않았는데 직접 RAG를 실행하고 이를 워크플로우 방식이라고 보고하지 않는다.
플랫폼 등록용 `__verify__`와 `API_TYPE=CHAT_MODE`는 모델 없이 JSON을 반환한다.
직접 `main.py`나 통합 앱을 먼저 import해도 워크플로우 앱의 경로는 섞이지 않는다.

`main_integrated.py`의 `/chat`은 RAG를 같은 프로세스에서 한 번 실행한다.
요청의 인증과 실제 연결된 SID를 확인한 뒤 `token`, `agentFlowExecutedData`, `end`를
그 SID에 전달한다. 최종 응답은 기존 `code/data/text` JSON이다. HTTP 응답이 끊겨도
이미 시작된 실행은 원장을 닫으며, 같은 SID의 중복 실행은 409로 막는다.
기존 `/json`과 `/stream`은 호환 경로로 보존한다.

각 앱의 `GET /chat-mode`와 `API_TYPE=CHAT_MODE`는 선택된 모드·실행자·전송 계약을
보여준다. `platform_binding=NOT_VERIFIED`는 채팅 화면 연결을 이 검사로 인증하지
않는다는 뜻이다. 코드서빙 시작 로그에는 적용한 `chat_mode`가 남는다.

## 반입과 검증

[반입본 안내](../../../08_DEPLOYMENT/GENOS/handoffs/routed_socket_chat_20261007_r2/GUIDE_UTF8.txt)의
새 ZIP과 실행 TXT를 사용한다. R1과 기존 로그는 보존한다.
코드 적용 → 같은 `~/DEV` checkout에서 선택 generation gate → Git push → 해당 commit의
코드서빙 리비전 배포 → 모드별 플랫폼 연결 → 워크플로우 테스트 화면 검증은 별도 단계다.
원문·generation·CURRENT·runtime DB·로컬 활성 포인터를 변경하지 않는다.

현장 질의 검증은 워크플로우 테스트 화면에서만 한다.

1. 통합은 `__verify__`, `API_TYPE=CHAT_MODE`, 실제 SID의 `SOCKET_CHECK`, 짧은 질의에서
   첫 token과 최종 JSON의 순서·중복/누락을 확인한다.
2. 워크플로우는 기존 Python 단계로 `WORKFLOW_SETTINGS`와 `SSE_CHECK`를 실행하고,
   일반 질의에서 `code_serving_transport.route=/stream`, opened 및 answer_events를 확인한다.
3. 양쪽의 코드 commit·선택 generation·내부 모델·team/runtime 설정을 인계 기록에 남긴다.

로컬에서는 실제 임시 HTTP/Socket.IO 포트에서 통합 토큰과 워크플로우 SSE 조각이
최종 답변보다 먼저 도착하고 RAG가 한 번 실행되는지 확인한다. ZIP 적용·재실행·
원복·알 수 없는 수정 보존·동일 checkout gate·로컬 bare Git push도 검증한다.
실제 GENOS 인증 전달·소켓 경로·플랫폼 전환·화면 렌더링은 현장 검증 전 미확인이다.
