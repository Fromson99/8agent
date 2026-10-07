# 팀별 원문 준비와 구조화

2026-09-17 작업 코드. 로컬 검증과 GENOS 현장 적용은 별개다.

## 입력과 선택

```
01_DATA/RAW/
  internal/risk_team/<기존 분류>/<원본·PDF·ZIP>
  internal/financial_team/
  external/risk_team/<출처>/<문서명>/<본문·별표서식>
  external/financial_team/<출처>/<문서명>/<본문·별표서식>
```

팀은 `<이름>_team` 폴더로 추가한다. 대소문자 구분, 영문·숫자·밑줄·하이픈을 허용한다.
기존 risk 외규 중 사진의 financial 범위와 겹치는 19종은 양쪽 팀 경로에 둔다.
사진의 financial 문서 61종 중 나머지 42종은 `financial_team`에 둔다.
기존 internal은 모두 `risk_team`이다. 지정 외 문서·공통 용어집은
기존 보관/공통 경로를 유지한다. 팀명은 검색용 메타데이터이며 접근권한 부여가 아니다.

2026-09-30 이관의 `RAW/union_file/manifest.json`은 공통 원본 150쌍의 두 경로와
SHA-256을 고정한다. 양쪽 팀을 한 번에 재구축할 때 XML 투영·ZIP 해제·PDF 변환은
한쪽에서 한 번 수행하고 동일 해시의 파생 파일을 각 팀 경로에 보존한다. 구조화와
색인은 동일 문서 ID에 대해 한 번 수행하며 두 팀 경로를 위치 메타데이터로 연결한다.
GENOS의 완료 세대를 재사용하는 이관은
[financial union 인계](../../../08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r1/README.txt)를 따른다.

유지된 진입점에서 한 번 이행한다.

```sh
.venv/bin/python 06_TOOLS/pipeline.py prepare-data --team-layout
.venv/bin/python 06_TOOLS/pipeline.py prepare-data --team-layout --apply
```

기존 `BUILD_SCOPE.json`이 있으면 그 파일 목록·해시·공개/내부 제한을 따른다.
기존 공식 PDF 영수증이 있으면 SHA로 결속해 같은 이름의 PDF를 함께 배치한다.
원본 파일명과 문서 아래의 별표서식 등 하위 경로를 유지한다.
범위가 없는 현장은 legacy RAW 출처별 폴더를 옮겨 담되 반출 허용을 자동 부여하지 않는다.
이미 팀 폴더에 둔 파일도 그대로 사용할 수 있다.

`CATALOG/TEAM_LAYOUT.json`이 새 작업 트리와 원본 경로·SHA 대응표를 선택한다.
이행은 새 작업 사본 생성이다. 과거 패키지·구조화 영수증이 참조하는 기존 RAW 경로를
삭제하지 않으며 새 팀별 실행에서는 선택하지 않는다. 재실행 시 동일 해시만 재사용한다.
`--document-scope`를 명시한 과거 실행은 계속 원래 고정 범위로 재현한다.

## 파일 수정·폴더 이동 후 등록 자동 갱신

```sh
.venv/bin/python 06_TOOLS/pipeline.py prepare-data --refresh-team-layout --apply
```

현재 등록 파일의 해시를 자동 재계산하고, 같은 내부/외부 분류에서 해시가 유일하게
일치하는 이동 파일은 새 경로에 결속한다. 폴더 이동 자체는 파일 해시를 바꾸지 않는다.
`--apply`를 빼면 변경 예정 목록만 출력한다. 공유 RAW 잠금 안에서 재검증 후 적용한다.
스캔은 파일 바이트를 읽지만 파싱·PDF 변환·모델 호출은 하지 않는다.

`CATALOG/TEAM_LAYOUT_HISTORY/<id>/before.json`, `after.json`, `receipt.json`을 먼저
보존하고 작업 등록 `TEAM_LAYOUT.json`만 교체한다. 완료 구조화·원본·과거 패키지·CURRENT는
변경하지 않는다. 이미 사용자가 덮어쓴 이전 원문 바이트는 해시만으로 복구할 수 없다.
이동 경로 후보가 여러 개면 중단하며, 신규 미등록 파일은 기존 수집 경로가 처리한다.
등록에서 사라진 경로는 새 등록에서 제외하고 이전 기록에 남긴다.
내용이 바뀐 파일은 과거 해시의 외부 반출 승인을 상속하지 않는다.
파생 PDF/MD 또는 ZIP 추출 계보가 깨진 경우에는 해시만 바꿔 승인하지 않고 중단한다.

