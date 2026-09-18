# GENOS 구조 응답 전처리기 v1

목적: 원본 PDF를 기존 GENOS layout/OCR/table 엔진으로 파싱하고 청킹 전 Docling 구조와
전체 텍스트를 반환한다. 문서의 계층 틀 생성·VLM 검수·재구조화는 8-AGENT가 담당한다.

## 기준 코드와 적용 범위

- 공개 원본: https://github.com/genonai/doc_parser_code_serving
- 고정 리비전: `aa610c3db24aaa02c65e953279f1a60d014babaf`
- 읽은 호출 경로: `genon/preprocessor/src/main.py` → `DocumentProcessor.__call__`
  → `facade/parser_processor.py`의 `_parse_docling` → `_build_docling_response`.
- 비교한 기존 청크 경로: `facade/attachment_processor.py`의 PDF 로더/청킹/벡터 응답.
- **현장 187번의 설치 원본을 확보한 것은 아니다.** 사진에서 확인한 청크 계약과 공개
  원본을 기반으로 작성한 새 파싱용 구현이다. 기존 187 리비전을 백업하고 별도 전처리기로
  검증한다. 아래 파일만 구버전 이미지에 올리면 모든 의존성이 맞는다고 가정하지 않는다.

`preprocessor.py`는 공개 parser facade를 상속한다. GENOS 플랫폼의 기존 main.py가
`from preprocessor import DocumentProcessor`로 적재하며 반환값을 `data`에 넣는다.
전용 `/run` HTTP 서버를 중복 구현하지 않는다. 기존 parser facade와 genon 모듈·포크
Docling이 설치된 이미지/소스가 필요하다. 독립 단일 파일 파서가 아니다.

## 파일

- `preprocessor.py`: 업로드할 새 진입 코드. PDF 전용, 생성 enrichment 차단,
  Docling 원문 트리 보존, 읽기 순서/전체 텍스트/해시 반환.
- `prepare_config.py`: 기존 **parser** YAML 옆에 새 설정을 생성한다. layout/OCR/
  table/guardrail/모델 URL·키 설정과 상대 리소스 경로를 보존하고 output/enrichment만 변경.
  attachment 전용 YAML을 parser 설정으로 자동 변환하지 않는다.
- 배포 ZIP의 `UPSTREAM.json`: 기준 소스와 파일별 해시. `upstream-source.zip`은
  같은 고정 리비전의 공개 배포 소스/의존성 명세를 포함한다. 모델 가중치는 포함하지 않는다.

## 현장 준비와 실행

1. 새 전처리기 리비전에 원본 프로젝트와 맞는 의존성을 준비한다. 기준 원본의
   requirements/pyproject 및 포크 wheel을 확인한다. 공개 Dockerfile의 타 사이트
   레지스트리·이미지·NFS 값을 현장 값으로 그대로 가정하지 않는다. 기존 현장 베이스
   이미지·승인된 내부 모델을 사용하며 외부 설치·외부 모델 fallback은 없다.
2. 기존 설치 `preprocessor.py`, parser YAML, 리비전/이미지/모델 ID와 해시를 백업한다.
3. 현장의 layout/OCR/table 엔드포인트가 설정된 parser YAML로 새 파일을 만든다.
   아래 경로는 예시이며 실제 설치 경로로 대조한다.

```bash
python prepare_config.py /app/resource/parser_processor_config.yaml /app/resource/8agent_parser_v1.yaml
```

4. 플랫폼 전처리기 코드로 이 디렉터리의 `preprocessor.py`를 선택한다. 서버 환경에
   `GENOS_STRUCTURE_CONFIG=/app/resource/8agent_parser_v1.yaml`을 지정한다. 기존
   인증/호출자 권한/NFS 공유 그룹은 유지한다. API `/run` 또는 지원 시 `/parser` 사용.
5. 8-AGENT 코드스페이스에는 새 서버의 ID 또는 URL, 서버 리비전을 명시한다.
   `GENOS_PREPROCESSOR_RESPONSE_MODE=docling`으로 고정하면 청크 응답을 거부한다.
   공유 폴더 및 원격 대응은 기존 설정을 유지한다.
6. 새 run ID로 PDF 한 건을 구조화한다(수신기 v4 이상).

```bash
export GENOS_PREPROCESSOR_RESPONSE_MODE=docling
export LLM_BACKEND=genos
export STRUCTURE_RECIPE_VLM=on
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id structured-server-001 --only-internal-pdf --limit 1 --stage structure --execute
```

## 요청·응답

요청: 기존 `{"file_path":"/shared/request/source.pdf","params":{...}}`.
서버 내부에서는 `document_payload()`가 다음을 반환하고 플랫폼이 한 번 감싼다.

```text
{code: 0, errMsg: success, data: {
  schema_version: 8agent-structured-pdf-v1,
  document: DoclingDocument model_dump JSON,
  full_text: 모든 읽기 순서 항목의 텍스트,
  reading_order: [{ref, label, text, char_span, pages}, ...],
  provenance: {source_sha256, config_sha256, base_module_sha256, ...},
  capabilities: {...}
}}
```

`document`가 정본이며 full_text는 편의 뷰다. 표는 논리 셀·병합·좌표를 원래 트리에
보존한다. 페이지 이미지/그림 URI는 원문 JSON에 남고 클라이언트가 외부 URL을 받으러
가지 않는다. 서버 전용 그림 URI는 수신 시 원본 PDF의 해당 좌표로 렌더한다.
청크·HTML·문자열 응답으로 성공을 위장하지 않는다. 페이지 집합·원본 해시·빈 결과를 검사한다.

## 검증과 복구

로컬 모의 엔진: 원본 트리/병합 셀/읽기 순서 보존, runtime enrichment 차단, 설정
보존·덮어쓰기 거부, 원본 해시와 클라이언트 Docling 역직렬화를 검사했다. 실제 내부
layout/OCR/table 모델 호출, 구버전 현장 이미지 호환성·성능·정확도는 미확인이다.
원본 facade의 enrichment=[] 지원을 포함해 현장 한 건의 결과를 확인해야 한다.

실패 시 새 서버 리비전을 비활성화하고 이전 리비전·YAML로 복구한다. 클라이언트는
기존 서버 ID/URL, `RESPONSE_MODE=auto`로 돌리고 새 run ID를 사용한다. 기존 원문,
완료 세대, 응답·설정 해시 기록을 보존한다. MAIN/CURRENT나 코드서빙을 자동 변경하지 않는다.
