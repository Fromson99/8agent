# GENOS Gemma thinking·토큰·모델 호출 진단 R1

후속 현장 사진에서 공유 `.log`의 표시 허용 목록 누락을 확인했다.
R1 이벤트 수집과 JSON 검증만으로 공유 로그 표시 성공을 보장하지 않았다.
현재 반입은 [표시 수정 R2](GENOS_THINKING_LOG_R2_20260928.md)의 TXT를 사용한다.
아래 R1 기록과 기존 첨부·검증 결과는 당시 이력으로 보존한다.

현재 작업 코드의 v5 모델 호출은 `gateway.ModelGateway.generate` →
`GenosTransport.send_once` → 내부 `/chat/completions`로 연결된다.
`chat_template_kwargs.enable_thinking=false`와 `stream=false`는 기존 요청을 유지한다.
진단 이벤트는 요청·응답 계약이나 모델 출력·검색 결과를 바꾸지 않는다.

사용자 제공 2026-09-28 현장 사진에서 `model_http.finished.duration_ms=67448`,
`model.attempt.received.duration_ms=67909`, HTTP 200을 확인했다.
이는 모델 HTTP 응답 대기 구간이며 thinking 실행 여부, 첫 토큰 시간,
서버 대기열·입력 처리·출력 생성 시간을 각각 증명하지 않는다.

기존 `observability._safe_fields`의 `TOKEN` 비밀값 필터가 숫자인
`prompt_tokens`·`completion_tokens`·`max_tokens`까지 제거하고 있었다.
정해진 6개 숫자 필드만 비음수 정수 또는 `null`로 허용한다. 문자열·목록·사전·
불리언·음수·소수는 계속 제외하고 인증키·access token 필터를 보존한다.

## 호출별 기록과 해석

`diagnostics_version=thinking-log-20260928-r1`이 새 리비전의 확인 표식이다.
각 이벤트는 기존 request/run/attempt/phase/model ID에 연결된다.

| 이벤트 | 추가/복구 필드 | 해석 |
|---|---|---|
| `model.attempt.started` | `thinking_requested`, `thinking_control_present`, `stream_requested`, `max_tokens` | 실제 전송 요청의 옵션; 모델 서버의 적용 증명이 아님 |
| `model.attempt.received` | `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_tokens`, `reasoning_tokens` | 서버가 반환한 토큰 수. 미제공/유효하지 않은 형식은 `null` |
| 같은 응답 이벤트 | `reasoning_field_present`, `reasoning_nonempty`, `reasoning_chars`, `response_content_chars`, `tool_argument_chars`, `finish_reason` | 추론 응답 유무/문자 수와 출력 규모만 기록; 내용은 출력하지 않음 |
| 같은 응답 이벤트 | `thinking_observation`, `thought_channel_marker_present` | 추론 보고 여부. marker 단독으로 실행 여부를 판정하지 않음 |
| 기존 `model_http.finished` | `duration_ms` | 모델 HTTP 응답 전체 대기. 네트워크·대기열·입력 처리·출력 생성을 포함하며 각각의 시간은 미측정 |

`thinking_observation=reasoning_reported`는 비어 있지 않은
`reasoning`/`reasoning_content`/`thinking` 또는 양수 추론 토큰을 반환했다는 뜻이다.
`no_reasoning_reported`는 해당 필드가 비어 있거나 추론 토큰 0을 보고했다는 뜻이다.
`unknown`은 추론 정보를 제공하지 않은 상태이며 OFF로 판정하지 않는다.
응답의 빈 thought channel도 thinking OFF 템플릿일 수 있으므로 marker만으로
추론 실행을 확정하지 않는다. 실제 서버 모델·채팅 템플릿·옵션 전달은 현장 확인 대상이다.

새 진단 이벤트에는 프롬프트·질문·원문·추론 원문·인증키를 출력하지 않는다.
기존 내부 journal/요청 보고서의 원본 보존은 유지한다.

## TXT 단독 반입과 검증

[실행 TXT](../../../08_DEPLOYMENT/GENOS/patches/GENOS_THINKING_LOG_20260928_R1_APPLY.txt)는
검증한 payload·설치기·배포 게이트를 내부 ZIP으로 포함한다. 이메일 첨부는 TXT 하나다.
별도 ZIP을 찾지 않으며 첫 단계부터 `/tmp/genos-thinking-log-r1-*.log`에 기록한다.

```bash
bash GENOS_THINKING_LOG_20260928_R1_APPLY.txt
```

기본 대상은 기존 `~/DEV` Git checkout이다. 필요할 때만 `DEPLOY_ROOT`와
`PYTHON_BIN`을 지정한다. latency R2/request-unlimited R1/relation-wait R1의
정확한 `gateway.py`·`observability.py` 바이트만 허용한다. 다른 버전·수정 파일·
다른 엔진 의존성의 해시 불일치는 덮어쓰기 전에 실패한다.

변경 파일은 위 두 Python 파일과 이를 소비하는 엔진 manifest·PIPELINE의 해시다.
데이터 generation/CURRENT·프로필·기존 워크플로우는 바꾸지 않는다.
백업 receipt에 파일별 before/after hash와 기존 Git commit을 기록하고,
재실행은 `ALREADY_APPLIED`로 확인한다. 적용 checkout의 `applied-code.zip`은
실제 코드·엔진 manifest·PIPELINE을 결속한다.

적용 diff 검토·commit 후 실제 선택된 generation으로 검증한다.

```bash
MODE=verify GENOS_GENERATION='/실제/선택/generation' bash GENOS_THINKING_LOG_20260928_R1_APPLY.txt
```

이 게이트는 동일 checkout의 커밋 코드와 ZIP·generation E2E·`verify_assets`를
확인하며 모델 호출은 하지 않는다. 통과한 commit을 push하고 새 코드서빙 리비전을
배포한다. 해당 리비전의 commit·generation 설정을 확인하고 실제 질문은
워크플로우 테스트 화면에서 실행한다. Git push·리비전 배포·현장 응답 성공은 별도다.

```bash
MODE=rollback ROLLBACK_FROM='/BACKUP_READY에/표시된/경로' bash GENOS_THINKING_LOG_20260928_R1_APPLY.txt
```

원복은 패치 이후 다른 수정이 없는 파일만 복구한다. 원복 commit/push와 이전 코드서빙
리비전 복귀는 별도로 수행하며 데이터 세대는 유지한다.

## 로컬 확인 범위와 남은 상태

모의 모델 응답으로 실제 요청 flag와 토큰 필드 출력, 추론 내용 비출력,
추론 정보 누락 시 `unknown`, 인증값 우회 차단을 검증했다.
설치기 계약·정확한 이전 두 소스 바이트의 TXT 적용/재실행/원복·커밋 ZIP 코드 게이트와
Python 3.11 구문 호환을 확인했다. 검사 결과는 패치 폴더의 `LOCAL_VALIDATION.json`에 남긴다.

현재 로컬 작업트리의 기존 `request_report.py`와 엔진 pin 불일치는 이 패치 범위 밖이며
그 파일·pin을 덮어쓰지 않았다. 전체 작업트리 generation 게이트 통과를 주장하지 않는다.
GENOS generation 경로·manifest hash·배포 commit·코드서빙 리비전·실제 thinking과
속도 원인은 현장 기록 전까지 미확인이다. 패치는 진단을 추가하며 속도 개선을 인증하지 않는다.
