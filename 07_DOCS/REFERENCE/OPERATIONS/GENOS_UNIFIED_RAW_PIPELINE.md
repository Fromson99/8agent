# GENOS raw 입력 통합 파이프라인

## 고정 구조

```text
외부 공개 원본 DatasetPackage ─┐
                               ├─ ingest → structure → delegation → terms → embed → scopes
GENOS 내부규정 업로드 파일 ────┘
```

외부와 내부는 **원본을 받는 입구만 다르다**. 외부 원본은 SHA-256이 고정된
`external-public-v1` 패키지를 검증해 반입하고, 내부규정은 GenOS가 새로 업로드한
파일만 `GENOS_UPLOAD_ROOT` 아래에서 받는다. 두 입구 모두 `lawrag.common-batch-v1`
실행 함수로 합류한다.

과거 LLM observation/frame, canonical/semantic generation, authoring queue, 과거 답변은
입력도 배포물도 아니다. `frames`도 기본 단계가 아니며, 새 LLM 처리가 필요할 때만
승인된 모델 설정으로 명시 실행한다.

## 설치 위치와 환경값

전체 묶음은 별도 상위 폴더를 만들지 않고 `/home/genos/DEV`에서 바로 푼다. 전달
조각은 `/home/genos/DEV/TRANSFER`, 실행 데이터와 generation은
`/home/genos/DEV/GENOS_DATA`에 둔다. 두 폴더는 Git에서 제외된다.

GenOS 환경 설정에는 최소한 다음 두 경로를 실제 마운트에 맞게 지정한다.

```bash
GENOS_DATA_ROOT=/home/genos/DEV/GENOS_DATA
GENOS_RUNTIME_DIR=/home/genos/DEV/GENOS_DATA/runtime
GENOS_UPLOAD_ROOT=/nfs-root
```

`GENOS_DATA_ROOT`는 쓰기 가능한 코드스페이스 경로다. 코드스페이스를 삭제하면 함께
삭제되므로 필요한 경우 DEV 전체를 백업한다.
`GENOS_UPLOAD_ROOT`는 GenOS가 업로드 파일을 보여 주는 최상위 읽기 경로다.

파이프라인 의존성 설치:

```bash
cd /home/genos/DEV
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-pipeline.txt
```

최초 구동 순서는 `external` → `publish` → `search`다. 새 내부규정을 올린 뒤에는
`internal` → `publish` → `search` 순서로 갱신한다.

## 외부 원본 최초 반입

ZIP에 포함된 7개 외부 공개 raw 패키지를 전부 검증하고 공통 파이프라인을 실행한다.

```json
{"API_TYPE": "PIPELINE_EXTERNAL"}
```

```bash
cd /home/genos/DEV
export PYTHONPATH="$PWD/02_BACKEND"
.venv/bin/python 06_TOOLS/COMMANDS/genos_unified_pipeline.py \
  --data-root "$GENOS_DATA_ROOT" external
```

모델 연결 없이 경로와 패키지만 먼저 확인하려면:

```bash
.venv/bin/python 06_TOOLS/COMMANDS/genos_unified_pipeline.py \
  --data-root "$GENOS_DATA_ROOT" bootstrap-external
```

## 내부규정 업로드 처리

GenOS 코드서빙 요청은 업로드 경로를 전달한다. 지정한 업로드 루트 밖의 경로,
심볼릭 링크, 지원하지 않는 확장자는 거부된다.

```json
{
  "API_TYPE": "PIPELINE_INTERNAL",
  "genosUploaded": [
    {"file_path": "/nfs-root/docs/새내부규정.docx"}
  ]
}
```

상태 확인:

```json
{"API_TYPE": "PIPELINE_STATUS"}
```

외부/내부 원본을 공통 파이프라인으로 처리한 다음, 현재 structure 결과에서 검색용
generation을 새로 만든다. 이 발행에는 과거 LLM observation/canonical bundle이 전혀
들어가지 않으며, 먼저 원문 lexical 검색만 활성화된다.

```json
{"API_TYPE": "PIPELINE_PUBLISH"}
```

발행이 끝나면 `GENOS_DATA_ROOT/generations/CURRENT.json`이 새 발행본을 가리키므로
`GENOS_GENERATION`을 비워 둬도 검색 서빙이 해당 발행본을 자동 사용한다. 특정 세대를
고정할 때만 응답의 `generation` 절대경로를 `GENOS_GENERATION`에 넣는다.

CLI 발행:

```bash
.venv/bin/python 06_TOOLS/COMMANDS/genos_unified_pipeline.py \
  --data-root "$GENOS_DATA_ROOT" publish
```

CLI로 같은 경로를 시험할 수도 있다.

```bash
.venv/bin/python 06_TOOLS/COMMANDS/genos_unified_pipeline.py \
  --data-root "$GENOS_DATA_ROOT" internal \
  --upload-root "$GENOS_UPLOAD_ROOT" \
  /nfs-root/docs/새내부규정.docx
```

## Git 경계

Git에는 코드와 설정 예시만 올린다. `GENOS_DATA`, `TRANSFER`, `GENOS_UPLOAD`,
`01_DATA/PACKAGES`, `01_DATA/INBOX`, `01_DATA/SEMANTIC`, 인덱스, 실행 상태,
`.env`, 분할 ZIP은 커밋하지 않는다.
