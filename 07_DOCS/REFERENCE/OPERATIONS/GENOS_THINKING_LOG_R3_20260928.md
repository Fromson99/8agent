# GENOS thinking 로그 R3 — 현장 request_report 구문 호환 설치

2026-09-28 현장 사진에서 R2 TXT의 내부 package hash와 manifest 검증은 통과했지만
`unsupported installed version; no changes: 02_BACKEND/semantic_runtime/request_report.py`
오류로 `prepare` 단계에서 종료 상태 1을 반환했다. 해당 실행은 백업·코드 쓰기 전이며
코드 적용 성공이 아니다. 모델 오류나 데이터 generation 오류로 해석하지 않는다.

R2 설치기는 정확한 전달본 전체 파일 hash만 허용했다. 현장 report 파일이 이 목록에
없어서 호환 가능한 추가 수정까지 거부했다. R3는 이 파일의 필요한 표시 구문을
Python AST로 확인하고 그 부분만 수정한다. 임의 파일 전체를 새 전달본으로 교체하지
않으며 기존 현장 추가 코드·팀별 기록·로그 기능은 해당 바이트대로 보존한다.

## 적용 전 확인과 변경 계약

1. 기존 `~/DEV` Git checkout에서 설치된 파일별 SHA·크기를 `INPUT_CHECK`로 기록한다.
2. 모든 선택 엔진 manifest와 PIPELINE pin, 의존 소스·스키마 hash가 실제 파일과 같은지
   확인한다. 변경 대상 파일도 **적용 전** 등록 hash와 같아야 한다. 기존 불일치를 승인해
   새 hash로 덮어쓰지 않는다.
3. report의 literal live field 목록, `_LiveLog.emit`의 필드 표시 loop와 safe 변환,
   요약 TXT의 service field loop를 확인한다. 예상한 계약과 다른 함수는 거부한다.
4. 출력 필드 목록·타입 검사 helper·누락값 `null`·진단 표시 loop·R3 표식만 수정한다.
   해당 구문 외 바이트는 그대로 보존하고 전체 결과를 Python 3.11 문법으로 검사한다.
5. 기존 소스/manifest/PIPELINE을 전체 백업한 뒤 원자 적용한다. 실패하면 백업으로
   복원한다. 적용 뒤 소스/manifest/PIPELINE을 다시 검증하고 실제 적용 소스를 담은
   `applied-code.zip`과 before/after receipt를 만든다.

R1/R2 gateway·숫자 토큰 필터가 이미 있으면 유지한다. 지원되는 미적용 소스에는
R1 진단 수집을 함께 적용한다. gateway/observability의 미지원 파일은 계속 거부한다.
동적으로 변환한 현장 report도 실제 적용 ZIP과 Git commit에 결속되며, 구문 검사만으로
GENOS 현장 검증을 통과한 것으로 보고하지 않는다.

## 반입·실행·검증·원복

[R3 실행 TXT](../../../08_DEPLOYMENT/GENOS/patches/GENOS_THINKING_LOG_20260928_R3_APPLY.txt)
하나를 사용한다. 이전 R1/R2 첨부 대신 R3를 사용하며 별도 ZIP은 필요하지 않다.

```bash
bash GENOS_THINKING_LOG_20260928_R3_APPLY.txt
```

기본 기존 `~/DEV`에 적용하며 필요할 때만 `DEPLOY_ROOT`·`PYTHON_BIN`을 지정한다.
첫 단계부터 `/tmp/genos-thinking-log-r3-*.log`에 지속 기록과 종료 상태를 남긴다.
`STRUCTURAL_CHECK_PASS`는 표시 구문 확인, `BACKUP_READY`는 백업 완료,
`APPLIED`는 코드 적용 완료다. 재실행은 `ALREADY_APPLIED`로 확인한다.

diff를 검토·commit한 뒤 정확한 실제 선택 generation으로 검증한다.

```bash
MODE=verify GENOS_GENERATION='/실제/선택/generation' bash GENOS_THINKING_LOG_20260928_R3_APPLY.txt
```

그 checkout으로 generation E2E·`verify_assets`와 적용 ZIP/commit hash를 확인한다.
검증한 commit push → 새 코드서빙 리비전 배포 → 해당 commit/generation 설정 확인 →
워크플로우 테스트 화면의 새 질문 순서다. 코드서빙 직접 테스트 UI/API를 요구하지 않는다.
코드 적용, commit/push, 리비전 배포, 현장 새 로그 성공은 각각 별도 상태다.

새 `.log`의 표식은 `live_diagnostics_version=thinking-live-20260928-r3`다.
`thinking_requested`, 입력·출력·추론 토큰, `thinking_observation`을 표시한다.
미제공은 `null`/`unknown`이며 OFF/0으로 확정하지 않는다. 모델 이벤트 생산자의 기존
`diagnostics_version=thinking-log-20260928-r1`은 유지한다. 새 진단 줄에는 추론 원문·
질문·원문·프롬프트·인증값을 표시하지 않는다.

```bash
MODE=rollback ROLLBACK_FROM='/BACKUP_READY에/표시된/경로' bash GENOS_THINKING_LOG_20260928_R3_APPLY.txt
```

적용 후 추가 수정이 있으면 원복 덮어쓰기를 거절한다. 원복 commit/push와 이전 코드서빙
리비전 복귀는 별도이며 모델 설정·데이터 generation/CURRENT·워크플로우 Python은 유지한다.

## 로컬 검증과 미확인 범위

R2 목록에 없는 모의 현장 추가 코드와 유효한 엔진 pin으로 최종 TXT 적용·재실행·원복,
적용 코드 ZIP/커밋 게이트를 확인한다. 여러 이전 report에 모의 추가 코드·한글·CRLF를
넣어 보존과 구문 호환을 검사한다. 함수 계약 변경·코드 pin 불일치·manifest/asset 훼손은
쓰기 전에 거부하고, 적용 쓰기 실패는 원복하며 이후 현장 수정은 덮어쓰지 않는다.
실제 ModelGateway → 비동기 공유 로그·JSON·요약 TXT 출력 검사도 수행한다.

상세 결과는 패치 폴더의 `LOCAL_VALIDATION.json`에 기록한다. 현장 원본 소스 전체는
현재 Codex 세션에서 접근할 수 없으며 실제 현장 구조 호환·generation 경로/hash·
commit·리비전·새 로그·thinking 상태는 현장 실행 기록 전까지 미확인이다.
