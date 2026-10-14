# 데이터 입력·생성

현재 전체 흐름은 [ARCHITECTURE](../00_SYSTEM/ARCHITECTURE.md), 데이터 계약은 [DATA_MODEL](../00_SYSTEM/DATA_MODEL.md)을 따른다.
경로는 `lawrag.platform.workspace`의 논리 `data` root로 해결한다. 완료 세대·RAW·원문 해시는 보존한다.

2026-09-17 팀별 작업 입력을 `RAW/internal/<team>`, `RAW/external/<team>`으로 배치했다.
`CATALOG/TEAM_LAYOUT.json`이 있으면 신규 기본 구축은 이 작업 트리를 선택한다.
기존 `BUILD_SCOPE.json`과 원래 파일은 과거 실행 재현용으로 보존하며 `--document-scope`를
명시하면 이전 범위가 우선한다. 사진의 financial 문서 61종은 financial_team에
등록했고 이 중 risk_team과 겹치는 19종은 양쪽에 보존한다. 공유 RAW 150쌍은
`RAW/union_file/manifest.json`에 해시로 고정한다. GENOS 현장 적용은 별도다.
[전처리 순서·분류·복구 안내](../07_DOCS/REFERENCE/OPERATIONS/GENOS_TEAM_RAW.md).

## 현재 생성 경로

```text
RAW 입력 (내규·외규, 형식별) → STRUCTURE → 용어·정의·참조 색인 → TERM/<run>/<document>/generation
```

- `RAW/<source>`: 원본과 입력 출처·버전·해시. 내규도 `RAW/internal`에서 PDF/XML/Office 등 형식별로 선택한다. `PDF/internal` 이동은 별도 이행 작업이다.
- `STRUCTURE/<fingerprint>`: 원문 구조와 `source.sqlite`. 의미 추출 작업은 만들지 않는다. PDF 구조 복원·검수는 유지한다.
- `LEXICON`: 선택 용어집과 문서 출현·정의 연결. 용어 목록 수집과 정의·관계 수집 완료는 별개다.
- `TERM/<run>/<document>/generation`: 원문 전용 저장소와 `navigation` 색인. `result.json`은 입력·코드·결과를 결속한다.
- `TERM/<run>/<document>/audit/navigation`: 신규 생성의 분리 전 완성 navigation 감사 snapshot과 해시 영수증. 검색용 generation에는 구축 표 4개를 제외하고 작성 측에서 원장을 보존·검증한다. 통합 릴리스는 `serving/audit/navigation`에 보관한다. [분리·기존 세대 이행](../07_DOCS/REFERENCE/OPERATIONS/NAVIGATION_STORAGE.md).
- `LOGS/<run>`: 실행·입력·오류·진행 기록. 현재 단계 상태는 `term-document-status.sqlite`에 저장한다.
- `SEMANTIC/GENERATIONS`, `SEMANTIC/TERM_INDEX`: 이미 사용하던 세대 저장 위치. 이름과 무관하게 신규 선택 데이터의 manifest 계약이 기준이다. 과거 의미 세대는 복구용으로 보존한다.

기존 `LLM` 의미 추출 결과 및 VECTOR 산출물은 신규 생성·RAG의 필수 입력에서 제외했다. 신규 의미 추출/검토/재추출과 조건식·Rule 생성은 실행하지 않는다.

## 실행

