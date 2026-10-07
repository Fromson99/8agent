# GENOS 답변 경로의 반복 준비·로그 대기 제거

2026-09-28 사용자 요청으로 MAIN 작업 코드의 RAG 서빙 경로를 수정했다.
리비전 표식은 `observability_revision=response-overhead-20260928-r1`이다.
전체 MAIN 중 원문·용어집을 소비하는 서빙 부분이며 데이터 구축이나 MAIN 활성화가 아니다.
GENOS 현장에 접근하지 않았고 실제 지연 감소량은 아직 측정하지 않았다.

## 제거한 비용

- 정상 단계의 시작·완료, 캐시 적중과 transaction 세부 로그를 DEBUG로 옮겼다.
  기본 INFO에서는 정제·직렬화·출력 자체를 생략한다. 요청·모델·완료·오류·진행 상태는 남긴다.
- 같은 이벤트의 콘솔·공유 로그·요청 기록이 정제 결과와 큐 크기를 한 번 계산해 재사용한다.
  문자열마다 환경변수를 전체 순회하던 작업을 이벤트별 한 번으로 줄였다.
  새 이벤트는 새 인증정보를 읽으며 중첩 목록·객체의 인증정보도 가린다.
- 공유 로그 폴더 생성·파일 열기·질문 저장을 요청의 동기 경로에서 제거했다.
  초기 준비와 상세 기록은 별도 daemon에서 실행한다. 파일 준비가 늦으면 시작 이벤트와
  run ID를 복구하고, 원장과 최종 보고서에 질문·모델 입력/응답·답변을 보존한다.
- 이미 검증한 navigation manifest와 작은 용어집 receipt를 파일 상태가 같을 때 재사용한다.
  glossary 준비는 요청 Store가 읽은 manifest를 다시 사용한다.
- StageRunner의 반복 코드 전체 해시·engine manifest 읽기와 Contracts의 검사기 생성을 줄였다.
  코드의 dev/inode/size/mtime/ctime 변경 시 재해시하며 각 단계의 기대 해시·포트·범위를 확인한다.
  배포 gate는 캐시 없는 전체 해시를 계속 사용한다.

진입점은 `service.py` → `Pipeline` → `ServingLegalAgent`/`ServingDocumentAgent` →
`StageRunner`/`Contracts`다. 로그 소비자는 컨테이너, 요청별 공유 .log/JSON/TXT와
기존 진행 상태/SSE다. 검색 순위·원문·팀 범위·모델 호출 수·시간 예산·원장 durable commit은 유지한다.
기존 v5 최종 검토 기본 비활성화와 프롬프트 축약은 별도 선행 변경이다.

## 현장 적용

[R3 패치 폴더](../../../08_DEPLOYMENT/GENOS/patches/response_overhead_20260928_r3/PATCH_NOTES.txt)의
부분 패치는 실행 파일 9개만 바꾸고, 영향받는 engine manifest와 PIPELINE pin을 결속한다.
report는 필요한 함수의 고정 구문 서명으로 검증하고 나머지 파일 8개는 R1의 정확한 hash
승인 목록을 유지한다. 기존 팀별 로그/표와 진단 버전을 유지한다. 호환되지 않는 함수나
기존 등록 pin 불일치는 적용 전에 중단한다. 과거 패키지는 수정하지 않았다.

2026-09-28 사진의 R1은 `PACKAGE_HASHES PASS` 뒤
`unsupported installed version; no changes: 02_BACKEND/semantic_runtime/request_report.py`로
백업·코드 쓰기 전에 종료했다. 사진의 두 팀 Git push는 그보다 먼저 성공했으며 이번
응답 속도 변경이 반영됐다는 뜻은 아니다. 동시기 다른 인계본은 정상 적용됐다는 사용자
보고가 있다. 이번 R1의 report 전체 hash 제한을 고치며 다른 전달본을 일괄 수정하지 않는다.
첫 사진에 현장 파일 SHA/구문은 없었다. 후속 R2 사진에는 아래 식별자가 있어
thinking R2 baseline → thinking R3 → fulltext diagnostics R1의 전달된 변환으로
설치 report 원본을 정확히 재현했다.