갱신 후 새 run ID로 구조화를 실행한다. PDF가 모두 준비됐으면 아래처럼 실행한다.

```sh
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id full-structure-refreshed-001 --stage structure --unzip off --pdf-conversion off --execute
```

구조화 실패 시 같은 run ID로 재개한다. 변경할 때마다 명시적으로 등록 갱신을 실행한다.
로컬 모의 계약 검증이며 GENOS 현장 적용은 별도다.

## 실행 순서와 스위치

`build-data-stages` 및 이를 호출하는 `build-all`에 연결했다.

0. ZIP 해제: 각 ZIP 옆에서 원래 폴더 구조로 병합. 동일 파일 재사용, 다른 내용 충돌 시 중단.
   중첩 3단계, 경로 이탈·링크·암호화 ZIP 차단. ZIP 자체는 보존한다.
1. XML → `<원본.xml>.md`: 등록 법령/행정규칙 XML 파서로 조문·부칙·별표 단서를 투영한다.
   MD는 열람용이며 XML 원문·별도 별표 첨부를 대체하지 않는다.
2. 변환 요청은 `.doc/.hwp/.xlsx/.xls/.pptx/.ppt`에 한정한다(`raw_preprocess.PDF_SOURCES`).
   같은 폴더·이름의 PDF가 이미 있으면 검사만 하고 요청하지 않는다. XML/HWPX/DOCX/HTML은
   파서가 원문 구조를 직접 읽고 좌표·열람용 PDF는 `core.structure.synthpdf`가 만들므로
   변환기로 보내지 않는다. 여러 원본이 같은 PDF 이름을 공유하면 우선순위로 한 번만 요청한다.
3. 원본 형식에 맞게 구조화: XML/HTML/HWPX/DOCX가 주 입력, PDF는 참고 파일.
   DOC·HWP는 변환한 PDF가 주 입력이다. 파생 MD를 별도 문서로 중복 적재하지 않는다.

```sh
# 파일 준비·해시만 점검. 변환 API/구조화 호출 없음; ZIP 결과는 계획까지만 확인.
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id team-check --check-only

# ZIP·XML MD 준비를 실행하고 PDF API 호출은 끈다.
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id team-prepare --stage raw --pdf-conversion off --execute

# risk_team만 준비부터 구조화까지. 이후 index/all은 기존 용어집 연결 조건도 필요하다.
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id risk-structure-001 --team risk_team --stage structure --execute
```

`--unzip on|off`, `--xml-markdown on|off`, `--pdf-conversion on|off`가 각각 독립 스위치다.
팀 레이아웃에서 기본은 모두 on. `GENOS_PDF_CONVERSION=off`로 PDF 생성 기본을 끌 수 있다.
XML은 PDF를 만들지 않으므로 XML Markdown 단계는 열람용 투영 그 자체다.
`--team`은 반복 지정 가능하다. `--only-internal`/`--exclude-internal`도 유지한다.
`--stage index`는 이미 준비된 파일을 읽으며 ZIP/변환을 재실행하지 않는다.
공유 RAW 잠금 때문에 준비 중 다른 빌드는 시작하지 않는다.

## PDF 전처리기 설정

2026-10-01 사용자 지시: 현행 TXT는 `GENOS_FULL_PIPELINE_BACKUP_E2E_R11_UTF8.txt`다.
XLS·XLSX와 그 출처가 확인된 파생 PDF는 이번 변환·적재에서 제외하고 RAW 원본은 보존한다.
준비 보고서의 EXCLUDED_SPREADSHEET와 수집 제외 사유
spreadsheet_form_excluded_by_user, 저장된 요청 제외 원장에 제외 범위를 남긴다.
과거 엑셀 변환의 FAILED/PENDING 영수증은 수정·삭제·재호출하지 않고 대기를 건너뛴다.
PDF 대기 콘솔에는 시간·상태만 표시하며 반복 FileNotFoundError 문자열은 제거한다.
상세 원인은 conversion.json에 유지하고 실제 의존성·권한·PDF 검증 실패는 출력한다.
실행 중인 R10은 현장에서 Ctrl+C로 종료한 뒤 같은 run ID로 R11을 실행한다.
이 작업은 엑셀 원본 삭제·서버 변환 작업 취소·기존 서빙 세대 갱신이 아니다.

