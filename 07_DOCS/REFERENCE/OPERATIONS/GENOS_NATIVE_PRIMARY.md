# GENOS 원본 우선 구조화와 내부 ZIP 병합

2026-10-15 작업 코드에 `--latest-internal-versions` 선택 옵션을 추가했다.
`build-all`과 `build-data-stages`의 같은 폴더·문서명 내규에서 유효한 `(YYYYMMDD)`가 가장
큰 판본만 구조화하며 RAW·이전 세대를 보존한다. 새 선택/제외 파일·해시·사유는 inventory에,
판본 메타데이터는 원문 SQLite에 남는다. 최신 날짜 충돌·무날짜/6자리와의 혼재는 중단하고
구버전으로 자동 복귀하지 않는다. 옵션을 생략하면 기존 전체 판본 선택을 유지한다.
새 run ID로 유지할 전체 RAW 범위를 구축하며 기존 세대와의 합병은 차단한다.
선택 코드 적용만으로 기존 검색 세대가 바뀌지 않는다.
[GENOS ZIP·실행·전환·원복](../../../08_DEPLOYMENT/GENOS/handoffs/latest_internal_20261015_r1/GUIDE_UTF8.txt).

2026-09-17 작업 코드. GENOS 현장 설치·실제 내부 문서의 중복 수·전수 품질은 미확인이다.
외부 개발 환경에서는 모의 문서와 공개 HWP/HWPX 픽스처로 연결을 검증했다.

추가 실제 실행: 공개 HWPX 6개에서 VLM 없이 구조화·SQLite 저장·캐시 재개를 확인했다.
한 원문 문단에 여러 마커가 있는 경우 빈 span이 생성되던 오류를 수정했다. 해당 마디는
자신의 시작 블록을 포함하고, 문자 단위 분할이 미검증인 공유 구간임을 경고로 남긴다.
원문·표·병합 범위 보존과 실행 성공 확인이며, 조항 계층의 의미 정확도나 전수 품질 인증은 아니다.
실행 기록: `09_ARTIFACTS/AUDITS/20260917-native-pipeline-samples/README.md`.

## 입력 배치와 선택

논리 data root의 `RAW/internal` 아래 기존 PDF의 **동일한 상대 폴더**에 같은 문서의
DOCX/HWPX/DOC를 둔다. 파일명은 확장자 앞까지 일치시킨다. 예:

```text
01_DATA/RAW/internal/
  1. 상위규정.zip
  1. 상위규정/
    01 이사회규정/
      이사회규정(170817).docx
      이사회규정(170817).pdf
      이사회규정(170817)(2).pdf
```

`structured-primary-pdf-reference-v2` 선택 순서는 XML → HTML → HWPX → DOCX → PDF → HWP → DOC다.
이는 같은 폴더·동일 기본 이름, 또는 기존 명시 scope의 같은 본문 묶음 안에만 적용한다.
첨부와 본문은 합치지 않는다. DOC+PDF에서는 PDF를 구조화하고 DOC를 원본 이력으로 남긴다.
DOC만 있으면 PDF 반입 필요 오류로 표시한다. HWP만 있는 기존 입력은 pyhwp 경로를 유지하지만,
HWPX로 변환해 반입하면 직접 XML 파서를 쓴다. HWP→HWPX 변환은 외부 한글 설치 환경에서 수행한다.
GENOS의 HWPX 구조 파싱에는 한글 설치가 필요 없고, DOCX에는 기존 Docling OOXML 의존성이 필요하다.

원본/PDF 연결은 이름에 근거한 후보 연결이며 내용 일치를 인증하지 않는다.
`pairing_content_verified=false`, `coordinate_alignment=unverified`를 남긴다.
DOCX/HWPX의 구조 정보·표를 우선 파싱하고, 연결 PDF는 구조화 폴더의 `reference-pdfs`에
해시 검증 후 복사한다. 로그의 구조화 이미지 보고서에서 참고 PDF를 열 수 있다.
참고 PDF를 자동 VLM 대조하거나 원본 XML 위치를 PDF 물리 좌표로 매핑하는 기능은 포함하지 않는다.
PDF가 주 입력이면 기존 전처리기·구조 VLM 경로를 사용한다.

원본의 표시용 합성 PDF는 문단/표의 가상 좌표용이다. 이 PDF를 다시 OCR/파싱하지 않는다.
원본 해시·합성 PDF 해시·파서 코드가 일치하는 native 캐시를 읽고, 불일치하면 원본에서 재생성한다.
HWPX는 문단/스타일 속성, 실제 병합 셀, 중첩 표, 각주, 이미지 참조, XML 위치를 보존한다.
복합 개체·미해결 그림은 경고를 남기므로 구조화 완료를 문서 전체의 정확도 인증으로 보지 않는다.

## ZIP 병합과 중복 점검 — 파이프라인 밖

ZIP 파일은 `RAW/internal`에 두어도 입력 문서로 처리되지 않는다. 다음 보조 스크립트는
기존 파일을 덮어쓰거나 삭제하지 않고, ZIP도 보존한다. 먼저 계획과 중복 보고서를 확인한다.