2026-10-08 MAIN의 `build-all` 기본값은 `00_SYSTEM/PIPELINE.json`의
`document_build.default_mode=native-no-models`다. 신규 팀 RAW는 현재의
XML/HTML/HWPX/DOCX/HWP 원본 파서로 구조화하고 구조 VLM·원격 PDF 변환을 끈다.
PDF는 명시적으로 로컬 파서를 선택한다. 원문 통합·용어 초안의 문서 근거 교체 후
2026-10-03 GENOS 최종 최적화 방식인 `compact-v2`와 단위 전문 색인을 명시 선택한다.
원문 source-v2, navigation-v7로 구축하며 감사 원장과 단계별 재개 기록을 보존한다.
2026-10-08 사용자 정정에 따라 로컬 MAIN은 `audit_profile=factorized-v1`/storage-v4를
선택한다. 검증된 출현·후보·기존 연결의 정수 좌표만 저장하고, 출현×후보 근거 및
추가 연결 출처는 같은 규칙의 SQLite view로 재현한다. 수천만 조합 행을 먼저 생성한 뒤
줄이는 방식이 아니므로 구축 중 감사 DB도 작다. 원문/후보/HELD 사유와 재개 계약은 유지한다.
용어 의미 검토·정의/번역 생성·모델 참조 검토는 실행하지 않는다. 새 결과는
서빙 자원을 포함한 후보이며 오프라인 계약 검사를 수행한다. 활성 MAIN 릴리스 전환은 별도다.
완료된 용어집 지식 묶음이 없으면 중단하며 legacy 저장 방식으로 자동 전환하지 않는다.
완료 navigation 감사 DB는 무손실 gzip으로 보관한다. 검증·재개 때 잠시 복원하므로
상주 용량과 구축/검증 중 최대 용량은 구분한다. 새 factorized 원장은 작은 DB 자체를
복원하며, 기존의 큰 감사 DB를 새로 생성하지 않는다. [생성·압축·복원](../07_DOCS/REFERENCE/OPERATIONS/NAVIGATION_STORAGE.md).

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id native-team-main-20261008-r1 --check-only
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id native-team-main-20261008-r1 --execute
# 구조화만: 이후 용어/색인을 실행하지 않는다.
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id native-team-main-20261008-r1 --stage structure --structure-vlm off --pdf-parser local --pdf-conversion off --execute
# 준비 완료된 원문/용어집을 재사용하는 GENOS compact-v2 연결·색인
.venv/bin/python -B 06_TOOLS/pipeline.py document-release reindex --from-run-id PREPARED --run-id NEW
```

기존 모델 검토 구축은 `build-all --with-model-review`로 명시적으로 선택한다.
처음부터 재구조화하지 않고 기존 결과를 재사용하려면 `document-release reindex`에
완료 prepared run을 지정한다. 모호한 참조와 미검토 정의는 그대로 보존하며, 모델을
쓰지 않았다는 이유로 정확도/검토 완료를 승인하지 않는다. GENOS 현장 코드·배포는 별도다.

2026-10-08 사용자 지시에 따라 팀 RAW의 신규 구축에서는 큰 단독 PDF
`기업공시서식 작성기준(2026.8.3 시행)`과 `별지서식(2026.7.28 시행)`을 제외한다.
`CATALOG/BUILD_EXCLUSIONS.json`이 정확한 RAW 경로·문서 ID·전체 해시·사유를 고정한다.
MAIN의 팀 입력 선택은 이를 적용하고 실행 계획에 제외 목록 파일의 해시를 결속한다.
현재 처리 입력은 **1,544문서(본문 78종·첨부 1,457개·비교표 9개)**다.
원래 80종 scope, 두 PDF 원본, 이전 실행·완료 구조화 캐시는 보존한다.
XML/HTML/HWPX/DOCX가 우선인 기존 표현본 선택 규칙은 유지한다.

로컬 `native-team-nopdf-20261008-r2`는 2026-10-08에 1,544건 구조화를 완료했고,
`native-team-nopdf-20261008-r2-index`는 compact-v2/unit 색인 254,784단위와
offline E2E 검증을 완료했다. 이번 실행의 LLM/VLM 호출은 0회이며 추가 스왑은 없다.
navigation 감사 원장은 1,202,704,384바이트에서 328,704,732바이트로 무손실 압축했다.
이 결과는 로컬 서빙 후보이며 활성 RAG 선택·GENOS 반입은 별도다.
[완료·용량 기록](../09_ARTIFACTS/AUDITS/20261008-native-team-nopdf/completion-receipt.json).

2026-10-08 후속 사용자 요청으로 로컬 서빙을 활성화했다. 새 선택은
`TERM_RELEASES/native-cm-serving-20261008-r2-index/serving/baseline/generation`의
**1,546문서 / unit 전문 색인 255,777단위**다. 기존 1,544개 구조화를 재사용하고,
CM51에서 필요한 `중소기업기본법`과 `중소기업창업 지원법 시행령` 2개는 이전 검증
공개 원문을 명시적 SourceSet으로 보충했다. 80종 RAW 범위와 두 PDF 제외는 그대로다.
CM 공통 51건/98근거/21문서를 새 원문 위치에 결속했고 실제 `service.service`의
선택 릴리스 `native-cm-serving-20261008-r1`/포인터 generation 46을 확인했다.
원문·실패 실행·이전 릴리스·CM 개인/퇴역 이력을 보존했다. 병행 코드 변경으로 마지막
실행 pin 검사가 실패한 r1 색인은 별도 r2 기록에서 동일 builder identity로 검증·재사용했다.
LLM/VLM 호출은 0회이고 GENOS 반입·법률 답변 품질 인증은 별도다.
외부 모델 원문은 이전 승인과 같은 65문서로 제한하고 내부 CM 질문 반출 제한을 유지한다.
[서빙·CM·롤백 완료 기록](../09_ARTIFACTS/AUDITS/20261008-native-cm-serving/completion.json).

2026-09-17 사용자 지정 범위는 사진 목록의 **80종과 그 문서에 딸린 등록 첨부**다.
`CATALOG/BUILD_SCOPE.json`이 `CATALOG/SCOPES/photo-required-80-hwpx-20260917.json`의
해시를 고정한다. `build-data-stages`와 이를 호출하는 `build-all`은 이 설정이 있으면
명시된 파일만 선택하며 목록 밖 RAW를 자동으로 다시 넣지 않는다. 원본 또는 출처 영수증의
해시가 바뀌면 중단한다. `--document-scope`로 별도 명시 범위를 선택할 수 있다.
`--only-internal-pdf`는 구성된 범위와 충돌하므로 함께 사용하지 않는다.

제외 원본은 `BACKUPS/photo-out-of-scope-20260917/originals.zip`에 별도 백업했다.
과거 패키지·릴리스의 원본 참조를 보존하기 위해 기존 RAW 경로도 유지한다.
공통 용어집은 문서 범위 밖이라는 이유로 제거하지 않는다. 새 입력 범위 설정은 기존
로컬 활성 159문서 릴리스나 GENOS 현장 상태를 변경하지 않는다.
[문서별 보유·처리 상태와 복구 안내](../09_ARTIFACTS/AUDITS/20260917-photo-80-scope/README.md).

2026-09-17 공개 법령·거래소·금투협의 HWP 1,287개를 한글 2024의 공식 변환기로
HWPX 파생본으로 생성했다. 원래 80종 범위와 RAW 원본을 보존하고, 새 DatasetPackage의
HWPX를 신규 구축 입력으로 선택한다. 전체 1,287개 본문·표/병합 셀 비교 및 HWPX 파서
읽기 검사, 전체 1,538개 선택 입력의 해시 검사를 통과했다. 내부 제한 입력 11개 표현본은
그대로 유지한다. 기존 실행의 재개에는 이전 scope를 사용하고, HWPX 입력 구축은 새 run ID를
사용한다. 기본 구축 범위 변경이며 구조화·색인 재구축이나 MAIN/GENOS 배포는 아니다.
[변환본·검증·롤백 안내](../09_ARTIFACTS/AUDITS/20260917-hwp-to-hwpx/README.md).

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id term-build-001 --check-only
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id term-build-001 --stage all --execute
```

