# GENOS 배포·환경·서버 전체 로그

사용자 요청에 따라 RAG 요청 보고서 밖의 배포 명령, 빌드, Python import,
환경 설정 실패, stdout/stderr, 일반 Python 로그, HTTP 상태와 예외 원문을 기록한다.
기존 실행 명령 앞에 공통 수집기를 붙이고 서버의 기존 진입점에 초기화를 연결했다.
로그 저장 기능이며 MAIN 검색·모델·데이터 계약을 바꾸거나 새 파이프라인을 만들지 않는다.

2026-10-07 후속 [오류 전체 표시 R10](../../../08_DEPLOYMENT/GENOS/handoffs/full_error_logging_20261007_r10/GUIDE_UTF8.txt)은
수집한 오류가 요청 로그·API·채팅에서 빠지거나 잘리는 경로를 수정한다.
거절된 모델 결정과 실제 검증 오류·재시도·전체 조사 사유·traceback을 전달하며,
큰 ERROR가 비동기 큐 상한에 걸리면 동기 기록으로 보존한다.
일반 요청의 비동기 처리와 인증정보 정제는 유지한다.
아래 로그 반입 R1의 최종 화면 메시지 유지 설명은 당시 상태이며, R10은 실패 화면에도 상세 오류를 표시한다.
코드 ZIP/리비전과 별도로 워크플로우 편집기에 R10의 전체 TXT를 적용해야 한다.
GENOS 실제 적용·NFS·워크플로우 검증은 미실행이다.

## 저장 위치와 파일

기본 저장 위치는 `/nfs-root/diamo/8-agent/logs/system/<run_id>/`다.
`GENOS_SYSTEM_LOG_DIR`로 다른 절대경로를 지정할 수 있다. 실행마다 새 ID를 생성하고,
서로 다른 프로세스는 `단계-PID-고유값-파일명`으로 충돌을 피한다.
여러 배포 단계를 묶으려면 같은 셸에서 `GENOS_LOG_RUN_ID`를 명시한다.

| 파일명 끝부분 | 내용 |
|---|---|
| `stdout.log`, `stderr.log` | 감싼 명령의 실제 출력 바이트. 줄바꿈·한글·비 UTF-8 바이트도 보존 |
| `python.raw.log` | Python 일반 로그·RAG 이벤트와 전체 traceback. request_id 등 원래 이벤트 필드 포함 |
| `exceptions.raw.log` | 처리되지 않은 메인/스레드 예외 원문 |
| `workflow.errors.raw.log` | 별도 Python 워크플로우의 전체 예외와 HTTP 오류 응답 본문 |
| `workflow.events.raw.jsonl` | 워크플로우의 일반 이벤트 원래 필드 |
| `environment.json` | 실제 sys.executable·Python 버전·호스트·PID·cwd·설정 경로·중요 코드 해시 |
| `events.jsonl` | 시작/종료·종료 코드·시그널·NFS 쓰기 실패/복구. 실제 runtime binding이 확인되면 경로·manifest 해시 |
| `result.json` | 감싼 명령의 실제 종료 코드 |

원문 파일은 내부 로그다. 오류 메시지와 traceback을 축약·번역·길이 제한하지 않는다.
환경 스냅샷은 명시된 경로/모드/포트 값과 변수 이름만 기록하고, 인증키와 비밀번호 값을
환경 전체 덤프로 기록하지 않는다. 기존 컨테이너/RAG 공유 로그의 인증정보 정제는 유지한다.
원문 오류에 인증정보나 내부 자료가 포함된다면 NFS 원문에도 그대로 포함되므로 내부에서만 다룬다.
배포 명령의 모든 인자를 별도 목록으로 출력하지 않고 실행 파일과 인자 수를 기록한다.

요청별 공유 로그는 `GENOS_SHARED_LOG_DIR/<한국날짜>/<team>/<request_id>-<고유값>.log`이며,
같은 이름 `.json`은 전체 요청 보고서, `.llm_raw.jsonl`은 실제 수신 모델 응답이다.
공유 경로가 미설정이면 이 요청별 파일은 생성하지 않는다.
[READ_ERROR_LOGS.txt](../../../08_DEPLOYMENT/GENOS/handoffs/full_error_logging_20261007_r10/READ_ERROR_LOGS.txt)를
`bash ... --contains 'request_id 또는 run_id'`로 실행하면 일치 파일 전체를 출력한다.
`--file '/실제/로그파일.log'`는 해당 파일을 끝까지 출력한다. 원본 수정/삭제는 하지 않는다.
이전에 표시 경로에서 버린 내용은 원장/수신 원문에 남아 있을 때만 확인할 수 있다.

## 현장 적용·빌드·서버 시작

현장 인계본은 [누적 로그 반입 R1](../../../08_DEPLOYMENT/GENOS/handoffs/system_logging_20261007_r1/README.md)이다.
직전 query-latency R3 누적 기능과 MAIN45 서빙 코드를 보존한다.
실제 `~/DEV`의 파일 해시를 검사해 알려진 선행 상태만 허용하고, 백업 후 적용한다.
임의로 바뀐 현장 파일, 데이터 generation, .env, Git 이력을 덮어쓰지 않는다.

첨부 APPLY TXT는 표준 라이브러리 수집기를 내장하므로 기존 DEV에 새 모듈이 없어도
ZIP 검사·환경 오류·check/apply/gate/rollback의 출력부터 수집한다. 실제 Python은 `python3`다.
실행 후 표시된 `RUN`, `NFS`, `SPOOL`, `NFS_COMPLETE`를 확인한다.

코드서빙 빌드 명령은 기존 requirements 파일을 그대로 사용하여 감싼다.

