# 데이터 처리 → 최신 뒷단 인계

의미 생성·정규화는 데이터 처리 작업이 맡는다. 이 문서는 적재 이후의 계약이다.
법률 필드의 정본은 `00_SYSTEM/LEGAL_SCHEMA.json`이 지정한 `legal-semantic-v2` 그대로다.

## 운영 플로우

`원문 구조 + CANONICAL_BUNDLE → legal-load → 단일 세대 DB·Projection·벡터 → legal-rag → feedback.proposal`

`legal-rag`는 PIPELINE.json의 retrieve → select → assemble → answer 엔진을 실제 순서대로 실행한다.
엔진 파일과 스키마는 release에 해시로 고정한다. 실행 중 과거 MAIN, domain_graph, legal_graph-v1, 연구 후보를 import하지 않는다.
조건 사실은 `bundle_id/clause_id` 키로 받으며 TRUE/FALSE/UNKNOWN을 구분한다. 미확인은 거짓이 아니다.
LLM은 후보 ID 선택과 인용 답변을 맡고, DB와 코드가 Rule·단서·명시 참조를 조립한다.

## 넘길 데이터

1. source SQLite: `document(document_id,name,source_artifact_sha256,json)`,
   `source_unit(document_id,unit_id,parent_id,json)`,
   `source_block(document_id,block_id,unit_id,text,source_artifact_sha256,json)`.
   unit.json은 기존 구조의 `span:[start,end)`, `block`, `family`, `title`, `surface`를 유지한다.
2. 하나 이상의 `CANONICAL_BUNDLE` JSON. Concept/Mention/Clause/Rule/Proviso/LegalRelation/Evidence 및
   원래 crosswalk를 보존한다. 모델 관측을 적재기가 자동으로 이 형태로 바꾸지 않는다.
3. 선택적 벡터 descriptor JSON과 NPZ. NPZ 배열은 `vectors`, `document_ids`, `block_ids`, `text_sha256`이다.
   descriptor에는 모델 파일 지문과 원문 store 해시가 필요하다. 없는 경우 vector는 NOT_CONFIGURED로 표시된다.

원문 좌표·해시, 관계 대상 ID, 같은 SourceSet, 의미 스키마를 검사한다. DRAFT는 DRAFT로 보존한다.
APPROVED는 데이터 처리 측이 실제로 승인한 경우에만 지정한다. 자동 승인 기능은 없다.

```bash
.venv/bin/python -B 06_TOOLS/semantic_runtime.py load \
  --source-store /absolute/path/source.sqlite \
  --bundle /absolute/path/canonical.json \
  --output 01_DATA/SEMANTIC/GENERATIONS/new-generation \
  --data-status DRAFT
```

복수 문서는 `--bundle`을 반복한다. 서로 다른 SourceSet은 먼저 처리 측에서 명시적으로 합성해야 한다.
벡터가 있으면 `--vectors /absolute/path/vectors.json`을 추가한다. 외부전송 허용 여부는 원래 SourceSet 정책을 따른다.

## 실행과 데이터 교체

```bash
06_TOOLS/serve.sh
.venv/bin/python -B 06_TOOLS/semantic_runtime.py status
```

`/health`는 활성 release와 generation, DRAFT/APPROVED 상태, vector 상태를 노출한다.
`POST /v1/rag/ask`는 `{question, document_ids:[], use_llm:true, clause_values:{}}`를 받는다.
`use_llm:false`는 원문 조회이며 LLM 답변으로 표시하지 않는다.
`GET /v1/rag/section?doc_id=...&node=...`는 요청한 항·호 범위를 반환한다. 없는 좌표는 404이며 조 전체로 확대하지 않는다.
`POST /v1/rag/feedback`는 `{run_id,signal,reason}`을 받고 검토 제안을 저장한다. DB를 직접 수정하지 않는다.

외부 Haiku는 ANTHROPIC_API_KEY를 사용한다. 비공개 SourceSet은 내부 endpoint를 설정하거나 원문 조회 모드를 사용한다.
내부 호환 API는 `SEMANTIC_LLM_BACKEND=openai-compatible`, `SEMANTIC_LLM_ENDPOINT`,
`SEMANTIC_LLM_TRUST_ZONE=internal`, `SEMANTIC_LLM_API_KEY`로 설정한다. 제품 모델 ID는 Haiku로 고정한다.

새 데이터를 적재한 뒤 동일 코드와 새 generation을 대상으로 `prepare`한다.

```bash
.venv/bin/python -B 06_TOOLS/semantic_runtime.py prepare \
  --code-root /home/jin/8-AGENT --generation 01_DATA/SEMANTIC/GENERATIONS/new-generation \
  --release-id new-semantic-release --authorization /absolute/path/user-directive.json \
  --validation /absolute/path/structural-checks.json
.venv/bin/python -B 06_TOOLS/semantic_runtime.py apply \
  --manifest 08_DEPLOYMENT/RELEASES/new-semantic-release/release.json --confirm-main
```

전환은 현재 포인터 해시를 비교한 뒤 새 generation과 append-only 영수증을 남긴다. 적용 후 서버를 재시작한다.
이번 전환은 사용자 지시에 의한 품질 기준 예외이며, 성능 실험을 Accepted로 바꿔 기록하지 않는다.
명시적 복구는 `semantic_runtime.py rollback --confirm-main` 후 재시작한다. 자동 legacy fallback은 없다.