이전 R10 기록: 2026-10-01 사용자 지시로 전체 실행 TXT는
`GENOS_FULL_PIPELINE_BACKUP_E2E_R10.txt`다. R9의 근거 없는 300초 PDF 출력 대기
중단을 제거했다. 기존 `GENOS_PDF_OUTPUT_WAIT_SECONDS`는 값과 무관하게 무시한다.
응답 후 같은 요청의 PDF를 시간 제한 없이 기다리며 10초마다 건수·경과시간을 표시한다.
의존성·권한·안정된 비정상 PDF의 실제 오류는 숨기지 않는다. HTTP 요청 자체의
기존 네트워크 timeout은 별도이며 이번 변경 범위가 아니다.
저장된 FAILED/PENDING 작업은 URL·리비전·공유 경로·입력 해시를 확인하고 원래
영수증을 보존한 뒤 같은 출력만 기다린다. API 재호출은 없으며 Ctrl+C로 사용자가
대기를 중단할 수 있다. 서버 작업 상태 API가 없어 장기 대기만으로 실패를 확정하지 않는다.
코드 백업·적용 영수증·원복과 PDF 검증을 유지하며 CURRENT·서빙 리비전은 변경하지 않는다.
로컬 모의 검증과 GENOS 현장 성공은 별도다.

이전 R7 인계 기록: 실제 원인 표시 수정과 재개를 묶은 실행본은
`GENOS_FULL_PIPELINE_BACKUP_E2E_R7.txt`다. 코드 변경 7개 파일을 기존 checkout에서
정확한 변경 구문/반복 상태로 확인하고 전체 계획의 Python 3.11 문법을 검증한 뒤 백업·적용한다.
별도 코드 ZIP 없이 TXT에 변경 명세가 내장되어 있으며 불일치는 쓰기 전에 중단한다.
PDF 의존성·변환 실패, 모델 응답 검증, 구조화/색인 결과·상태표·진행 출력 및
LLM/임베딩/VDB 연결 진단에 원래 예외 종류·메시지·원인 연결을 남긴다. 설명은 원문 뒤에
추가하며 인증키 가림을 유지한다. backend snapshot인 서빙 릴리스/리비전은 별도다.
GENOS_ERROR_PATCH_MODE=rollback 및 GENOS_ERROR_PATCH_RECEIPT로 코드 적용 영수증을
지정하면 현재 해시 확인 후 이전 코드로 복구하고 구축은 실행하지 않는다.
실패 변환 영수증에 error/error_type/expected_pdf를 추가하며 기존 완료 이력은 덮어쓰지 않는다.
구조화 지문에 결속된 코드가 달라졌으므로 기존 캐시의 재사용 판정은 새 코드에 따라 달라질 수 있다.
R6의 PDF 의존성 확인·저장된 PDF 검증 복구와 R5의 백업 재사용을 이어서 실행한다.
현장 코드 반영·전체 구축·코드서빙 배포는 미확인이다.

2026-10-01 09:14 KST: 전체 구축 TXT 현행은 같은 handoff 경로의
`GENOS_FULL_PIPELINE_BACKUP_E2E_R6.txt`다. 현장 진단에서 저장된 source.pdf의 존재·정상
헤더·원본 해시 일치를 확인했으나 실행 python3에 PyMuPDF가 없어 전체 PDF 검사는
미확인이었다. 기존 변환기는 pdf_check의 ImportError도 no valid sidecar PDF로 묶는다.
R6는 실제 python3에서 fitz를 먼저 확인하고, 없으면 checkout requirements.txt의 정확한
PyMuPDF pin을 설정된 pip index 또는 GENOS_PDF_WHEEL_ROOT의 오프라인 wheel로 설치한다.
사용 가능한 pip 패키지 공급은 현장 조건이며 로컬 검사만으로 설치 성공을 보고하지 않는다.
저장된 실패 작업은 같은 converter URL·리비전·공유 경로와 원본 해시를 검증하고
PDF 열기·쪽수·암호화·해시 안정성을 확인한 경우에만 재사용한다. 이전 영수증은 해시 이름으로
보존하고 복구 영수증에 계보를 남긴다. 사진의 HTTP 200/API code 1은 PDF_WITH_API_WARNING으로
유지한다. 복구는 /run을 다시 요청하지 않으며, 통신 단절·PDF 미완성·변경된 입력은 중단한다.
R4의 즉시 출력, R5의 정확한 r2 백업 검증·재사용과 중단 파일 보존을 유지한다.
코드서빙·CURRENT는 변경하지 않는다. 현장 PDF 열기·후속 구조화·전체 구축은 미확인이다.

