# Socket.IO 없는 통합 직접 실행 / 분리 워크플로우 R3

사용자가 R2 코드 ZIP을 현장 `~/DEV`에 `apply`까지만 실행했다고 보고했다.
Git push, 새 코드서빙 리비전 배포, 채팅앱 전환은 하지 않았다고 확인했다.
R3는 그 적용 상태에서 두 실행 방식을 유지하면서 자체·플랫폼 Socket.IO 전송을
사용하지 않는 교체 인계본이다. 현장 파일의 실제 해시와 선택 NFS generation은
R3 `check` 출력 전까지 미확인이다.

| `GENOS_MAIN_MODE` | 호출 주체 → 코드서빙 | 응답 |
|---|---|---|
| `integrated` | 채팅앱 → `main.py`의 `/chat` → 같은 프로세스 RAG | 기본 완성 JSON |
| `workflow` (미설정 기본값) | GENOS Python `run(data)` → 코드서빙 `/stream` → RAG | 단계 사이 HTTP SSE, 워크플로우 최종 JSON |

`existing`은 R2 호환을 위해 `workflow`의 별칭으로 남긴다. 두 모드 모두
`python3 main_router.py`로 시작하고 부팅 때 선택된다. 설정 변경은 새 리비전이나
재시작 뒤 적용된다. `main_integrated.py`는 이전 Run 설정을 위한 직접 JSON
호환 진입점이며 Socket.IO 서버를 띄우지 않는다. Build는
`python3 -m pip install -r 08_DEPLOYMENT/GENOS/requirements-sse.txt`다.
과거 `requirements-socketio.txt`를 그대로 참조하는 리비전도 SSE 의존성만 설치한다.

통합 모드는 `GENOS_CHAT_TRANSPORT=json`으로 고정하면 `/chat`의 기존
`{code,data.text}` 완성 응답을 쓴다. 별도 Python 워크플로우, 소켓 SID,
Socket.IO 옵션이 필요 없다. 과거 `main.py`의 명시적 HTTP SSE 기능은 기존
호환 경로로 남지만 이 배치의 기본 동작은 JSON이다.

워크플로우 모드는 기존 코드서빙 `/stream`의 HTTP `text/event-stream`을
Python 단계가 읽고 최종 결과를 반환한다. R3 전체 워크플로우 TXT는
`socketIOClientId`가 입력에 있어도 `main_socketio`를 import하거나 이벤트를
보내지 않는다. 기존 HTTP SSE 응답에서 사용하는 공통 표시 도우미의 주입형
emitter는 유지해 직접 HTTP SSE 회귀를 막았다. `WORKFLOW_SETTINGS`는
`socketio_enabled=false`, `progress_mode=off`를 보고한다.

두 방식 모두 GENOS 컨테이너 서비스의 `socket.io 실시간 스트리밍 사용` 옵션을
**끈다**. 서버 환경변수만으로 채팅앱 대상이나 워크플로우 편집기 코드가 바뀌지는
않는다. 통합 연결은 새 코드서빙 `/chat`을, 분리 연결은 기존 Python 워크플로우와
그 단계가 참조하는 `/stream` 코드서빙 ID를 선택한다. 현장 테스트는 워크플로우
테스트 화면에서만 수행한다.

## R2 apply 상태에서 교체

R3 ZIP과 R3 APPLY TXT를 함께 `~/DEV/TRANSFER`에 놓고 실제 선택된
generation 절대경로를 지정한다. 과거 ZIP들을 순서대로 적용하지 않는다.

```bash
export GENOS_GENERATION='/실제로/선택한/절대/generation/경로'
bash ~/DEV/TRANSFER/GENOS_NO_SOCKET_CHAT_20261007_R3_APPLY.txt check "$GENOS_GENERATION"
bash ~/DEV/TRANSFER/GENOS_NO_SOCKET_CHAT_20261007_R3_APPLY.txt apply "$GENOS_GENERATION"
cd ~/DEV
python3 -m pip install -r 08_DEPLOYMENT/GENOS/requirements-sse.txt
GENOS_MAIN_MODE=integrated bash ~/DEV/TRANSFER/GENOS_NO_SOCKET_CHAT_20261007_R3_APPLY.txt verify "$GENOS_GENERATION"
GENOS_MAIN_MODE=workflow bash ~/DEV/TRANSFER/GENOS_NO_SOCKET_CHAT_20261007_R3_APPLY.txt verify "$GENOS_GENERATION"
```

`check`에서 `CHECKOUT_DRIFT`, 알려지지 않은 staged/dirty 파일, cache·generation
해시 불일치가 나면 적용을 멈추고 `CHECKOUT_PREFLIGHT-*.json`의 파일명·해시를
확인한다. R2 적용 백업과 기존 원문·DB·CURRENT·NFS generation을 보존한다.
R3 `apply`도 새 백업 경로를 출력한다. R3를 원복할 때는 그 **정확한 R3 백업**을
`rollback /정확한/backup`으로 지정한다. R2 백업으로 바로 되돌리면 R1 또는
그 전 상태가 선택될 수 있으므로 이번 두 모드 전환 방법으로 사용하지 않는다.

현장 Git push는 `verify` 후 같은 `~/DEV` checkout과 generation의 release gate를
통과한 commit만 진행한다. 별도 Git 저장소를 쓰면 R3 PUSH_NEW_REMOTE TXT의
`GENOS_NEW_REMOTE_URL`을 실제 URL로 지정한다. push, 코드서빙 새 리비전,
채팅앱 바인딩은 각각 별도 단계다. 사용자가 보고한 현재 상태는 `apply`까지이므로
기존 서비스 리비전은 이 보고만으로 바뀐 것으로 보지 않는다.

현장 확인은 각 모드의 `__verify__`, 통합 일반 질문의 완성 JSON, 분리 방식의
`WORKFLOW_SETTINGS`/`SSE_CHECK`와 일반 질문의 `/stream` 소비·최종 JSON을
기록한다. 로컬 모의 테스트 성공은 GENOS 내부 모델·플랫폼 연결 성공이 아니다.
