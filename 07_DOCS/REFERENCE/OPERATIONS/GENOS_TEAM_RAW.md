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
사진의 중복 없는 외규 28종은 `risk_team`, 기존 지정 80종 중 나머지 외규는
`financial_team`, 기존 internal은 모두 `risk_team`이다. 지정 외 문서·공통 용어집은
기존 보관/공통 경로를 유지한다. 팀명은 검색용 메타데이터이며 접근권한 부여가 아니다.

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