2026-10-01 08:47 KST: 전체 구축 실행 TXT의 현행 수정본은
`08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_FULL_PIPELINE_BACKUP_E2E_R3.txt`다.
별도 변환 서비스를 설정하지 않았으면 기존 `GENOS_PREPROCESSOR_ID/URL`과
`GENOS_PREPROCESSOR_SHARED_ROOT`를 같은 `/run` PDF 변환에 연결한다.
서버에 `converter` 파라미터를 추가하지 않는다. 별도 변환기 설정은 우선하며
`/parser` URL은 변환에 사용하지 않는다. 설정 검사를 모델 호출·백업보다 먼저 수행한다.
모든 터미널/지속 로그에 KST 시각, 단계 시작과 전체 경과 초를 표시하고 실패 단계·줄·실제
종료 코드 및 문서 실패 요약을 남긴다. 같은 GENOS_RUN_ID로 기존 백업을 검증·재사용한다.
원본 옆 PDF 발행·변환 대상·구조화 경로는 그대로다. R2는 보존하며 코드서빙과 CURRENT는
변경하지 않는다. 로컬 설정·실패 경로 5개 검사 통과이며 GENOS 전체 구축은 미확인이다.

PDF **파싱**용 `GENOS_PREPROCESSOR_*`와 PDF **생성**용 설정은 분리했다.
현재 확인된 계약은 `POST /run`에 `file_path`와 `params`를 보내고 공유 저장소의
입력 옆 `source.pdf`를 회수하는 방식이다. 직접 PDF 바이너리를 내려주는 API가 아니다.

```sh
export GENOS_PDF_CONVERTER_ID=187
export GENOS_PDF_CONVERTER_SHARED_ROOT=/nfs-root/diamo/8-agent/pdf-output
# 서버 측 같은 저장소의 경로가 다를 때만 실제 대응 경로 지정
# export GENOS_PDF_CONVERTER_REMOTE_ROOT=/실제/서버/경로
export GENOS_PDF_CONVERTER_TIMEOUT=900
# 명시 URL은 ID보다 우선. 선택: GENOS_PDF_CONVERTER_URL, _REVISION, _API_KEY
```

공유 디렉터리는 양쪽에서 읽고 쓸 수 있어야 한다. 클라이언트가 서버 마운트를 만들지 않는다.
GENOS 서버에는 이번 세션에서 접근하지 않았다. 187의 DOC 1건 PDF 확보는 이전 현장 기록이며,
현재 DOCX/HWPX/MD 전수 지원·렌더 품질은 현장 확인이 필요하다.
요청의 이미지/표/요약 enrichment 옵션을 0으로 보내고 우리 클라이언트는 모델을 호출하지 않는다.
다만 `/run` 서버는 변환 후 파싱/OCR 등을 계속할 수 있으므로 서버 내부 VLM 비실행까지
보장하지 않는다. 해당 배포 설정 확인이 필요하다.

HTTP/API 성공이어도 PDF가 없거나 열리지 않으면 실패한다. 후속 파싱 오류가 있어도
PDF를 확보했으면 `PDF_WITH_API_WARNING`으로 구분한다. PDF 헤더·열기·쪽수 검사는
시각적 완전성/내용 품질 인증이 아니다. 타임아웃·통신 단절은 PENDING으로 보존하고
같은 run에서 자동 재요청하지 않는다. 작업을 확인한 뒤 새 run을 선택한다.

## 산출물·RAG·복구

- `LOGS/<run>/preparation/`: 단계 목록, ZIP 회원명/해시, 전처리기 요청·상태·작업 경로.
- `CATALOG/RAW_DERIVATIVES.json`: XML MD/PDF의 원본·파생 SHA 및 ZIP 추출 계보.
- `STRUCTURE`: `document_metadata`에 팀, 내부/외부, 문서명, 파일명, 전체 폴더 경로,
  중복 별칭과 원래 위치를 보존. `source.sqlite`를 통해 navigation 문서 검색에 연결한다.
