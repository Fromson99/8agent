# 팀별 요청 로그와 질문·답변 요약표

작업 코드의 `service.py → DeferredReport → request_summary` 경로다.
코드서빙 두 개가 같은 공유 로그 루트를 사용해도 요청의 `team_id`별로 나눈다.
로컬 계약 검증이며 실제 GENOS 적용과 NFS 파일 잠금은 현장 확인 전까지 미확인이다.
로컬 MAIN의 frozen 릴리스·활성 포인터와 원문 세대는 바꾸지 않는다.

## 설정과 저장 위치

두 코드서빙 환경에는 같은
`GENOS_SHARED_LOG_DIR=/nfs-root/diamo/8-agent/rag-request-reports`를 유지한다.
워크플로우 리비전 환경의 `TEAM_ID`를 각각 지정한다. 기존 Python은 이를 입력
`team_id`보다 우선 전달하므로 별도의 로그 팀명을 만들지 않는다.

| 워크플로우 | TEAM_ID | 저장 폴더 |
|---|---|---|
| 위험관리 | `risk_team` | `YYYY-MM-DD/risk_team/` |
| 재무관리 | `financial_team` | `YYYY-MM-DD/financial_team/` |

재무팀 이름은 현재 팀 데이터와 같은 `financial_team`이다. 팀 미지정·경로 형식
오류의 요청은 로그만 `unassigned`로 분류한다. 잘못된 검색 팀을 승인하거나
전체 검색으로 대체하지 않으며 기존 팀 검증과 요청 결과를 유지한다.

날짜는 **한국 시간의 요청 시작일**이다. 자정을 넘어 완료되어도 시작한 날짜·팀
아래에 `.log`·JSON·TXT와 요약표를 함께 기록한다.

```text
rag-request-reports/
  2026-09-28/
    risk_team/
      질문답변.xlsx
      질문답변.csv
      <요청ID>-<고유값>.log
      <요청ID>-<고유값>.json
      <요청ID>-<고유값>.txt
      _qa/<요청ID>-<고유값>.row
    financial_team/
      질문답변.xlsx
      질문답변.csv
      ...
```

## 요약표와 동시 기록

요청 시각·팀·사용자 ID·질문·최종 답변·처리 상태·HTTP·소요시간·오류·요청 ID·
실행 ID·상세 로그 경로·JSON 경로를 한 행에 기록하며 최신 요청이 위에 온다.
경로는 표가 있는 팀 폴더 기준이다. 사용자 ID는 전달된 값이며 이름을 추정하지 않는다.
XLSX는 첫 행 고정·필터·줄바꿈을 지원하고 CSV는 UTF-8 BOM으로 만든다.

기존 별도 finalizer가 먼저 작은 요약 행과 표를 쓰고 전체 journal/JSON/TXT를 쓴다.
요청 반환 스레드에서 표 쓰기를 기다리지 않는다. 질문 없는 PING은 요약 행을 만들지 않는다.
실패 응답도 질문·HTTP·오류를 남긴다. `답변 완료`는 코드서빙 생성 결과이며
채팅 수신 확인이나 법률 검토 통과 인증이 아니다.

팀·날짜별 `.qa.lock`의 `flock`으로 프로세스 간 갱신을 직렬화한다.
원본 요약은 요청별 append-only `_qa/*.row`이며 XLSX/CSV는 임시 파일에서 완성한
뒤 원자적으로 교체한다. 같은 요청 ID의 별도 호출도 고유값이 달라 각각 보존한다.
요약 행 목록과 `.qa.snapshot`의 지문이 같으면 중복 재생성을 생략한다.
실시간 갱신은 전체 프롬프트·journal JSON을 매번 읽지 않는다.

XLSX는 표준 라이브러리로 만들며 새 서버 패키지가 없다. 사용자·모델 문장은 수식이
아닌 텍스트 셀이다. CSV의 수식 시작 문자도 텍스트로 처리한다. XLSX의 셀 제한을
넘는 답변만 표시용으로 줄이고 JSON 확인 문구를 붙인다. 원본·CSV·요약 행은 보존한다.
파일 `0640`·폴더 `0750`·비밀값 가림을 유지한다. 열어 둔 엑셀은 다시 열어 최신 표를 본다.

