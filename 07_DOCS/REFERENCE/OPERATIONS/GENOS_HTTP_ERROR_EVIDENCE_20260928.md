# 워크플로우 HTTP 500 응답 증거

현장 설정 검사 사진에서 /workspace의 service.py·현재 워크플로우·stream_app.py
SHA가 R3와 일치하고 PIPELINE/프로필 요청 시간은1800초였다. 별도8agent-v5/ 아래에는
옛300초 프로필·genos_call·authoring과 이전 워크플로우가 남아 있었다.
이 폴더가 있다는 것과 배포가 이 진입점을 쓰는 것은 다르다. 현재 service의 명시
GENOS_GENERATION/GENOS_DATA_ROOT 선택은 해당 service.py의 _ROOT를 코드 루트로
쓰며 8agent-v5/를 이름이나 날짜로 자동 선택하지 않는다. 실제 실행 파일과 모듈
경로는 현장 리비전/실행 설정으로 별도 확인해야 한다.

runtime/에서 표시된 파일은 runs/...json 결과였다. 사진에는 aiohttp.ClientSession,
실행 래퍼, proxy/gunicorn timeout 설정이 없다. 검사기는CodeSpace환경을 읽으므로
그곳의 프록시 없음·시간 값이 워크플로우 프로세스의 환경을 인증하지 않는다.

기존 워크플로우는HTTPError의 실제 응답 본문을 stdout에만 남기고, 결과에는
HTTP상태·경과시간·generic문구만 넣어 발생 위치 판단을 어렵게 했다.
작업 코드에 http-error-origin-20260928-r1 진단을 추가했다. HTTP500이 도착하면
최대16KiB만 읽고 http_error_diagnostics에 allowlist 응답 헤더,본문 형식·캡처 길이·
해시,구조화 오류 code/type/error_type,최대1500자 오류 발췌,timeout 등 단서,
워크플로우 실제socket대기와proxy환경 존재 여부를 남긴다. 쿠키·인증 헤더는
제외하고 환경 인증키·현재 질문은 가린다. 요청/답변/원문 필드를직접 내보내지 않는다.
에러 본문이 요청/원문JSON을에코하면 해당 발췌를생략한다.

WORKFLOW_SETTINGS는http_error_diagnostics_revision을보여주며,기존timeout-sync-
20260928-r1 시간리비전과2100초대기를유지한다. 정상답변,호출횟수,재시도정책,
/json·/stream선택,기존service_error의문맥은유지한다. 현재캐시·manifest·CURRENT·
서빙service코드·모델환경은바꾸지않았다. 세대재구축이나코드서빙리비전변경은
이워크플로우진단을위해필요하지않다.

61개관련검사가통과했다. 가상시간300초HTTP500·실제timeout구분,/json·/stream
각한번호출,오류본문/헤더전달,토큰·질문에코제외,16KiB한계를확인했다.
Python3.10/3.11문법검사를통과한붙여넣기TXT를인계한다. 현장원인확정·
500해소·새워크플로우저장/배포는별도이며인계당시미확인이었다.

적용은 새 *_WORKFLOW_PASTE_ALL.txt 전체를 워크플로우 Python 단계에 붙여넣고
저장·배포한다. WORKFLOW_SETTINGS에서 진단 리비전을 확인한 뒤 기존 실패 질문을
한 번 실행하고 http_error_diagnostics를 확인한다. 원복은 R3 워크플로우 전체
코드로 되돌린다. 코드 ZIP을 다시 적용하거나8agent-v5를일괄변경/삭제하지 않는다.

## 후속 현장 결과: 300초 뒤 plain-text HTTP 500

2026-09-28 사용자가 제공한 다섯 장의 워크플로우 테스트 사진에서 다음을 확인했다.
워크플로우 1232의 `legal_finance_team`이며, 실제 질문과 답변 원문은 기록하지 않는다.

