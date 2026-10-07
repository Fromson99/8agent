# 승호 브랜치와 300초 실패 경로 비교

2026-09-28 사용자 요청으로 외부 Git의 승호 브랜치 두 개를 fetch한 뒤 읽었다.
현재 작업 브랜치를 바꾸거나 팀원 코드를 수정하지 않았다. 현장 GENOS에는 접근하지 않았다.

- `infocz/fde/seungho/integration`: `f43a11d1562f708c00dc9f954d6bf2cde6907af8`,
  2026-09-28 14:16 +09:00, `LoanInvestment update commit`.
- `infocz/fde/seungho/els`: `949737ca948ce101d4fa59f013002fe7e7f09dec`,
  2026-09-02 10:57 +09:00. 최신 통합 브랜치의 보고서 경로와 구분한다.
- 비교한 우리 코드는 `feature/legal_RAG`의 현재 작업 파일이다. HEAD만으로
  미커밋 변경을 포함한 비교 대상 전체를 식별할 수 없어 파일 SHA도 별도 기록했다.

읽은 소스 스냅샷과 SHA 영수증은
`90_RUNTIME/OUT/audit/genos-seungho-20260928/`에 있다.
이 스냅샷은 로컬 코드 증거이며 현장 배포 리비전과 동일하다는 보증은 아니다.

## 변경 전 연결 차이

아래 표와 우리 코드의 줄 번호는 비교 당시 스냅샷 기준이다. 후속 SSE 패치로
워크플로우의 전송 선택을 바꿨으며 현재 상태는 문서 끝의 후속 구현을 따른다.

| 항목 | 승호 통합 브랜치의 보고서 생성 | 우리 현재 법률 RAG |
|---|---|---|
| 긴 요청 선택 | REPORT_GENERATE / REPORT_EXTRACT / REPORT_PARSE는 항상 /stream 우선 | _ChatProgress.enabled일 때만 /stream |
| 소켓 ID 없는 워크플로우 테스트 | /stream을 읽음. 화면 소켓 출력 여부와 별개 | /json을 호출함 |
| 진행 표시를 끔 | REPORT_PROGRESS=off여도 긴 요청은 /stream | GENOS_RAG_PROGRESS_UI=off이면 /json |
| /stream 미지원 | HTTP 404/405에서만 /json으로 한 번 전환 | 같은 규칙 |
| 서버 HTTP 앱 | front.app:app을 시작 명령으로 실행하도록 소스/문서에 연결 | stream_app:app은 선택형 앱. 기본 service 함수 로더는 /stream을 만들지 않음 |
| 서버 heartbeat | 10초마다 SSE 주석 또는 마지막 진행 상태 갱신 | stream_app도 조용한 동안 10초마다 heartbeat를 보냄 |
| 스트림 클라이언트 대기 | REPORT_STREAM_READ_TIMEOUT 기본 120초의 소켓 읽기 대기 | GENOS_CODESERVING_TIMEOUT_SECONDS 기본 2100초의 소켓 대기 |
| JSON 클라이언트 대기 | REPORT_TIMEOUT_SECONDS 기본 1800초 | 기본 2100초 |

승호 보고서 워크플로우는 `_turn`의 `api_type in LONG_APIS` 분기로
`run_step`을 부른다(report_chat.py:1645). `run_step`은 소켓 ID 여부와 무관하게
`stream_job`을 부른다(:1298). `open_stream`은 `/stream`에 연결하고
120초 대기를 넘긴다(:1185–1202). `STREAM_READ_TIMEOUT`은 해당 파일 :216에 있다.
소켓 진행 표시가 실패하거나 꺼져도 이 HTTP 경로를 JSON으로 바꾸는 조건은 없다.

승호 서버의 `front/app.py:68`은 즉시 StreamingResponse를 반환하고,
`front/stream.py:129`의 별도 beat task가 10초마다 데이터를 넣는다.
계산은 별도 스레드에서 돌아 이벤트 루프가 heartbeat를 계속 처리한다.
`README.md:763`에는 커스텀 시작 명령
`uvicorn front.app:app --host 0.0.0.0 --port <리비전이 쓰는 포트>`가 명시돼 있다.

