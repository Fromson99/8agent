# GENOS 폴더 → 스키마 추출·재추출 → 임베딩 → 적재

이 명령은 과거 LLM 생성물을 복사하지 않습니다. 지정한 원문 폴더를 재귀적으로 읽어
현재 `00_SYSTEM/LEGAL_SCHEMA.json`이 고정한 스키마로 새 DRAFT 세대를 만듭니다.
기존 모델 URL·키·HTTP 전송 코드는 유지합니다. Python 3.11 이상과 기존 GENOS 의존성이 필요합니다.

XML 중심의 최소 서빙 환경과 달리 DOCX/PDF 등의 기존 파서는 `requirements-pipeline.txt`가
필요합니다(특히 `docling==2.117.0`). 파서 패키지가 없으면 임의의 간이 청킹으로 대체하지 않고
필요 패키지를 알려주며 멈춥니다. 사내 환경에서는 승인된 패키지 미러/오프라인 wheel로
이 의존성을 준비하세요. 설치 파일이 대형 OCR/로컬 모델 패키지를 자동 다운로드하지는 않습니다.

## 연결한 로직

`원문 목록/해시 동결 → 파일 형식/등록 태그에 따른 구조화 → 조문 단위 작업 큐 →
LLM 스키마 추출 → JSON 스키마·원문 좌표·전체 범위 검증 → LLM 검토 →
실패 피드백을 넣어 재추출 → 임베딩 배치 → 원문/스키마/벡터 적재 → 재열기 검증`

예전 간이 `e2e`는 원문 구절 추출 데모였습니다. 새 `build`는 ADR-0252의 동결된
source-ids rev-001 authoring 큐를 명시적으로 재사용합니다. 이 큐가 개념·언급·의미절·규칙·
단서·관계·근거의 실제 SemanticGraph를 만들고 검토/재추출합니다. 검색용 인용구만 만드는
대체 스키마가 아닙니다. 실험 코드의 자동 탐색, 연구 성능 결과의 MAIN 승격은 하지 않습니다.

LLM이 선택하는 근거 ID는 코드가 만든 원문 구간 ID입니다. 원문/좌표/해시는 코드가 결속합니다.
미해결 청크·잘못된 스키마·원문 불일치는 성공으로 처리하지 않습니다. 검토자는 같은 모델의
별도 호출이므로 사람의 정확성 승인과 같지 않습니다. 출력은 `DRAFT`, `production_approved=false`입니다.

## 폴더

```text
/home/genos/DEV/
  00_SYSTEM/  02_BACKEND/  06_TOOLS/ ...     코드 (기존 구조)
  UPLOADS/                                 내규 원본을 올릴 폴더
    위험관리규정.docx
    영업/규정.pdf
  EXTERNAL_RAW/                            외규 원본 (이미 둔 다른 경로도 가능)
  GENOS_DATA/builds/rules-v1/               새 실행 결과 (--build-dir)
  TRANSFER/                                ZIP/설치 스크립트만
```

`UPLOADS`에는 원본만 넣습니다. 결과 폴더/ZIP/Git 저장소 전체를 입력 폴더로 지정하지 마세요.
원본과 결과 폴더는 서로 안에 들어갈 수 없습니다. 기존 원본·데이터·Git을 지울 필요가 없습니다.
코드 서빙에서도 읽을 영속 볼륨을 사용해야 합니다. 이 명령 자체는 마운트/원격 저장소 인증을
만들지 않으며, S3/Git URL이 아니라 GENOS에 마운트된 실제 디렉터리를 받습니다.

## 실행 — 내규만

먼저 `genos-schema-build-20260909.zip`과 설치 스크립트 첨부를 `DEV/TRANSFER`에 놓고
아래처럼 패치합니다. `unzip`은 필요 없습니다. 현장 수정 파일을 발견하면 덮어쓰지 않고 멈추며,
알려진 기존 파일은 `runtime/patch-backups`에 백업합니다.

```bash
cd /home/genos/DEV/TRANSFER
base64 -d genos_apply_schema_build.sh.b64.txt > genos_apply_schema_build.sh
bash genos_apply_schema_build.sh --install-only
```

모델 URL/키/서빙 ID는 연결에 성공한 코드스페이스 환경변수 그대로 사용합니다.
`GENOS_LLM_REVISION`에는 현재 LLM 배포 리비전(또는 운영자가 관리하는 불변 배포 버전)을
설정합니다. API model ID와 serving ID는 자동 모델 조회 결과/게이트웨이 경로로 구분되며,
임의로 226을 요청 본문의 model 값에 넣지 않습니다.

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_build.sh \
  --input-root /home/genos/DEV/UPLOADS \
  --source internal \
  --model-revision '현재-LLM-배포-리비전으로-교체' \
  --build-dir /home/genos/DEV/GENOS_DATA/builds/rules-v1 \
  --embed-batch-size 64
```

`GENOS_INPUT_ROOT`(또는 `GENOS_UPLOAD_ROOT`)와 `GENOS_LLM_REVISION`을 환경변수로
넣었다면 `--input-root`, `--model-revision`은 생략할 수 있습니다.

외규도 함께 같은 세대에 넣으려면 위 명령에 다음을 추가합니다.

```bash
  --external-root /home/genos/DEV/EXTERNAL_RAW