전체 구조화·명시 기존 세대 통합·기존/신규 용어 후보 통합 검토·전체 연결과 서빙 후보 생성까지 실행하려면 `build-all --run-id term-build-001 --execute`를 사용한다.
단계 실행·재개·GENOS 인계는 [운영 가이드](../07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md)를 따른다.
GENOS PDF 파싱은 [전처리기 ID/URL 환경 설정](../07_DOCS/REFERENCE/OPERATIONS/GENOS_PREPROCESSOR_PARSING.md)을 사용한다.
동일 폴더의 HWPX/DOCX와 참고 PDF, ZIP 병합·중복 점검, 파일명/폴더 보존은
[원본 우선 반입](../07_DOCS/REFERENCE/OPERATIONS/GENOS_NATIVE_PRIMARY.md)을 따른다.
외규 지정 scope가 설정돼 있어도 `--only-internal`로 RAW/internal 전체 형식을 별도 처리한다.

새 입력은 출처·문서 ID·버전·해시·공개/내부·실제/모의 구분을 기록하고 RAW에서 검증한다. 외부·내부 데이터는 DatasetPackage와 명시적 SourceSet 범위를 보존한다. DRAFT 생성은 배포 승인이나 데이터 반출 승인을 뜻하지 않는다. 내부 데이터 처리는 망분리 GENOS에서 수행한다.

`TERM_RELEASES/<run>`은 명시적으로 선택한 기존 세대와 이번 문서의 통합 후보다. 기존 문서 유지는 `build-all --base-generation <path>`로 지정한다. 신규 세대·문서 간 참조·검토·활성화/롤백은 [추가 문서 연결](../07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_CONNECTIONS.md)을 따른다.
