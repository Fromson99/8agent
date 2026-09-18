# GENOS PDF 파싱 → 원문·용어 적재

## 2026-09-16 현행: 청크와 구조 응답의 두 경로

현장 v4 설치 후 `GENOS chunk page range differs from source PDF`를 추가 확인했다.
공개 attachment_processor의 compose_vectors는 `n_page=max(loader의 0-based page)`로
계산한 뒤 `i_page/e_page`에만 1을 더한다. 기존 수신기가 `n_page==실제 PDF 쪽수`를
강제한 것이 호환 오류였다. assembly v2는 실제 PDF 쪽수를 정본으로 사용하고,
`n_page`가 실제 쪽수 또는 마지막 청크 시작 페이지의 0-based 값인 경우를 구분해 기록한다.
페이지 번호 자체는 이동하지 않으며 범위 초과·서로 다른 n_page·누락 청크 검사는 유지한다.
누락된 빈 페이지와 본문 누락은 후속 전체 페이지/VLM 검사로 구분한다. 수정 관련 46개
모의 검사와 패치 적용·반복·복구·다른 코드 덮어쓰기 거부 검사를 통과했다. 현장 재실행은 미확인이다.

현장 사진에서 기존 전처리기가 `code=0`, `data=[11개 청크]`를 반환한 것을 확인했다.
현재 수신기는 `GENOS_PREPROCESSOR_RESPONSE_MODE=auto`(기본), `chunks`, `docling`을 지원한다.
아래 2026-09-15의 Docling 전용/청크 거부 설명은 이전 구현 기록이며 이 절이 우선한다.

1. **기존 서버**: 모든 청크의 `i_chunk_on_doc`를 정렬하고 0..N-1, `n_chunk_of_doc`,
   `i_page/e_page/n_page`를 원본 PDF와 검사한다. 원문 바이트를 보존한 JSON 응답과
   `assembled-input.json`에 전체 결합 텍스트·청크별 문자 범위·원문 메타데이터를 남긴다.
   중복/겹침을 임의 삭제하지 않고 청크 사이에 명시적 개행을 넣는다. 실제 행별 요소를
   공용 구조화 엔진으로 전달한다. 청크 경계가 곧 의미 마디라는 가정은 하지 않는다.
2. **구조 서버**: `data.document`를 그대로 복원한다. 별도 수정본은 Docling 트리와
   `full_text`, 읽기 순서별 self_ref/문자 범위, 원본·서버 설정·기반 모듈 해시를 반환한다.
   [서버 코드와 설치 계약](../../../../08_DEPLOYMENT/GENOS/preprocessor/README.md)을 따른다.
3. **공통 후속**: 전체 파싱 텍스트 → 구간/틀 생성 → 전체 적용 → PDF VLM 틀 검수·보정
   → 최종 틀로 재구조화 → source.sqlite → 용어 연결·색인. 전체 텍스트는 생략하지 않는다.
   이미지 샘플링은 별개이며 청크 입력은 원본 PDF **모든 페이지** 검수를 강제한다.
   최종 `final-template.json`, `final-restructured-tree.json`을 recipe journal에 보존한다.

청크 입력의 `STRUCTURE_RECIPE_VLM=off`는 후속 적재를 중단한다. 셀·좌표가 없다는
사실은 parser_evidence/검수 coverage에 남으며, 틀 승인으로 좌표·표 복원까지 승인하지 않는다.
청크의 다중 페이지 범위는 정확한 텍스트–페이지 매핑이 없으므로 현재 보류한다. 페이지별
청크 또는 구조 응답 서버를 사용한다. 누락/중복 인덱스·빈 텍스트도 성공 처리하지 않는다.
전체 텍스트가 문맥 예산을 넘으면 잘라서 통과시키지 않고 보류한다. 기본 요청 상한 160,000자,
설정 최대 500,000자와 별개로 구간 생성 입력은 180,000자 상한이다. 긴 문서 분할 처리는 후속 과제다.

현장 내규/모델은 외부로 호출하지 않았다. 합성 PDF·모의 HTTP/VLM으로 연결 검증했고
실제 OCR·표·구조 정확도, 현장 모델 예산, 서버 의존성은 GENOS에서 확인해야 한다.

