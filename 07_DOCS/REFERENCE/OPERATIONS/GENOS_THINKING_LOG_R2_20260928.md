# GENOS thinking 로그 R2 — 공유 .log와 요약 TXT 표시 수정

현장 R2 설치는 `request_report.py` 전체 파일 hash가 지원 목록에 없어 쓰기 전에
중단됐다. 현재 반입은 [현장 표시 구문을 보존하는 R3](GENOS_THINKING_LOG_R3_20260928.md)를
사용한다. 아래 R2 구현·첨부·검증 기록은 당시 이력으로 보존한다.

2026-09-28 사용자 현장 사진의 공유 `.log`에는 `model.attempt.started`와
`model.attempt.received` 이벤트만 표시되고 R1 진단 항목이 보이지 않았다.
R1은 gateway 이벤트와 JSON 수집만 검증했으며, 실제 공유 로그의
`request_report._LIVE_FIELD_NAMES` 허용 목록을 갱신하지 않은 것이 확인됐다.
항목 부재만으로 R1 미적용·구 리비전 실행을 확정할 수 없다.
사진의 모델 HTTP 대기는 33,545ms, 호출 응답 수신은 34,014ms이며 thinking은 미확인이다.

R2는 기존 `service.py` → v5 `ModelGateway.generate` → GENOS 내부 모델 →
`observability` → `_LiveLog.emit` 배선을 유지하고 공유 `.log` 허용 목록과
`format_readable_report`의 요약 `.txt` 출력에 진단 항목을 연결한다.
모델 요청·JSON 원본·journal·데이터 generation/CURRENT·워크플로우는 유지한다.

## 실제 공유 로그의 확인 표식

새 리비전의 새 질문에서 다음 표식을 확인한다. 기존 로그는 수정하지 않는다.

```text
live_diagnostics_version=thinking-live-20260928-r2
thinking_requested=false
prompt_tokens=… completion_tokens=… reasoning_tokens=… thinking_observation=…
```

`diagnostics_version=thinking-log-20260928-r1`은 모델 이벤트 생산자의 기존 버전이며
보존한다. `live_diagnostics_version=thinking-live-20260928-r2`는 해당 항목을 실제로
표시한 공유 로그의 버전이다. 둘은 생산자와 표시 경로를 각각 식별한다.

토큰·추론 정보가 미제공이면 `null`, 관찰은 `unknown`으로 표시한다.
`null`을 0으로 보거나 `unknown`을 OFF로 판정하지 않는다.
`no_reasoning_reported`는 비어 있는 추론 응답 또는 추론 토큰 0의 보고,
`reasoning_reported`는 비어 있지 않은 추론 응답 또는 양수 추론 토큰의 보고다.
빈 thought marker 단독으로 실제 thinking 실행을 판정하지 않는다.

표시 필드의 토큰/문자/바이트 수는 비음수 정수, flag는 bool, 상태는 고정 enum만
허용한다. 숫자 필드에 문자열·객체를 넣어 인증값 필터를 우회할 수 없다.
새 진단 줄에 추론 원문·프롬프트·질문·원문·인증값을 출력하지 않는다.
기존 내부 상세 로그와 감사 원장은 원래 계약대로 보존한다.

## 반입·적용·검증·원복

[R2 실행 TXT](../../../08_DEPLOYMENT/GENOS/patches/GENOS_THINKING_LOG_20260928_R2_APPLY.txt)
하나를 사용한다. R1 첨부 대신 R2를 사용하며 별도 ZIP은 필요하지 않다.
기본 대상은 기존 Git checkout `~/DEV`이며 변경 전 백업·before/after hash·
기존 commit을 기록한다. 첫 단계부터 `/tmp/genos-thinking-log-r2-*.log`에
지속 로그와 종료 상태를 남긴다. 재실행은 `ALREADY_APPLIED`로 확인한다.

```bash
bash GENOS_THINKING_LOG_20260928_R2_APPLY.txt
```

R1 적용본과 검증된 R1 이전 코드의 해시별 payload를 포함한다. 코드 버전마다
기존 내용에 표시 수정만 적용한 바이트를 따로 보존하고 설치기가 정확한 hash로
선택한다. 현재 wire projection·팀별 로그와 이전 관계 로그 변경은 각 버전대로
유지한다. 이미 있는 R1 gateway/숫자 필터는 그대로 쓰며 미적용의 지원 바이트는
R1 진단 수집을 함께 적용한다. 임의 버전이나 다른 엔진 의존성 해시 불일치는
덮어쓰기 전에 중단한다.

변경 파일은 해당 버전의 `gateway.py`·`observability.py`·`request_report.py` 중
실제로 다른 바이트와 그 파일을 소비하는 엔진 manifest·PIPELINE의 hash다.
모델·프로필·데이터 세대는 바꾸지 않는다.

diff 검토·commit 후 동일 checkout과 실제 선택 generation을 검증한다.

```bash
MODE=verify GENOS_GENERATION='/실제/선택/generation' bash GENOS_THINKING_LOG_20260928_R2_APPLY.txt
```

검증한 commit push와 새 코드서빙 리비전 배포는 별도 단계다.
리비전의 commit·generation 설정을 확인하고 질문은 워크플로우 테스트 화면에서
실행한다. 코드서빙 직접 테스트 UI/API를 요구하지 않는다.

```bash
MODE=rollback ROLLBACK_FROM='/BACKUP_READY에/표시된/경로' bash GENOS_THINKING_LOG_20260928_R2_APPLY.txt
```

패치 이후 다른 수정이 있으면 원복 덮어쓰기를 거절한다. 코드 원복 commit/push와
이전 코드서빙 리비전 복귀는 별도이며 기존 데이터 세대는 유지한다.

## 검증 범위

모의 모델을 기존 `ModelGateway.generate`로 호출하고 실제 `live_log` 비동기 writer와
JSON 수집·요약 TXT를 함께 통과시켜 요청 flag, 토큰 수, 양수·0·미제공 추론 정보의
출력을 확인했다. 프롬프트·질문·추론 내용 비출력과 필드 타입 우회 차단도 확인했다.
검증은 새 모델 실험이 아닌 로컬 계약/회귀 검사다.

최종 TXT의 현재 바이트·R1 적용본·R1 이전·관계 로그 버전 적용/재실행/원복과
커밋 코드 ZIP 게이트, Python 3.11 구문을 확인한다. 상세 결과는 패치 폴더의
`LOCAL_VALIDATION.json`에 기록한다. 현장 generation 경로·manifest hash·commit·
코드서빙 리비전·새 로그 표시·실제 thinking 여부는 현장 확인 전까지 미확인이다.
