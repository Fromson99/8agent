# 기존 채팅과 통합 Socket.IO 채팅을 나란히 실행하는 코드

2026-10-07 사용자 요청에 따라 기존 코드서빙은 그대로 두고, 새 코드서빙에서
환경변수로 `/chat`의 전송 방식을 선택하는 작업 코드를 추가했다.
이 문서는 작업 코드와 로컬 검증 범위를 설명한다. GENOS 현장 리비전이나 채팅앱을
실제로 생성·연결·검증한 기록은 아니다.

## 두 진입점

| 코드서빙 | Run | 설정 | `/chat` |
|---|---|---|---|
| 기존 인스턴스 | 기존 Run 명령 | 기존 설정 | 기존 동작 그대로 |
| 새 인스턴스 | `python3 main_router.py` | `GENOS_MAIN_MODE=existing` | 현재 `main.py`의 JSON/선택형 SSE |
| 새 인스턴스 | `python3 main_router.py` | `GENOS_MAIN_MODE=integrated` | `main_integrated.py`의 JSON + Socket.IO token/end |

새 코드서빙은 기존 checkout/코드 세대와 동일한 RAG 구현을 사용한다.
`main_router.py`가 부팅할 때 한 번 앱을 고르므로 설정 변경 시 새 리비전/재시작이 필요하다.
기존 인스턴스와 새 인스턴스는 서로 다른 코드서빙 ID와 포트를 사용할 수 있다.
기존 `service/service.py`, `service.py`, `main.py`의 입구는 바꾸지 않았다.
통합 모드에서 `/chat → semantic_runtime.chat_adapter.chat → service.service`
`→ /v1/rag/ask → legal_agent v6`의 한 요청을 실행한다.

## 새 코드서빙 설정

Build (GENOS 현장 Python):

```text
python3 -m pip install -r 08_DEPLOYMENT/GENOS/requirements-socketio.txt
```

Run (`PORT` 등의 기존 수신 포트 환경변수가 없는 리비전에서는 `--port <기존 수신 포트>` 추가):

```text
python3 main_router.py
```

환경 설정 이름:

```text
GENOS_MAIN_MODE=integrated
GENOS_SOCKETIO_PATH=socket.io
GENOS_CHAT_TRUST_PLATFORM_IDENTITY=1
GENOS_CHAT_GATEWAY_TOKEN=<플랫폼에서 /chat으로 전달하는 Bearer 토큰과 일치하는 비밀값>
```

토큰 값은 로그·문서·Git에 기록하지 않는다. 기존 인증 함수는 값 길이가 32자 이상이고
요청의 `Authorization: Bearer ...`와 일치할 때만 플랫폼 신원을 신뢰한다.
이 조건과 실제로 이 코드서빙에 연결된 `socketIOClientId`가 모두 만족해야
해당 연결에 토큰을 보낸다. 신원을 확인할 수 없거나 다른 서버의 SID라면
완성 JSON은 반환하되 Socket.IO 전송은 생략하고 `socketio_transport.reason`에
`platform_identity_unverified` 또는 `socket_not_connected_here`를 남긴다.
인증이 GENOS 게이트웨이에서 소비되어 코드서빙에 전달되지 않는다면
해당 플랫폼의 공식 인증·연결 계약을 먼저 확인해야 한다. 이 검사를 끄고
클라이언트가 지정한 SID로 임의 전송하면 다른 대화로 답이 갈 수 있다.

GENOS 컨테이너 서비스 화면에서 새 코드서빙을 `워크플로우로 사용`, 채팅 경로 `/chat`으로
설정한다. `GENOS_MAIN_MODE=integrated`에서는 **socket.io 실시간 스트리밍 사용**을 켠다.
반면 `GENOS_MAIN_MODE=existing`에서 현재 HTTP SSE를 쓸 때는 그 옵션을 끈다.
사진에는 소켓 경로와 namespace의 실제 연결 값은 나오지 않는다.
현재 코드는 기본 namespace `/`, 기본 경로 `/socket.io`를 사용한다.
GENOS 샘플 코드에 다른 경로가 명시되어 있으면 `GENOS_SOCKETIO_PATH`를 그 경로로 설정하고,
다른 namespace라면 코드를 그 계약에 맞춰 수정·검증한다.

## 입력·출력

통합 모드의 `/chat`은 `{"code":0,"data":{"text":"...",...}}`를 한 번 반환한다.
연결이 유효하면 실행 중 `token`, Reasoner 블록 `agentFlowExecutedData`,
끝에 `end` 이벤트를 같은 SID로 보낸다. 답변 조각은 이미 있는
`answer_stream.capture`를 사용하므로 모델·RAG 실행을 중복하지 않는다.
한 SID의 요청을 동시에 두 번 시작하면 409로 거절해 토큰이 섞이지 않게 한다.
HTTP 연결이 끊겨도 이미 시작한 RAG는 원장을 닫고 끝나며 재질의하지 않는다.
플랫폼 등록용 `question=__verify__`와 `API_TYPE=SOCKET_CHECK`는 모델을 호출하지 않는다.

`SOCKET_CHECK`의 `socketio_transport.connected=true`는 서버에 SID가 실제 연결됐고
플랫폼 신원이 확인됐다는 뜻이다. 이 값만으로 채팅 화면의 토큰 렌더링 성공을
뜻하지는 않는다. 현장 검증은 기존 워크플로우 테스트 화면에서 다음 순서로 한다.

1. `{"question":"__verify__"}`가 JSON `text=verified`를 반환한다.
2. GENOS가 실제로 제공한 `socketIOClientId`를 포함한
   `{"API_TYPE":"SOCKET_CHECK"}`에서 `connected=true`, 경로와 reason을 확인한다.
3. 짧은 일반 질문에서 첫 `token`이 최종 JSON 전에 화면에 나타나고,
   `end` 뒤의 최종 답과 중복·누락이 없는지 확인한다.
4. 같은 질문을 기존 코드서빙에 보내 이전 경로가 그대로 응답하는지 확인한다.

로컬에서는 FastAPI/Socket.IO를 실제 임시 포트로 함께 띄워 답변 토큰이
완성 JSON보다 먼저 도착하는 것과 다른 SID 차단·중복 요청 거절을 검증했다.
현장 컨테이너 서비스의 정확한 Socket.IO 경로·인증 헤더 전달·화면 렌더링은 미확인이다.
로컬 MAIN 활성 릴리스 generation 44와 GENOS 데이터 generation은 이 작업 코드로 바뀌지 않는다.
코드 적용·동일 checkout generation gate·Git push·새 코드서빙 리비전 배포·채팅앱
선택은 각각 별도 상태로 확인한다.