2026-09-16 로컬 검증: 전처리기/새 서버/틀 영역·페이지·runtime/원문 세대/admission/
코드 교체 계약 검사 **156개 통과**, 기존 Docling annotations deprecation 경고 1개.
청크 → 틀의 장·조 부모 수정 → 이전 승인 무효화 → 재검수 → 최종 재구조화 → 색인까지
모의 내부 모델로 확인했다. 이는 품질 비교 실험이나 GENOS 배포 성공이 아니다.

## 이전 Docling 전용 구현 기록

2026-09-15 사용자 지시로 GENOS PDF 파싱을 전처리기에 위임했다.
코드스페이스는 Docling JSON을 복원해 기존 구조화·용어 색인에 전달한다.
현장 전처리기 187의 이 계약 지원·모델 상태·실제 문서 처리 성공은 아직 미확인이다.
이 변경은 작업 코드이며 기존 전달 ZIP, GENOS 설치본, CURRENT, MAIN을 바꾸지 않는다.

## 실행 순서와 입력·출력

```text
pipeline.py build-all → 용어집 검토 → build-data-stages
pipeline.py build-data-stages --stage all
  → RAW/internal + 외규 RAW/<source> 목록·원문 해시
  → PDF는 공유 NFS의 요청별 source.pdf 사본으로 준비
  → 선택한 GENOS 전처리기의 POST /run (또는 명시한 /parser)
  → data.document: DoclingDocument JSON
  → 기존 parse_adapter: 읽기 순서·표 셀·페이지·bbox
  → 기존 원문 구조화 및 설정된 PDF VLM 검수
  → STRUCTURE/<지문>/source.sqlite
  → 선택 용어집의 용어 출현·정의·명시 참조 색인
  → TERM/<run-id>/<문서 ID>/generation (DRAFT)
```

`genos_build.execute`도 같은 `genos_stages.execute`를 사용한다. 이 실행기는 PDF에
`preprocessor`를 기본 선택하며, 설정 누락은 실행 전 오류다. XML/HTML 전용 파서와
원래 Office 형식 경로는 유지한다. 내규 RAW의 Office/ZIP을 PDF로 바꾸는 일은 별도 준비 단계다.
직접 API/공용 `parse_adapter` 사용 시에도 `GENOS_PDF_PARSER=preprocessor`를 지정하면
같은 클라이언트를 사용한다. 독자 파서를 가진 과거 실행기에 자동 적용됐다고 간주하지 않는다.

코드스페이스의 PDF 경로에서 로컬 Docling 모델 초기화·다운로드·RapidOCR 모델 로딩은
하지 않는다. JSON 복원용 `docling-core`, 기존 PDF 좌표·글꼴 처리용 PyMuPDF와 HTTP
클라이언트 httpx는 필요하다. 기존 requirements-pipeline의 Docling 설치 여부와 무관하게
이 경로의 추론은 서버에서 수행한다. 외부/로컬 개발 파서는 원래 동작을 유지한다.

## 코드스페이스 환경 설정

`.env.genos.example`은 복사용 안내다. 실제 키를 파일이나 Git에 쓰지 말고 코드스페이스의
환경 설정에 등록한다. 다음 프로세스부터 적용되며 실행 중 프로세스는 재시작한다.

| 환경변수 | 값·의미 |
|---|---|
| `GENOS_PDF_PARSER` | `preprocessor` (GENOS 단계 실행기의 기본값). `local`은 명시적 원복 |
| `GENOS_PREPROCESSOR_ID` | 사용할 **파싱용 전처리기 ID**. 숫자 ID로 `http://preprocessor-{ID}:8080/run` 생성 |
| `GENOS_PREPROCESSOR_URL` | 선택사항. 지정하면 ID보다 우선. 서비스 기본 URL 또는 `/run`, `/parser`로 끝나는 전체 URL |
| `GENOS_PREPROCESSOR_REVISION` | 선택사항. 배포 코드·이미지·모델·설정 조합의 식별자. 변경 시 반드시 갱신 |
| `GENOS_PREPROCESSOR_SHARED_ROOT` | 필수. 코드스페이스와 전처리기가 공유하는 **기존** 디렉터리의 코드스페이스 경로 |
| `GENOS_PREPROCESSOR_REMOTE_ROOT` | 같은 디렉터리가 전처리기에서 다른 경로일 때 지정. 공란이면 SHARED_ROOT와 동일 |
| `GENOS_PREPROCESSOR_TIMEOUT` | 요청 제한 초, 기본 900 (1~7200) |
| `GENOS_PREPROCESSOR_MAX_RESPONSE_MB` | JSON 응답 상한 MiB, 기본 128 (1~512) |
| `GENOS_PREPROCESSOR_API_KEY` | 인증이 필요한 경우만 비밀 값. Bearer 헤더로 전송 |