| 항목 | 사진의 값 |
|---|---|
| workflow_revision | timeout-sync-20260928-r1 |
| http_error_diagnostics_revision | http-error-origin-20260928-r1 |
| JSON / stream socket timeout | 모두 2100초 |
| failure_kind / http_status | http_error / 500 |
| tm_total | 300.062초 |
| response server | envoy |
| content-type | text/plain; charset=utf-8 |
| x-envoy-upstream-service-time | 300008 |
| captured_body_bytes / body_format | 21 / text |
| error_body_excerpt | Internal Server Error |
| error_fields / error_hints | 빈 객체 / 빈 목록 |
| workflow proxy environment flags | HTTP_PROXY·HTTPS_PROXY·ALL_PROXY·NO_PROXY 대소문자 모두 false |

이 결과는 새 진단 코드가 워크플로우에서 실행되고, 워크플로우의 2100초 대기가
만료되기 전에 상대 서버로부터 HTTP 500을 받은 증거다. 사진의 시간 값이나
Codespace의 R3 SHA 일치만으로 실행 중인 코드서빙 커밋·데이터 세대를 확정하지 않는다.

`x-envoy-upstream-service-time`은 upstream 처리와 Envoy–upstream 간 네트워크에
걸린 밀리초다. 따라서 300008은 약 300.008초의 관측 시간이며, 타임아웃 설정값을
직접 보여주는 헤더는 아니다. Envoy는 server 헤더를 덮어쓸 수 있으므로
`server: envoy`만으로 500 생성 주체를 Envoy로 확정할 수 없다.
일반적인 Envoy 요청 타임아웃의 상태는 504이며, 별도 응답 변경 설정은 현장 미확인이다.

우선 확인 대상은 `/api/gateway/code_serving/{id}/json`을 처리하는 GENOS 중계
백엔드와 코드서빙 실행 래퍼다. 이전에 같은 요청 ID의 서비스 내부 보고서가
385.970초 뒤 HTTP 200 반환을 기록한 사례는 이 바깥 호출 경로를 조사할 근거다.
이번 사진의 요청이 내부에서 200으로 끝났는지는 아직 확인하지 않았다.

설정을 생략한 HTTP 클라이언트 기본값도 조사해야 한다. aiohttp는 기본 total
timeout이 300초다. GENOS 플랫폼이 aiohttp를 사용하는지는 미확인이므로 원인 후보로
남긴다. plain-text `Internal Server Error`는 처리하지 않은 서버 예외와도 일치하지만,
이 본문만으로 특정 라이브러리나 서버 프로세스를 식별할 수는 없다.

운영 담당자에게 해당 실패 시각·호출 경로의 Envoy access log에서
`RESPONSE_CODE_DETAILS`, `RESPONSE_FLAGS`, `UPSTREAM_HOST`, `UPSTREAM_CLUSTER`를
확인하도록 요청한다. 워크플로우 request_id가 플랫폼 request ID와 동일하게
전파된다고 가정하지 말고 시각·경로·플랫폼 로그 ID를 함께 대조한다.

- `via_upstream`: 해당 Envoy의 upstream이 응답 코드를 정했다. 기록된 upstream
  백엔드의 300초 시점 traceback과 HTTP 클라이언트 timeout을 확인한다. upstream이
  또 다른 프록시이면 그 다음 호출까지 추적한다.
- `upstream_response_timeout` 또는 다른 timeout detail: 해당 Envoy에서 timeout이
  발생한 근거다. 실제 route/request/idle 설정과 500으로 바꾸는 응답 정책을 확인한다.

원인 위치가 확인되면 그 프로세스가 실제 읽는 설정을 변경해야 한다. 우리
워크플로우의 `GENOS_CODESERVING_TIMEOUT_SECONDS`를 다시 높이는 것만으로는
중계 백엔드의 클라이언트 기본값이나 Envoy 설정을 바꾸지 못한다.
코드·캐시·generation·manifest 수정, 데이터 재구축, 현장 문제 해소는 수행하지 않았다.

공식 근거:

- [Envoy upstream 시간과 요청 timeout](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/router_filter)
- [Envoy server 헤더 정책](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto)
- [Envoy 응답 생성 주체와 timeout detail](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_conn_man/response_code_details)
- [aiohttp 기본 300초 timeout](https://docs.aiohttp.org/en/stable/client_quickstart.html#timeouts)
