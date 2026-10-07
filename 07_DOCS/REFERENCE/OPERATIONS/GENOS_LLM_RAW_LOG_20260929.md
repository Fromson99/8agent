# GENOS 수신 LLM 출력 원문 로그 R4

R4는 사용자 요청에 따라 기존 R2 판단 수정과 R3 intent/actions 수정을 함께 포함하고,
LLM 서빙에서 수신한 출력 문자열을 요청별 로그에 추가한다. 기존 한국어 판단 요약은
JSON 해석·참조 변환·항목 제한을 거치므로 원래 응답 확인에는 별도 원문 블록이 필요하다.

## 실행 경로와 기록 계약

`service.py` → `request_report.DeferredReport`/`live_log` → `_LiveLog._poll_journal`이
기존 readonly `journal.sqlite`의 `ATTEMPT_FINISHED`와 `model_attempt.response_json`을 읽는다.
그 응답을 기존 `MODEL RESPONSE / LLM ANSWER` 요약 직전에 `MODEL RAW RESPONSE`로 출력한다.
`live_log`에서 만든 실제 파일 경로를 handler에 전달한다. `os.fdopen` stream의 name은
경로가 아닌 파일 descriptor일 수 있으므로 sidecar 경로로 사용하지 않는다.

* 기존 요청 `.log`: `<<< BEGIN message.content >>>`와 END 사이에 수신 문자열을
  JSON 해석·참조 매핑·공백 정리·길이 제한 없이 기록한다. 문자열 길이와 SHA-256을 덧붙인다.
* 같은 이름 `.llm_raw.jsonl`: 호출별 JSON 한 줄로 content 문자열, 모든 choice와 tool call,
  refusal, finish_reason, 수신 body와 HTTP 상태를 보존한다. JSON escape는 파일 표현이며
  JSON을 읽으면 원래 문자열과 같다. 비JSON 오류 응답의 body_text도 기록한다.
* request/run/attempt/logical_call/view ID, attempt_no, phase와 가능한 source_stage를 기록한다.
  최초/수정 응답을 따로 남기며, 수정 요청에는 schema_repair와 직전 validation_error를 기록한다.
* 기존 인증정보 마스킹을 유지하고 적용 여부를 `redaction_applied`로 표시한다.
  원문 SHA-256은 실제 로그에 표시한 문자열의 해시다. 질문·프롬프트를 이 블록에 복제하지 않는다.
* 기존 journal/log worker에서 append한다. sidecar 권한은 0640이며 심볼릭 링크는 거절한다.
  sidecar I/O 실패 시 UNAVAILABLE를 표시하고 `.log` 원문과 journal을 유지한다.
  프로세스 강제 종료·NFS 장애·기존 보고서 용량 제한이면 공유 로그 생성은 보장하지 않는다.

이는 **우리 코드가 LLM 서빙에서 받은 출력**이다. GENOS가 출력 가드레일을 적용한 뒤
거절/대체 응답을 보냈다면 그것을 기록한다. 적용 전 모델 내부 출력을 복원하지 않는다.
`SUCCEEDED`는 수신 transport 상태이며 모델 proposal 검증 성공을 의미하지 않는다.

## 현장 확인

[R4 인계](../../../../09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-raw-log-r4/)의
ZIP과 APPLY.txt를 같은 폴더에 저장한다. R2/R3 대신 R4 하나를 사용한다.

```bash
bash GENOS_MODEL_DECISION_REPAIR_RAW_LOG_20260929_R4_APPLY.txt
```

기존 `~/DEV`에 백업 후 승인한 함수만 적용한다. `DEPLOY_ROOT`와 `PYTHON_BIN`을 필요 시
지정한다. `MODE=check`는 사전 확인, 재실행은 ALREADY_APPLIED, BACKUP_READY 경로를
사용한 `MODE=rollback ROLLBACK_FROM=...`은 적용 전 바이트와 pin 복구다.
미등록 함수 변경은 쓰기 전에 거절하며 다른 현장 함수와 추가 코드는 보존한다.
적용 첫 단계부터 `/tmp/genos-selective-*/run.log`와 종료 상태를 기록한다.