| 후속 사진의 항목 | 재현한 값 |
|---|---|
| report SHA-256 | `febd2ee7639102e4c376ccbb7ea98dec7a4b0dbd8ded86d32dfc7956c1d18b40` |
| report 크기 | 44,082 bytes |
| `_LiveLog.emit` canonical AST SHA | `4a00a4ad8dd1f9e2e0c9c7e772dd1edb91200703ee467fec8e5d3d579d817bd4` |

이 원본에서 R2의 같은 함수 거부를 재현했다. R2 구성기는 baselines/variants와
thinking/team 파생만 검사했고 fulltext 표시 파생 및 R1의 primary preimage를 빠뜨렸다.
R3는 해당 fulltext projection을 그대로 유지하는 검증된 비동기 emit을 결속한다.
정확한 원본은 R3 폴더의 해당 SHA baseline과 `FIELD_REPRODUCTION.json`에 남긴다.
R1/R2의 기존 ZIP·TXT·검증 기록은 보존하며 현장 오류를 수정본 성공으로 해석하지 않는다.

이전 [thinking R3 동일 오류](GENOS_THINKING_LOG_R3_20260928.md)와
[팀 로그 R3 Python 호환 수정](GENOS_TEAM_REQUEST_LOGS_20260928.md)의 방식을 반영했다.
필요한 함수 10개와 추가 메서드 2개만 검증·수정하고 진단 필드·thinking 표시·다른 함수·
현장 추가 바이트는 보존한다. 팀 R3와 같은 canonical AST JSON으로 Python 3.11/3.14에서
동일 서명을 만든다. 구형 동기 로그 판에 writer가 없으면 기존 AsyncHandler를 연결해
질문 기록·닫기 누락도 고친다. 검색·모델·데이터 계약은 R1과 같다.

- [R3 ZIP](../../../08_DEPLOYMENT/GENOS/patches/GENOS_RESPONSE_OVERHEAD_20260928_R3.zip)
- [R3 실행 TXT](../../../08_DEPLOYMENT/GENOS/patches/GENOS_RESPONSE_OVERHEAD_20260928_R3_APPLY.txt)

```bash
bash GENOS_RESPONSE_OVERHEAD_20260928_R3_APPLY.txt
```

같은 폴더에 제공한 ZIP·실행 TXT·패치노트 TXT를 놓고 `bash ..._APPLY.txt`를 실행한다.
기본 대상은 기존 `~/DEV`이며 실제 Git root로 해석한다. 지속 로그·파일별 백업·적용 영수증을
남기고 재실행은 적용된 바이트를 확인한다. Python 3.11 이상이며 새 의존성은 없다.
데이터 재구축·CURRENT 변경·워크플로우 Python 교체는 필요하지 않다.
`MODE=check`는 파일 변경 없이 구문·pin을 확인한다. `INPUT_CHECK`에 실제 파일 SHA/크기,
`STRUCTURAL_CHECK_PASS`에 before/after SHA를 기록한다. CRLF는 이전 팀 R3와 같은
Git 공백 검사 옵션으로 보존한다. 적용된 ZIP/커밋 비교는 Git에 실제 저장된 바이트도 확인한다.

적용 파일과 engine/PIPELINE 변경을 검토해 commit한 뒤 `MODE=verify GENOS_GENERATION=실제_절대경로`
모드로 그 checkout의 code gate, generation E2E와 verify_assets를 실행한다.
같은 commit을 push하고 GENOS 코드서빙 새 리비전을 배포해야 효과가 생긴다.
이 세 단계와 워크플로우에서 질문 성공은 별도 상태다.

현장 질문은 워크플로우 테스트 화면에서만 실행한다. `request.started`나 `rag.prepare.started`의
새 표식과 `session.open.ready`, `rag.loop.started`, 모델 시작/완료, `request.returning`을 본다.
서로 다른 실제 질문에서 같은 worker ID의 준비와 전체 시간을 구분한다.
필요한 상세 계측은 코드서빙 환경의 기존 `GENOS_LOG_LEVEL=DEBUG`로 다시 켤 수 있다.
DEBUG는 상세 처리 비용을 다시 발생시킨다.