우리 워크플로우의 `_ChatProgress.enabled`는 진행 모드와 socketIOClientId를 함께
확인한다(genos_rag_chat.py:371). `_run_once`는 그 값을 HTTP 경로 선택에도 사용한다
(:670). 따라서 소켓 ID가 없는 테스트는 SSE 서버 코드가 ZIP 안에 있어도 /json이다.
우리 stream_app 자체에는 heartbeat 구현이 이미 있다(:104–113).
현장 리비전이 이 앱을 실행하는지, /stream이 제공되는지는 아직 확인되지 않았다.
채팅에 소켓 ID가 있어도 /stream이 404/405를 반환하면 /json으로 복귀한다.

## 40분 대기와의 관계

120초나 2100초를 urllib에 넘긴 것은 스트림 전체 수행 시간을 재는 별도 타이머가
아니다. 데이터를 계속 읽는 동안 소켓 대기가 갱신될 수 있다. 승호 스트림 reader에는
전체 작업을 300초나 1800초에서 취소하는 별도 deadline이 없다. 10초마다 전달되는
SSE는 이런 읽기 대기 및 중간 계층의 idle 제한에 대응할 수 있는 구조다.
플랫폼의 절대 total 제한까지 해제한다고 가정하지 않는다.

사용자는 후속 답변에서 다른 팀원이 40분 기다린 뒤 결과까지 받았다고 확인했다.
이는 사용자 제공 현장 정보이며 이 세션에서 재현한 실행 결과는 아니다.
그 작업이 보고서 SSE 경로라면 우리 무응답 JSON 경로의 300초 실패와 함께 성립할 수 있다.
플랫폼 전체 모든 호출에 공통으로 300초 상한이 있다는 결론은 뒷받침되지 않는다.
다만 해당 팀원의 실제 과제·배포 리비전과 현장 코드의 동일성은 아직 확인되지 않았다.

통합 브랜치의 ELS QA는 별개다. `02-els-qa/deploy/workflow/els_chat.py:87`의
기본 timeout은 60초이고 :224에서 /json을 읽는다. 이 소스를 보고 40분 SSE라고
설명하면 안 된다. 보고서 경로의 120초는 모델 호출 timeout이나 JSON timeout과도
구분해야 한다.

## 우리 쪽에서 맞춰야 할 부분과 미확인 범위

기존 SSE 전송을 활용하려면 두 부분이 함께 연결돼야 한다.

1. 코드서빙 리비전이 `08_DEPLOYMENT/GENOS/stream_app.py`를 HTTP 앱으로 실제 실행한다.
   시작 명령의 형태는
   `uvicorn stream_app:app --app-dir 08_DEPLOYMENT/GENOS --host 0.0.0.0 --port <실제 리비전 수신 포트>`다.
   현장 포트를 임의로 정하지 않는다. 플랫폼 기본 service 로더와 커스텀 앱은 별도 실행 경로다.
2. 워크플로우의 긴 법률 요청에서 SSE 선택을 채팅 소켓 표시 여부와 분리한다.
   소켓이 없어도 /stream을 읽고 최종 결과를 dict로 반환할 수 있어야 한다.
   표시 off는 화면 출력만 제어하도록 한다. 404/405 외 500/중간 실패를 자동 재호출하지 않는다.

비교 시점에는 위 두 부분을 변경·배포하지 않았다. 현재 현장
300초 HTTP 500의 생성 주체는 별도 Envoy/백엔드 로그 확인이 필요하다.
SSE 데이터가 실제 게이트웨이를 통과하는지와 300초 이후 최종 답변이 전달되는지는
워크플로우 테스트 화면에서 확인해야 한다. 데이터 재구축이나 캐시 hash 변경은 이 연결에 필요하지 않다.
우리 RAG의 전체 작업 예산 1800초는 이 전송 선택과 별도이며, SSE만으로 40분 작업을 허용하지 않는다.

## 후속 구현

같은 날 사용자 지시에 따라 `sse-transport-20260928-r1`을 구현했다.
소켓 ID와 진행 표시 여부에 관계없이 `/stream`으로 법률 질문을 보내고,
서버의 초기 응답·10초 heartbeat·최종 결과를 기존 HTTP 연결에서 읽는다.
HTTP 404/405에서만 한 번 JSON으로 전환하고, HTTP 500이나 스트림 중단 시 작업을 재실행하지 않는다.
SSE_CHECK는 워크플로우에서 실제 SSE 앱과 리비전을 모델 호출 없이 확인한다.
포트는 기존 코드서빙 시작 명령 또는 플랫폼 환경변수를 재사용하며 별도 회신 포트가 없다.
로컬 검사와 현장 배포를 구분한
[인계 안내](GENOS_SSE_TRANSPORT_20260928.md)를 따른다.