- 동일 해시의 원문은 중복 구조화를 줄이고 여러 위치는 별칭으로 남긴다.
  공개/내부 또는 반출 제한이 충돌하면 합치지 않는다.
- 경로·준비 코드·동반 PDF가 달라지면 새 구조화 지문이다. 기존 용어 색인·RAG 릴리스에
  자동 반영되지 않으며 새 structure/index·서빙 후보 구축이 필요하다.

```sh
# 이전 범위 선택으로 복구. 새 파일과 과거 파일·영수증은 삭제하지 않음.
.venv/bin/python 06_TOOLS/pipeline.py prepare-data --rollback-team-layout --apply
```

코드 복구는 코드 교체 도구의 rollback receipt를 사용한다. 데이터 선택 복구와 별도다.

## 구조화 실패 문서만 재실행

`06_TOOLS/OFFLINE/genos_failed_structure_retry.py --run-id <기존 run>`은 원래 문서 상태 DB의
구조화 FAILED만 추려 새 `LOGS/failure-retry-<시각>-<고유값>/failures.html`, CSV, JSON에
문서명·경로·실제 오류·검수 호출 예산 기록을 저장한다. 조회는 본 작업 실행 중에도 가능하다.
현장에는 `GENOS_FAILED_STRUCTURE_RETRY_R1_UTF8.txt` 전체를 전달하고 기존 DEV에서 Bash로 실행한다.

`--execute`는 본 작업 잠금이 풀린 뒤 실패 문서만 기존 `genos_stages.execute`로 순차 처리한다.
원래 inventory와 현재 원문·메타데이터가 다르면 재시도를 거부한다. PDF 변환을 재요청하지 않는다.
기본값은 문서별 검수 호출 256회, 묶음 3페이지이며 `--max-calls`, `--window-pages`로 조정한다.
스키마·부모 관계 검증은 유지한다. 이는 복구용 설정이지 검증 실패를 승인하거나 품질을 인증하는 것이 아니다.
원래 상태 DB/실패 이력은 그대로 두며, 재시도 상태는 새 run의 `doc-status.html`에서 확인한다.
`--document-id <ID>`로 단건 재시도할 수 있다. 선택적 `--merge`는 검증된 성공 영수증만 원래
structure selection에 합치고 이전 선택 파일을 백업한다. CURRENT 변경·색인 실행·서빙 배포는 하지 않는다.

### DOCX 로컬 Docling 의존성 제거 (2026-10-01)

`parse_adapter.parse_docx`는 `docx_native.parse`로 연결된다. Python 표준 ZIP/XML로 본문 순서,
Word 제목 수준, 자동 번호·들여쓰기·글꼴, 표의 가로/세로 병합 셀과 포함 그림을 읽고
기존 `ParseResult → prepare_converted → 합성 PDF/parse.json → 구조화` 계약을 유지한다.
로컬 Docling 설치나 모델 다운로드는 필요 없다. PDF의 GENOS 전처리기 경로는 변경하지 않는다.
원래 Word 페이지 배치와 합성 좌표는 다르며 중첩 표 내부 격자·OLE·미지원 그림은 미확인 경고,
해석하지 못하는 altChunk·깨진 입력은 실제 오류로 남긴다. 스키마/구조 검증을 우회하지 않는다.

현장 `GENOS_DOCX_NATIVE_R1_UTF8.txt`는 기존 DEV에서 본 작업 종료 후 적용한다.
parse_docx 함수만 교체하고 새 docx_native 모듈을 추가하며 현장 다른 함수 수정은 보존한다.
원래 함수가 다르거나 작업 잠금이 잡혀 있으면 쓰기 전에 거부한다. 재적용은 무변경 확인이며
출력 receipt를 지정한 `--rollback <receipt.json>`으로 이전 바이트를 복구한다.
코드 변경은 기존 parser_identity의 core 파일 해시에 포함되므로 다음 실행/실패 재시도는
새 구조화 지문을 사용한다. 실행 중 Python 프로세스는 바뀌지 않으며 다음 프로세스에서 적용된다.
원래 실패 run의 RAW/상태 DB는 보존한다. GENOS 내부 문서 성공은 현장 검증 전 미확인이다.