## 검증·한계·원복

이전 R2 로컬 검사 160개 통과(수정본 124개, 기존 보고서·로그·완료·정제 계약 36개).
이 검사는 fulltext 표시가 적용된 현장 조합을 포함하지 못해 현장 호환 근거가 부족했다.
기존 R1 variant 자체의 실행 검사는 대체된 전달 이력이라 후자의 선택에서 제외했다.
R1 전체 hash 거부 재현, thinking R3/팀 R3 조합 10종의 LF/CRLF와 다른 함수·진단 바이트
보존, 파일 열기가 막힌 상태의 답변 반환, 팀별 XLSX/CSV/질문 로그, 부정 구문·pin·asset
거부와 쓰기 실패 원복을 확인했다. 실제 Python 3.11의 최종 ZIP/TXT를 `~/DEV` 모의 링크로
검사·적용·재실행·commit 바이트 비교·원복하고 모의 팀 요청 출력을 확인했다.
이 검사는 로컬 모의 코드 checkout이며 GENOS generation gate/리비전/속도 성공이 아니다.
세부 영수증은 R2 폴더 `LOCAL_VALIDATION.json`에 기록한다.

R3는 원본 해시·크기·함수 서명을 함께 재현해 R2 실패를 먼저 확인한다. 적용 전
실행 파일 9개를 실제 보존 바이트로 구성하고 해당 report를 넣어 최종 ZIP/TXT의
check·적용·재실행·Git commit 바이트 비교·원복을 실제 Python 3.11에서 확인한다.
LF/CRLF와 기존 request-unlimited service 판을 검사하고, 같은 설치 report에서
팀별 질문 로그·XLSX/CSV, fulltext 수치 필드와 thinking R3 표식을 확인한다.
선택 generation과 GENOS 리비전 검증은 이 로컬 코드 검사와 별도로 수행해야 한다.
R3의 상세 검증 기록은 해당 폴더 `LOCAL_VALIDATION.json`과 `FIELD_REPRODUCTION.json`이다.
최종 R3 및 관련 회귀 검사 253개 통과(R3 217개, 기존 기록·로그·완료·정제 36개).
쓰기 전 함수·코드 pin·manifest·schema·asset 거부와 9개 파일의 중간 적용 실패 원복도
확인했다. 구형 R1 variant 자체의 실행 검사 10개는 이 변경의 선택에서 제외했다.

인증정보 회전·중첩 가림, INFO에서 상세 정제 생략, 막힌 파일 열기/쓰기 중 답변 반환,
요청 취소·용량 포화·저장 실패, 늦은 run ID 복구, 파일/기대 pin 변경 거부와 실제 단계 실행을
모의 계약으로 확인한다. 설치기 적용·재실행·코드 ZIP/commit 비교·원복도 별도로 확인한다.
실제 모델·속도 비교 실험은 수행하지 않는다. 세부 결과는 인계 폴더와 audit의 검증 기록에 남긴다.

구형 document-navigation의 `test_named_document_ranks_first_without_hiding_other_documents`는
수정 전의 격리 코드에서도 같은 순서 실패가 재현됐다. 이번 서빙 준비 수정의 통과로 처리하지 않는다.

공유 기록은 기존과 같은 제한된 best-effort 사본이다. 영속 감사 정본은 journal이며,
프로세스 강제 종료나 저장 장애에는 공유 사본이 늦거나 누락될 수 있다.
선택 릴리스·실제 generation·코드서빙 리비전과 현장 속도는 미확인이다.
원복은 `MODE=rollback ROLLBACK_FROM=실제_백업경로`로 코드·pin을 함께 되돌리고
이후 편집이 있는 파일은 덮어쓰지 않는다. 서빙도 이전 검증 리비전으로 별도 복귀한다.
