# MAIN PDF 구간별 구조화 틀·bbox 검수

2026-09-14 작업 코드: `genos-recipe-v22-main-regions`.
사용자의 MAIN 배선 지시로 ADR0396의 구간별 틀 프로세스를 공용 입력 경로에 연결했다.
ADR0397의 모델 비교 기록과 완료 후보는 그대로 보존했다. 신규 품질 실험이나
Accepted arm 승격, 활성 RAG 데이터/CURRENT 변경, GENOS 배포를 수행한 것은 아니다.

## 실행 경로와 소비자

`build-data-stages`의 입력은 논리 data root의 내규 `PDF/internal`(PDF만)과
외규 `RAW/<source>`다. `build-all`도 같은 선택을 사용한다. 내규 원본·ZIP은
`RAW/internal`에 보존하며 이 명령이 자동 변환하거나 대체 입력으로 선택하지 않는다.
PDF 경로 전환 후에는 새 run-id로 시작하고 같은 명령으로 재개한다. 이전 구조화·완료
세대는 보존하며 코드/입력 지문이 달라진 결과는 새 구조화 키로 저장한다.
기존 RAW를 직접 지정하는 레거시 실행기와 API 업로드의 입력 계약은 별도다.

```text
pipeline.py build-all
  → 용어집 review complete → build-data-stages --stage all
pipeline.py build-data-stages --stage structure|all
  → genos_stages.structure → genos_build.ingest_files
업로드·재해석 API / service.py PIPELINE_*의 공용 ingest 경로
  → ingest.interpret_doc
  → 원본 PDF이고 VLM 활성 상태이면 recipe_runtime.revise_pdf
      전체 파싱·원문 좌표 보존
      → 전체 문서에 걸친 연속 청크 샘플링 + 원본 지면
      → 형식 전환 구간 감지
      → 형식별 계층·번호 문법 생성
      → 구간별 실행·원문 좌표를 유지한 합침
      → 프론트 뷰어와 같은 bbox 결과로 VLM 검수
      → 틀/구간 변경 시 재구축·이전 승인 무효화·재검수
  → 기존 viewer result.json / meta.json / structure-receipt.json
  → authoring-source.sqlite → 문서–용어 연결 → 의미 추출·검토 → 임베딩/DRAFT
```

`PIPELINE.json.authorities.document_ingestion`은 이 실행 계약을 가리킨다.
기존 CLI와 API의 공용 ingestion 함수를 교체했으며 별도 병렬 실행기를 추가하지 않았다.
engine-host `legal-authoring`의 extract/admit/index는 아직 MIGRATION_REQUIRED다.
이번 배선은 MAIN의 실제 CLI 문서 구축 경로이며 그 미연결 profile을 READY로 바꾸지 않는다.

## 모델이 만드는 것

문서 시작 몇 페이지만 보지 않는다. 전체 블록의 전환 단서와 시작·중간·끝, 표기·배치
유형을 대표하는 연속 청크를 사용한다. 모델은 본문·부칙·별표·서식처럼 형식이 달라지는
경계를 원문 근거로 제안한다. 같은 형식의 여러 구간은 한 틀을 재사용한다.

틀에는 관측된 표기 계열마다 다음 규칙을 둔다.

- `parent_family`: 바로 위 표기 계열. 예: `kr_article → kr_장` 또는 `1. → 가.`.
- `heading_position`: 행 시작, 상위 제목 직후, 원문 스타일 제목 중 선택.
- `sequence`: 연속 번호 / 증가 번호 / 순서 제약 없음.
- `reset_scope`: 상위 제목별 또는 해당 구간 전체에서 번호를 센다.

구간 경계에서 번호 상태를 새로 시작하므로 여러 부칙의 제1조를 한 수열로 강제하지 않는다.
같은 `1.`도 본문과 서식에서 서로 다른 상위 계열을 가질 수 있다. 각 구간은 원문 블록을
빠짐없이 한 번씩 덮고 부모·본문 span이 구간 밖으로 새지 않는다. 원문·표·좌표는 유지한다.

검수 모델은 `template_changes`로 해당 형식을 공유하는 모든 구간의 규칙을 수정하거나,
`resegment`로 형식 경계를 다시 탐지하도록 요청한다. 개별 후보 ID 수정, 임의 Python·정규식
생성, 원문 덮어쓰기는 실행 인터페이스에 없다. singleton 제목도 명시한 계층대로 실행한다.

## 검수·후속 단계·캐시

원본 페이지와 실제 `viewer.payload` bbox를 그린 이미지를 함께 제공한다.
`reviewed_state_id`는 원문·구조·구간 틀·페이지·실제 이미지의 해시에 결속된다.
틀/경계를 바꾸면 이전 창의 승인을 무효화하고 다시 검수한다. 근거 없는 승인, 순환/무변경
수정, 원문 부족, 호출/교정/재분할 한도 소진은 `NeedsReview`로 중단하고 기록을 보존한다.