기존 보고서와 같은 best-effort 사본이다. finalizer 포화·프로세스 종료·NFS 오류로
미완료일 수 있다. 잠금은 최대 10초 대기하고 실패하면 `shared_summary.failed`를 남긴다.
답변·상세 보고서 처리는 계속하며 이미 저장된 `.row`로 표를 복구할 수 있다.

## 기존 기록 요약과 복구

저장소 루트에서 코드스페이스의 기존 Python으로 실행한다. 질의·모델 호출은 없다.

```bash
PYTHONPATH=02_BACKEND python3 -m semantic_runtime.request_summary \
  --root /nfs-root/diamo/8-agent/rag-request-reports --date 2026-09-28
```

`--team risk_team`·`--team financial_team`으로 한 팀만 처리하거나 `--date`를
생략해 모든 날짜를 처리한다. 과거 날짜 바로 아래 JSON도 팀별 표로 요약하며
기존 `.log`·JSON·TXT는 이동·덮어쓰기하지 않는다. 과거 팀 미지정은 `unassigned`다.
시각은 저장된 요청 시작 시각, `request.started`, 보고서 생성 시각 순으로 사용한다.
기존 JSON 없이 `.log`만 있는 기록에서 답변을 추정하지 않는다.

두 코드서빙 모두 새 코드와 `semantic_runtime/request_summary.py`를 포함한
리비전으로 적용해야 한다. 기존 워크플로우에 `TEAM_ID`가 있으면 Python 본문 교체
없이 두 환경 값을 확인하면 된다. 데이터 재구축은 필요 없다. 현장 질문 확인은
워크플로우 테스트 화면에서 팀별로 진행하고 같은 요청 ID의 표·로그를 대조한다.
복구는 이전 코드서빙 리비전 선택이며 원본 기록은 삭제하지 않는다.

로컬 검증은 별도 프로세스의 동시 갱신, 팀 분리, 자정 경계, 실패 응답, 비밀값 가림,
엑셀 셀·필터, 기록 재생성, 요청 반환 비차단 계약이다. 실제 현장 적용은 별도다.

## 현행 GENOS 인계본 R3 — Python 버전 간 함수 검사 일치

추가 현장 사진에서 R2는 `DeferredReport.__init__` 검사에 실패했다. Python 3.14의
`ast.dump` 빈 필드 출력이 3.11과 달라 같은 함수의 해시가 달랐다. 실제 Python 3.11에서
사진의 `ebec1d1454229f6c8d6d9fbef0b684c6dc61fa6f46d663f172efee0d2898ac54`를
재현했다. **팀 로그 R1/R2 대신 R3를 사용한다.** 기존 ZIP/TXT는 이력으로 보존한다.

- [R3 패치 ZIP](../../../08_DEPLOYMENT/GENOS/patches/GENOS_TEAM_REQUEST_LOGS_20260928_R3.zip)
- [R3 전체 실행 TXT](../../../08_DEPLOYMENT/GENOS/patches/GENOS_TEAM_REQUEST_LOGS_20260928_R3_APPLY.txt)
- [R3 적용·검증·원복](../../../08_DEPLOYMENT/GENOS/patches/team_request_logs_20260928_r3/PATCH_NOTES.txt)

R3는 AST 필드를 고정 JSON 형식으로 직렬화해 빈 필드도 보존한다. 3.12에서 추가된
빈 `type_params`만 제외하고 실제 구문 차이는 검사한다. 기존 코드·manifest·schema의
바이트 SHA 검증은 유지한다. 호환되지 않는 대상 함수는 목록으로 함께 출력한다.
실제 Python 3.11과 3.14에서 이전 전달본의 서명·변환 바이트 일치를 확인했다.
3.11 프로세스에서 `~/DEV` 링크, LF/CRLF, 적용·재실행·commit 비교·원복과 모의 요청의
팀별 plain 로그·XLSX·CSV 생성도 확인했다. 관련 검사 74개 통과이며 현장 배포는 미확인이다.

같은 사진의 SSE R1 링크 거부는 별도 설치기 문제다. 이미 발송된 SSE R2 인계본을 쓴다.
팀 로그 R3는 SSE 설치기나 워크플로우 본문을 변경하지 않는다.

## 이전 GENOS 인계본 R2 (R3로 대체)