실패 재시도 R2는 `--format docx`로 DOCX만 먼저 처리한다. `--format pdf`만 지정하고
`--execute`를 생략하면 모델 호출 없이 PDF 실패 진단 목록을 만든다. 최근 검수 verdict,
호출 수·출력 제한 신호·보류 코드·checkpoint 경로를 HTML/CSV/JSON에 추가한다.
`overlapping_sibling_spans`는 형제 노드 span 겹침이며 호출 예산 소진과 다른 오류다.
configured data root의 심볼릭 링크는 실제 root로 한 번 해석하고 내부 링크 금지는 유지한다.
진행 중 전체 재시도를 종료해도 개별 STRUCTURE 산출물은 보존되지만, 종료 전에
structure-selection 저장/원래 선택 merge가 끝났다고 가정하지 않는다.

`GENOS_STRUCTURE_FORENSICS_R1_UTF8.txt --run-id <정확한 run>`은 읽기 전용 세부 진단이다.
기본 PDF 구조화 실패만 조사하고 `--format all/docx/hwpx`, `--document-id`로 범위를 고른다.
새 `LOGS/structure-forensics-*/diagnostics.html/json`에 단계별 상태 수, 원래 selection 상태,
각 journal의 호출/hold/예산 이벤트, checkpoint 보정 횟수·pending window·승인 수,
baseline/window/final 트리별 겹친 형제와 잘못된 부모 구간·블록·페이지를 기록한다.
저장된 트리 revision을 각각 진단하며 baseline 오류를 최종 오류로 단정하지 않는다.
영수증/SQLite 존재는 표시하지만 전체 해시 검증/색인 완료/서빙 활성화를 인증하지 않는다.
원문·provider 응답은 기본 제외한다. `--include-text`는 현장 내부 진단용 원문 포함 옵션이며
내부 문서 내용을 외부 메일/모델에 전송하는 승인이 아니다. 모델 재호출·코드/기존 산출물
수정·CURRENT 전환은 없고 실행 중에는 읽기 시점이 서로 다를 수 있다.

`--stage structure`와 실패 재시도는 파싱·구조 생성·VLM 구조 검수/보정·구조 저장까지다.
문서–용어 연결, 용어/정의/명시 참조 색인과 후속 연결 보정·통합 서빙 구축은 별도 후속 단계다.
R11 전체 TXT는 structure 단계 exit!=0이면 document-release build 전에 종료한다.
따라서 구조화 VLM 호출을 후속 용어 연결 LLM 처리 완료로 해석하지 않는다.

### 번호 항목 블록 분할 + 최단 실패 PDF 단건 검증 (2026-10-01)

`GENOS_SPAN_FIX_SHORTEST_R1_UTF8.txt`는 기존 checkout의 ingest/model을 백업 후
수정하고 `structure/source_lines.py`를 추가한다. unbound 구조화 입력에서 한 텍스트
블록 안의 여러 줄 시작 번호 항목을 분리하며 원문 문자 범위·해시·페이지·요소·원래 bbox를
보존한다. bbox는 하위 줄의 실제 좌표가 아니라 공유된 원래 bbox임을 기록한다.
표·날짜·줄 중간 참조는 분리하지 않으며 트리 검증을 해제하거나 부모 범위를 늘리지 않는다.
모든 `invalid_tree_parent`/`overlapping_sibling_spans` 해결을 보장하지 않는다.

`GENOS_DATA_ROOT=/workspace/01_DATA bash TRANSFER/GENOS_SPAN_FIX_SHORTEST_R1_UTF8.txt --run-id financial-risk-full-e2e-20260930-r3`
는 실패 PDF들의 실제 페이지 수를 비교하고 최단 한 건만 새 child run에서 구조화한다.
`SHORTEST_SELECTED`와 `shortest-selection.json`에 선택 근거를 남긴다. 진행 중 파이프라인
lock이 있으면 적용을 거절한다. 기본 merge·색인·CURRENT·서빙 변경은 없으며 원래 ledger는
보존한다. 코드 롤백은 동일 TXT `--rollback <출력된 receipt.json>`으로 실행하고 백업을 보존한다.
로컬 합성 계약 검사 통과는 현장 내부 문서/모델 처리 성공을 의미하지 않는다.