```

외규만 처리하려면 `--input-root 기존외규원본경로 --source external`을 씁니다.
외규/내규의 차이는 원문 위치·출처 표시이며, 추출 이후 파이프라인은 같습니다.
기존 수집 corpus 전체에는 본문과 변환 사본이 중복될 수 있습니다. 실제 사용할 원본만
모은 폴더를 지정하세요. 중복 내용은 임의의 출처를 선택하지 않고 오류로 알립니다.

실제 모델 호출 없이 대상 파일/태그만 보려면 Bash 래퍼 대신 아래 명령을 사용합니다.

```bash
.venv/bin/python 06_TOOLS/COMMANDS/genos_unified_pipeline.py build \
  --input-root /home/genos/DEV/UPLOADS \
  --build-dir /home/genos/DEV/GENOS_DATA/builds/rules-v1
```

## 형식과 태그

- 법령 XML은 기존 XML 태그 엔진, 조문 HTML은 기존 HTML 엔진을 사용합니다.
- PDF/HWP/HWPX/DOCX는 기존 파일 파서와 구조 유도 엔진을 사용합니다.
- 파일 옆 `파일명.확장자.genos.json`의 `doc_type`이 있으면 기존 `core/registry.yaml`에
  등록된 **파서 + 형식 + fitness gate**를 사용합니다. 임의의 Python 경로를 태그로 실행하지 않습니다.
- 기존 `format_bindings.json`은 `--bindings /경로/format_bindings.json`으로 넘깁니다.
  우선순위는 파일 sidecar > 문서 ID binding > 폴더 binding > 형식 기본 엔진입니다.
- DOCX에 Word 제목 스타일 자체를 신뢰하도록 명시한 경우 `{"engine":"docxstyle"}`을 씁니다.
  태그 없는 DOCX에는 일반 구조 유도를 사용합니다. `doc_type`과 `engine`을 동시에 지정할 수 없습니다.
- 다른 확장자(MD/TXT/전사 JSON 등)는 sidecar의 `doc_type`이 있고 해당 파서가 등록된 경우만
  처리합니다. 임의 XML/일반 웹 HTML을 법령 XML/조문 HTML로 변환해주는 범용 도구는 아닙니다.

예: `위험관리규정.pdf.genos.json`

```json
{"doc_type":"등록부에 실제로 등록한 유형명","folder":"내규","name":"위험관리규정"}
```

등록부에 없는 유형, 없는 형식 파일, fitness 실패, 어떤 구조 마디에도 속하지 않는 원문 블록은
LLM 호출 전에 멈춥니다. 원문을 조용히 누락하거나 새로운 조문을 만들어내지 않습니다.
이미지 PDF의 OCR 등은 해당 기존 파서의 설치/지원 범위에 따릅니다.

## 배치·진행·재시작

- `--segment-chars 6000`: LLM 스키마 추출 작업의 원문 문자 묶음 크기. 조문 경계를 먼저 따르고
  큰 조문은 원문 좌표를 보존해 나눕니다.
- `--embed-chunk-chars 1400`: 임베딩 입력의 최대 문자 수. 구조화 블록을 넘어 합치지 않습니다.
- `--embed-batch-size 64`: 한 번의 임베딩 요청에 넣을 청크 수. 159개면 64/64/31이며 전체 제한이 아닙니다.
- `--max-attempts 3`: 추출/검토 단계별 총 시도 상한. 잘못된 응답의 검증 오류와 검토 피드백이
  다음 추출에 들어갑니다. 무제한 재호출하지 않습니다.
- `--max-calls 10000`: 한 번 실행의 authoring API 예산. 다 못 끝나면 적재하지 않고 멈춥니다.
- `--max-tokens 8192`, `--timeout 300`: 응답 길이/요청 시간 제한. 잘린 답변은 통과하지 않습니다.

진행은 `[1/5] 구조화`, `[2/5] extract/review/재추출`, `[3/5] 임베딩 누적 수`,
`[4/5] 적재`, `[5/5] 재열기 검증`으로 터미널에 표시됩니다.

중간 중단 후에는 **같은 명령 끝에 `--resume`**을 붙입니다. 완료된 추출/검토/임베딩 배치는
재사용합니다. 서버가 응답했지만 로컬에 기록되기 전에 강제 종료된 호출은 결과를 알 수 없어
다시 호출될 수 있습니다. 네트워크 오류는 30초 후 재개하며, 상한 소진 문서는 상태를 확인해야 합니다.

원문/태그/스키마/관련 코드/모델 리비전이 바뀌었다면 `rules-v2`처럼 새 `--build-dir`을 쓰세요.
같은 폴더를 지우고 덮어쓰거나 다른 버전의 결과를 섞지 않습니다. 스키마 변경 시 현재 스키마를
다시 읽지만, breaking 변경은 추출기/검증기/적재기 호환 업데이트도 필요합니다.

## 결과와 배포

`rules-v1/result.json`의 `ok:true`와 아래 결과를 확인합니다.

- `queue/queue.sqlite`: 작업별 실제 프롬프트·응답·검증·재추출·사용량·시간
- `handoff/*.bundle.json`: 검토를 통과한 실제 스키마 데이터
- `generation/store.sqlite`: 원문·의미 엔티티·관계·검색 인덱스
- `generation/vectors.sqlite`: 외부 Vector DB 없는 파일형 임베딩 인덱스
- `generation/manifest.json`: 원문·스키마·벡터 해시 및 DRAFT 상태

로컬 개발 테스트에서는 이 새 generation을 명시적으로 열 수 있습니다. 기존 서비스의
CURRENT/ACTIVE 포인터, 모델 정책, Git push, GENOS 코드 서빙 배포는 이 명령이 변경하지 않습니다.
LLM 검토 통과는 사람의 정본 승인이나 법률 정확성 인증이 아닙니다. 실제 운영 배포는 별도 승인과
영속 데이터 경로 설정을 거쳐야 합니다. 이 변경의 검증은 가상 문서/모의 API 기반이며 현장 실행은 미확인입니다.