- `visual_approved`: 모든 페이지의 이미지 검수 완료. 의미 정확성 승인이 아니다.
- `visual_sampled`: 선택한 페이지 검수 완료. 미검수 페이지를 명시한다.
- 실패/보류: 성공 태그를 저장하지 않고 해당 문서의 의미 추출·임베딩을 차단한다.

`meta.json`과 `result.json`에 같은 `recipe_review`를 저장한다. 이 기록에는 process/runtime,
모델, 구간 수, 틀 수, run ID, 호출 수, 검수 범위가 있다. `genos_stages` 문서별 보고서도 이를
전달한다. metadata/result 검수 기록이 다르거나 실패 상태이면 admission에서 거부한다.
한 문서의 실패 때문에 다른 정상 문서까지 중단하지 않는다.

원문·블록·구조 코드·모델 설정·틀·검수 범위와 재구축 트리가 같을 때만 캐시를 재사용한다.
재사용에도 모델/검수 메타데이터를 유지하며 모델 호출은 0회다. 이번 runtime 버전과 파일
해시 변경으로 이전 구조화 캐시/승인 태그를 새 프로세스의 성공으로 재사용하지 않는다.
이미 완료된 문서·릴리스는 덮어쓰지 않고 새 구조화 키로 생성한다.

## 설정과 실행

MAIN/GENOS는 기존 내부 VLM 설정을 사용한다. Gemini 실험용 API 키나 research candidate를
제품 경로에서 읽지 않는다. 더 나은 내부 VLM을 사용할 때는 기존 `GENOS_LLM_MODEL` 또는
선택한 `GENOS_LLM_PROFILE`의 모델/서빙 ID/키를 일치시킨다. 다른 모델로 자동 fallback하지 않는다.
현재 Codex 환경에서는 GENOS 접속·배포·내부 모델 품질 확인을 할 수 없다.

```bash
export LLM_BACKEND=genos
export STRUCTURE_RECIPE_VLM=on
export STRUCTURE_RECIPE_REVIEW_MODE=adaptive
# 내부 모델이 지원하는 경우 출력 예산을 늘릴 수 있다.
export STRUCTURE_RECIPE_MAX_TOKENS=16384

# 데이터 입력 목록 확인 (모델 호출 없음)
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id region-main-001 --check-only
# 구조화까지만 실행하고 문서별 검수 기록 확인
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id region-main-001 --stage structure --execute
# 검토된 용어집 완료부터 문서 DRAFT까지 기존 MAIN 명령
.venv/bin/python 06_TOOLS/pipeline.py build-all --run-id region-main-001 --execute
```

`build-all`은 용어집 검토 미완료 시 문서 단계로 넘어가지 않는다. 구체적인 모델·키 연결은
[GENOS.md](../../../../GENOS.md), 데이터 경로는 [4단계 가이드](GENOS_FOUR_STAGE.md)를 따른다.

| 설정 | 기본값 / 의미 |
|---|---|
| STRUCTURE_RECIPE_VLM | auto: LLM_BACKEND=genos일 때 활성; on/off 명시 가능 |
| STRUCTURE_RECIPE_REVIEW_MODE | adaptive: 유형·위험 표본 검수; full: 같은 프로세스로 모든 페이지를 창 단위 검수 |
| STRUCTURE_RECIPE_MAX_PAGES | 6; 창의 원본 페이지 수. bbox 검수에는 원본+오버레이 이미지 두 장씩 제공 |
| STRUCTURE_RECIPE_MAX_DOCUMENT_PAGES | 2000 |
| STRUCTURE_RECIPE_MAX_CHARS | 160000; 요청 문맥 상한 |
| STRUCTURE_RECIPE_MAX_TOKENS | 4096; 최대16384 |
| STRUCTURE_RECIPE_MAX_CALLS | 64; 문서별 논리 호출 상한, 전송 재시도는 별도 기록 |
| STRUCTURE_RECIPE_MAX_CORRECTIONS | 6; 형식 경계 재탐지는 최대2회 |
| STRUCTURE_RECIPE_TAGS | 기본 structure store의 상위 디렉터리/structure-recipes.json |

로그는 구조 store 상위의 `structure-recipe-runs/<run_id>`에 저장된다. 원문 청크 계획,
구간·틀·실제 트리·bbox 이미지·모델 응답·실패 원인을 연결해서 확인할 수 있다.
MAIN의 문서별 상태/재개 명령은 기존 `01_DATA/LOGS/<run-id>`를 사용한다.