2026-09-28 현장 사진에서 R1의 패키지 검증은 통과했지만 `request_report.py` 전체
SHA 목록에 없는 버전이라 코드 쓰기 전 중단했다. 이전 thinking R2 variant에서도
같은 거부를 로컬로 재현했다. 사진에는 현장 원본 SHA·함수 내용이 없어 정확한
현장 조합까지 특정하지는 않는다. 아래 R2는 전달 이력이며 현행 적용본은 R3다.

- [R2 패치 ZIP](../../../08_DEPLOYMENT/GENOS/patches/GENOS_TEAM_REQUEST_LOGS_20260928_R2.zip)
- [R2 전체 실행 TXT](../../../08_DEPLOYMENT/GENOS/patches/GENOS_TEAM_REQUEST_LOGS_20260928_R2_APPLY.txt)
- [R2 적용·검증·원복](../../../08_DEPLOYMENT/GENOS/patches/team_request_logs_20260928_r2/PATCH_NOTES.txt)

R2는 고정한 템플릿으로 필요한 보고서 함수 9개와 필수 import만 수정한다. 대상 함수의
AST가 이전/현재 계약과 같아야 하며 다른 함수·진단 필드·표시 루프·현장 추가 바이트는
보존한다. 전체 report SHA가 달라도 호환 가능한 구문과 등록 pin이 확인되면 적용한다.
변환 asset도 SHA로 결속한다. 기존 엔진/소스/스키마 hash 불일치를 승인하지 않는다.

`INPUT_CHECK`에 실제 설치 SHA·크기를 기록하고 `STRUCTURAL_CHECK_PASS` 이후 전체
pin을 검증한 뒤 백업·원자 적용한다. 재실행·쓰기 실패 원복·후속 수정 보호와 적용
결과 ZIP/commit/generation 결속은 R1과 같은 계약이다. 실제 GENOS 함수 구조와
generation/리비전/새 요청 로그 확인은 현장 실행 전까지 미확인이다.

## 이전 GENOS 인계본 R1 (R2로 대체)

- [부분 패치 ZIP](../../../08_DEPLOYMENT/GENOS/patches/GENOS_TEAM_REQUEST_LOGS_20260928_R1.zip)
- [전체 실행 TXT](../../../08_DEPLOYMENT/GENOS/patches/GENOS_TEAM_REQUEST_LOGS_20260928_R1_APPLY.txt)
- [적용·검증·설정·원복 안내](../../../08_DEPLOYMENT/GENOS/patches/team_request_logs_20260928_r1/PATCH_NOTES.txt)
- [반입 해시·미확인 상태 receipt](../../../08_DEPLOYMENT/GENOS/patches/GENOS_TEAM_REQUEST_LOGS_20260928_R1_RECEIPT.json)

TXT에는 ZIP 전체가 포함되어 있다. 기본 `bash ...APPLY.txt`는 기존 `~/DEV`를 백업 후
수정하며 `MODE=check`는 소스 변경 전에 지원 버전·기존 pin을 검사한다.
변경 검토와 commit 뒤 `MODE=verify`는 그 checkout과 적용 결과 `applied-code.zip`을
비교하고 기존 선택 generation을 검증한다. 데이터 설정·CURRENT는 갱신하지 않는다.
통과 commit을 push하고 두 코드서빙에 새 리비전을 반영해야 한다.

`request_report.py`의 지원 이전 바이트 8종과 새 모듈 두 개를 SHA-256으로 고정했다.
기존 thinking R2/R3와 relation-wait/request-unlimited 조합을 확인했으며 다른 바이트나
무관한 기존 pin 불일치는 변경 전에 거부한다. 3개 모듈을 엔진 files에 포함하고 해당
manifest pin만 함께 갱신한다. 원복 시 기존 파일을 복구하고 이번에 새로 넣은 파일만
제거한다. 이후 수정이 있으면 원복은 덮어쓰지 않는다.

계약·회귀·설치 검사 **72 passed**. Python 3.11 문법, `bash -n`, ZIP 크기·SHA-256,
JS 제외와 전체 TXT의 검사·적용·재실행·commit 비교·원복을 검증했다.
TXT의 generation 실행 검사는 명시적 모의 fixture이며 실제 GENOS E2E 성공이 아니다.
현장 commit·push·generation 결속·두 서빙 리비전·워크플로우·NFS 동시 갱신은 미확인이다.