runtime 파일 6개와 해당 checkout의 엔진 manifest/PIPELINE pin을 결속한다.
이번 원문 기록 추가의 작업 runtime 변경은 `request_report.py` 하나와 엔진 manifest 26개다.
데이터 generation·CURRENT·내부 모델·워크플로우 Python 교체는 필요하지 않다.

변경 파일을 확인하고 commit한 뒤 같은 checkout과 실제 generation으로 검증한다.

```bash
GENOS_GENERATION=/실제/선택/generation MODE=verify bash GENOS_MODEL_DECISION_REPAIR_RAW_LOG_20260929_R4_APPLY.txt
```

동일 commit을 push하고 새 코드서빙 리비전을 배포한 후 **워크플로우 테스트 화면**에서
문제 질문을 재현한다. 기존 `GENOS_SHARED_LOG_DIR` 설정을 유지한다.
공유 로그의 날짜/팀 폴더에 있는 요청 `.log`에서 RAW 블록을
찾고, 같은 파일명의 `.llm_raw.jsonl`을 확인한다. 새 원문 기록의 표식은
`raw_log_revision=llm-raw-log-20260929-r1`이다. 원문은 터미널의 한국어 요약만으로 확인하지 않는다.
예전 요청의 `.log`를 소급 수정하지 않는다. 이전 수신 응답은 보존된 journal/JSON 보고서로 확인한다.

메일의 읽기 전용 VIEW.txt에 확인할 요청의 `.llm_raw.jsonl` 경로를 넘기면 JSON escape를
풀어 최초·수정 출력 문자열을 그대로 터미널에 표시한다. 최신 파일을 임의로 선택하지 않는다.

```bash
bash GENOS_LLM_RAW_VIEW_20260929_R4.txt /실제/요청.llm_raw.jsonl
```

1. 최초 content에 DRAFT/CLARIFY와 비어 있지 않은 actions가 함께 있는지 확인한다.
2. 같은 logical_call_id/view_id에서 다음 attempt와 실제 수정 응답이 있는지 확인한다.
3. finish_reason/content_filter, refusal, HTTP 오류나 provider의 guardrail 필드를 확인한다.
4. 같은 요청 시각·대상 LLM 서빙의 GENOS 가드레일 탐지 기록과 대조한다.

필터 신호가 없다고 미개입을 확정하지 않는다. `request finalized; remaining source judgments
not fabricated`는 공통 FINAL 기록이며 가드레일 탐지 결과가 아니다. 로그 추가는 필터를
해제하거나 반복 한도·원문 근거 검증을 완화하지 않는다.

## 로컬 검증과 현장 상태

모의 journal에서 긴 문자열·줄바꿈·잘못된 JSON, 최초/수정 계보, refusal/content_filter,
비JSON HTTP 오류, 여러 tool arguments와 비정상 provider 필드, 마스킹, 중복 없는 poll,
sidecar 실패·journal 불변을 검증한다. 실제 인계 ZIP/TXT를 사진 기준·R2·R3·통합판 및
승인된 과거 request_report 바이트에 적용해 전달한 runtime의 검사를 수행한다.
Python 3.11/3.14 설치·재실행·원복, 추가 함수 보존과 commit된 checkout/ZIP 대조도 확인한다.
결과는 [감사 기록](../../../../09_ARTIFACTS/AUDITS/20260929-llm-raw-log/)과 R4 VALIDATION.json에 보존한다.

작업 코드·패키지 검증이며 로컬 frozen MAIN은 변경하지 않는다. GENOS 실제 배포,
실제 내부 응답 원문과 가드레일 차단 여부는 현장 기록이 돌아오기 전까지 미확인이다.
