# 온사이트·폐쇄망 실행 가이드

이 경로는 프론트엔드, Docker, 외부 API를 전제로 하지 않는다. 기존 파일형 벡터 정본과
배치 파이프라인은 그대로 유지하고, 로컬 OpenAI-compatible LLM과 Qdrant는 환경변수로
명시했을 때만 활성화한다.

## 1. 반입 전에 묶어야 할 것

- 저장소와 Python wheelhouse(`requirements-serving.txt`, 로컬 임베딩을 쓰면
  `sentence-transformers` 및 CPU용 torch 포함)
- 로컬 임베딩 모델 디렉터리 전체. `EMBED_MODEL`은 그 절대경로를 가리킨다.
- 기존 `data/structure`, `data/corpus`, `data/embeddings/sections`와 필요한 sidecar
- OpenAI-compatible `/v1/models`, `/v1/chat/completions`를 제공하는 로컬 LLM 서버
- 선택 사항: Qdrant 서버와 영속 volume

`.env.onsite.example`을 현장 경로에 맞게 복사한다. 운영 비밀은 파일에 커밋하지 않는다.
`scripts/onsite.sh`는 Hugging Face와 Transformers의 오프라인 플래그를 기본으로 켠다.

## 2. 연결과 자산 확인

```bash
scripts/onsite.sh doctor --strict
scripts/onsite.sh llm-check --log data/pipeline/llm-connection.json
scripts/onsite.sh vector-check
scripts/onsite.sh vector-check --query "설명의무"
```

`doctor --strict`는 LLM/Qdrant URL이 loopback·사설 IP인지 확인한다. 사내 DNS 이름은
`ONSITE_ALLOWED_HOSTS=llm.intra,qdrant.intra`처럼 명시한다. `llm-check`는 실제
structured-output 한 번을 호출하므로 연결 시험 때만 실행하고 로그를 보존한다.

## 3. Qdrant 사용

파일형 `vectors.npz + meta.jsonl`이 재생성 정본이다. 먼저 기존 정본을 만들거나 반입한 뒤
Qdrant로 동기화한다.

```bash
export RAG_VECTOR_BACKEND=qdrant
scripts/onsite.sh vector-sync
scripts/onsite.sh vector-check --query "자본시장법 설명의무"
```

collection을 비우고 정확히 다시 만들 필요가 있을 때만 `vector-sync --recreate`를 사용한다.
이 옵션은 대상 Qdrant collection을 삭제하므로 운영 중에는 사전 백업과 명시 승인이 필요하다.

## 4. 프론트 없는 신규 파일 처리

예를 들어 반입 파일이 `/media/A`에 있으면 다음 한 줄로 처리한다.

```bash
scripts/onsite.sh process /media/A --folder 2026-08-현장반입
```

지원 형식은 XML, HTML, HWP, HWPX, DOCX, PDF다. 원본은 수정하지 않고
`PIPELINE_INBOX`에 복사한 뒤 `ingest → structure → delegation → terms → embed → scopes`를
실행한다. 실행 상태와 사건 로그는 `PIPELINE_DIR`에 남고, 같은 바이트의 문서는 기존
`doc_id`를 재사용한다.

LLM 프레임 생성까지 필요한 경우:

```bash
scripts/onsite.sh process /media/A --folder 2026-08-현장반입 \
  --stages ingest,structure,delegation,terms,frames,embed,scopes
```

저장소 정책상 제품 context를 만드는 `frames`는
`claude-haiku-4-5-20251001`만 허용한다. 로컬 서버가 다른 모델 ID를 제공하면 CLI가 이
단계를 거부한다. 다른 로컬 모델은 `llm-check` 같은 격리 연결 확인에는 쓸 수 있지만 제품
답변 또는 제품 context를 변경하는 경로에는 연결하지 않는다.

기계가 읽을 JSON이 필요하면 서브명령 앞에 `--json`을 둔다.

```bash
scripts/onsite.sh --json doctor --strict
scripts/onsite.sh --json process /media/A --folder batch-001 > run-receipt.json
```

## 5. 온프레미스 운영 체크

- `doctor --strict`가 전부 통과하기 전 서비스나 배치를 시작하지 않는다.
- 모델·wheel·문서·벡터의 SHA-256과 버전을 반입 목록에 고정한다.
- `data/structure`, `data/pipeline`, Qdrant volume은 재시작 후에도 남는 경로에 둔다.
- OS 시간 동기화, 디스크 여유, 파일 권한, UTF-8 locale을 확인한다.
- `.env`, API key, 원문 문서, LLM 요청·응답 로그를 외부 반출 대상에서 제외한다.
- 새 문서는 먼저 CLI로 소량 처리하고 격리 점수·실패 목록을 확인한 뒤 전체 묶음을 넣는다.
- 기본 `scripts/serve.sh`는 `0.0.0.0`에 바인딩한다. 단일 장비 현장이라면
  `HOST=127.0.0.1 scripts/serve.sh`로 loopback에만 바인딩한다.