```bash
bash 06_TOOLS/OFFLINE/genos_unpack_internal.sh
bash 06_TOOLS/OFFLINE/genos_unpack_internal.sh --apply
```

기본은 `RAW/internal/*.zip`이다. ZIP명이 `1. 상위규정.zip`이고 내부 첫 폴더가
`1. 상위규정/`이면 중복 폴더를 추가하지 않는다. 첫 폴더가 없으면 ZIP명 폴더를 한 번 붙인다.
원본 ZIP명이 기존 PDF 폴더명과 다르면 출력 계획을 보고 배치를 명시한다:

```bash
# ZIP 내부에 이미 1. 상위규정/, 2. 리스크관리담당 소관 준칙/ 등이 들어 있는 경우
bash 06_TOOLS/OFFLINE/genos_unpack_internal.sh --zip TRANSFER/originals.zip --layout root
bash 06_TOOLS/OFFLINE/genos_unpack_internal.sh --zip TRANSFER/originals.zip --layout root --apply
```

`--layout named`는 항상 ZIP명 폴더를 붙인다. UTF-8과 CP949 한글 이름을 지원하며
다른 인코딩은 `--encoding`으로 지정한다. 경로 탈출/심볼릭 링크/암호화/4 GiB 초과는 중단한다.
중첩 ZIP은 자동 재귀 해제하지 않고 `nested_archives_not_expanded`에 표시한다.
같은 목적지의 다른 내용이나 파일/폴더 충돌은 사전 점검에서 전체 쓰기를 차단한다.

콘솔이 가리키는 `LOGS/internal-zip-*.json`에서 `files`의 목적지, `conflicts`,
`exact_duplicates`, `similar_names_different_contents`를 확인한다. 매 실행은 새 보고서를 쓴다.
SHA-256이 같은 파일만 정확한 중복이다. `(2)` 등 복사 접미사는 같은 폴더·형식·해시의
동료 파일이 있을 때만 입력 묶음에 합친다. `(170817)` 같은 날짜는 지우지 않는다.
다른 내용의 복사본은 별도 입력으로 유지한다. 같은 문서가 여러 폴더에 있어도 모든 별칭과
폴더 경로를 남긴다. 출처/형식 권한이 충돌하는 동일 내용은 임의로 합치지 않는다.
실제 파일 삭제나 백업 이동은 하지 않는다. 재실행은 동일 파일을 REUSE한다.

## 구조화 실행

사진의 외규 선택 목록이 `CATALOG/BUILD_SCOPE.json`에 설정되어 있어도
`--only-internal`은 그 목록과 독립적으로 `RAW/internal`의 모든 지원 형식을 선택한다.
`--only-internal-pdf`는 원본 우선 선택을 우회하는 PDF 전용 진단 옵션이므로 이번 작업에 쓰지 않는다.

```bash
bash 06_TOOLS/COMMANDS/genos_data_stages.sh --run-id native-internal-001 --only-internal --check-only
bash 06_TOOLS/COMMANDS/genos_data_stages.sh --run-id native-internal-001 --only-internal --stage structure --execute
```

`LOGS/native-internal-001`의 inventory, `doc-status.html`, `structure-images.html`을 확인한다.
모든 내부 파일의 실제 중복 판단은 이 환경의 해시 보고서로 한다. 사진의 파일 크기만으로 판단하지 않는다.
실패한 개별 문서는 상태표에 남고, 완료 구조는 같은 run ID로 재사용한다.
입력/파일명/폴더/연결 PDF/코드가 바뀌면 새 run ID를 사용한다. 이전 세대는 덮어쓰지 않는다.

기존 용어집·지식 묶음과 모델 설정이 준비된 경우 구조화 이후 통합 용어 검토·색인까지:

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id native-internal-001 --only-internal --execute
```

외규 등 기존 문서를 유지하려면 명시적으로 `--base-generation <기존 세대 경로>`를 붙인다.
완료 산출물은 DRAFT이며 MAIN/CURRENT·GENOS 서비스 배포는 자동 변경하지 않는다.
구조화만 완료했다고 용어 검토/문서 연결/RAG 색인까지 완료된 것으로 보고하지 않는다.

## 이름과 폴더를 RAG로 전달

`document_metadata`에 원래 파일명, 상대 경로, 순서가 있는 폴더 목록, 표시 이름,
중복 별칭, 전체 표현본 해시와 PDF 참조를 저장한다. 이 정보는 result.json과 source.sqlite의
문서 JSON을 거쳐 통합 원문 세대에 전달된다. RAG ReverseMatcher가 문서명뿐 아니라
원본 파일명·폴더명·별칭을 문서 탐색에 쓰고, 탐색 결과에 상대 경로를 반환한다.
모델에 전달하는 탐색 메타데이터에는 내부 절대 경로/참고 PDF 바이너리를 싣지 않는다.
폴더명 자체를 법률 내용이나 상하위 법적 권한의 근거로 삼지는 않는다.