ID는 전처리기 서비스 선택값이다. 해당 전처리기 안에서 사용하는 레이아웃·OCR·표 모델과
모델서빙 ID는 **전처리기 자체 설정**에서 관리한다. 특정 전처리기 ID나 모델서빙 ID를
우리 코드에 고정하지 않는다. `REVISION`은 운영자가 제공한 결속값이며 서버가 자동으로
검증해 돌려준 모델 버전이라고 보고하지 않는다.

공유 루트는 실제 마운트 대응을 확인한 경로여야 한다. 예시 경로
`/nfs-root/diamo/8-agent/parser-input`을 자동 생성하거나 공유된 것으로 가정하지 않는다.
요청마다 새 하위 디렉터리(2770)와 원본과 동일한 PDF 사본(0640)을 만든다.
두 컨테이너 계정은 같은 그룹으로 읽고 산출물을 쓸 수 있어야 하며, 필요하면 공유 루트의 setgid 그룹을
관리자가 지정한다. 원문 해시는 복사 전후·응답 수신 후 확인한다.

## 전처리기 측 필수 계약

공개 GENOS 구현의 **`parser_processor.py`**를 사용하고 서버 YAML에서 다음을 선택한다.
기존 레이아웃·OCR·표 모델 연결 설정은 현장에 맞게 유지한다.

```yaml
output:
  format: docling
enrichment: []
```

원문 적재용 설정에서는 생성 목차·메타데이터 추출·표 재작성·요약·이미지 설명 등
enrichment를 활성화하지 않는다. 파싱과 OCR은 관측값이며 정답 승인이 아니다.
클라이언트도 이미지/표 설명·요약 런타임 플래그를 0으로 보내지만 이것만으로 서버 YAML의
모든 enrichment를 끌 수 있는 것은 아니다. 서버 설정 확인이 필요하다.

요청은 파일 업로드가 아니라 **서버가 읽는 파일 경로**를 전달한다.

```json
{"file_path":"/server/shared/<request-id>/source.pdf","params":{"img_desc":0,"chart_desc":0,"doc_summary":0,"table_desc":0,"table_refine":0,"table_text_desc":0}}
```

필수 응답:

```text
{"code": 0, "data": {"document": <DoclingDocument의 model_dump(mode="json")>}}
```

`data.document`를 docling-core로 검증하고 원본 PDF와 페이지 집합을 대조한다.
표의 논리 셀·병합 범위·원래 좌표계와 읽기 순서는 기존 어댑터로 전달한다.
서버 전용 이미지 경로/URL은 별도 다운로드하지 않는다. 원본 응답에는 보존하되 실행 중
그림 이미지 참조에서는 제외하고, 원본 PDF의 해당 좌표를 렌더해 픽셀을 복원한다.
좌표가 없거나 유효하지 않아 복원할 수 없으면 미확인 경고를 남긴다. 인라인 이미지는 유지한다.
다른 컨테이너의 이미지 경로를 코드스페이스 로컬 파일로 해석하지 않는다.

첨부용/변환용/적재용 전처리기의 기본 **청크 목록**이나 텍스트 응답은 이 계약과 다르다.
호환되지 않으면 `data.document` 오류로 중단하며, 로컬 파서로 재시도하거나 임의의 표 구조를
만들지 않는다. 현장 187이 첨부용이면 파싱용으로 구성한 서비스의 ID/URL을 환경변수에 넣는다.
공개 소스의 `/parser`는 설치 전처리기가 `IS_PARSER`를 제공할 때만 동작한다.

## 실행·재개·확인

환경 설정과 서버 계약을 준비한 뒤, 프로젝트 루트의 Linux 터미널에서:

```bash
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id genos-parser-001 --check-only
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id genos-parser-001 --stage structure --execute
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id genos-parser-001 --stage index --execute
```

structure에는 용어집이 필요하지 않다. index/all에만 선택 용어집이 필요하다. 한 번에 처리할 때는 `--stage all`을 사용한다.
`--check-only`는 입력 목록 검사이며 API/파싱 성공 검사가 아니다.