```bash
python3 genos_log_runner.py --phase build -- python3 -m pip install -r requirements-serving.txt -r 08_DEPLOYMENT/GENOS/requirements-sse.txt
```

기존 시작 명령이 `python3 main_router.py --port ...`이면 같은 포트를 유지해 감싼다.
PORT 등 기존 환경변수가 있다면 아래 명령에서 `--port`를 생략할 수 있다.

```bash
python3 genos_log_runner.py --phase serving -- python3 main_router.py
```

`GENOS_MAIN_MODE=integrated`는 직접 JSON, `workflow`는 기존 Python 워크플로우 SSE다.
로그 기능으로 모드·플랫폼 연결·기존 포트를 변경하지 않는다.
플랫폼 service 함수 로더는 루트 `service.py`의 초기화부터 수집하며,
플랫폼 로더 자체의 시작 이전 출력을 수집하려면 그 시작 명령을 wrapper로 감쌀 수 있어야 한다.
`python3 service.py`를 서버 시작 명령으로 쓰지 않는다.

운영 환경에는 `GENOS_SYSTEM_LOG_DIR=/nfs-root/diamo/8-agent/logs/system`을 설정한다.
기본 일반 로그 수준은 INFO다. 상세 RAG 내부 이벤트까지 필요하면 기존 `GENOS_LOG_LEVEL=DEBUG`를,
외부 라이브러리 DEBUG 로그까지 필요하면 `GENOS_SYSTEM_LOG_LEVEL=DEBUG`를 추가한다.
`GENOS_SYSTEM_LOG_ENABLED=0`은 자동 서비스 수집만 끈다. 명시적으로 실행한 wrapper는 계속 수집한다.
WSL 계약 검사에서는 모의 경로를 쓰거나 자동 수집을 꺼서 운영 NFS를 만들지 않는다.

## 별도 워크플로우

ZIP/Git 배포와 워크플로우 편집기 변경은 별도다. 분리 방식을 사용하면 새
`WORKFLOW_PASTE_ALL.txt` 전체를 편집기에 반영한다. 정본 `genos_diagnostics.py`를
동일 해시로 압축 내장해 코드서빙의 모듈을 워크플로우 컨테이너가 공유한다고 가정하지 않는다.
워크플로우 환경에도 로그 저장 경로를 지정해야 하며 NFS mount/권한은 현장 확인 대상이다.
일반 이벤트, 통신 오류 원문, 전체 traceback을 저장하고 기존 최종 JSON/화면 메시지는 유지한다.
HTTP 오류 본문을 끝까지 읽어 한 번 저장하고, 같은 원본 바이트로 기존 진단/응답을 처리한다.

## NFS 실패·복구·저장공간

요청 스레드는 먼저 로컬 pending 파일을 fsync하고 NFS 전송은 별도 daemon 스레드가 수행한다.
NFS에 기록한 바이트를 fsync·대조한 뒤 성공한 pending만 제거한다. NFS 성공분의 원문을
로컬에 계속 중복 보관하지 않는다. 프로세스 간 파일을 공유해 쓰지 않는다.
기본 spool은 `/tmp/8-agent-system-logs-<uid>/`이고 `GENOS_LOG_SPOOL_DIR`로 지정할 수 있다.
NFS 실패의 전체 traceback은 콘솔과 pending 이벤트에 기록한다. NFS가 복구되면 재전송한다.

종료 때 `NFS_COMPLETE False`이면 표시된 SPOOL을 보존하여 아래처럼 재전송한다.

```bash
python3 genos_log_runner.py --recover '<출력에 표시된 실제 SPOOL 절대경로>'
```

복구는 명령/배포를 재실행하지 않고 해당 로그만 전송한다.
원래 바이트 위치에 다시 쓰므로 전송 중단 후 재전송에서도 원문을 중복 이어 붙이지 않는다.
spool별 잠금으로 원래 프로세스와 수동 복구의 동시 전송을 거부한다.
완료된 .log는 필요할 때 무손실 gzip으로 보관할 수 있으나 자동 삭제·회전은 수행하지 않는다.
spool 폴더의 작은 `spool.json`·잠금 파일은 복구 위치 증거로 보존한다.

임시 로컬 저장소는 재배포/컨테이너 삭제 후 보존을 보장하지 않는다. NFS가 계속 불통이면
컨테이너를 없애기 전에 pending을 회수해야 한다. 로컬 쓰기까지 실패하면 콘솔에
`LOCAL_SPOOL_FAILED`를 남기며 NFS 성공으로 표시하지 않는다.
NFS의 서버 간 fsync 내구성과 실제 장애 복구는 현장 인증 전까지 미확인이다.

## 수집 범위와 검증 상태

우리 명령·Python 프로세스가 시작된 뒤 출력한 내용이 대상이다. 업로드 UI,
Git 서버, 이미지 pull, 스케줄링, NFS mount 자체, 플랫폼 빌드의 wrapper 실행 이전 오류는
프로세스에 전달되지 않으므로 이 코드가 자동 수집할 수 없다.
그런 플랫폼 로그는 현장 화면에서 원문을 내보낸 뒤 같은 NFS에 보관해야 한다.
Python 자체가 없거나 원본 코드의 문법 오류가 있으면 반드시 바깥 wrapper/플랫폼 로그를 사용한다.
실제 GENOS 접속·리비전 배포·workflow 화면 테스트는 이 외부 세션에서 수행하지 않는다.
로컬 계약/합성 반입 검증, 현장 적용, Git push, 리비전 배포, 실제 요청 확인을 별도 상태로 기록한다.
로컬 ACTIVE_RELEASE와 데이터 CURRENT는 이번 로그 기능으로 전환하지 않는다.