`build-all --execute → build-data-stages --stage all → ingestion`에서도 VLM 이벤트를
문서별 진행 표시로 직접 전달한다. 형식 구간 감지, 틀 생성 n/m, 구조 적용 회차,
bbox 검수 n/m창·페이지, 수정 횟수·이전 승인 해제, 모델 호출·재시도·응답 시간·사용량,
검수 완료/보류를 표시한다. `progress.log`에는 상태 변경 요약, `detail.log`에는
`[STRUCTURE VLM]` 구조화 이벤트, `current.json`에는 현재 단계와 `vlm_run_id`가 남는다.
용어 검토가 완료되지 않아 build-all이 앞 단계에서 멈추거나 입력 점검만 실행하면
VLM 로그는 발생하지 않는다. 구조화 캐시 재사용은 별도 CACHE 상태로 표시한다.

대화형 터미널에서는 줄을 계속 추가하지 않고 누적 현황판을 같은 위치에서 갱신한다.
이번 실행의 구조화·의미 추출·임베딩 완료/실패 건수, 현재 문서의 단계별 상태,
구간·틀·검수·수정·모델별 최신 상태와 최근 결과 두 건을 유지한다. 화면 높이에 맞춰
표시 행 수를 제한한다. 터미널 갱신을 지원하지 않는 출력/파이프에서는 문서 단계
시작·종료 요약만 출력한다. 중간 이벤트는 계속 progress.log/detail.log에 기록한다.
`current.json`은 현재 문서의 누적 단계·VLM 상태를, `progress-summary.json`은 이번
호출에서 처리한 문서별 단계 결과를 저장한다. 후자는 단계 종료 시 갱신하며 이전
호출의 결과와 합산하지 않는다. 전체 재개 이력의 정본은 기존 문서 상태표/ledger다.
전용 GENOS 로거도 구축 CLI 실행 동안 detail.log로 연결해 현황판에 끼어들지 않게 한다.

개별 VLM 실행의 `events.jsonl`은 상세 이벤트 전체를 보존한다. 컨테이너 로그는
파일 저장·페이지 렌더링·단계 시작/종료·대기 이벤트를 DEBUG로, 재시도를 WARNING,
단계 실패·검수 보류를 ERROR로 구분한다. 기본 INFO에서도 구간·틀·검수 진행과 모델
호출 정보는 확인할 수 있다. DEBUG 전환은 기존 `GENOS_LOG_LEVEL=DEBUG`를 사용한다.
진행 이벤트에는 원문·프롬프트·모델 응답을 넣지 않는다. 해당 내용은 기존 접근 제한
실행 디렉터리의 검수 근거로 보존하며 이 변경은 자동 삭제나 보관 정책을 추가하지 않는다.

## 지원 범위와 남은 한계

XML/HTML 전용 파서, 명시적인 형식 바인딩과 DOCX 스타일 경로가 우선한다.
HWP/DOCX의 합성 PDF는 원본 지면 증거가 아니므로 VLM 대상에서 제외한다.
원본 또는 검증된 변환 PDF를 별도 PDF로 입력하면 이 경로를 사용한다.
OCR 필요 페이지는 기존 Docling·한국어 RapidOCR 자산 설정을 요구하며 텍스트가 없으면 보류한다.

ADR0397에서 Flash는 KRX 본문 장·조 연결을17/17로 개선하고 누락 항을 발견했다. 그러나
블록 중간의 `②` 분리와 날짜 조각의 잘못된 번호 인식을 복구하는 기능은 아직 없다.
`resegment`는 형식 구간을 나누며 원문 블록을 분할·재결합하는 명령이 아니다.
VLM 승인과 문서 전체 정확도는 구분하고 결과는 DRAFT로 후속 검토에 넘긴다.

## 검증·롤백·이력

합성 원문과 가짜 내부 모델 응답으로 공용 ingestion→구간 틀→bbox→저장/재사용,
실패 문서의 후속 차단, 기존 XML 문서의 단계별 의미 추출·임베딩 연결을 검사한다.
이는 실제 내부 데이터 품질·현장 배포 검증을 대신하지 않는다.

`STRUCTURE_RECIPE_VLM=off`는 기존 휴리스틱 구조화로 되돌린다. 모델 설정/코드 복원은 새
구조화 키를 사용한다. 이전 태그나 CURRENT를 수동으로 덮어쓰지 않는다.
변경 전 파일·해시와 도입 기록은 [배선 감사](../../../../09_ARTIFACTS/AUDITS/20260914-region-main-wiring/README.md)에 있다.

이전 배선/검수 이력: ADR0358, ADR0370~0381. 구간 틀 원본: [ADR0396](../../../../04_EXPERIMENTS/ADR/ADR-0396-pdf-region-explicit-ladder/README.md).
모델 비교: [ADR0397](../../../../04_EXPERIMENTS/ADR/ADR-0397-pdf-model-tier-benchmark/MODEL_COMPARISON.md).