- `STRUCTURE/<지문>/preprocessor/<request-id>/`: 요청, 원본 응답, 응답 해시·상태·시간 영수증.
- `structure/<문서 ID>/parse.json`: 정규화 요소, 파서 지문, 응답 해시.
- `result.json`과 원문 SQLite: 파싱 출처와 응답 해시를 후속 적재에 보존.
- `structure-receipt.json`: 전체 구조화 폴더 파일 해시. 완료 캐시 변조 시 재사용 거부.
- `TERM/<run>/<문서 ID>/generation`: 원문·용어 색인 DRAFT. 자동 활성화 없음.

같은 원문·코드·서버 URL·배포 리비전·설정일 때 완료 파싱을 재사용한다. 서버 설정/모델을
바꾸면 `REVISION`과 run ID를 새로 지정한다. API 키는 지문/요청/영수증에 저장하지 않는다.
`llm_calls=0`은 원문·용어 색인 단계 범위이며 전처리기 내부 모델 호출 수는 응답에 없어
`preprocessor_model_calls=null`로 표시한다. 별도 PDF VLM 검수는 기존 설정을 따른다.

시간 초과·접속 실패·비정상 응답은 자동 재시도하지 않는다. 공유 PDF와 오류 기록을 남긴다.
서버가 계속 처리 중인지 현장에서 확인한 뒤 같은 명령을 명시적으로 재실행한다.
처리 중일 수 있는 공유 요청 폴더는 삭제하지 않는다. 내부 원문/응답은 GENOS 안에 보존한다.

## 원복과 검증 범위

`GENOS_PDF_PARSER=local`로 바꾸고 새 run ID로 실행하면 기존 로컬 Docling 경로다.
그때는 코드스페이스 모델 파일과 필요 시 OCR 자원이 다시 필요하다. 이전 완료 데이터와
파싱 영수증은 보존한다. 기존 서버 설정을 수정했다면 해당 전처리기의 이전 리비전으로
별도 복구한다. 이 코드 변경은 서버 배포나 MAIN 승격을 수행하지 않는다.

외부 WSL 검증은 모의 HTTP 응답의 연결·셀/좌표 보존·실패 차단·파싱 캐시·SQLite·용어
색인까지다. 실제 내부 문서 품질, 현장 Python 3.11 및 docling-core 버전 호환성, 공유 그룹
권한, 전처리기 187의 배포 상태는 현장 검증 항목이다.

확인 결과: `test_genos_preprocessor_ingestion.py`, `test_term_source_generation.py`,
`test_genos_admission.py` 합계 **80개 통과**. 기존 Docling `annotations` 사용에 대한
deprecation 경고 1개가 있었다. 변경 Python 파일의 3.11 문법과 PIPELINE 문서 연결도 확인했다.
기존 `test_genos_internal_pdf_input.py`는 이미 폐기된 `genos_staged.STAGES`를 간접 import해
수집되지 않는다(이번 변경 전 HEAD도 같은 상태). 이번 원문·용어 E2E 검사는 현행 계약 테스트로 수행했다.

## 근거와 코드

- [GENOS 공개 parser_processor (고정 리비전)](https://github.com/genonai/doc_parser_code_serving/blob/aa610c3db24aaa02c65e953279f1a60d014babaf/genon/preprocessor/facade/parser_processor.py): `_build_docling_response`의 `output.format=docling`.
- [공개 API](https://github.com/genonai/doc_parser_code_serving/blob/aa610c3db24aaa02c65e953279f1a60d014babaf/genon/preprocessor/src/main.py): `/run`, 조건부 `/parser`.
- 클라이언트: `lawrag.core.genos_preprocessor`; 연결: `genos_stages.structure → parse_adapter.parse_pdf`.
- 구조화 이후 선택적 VLM: [GENOS_RECIPE_VLM.md](GENOS_RECIPE_VLM.md).
- 현행 원문·용어 계약: [DATA_MODEL.md](../../../00_SYSTEM/DATA_MODEL.md).

REVISION 미설정 시 같은 run ID 안에서만 구조화 캐시를 재사용한다. 서버 설정 변경 시 새 run ID를 사용한다. index 단계는 완료 structure-selection.json을 소비하며 전처리기 설정을 읽지 않는다. 최신 병렬 실행·RAW 입력 계약은 [실행 안내](GENOS_FOUR_STAGE.md)를 따른다.