### 성공분 후속 실행 R2 — 재시도 병합 원장 불일치 (2026-10-01)

현장 R1의 `Structure selection and latest status ledger disagree`는 재시도 merge가
선택 영수증에 성공분을 추가하지만 원래 실패 원장을 보존하는 계약과 후속 select의
PASSED 집합 일치 검사가 충돌한 것이다. `GENOS_SUCCESS_CONTINUE_R2_UTF8.txt`는
`structure_selection.py` 수정과 `retry_adoption.py` 추가를 기존 checkout에 백업 후 적용한다.
merge 이전 백업 해시·선택 합집합·child 종료 상태·PASSED·원래 입력 inventory 일치와
기존 release consumer의 영수증/구조/원문 SQLite 검증을 모두 통과한 재시도 성공만
후속 성공 집합에 포함한다. 원래 원장·실패 기록은 덮어쓰지 않으며 채택 증거는 새 origin에
결속한다. 증거 없는 불일치는 계속 중단한다. 재파싱/VLM 재호출은 없다.

`bash TRANSFER/GENOS_SUCCESS_CONTINUE_R2_UTF8.txt`로 실행하며 R1 대신 사용한다.
선택 수를 확인하고 YES를 입력하면 성공분 후속 구축을 시작한다. REVIEW_PENDING에는
동일 TXT로 재개한다. 코드 롤백은 동일 TXT `--rollback <출력 receipt.json>`이다.
후속 생성물은 보존하며 CURRENT/공유 발행/코드서빙 배포는 하지 않는다.
로컬 계약·인계 검사 29개 통과, GENOS 실제 적용과 후속 구축은 현장 미확인이다.

`GENOS_RELEASE_PROGRESS_R1_UTF8.txt`는 별도 DEV 터미널에서 기본 읽기 전용 감시로
현재 성공분 후속 run의 저장된 단계·용어 검토 job·참조 case 상태를 10초마다 표시한다.
DB는 mode=ro/query_only로 읽고 실제 종료 상태와 실패·미확인·남은 처리를 분리한다.
아직 계획이 없는 단계의 전체 수·시간 ETA는 추정하지 않는다. 감시 종료는 구축을 종료하지 않는다.
현재 구축이 끝난 뒤 `--build`로 재개하면 기존 CLI를 그대로 실행하면서 메모리 wrapper로
원문 검증·통합·용어 후보·LLM 검토·문서 연결·색인·참조 보정·자산 검증의 시작/반환/중단과
경과 시간을 출력한다. 파이프라인 소스 바이트·plan hash·모델 설정·CURRENT는 변경하지 않는다.
저장된 완료 기록만으로 프로세스 생존이나 무결성 인증을 주장하지 않는다.
로컬 모의 감시·계수·실행 배선·인계 검사 6개 통과, 실제 현장 표시와 처리 속도는 미확인이다.

진행 도구 현행 수정본은 `GENOS_RELEASE_PROGRESS_R3_UTF8.txt`다. 현장 R1은 없는
`reference_resolution.advance` 로그 wrapper에서, R2는 현장 CLI가 지원하지 않는
`--reference-model-profile` 옵션에서 build 시작 전 중단했다. 단순 로그 호환으로
해결할 문제가 아니라 실제 후속 참조 LLM 자동 실행 연결이 누락된 코드 차이였다.
R3의 `--build`는 release의 build·참조 audit 함수와 CLI 옵션/호출 부분, reference의
advance·자동 승인 함수를 기존 checkout에 백업 후 적용한다. 나머지 함수/모듈은 보존한다.
현장 의존 함수/시그니처·파싱/CLI 도움말 검사를 쓰기 전에 수행한다. 이미 다른 compiler
해시로 구축 계획을 저장한 run은 덮어쓰지 않고 중단한다. 이전 사진처럼 build 전 오류만
발생했다면 기존 선택 run을 사용한다. 데이터 CURRENT·코드서빙 배포는 하지 않는다.

감시 오류는 원문 예외·traceback을, 구축 실패는 원문 예외·전체 traceback·실행 인수·종료
코드를 출력한다. 실패 뒤 일반 진행 스냅샷은 붙이지 않는다. 코드 rollback은 동일 R3 TXT
`--rollback <출력 receipt.json>`이며 완료 데이터는 삭제하지 않는다. 현장 성공은 미확인이다.
