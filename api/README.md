# API — 신탁계약 정합성 검증을 HTTP 로

두 엔진을 하나의 FastAPI 앱에 올리고, GenOS 채팅에 붙일 수 있게 SSE 어댑터를 얹었다.
판정 로직은 건드리지 않았다 — 이 계층은 파일을 받고, 엔진을 부르고, 결과를 그대로 낸다.

| 엔진 | 무엇 | LLM |
|---|---|---|
| `trust-parser` (`/v1/parser/*`) | 온톨로지 기반 결정론 엔진. 파싱·대사·질의 | 불필요 (선택 단계만 사용) |
| `first-agent` (`/v1/agent/*`) | 문서 해석을 LLM 이 하는 대사 파이프라인 | **필수** (또는 스냅샷 재생) |
| GenOS 어댑터 (`/chat/stream`) | 위 엔진을 채팅으로 — SSE | 불필요 |

## 지금 당장 실행

```bash
# 로컬 (venv 는 두 프로젝트가 공유한다 — trust-parser/.venv 는 심볼릭 링크)
python3 -m venv .venv && .venv/bin/pip install -r deploy/api/requirements.txt
.venv/bin/uvicorn api.app:app --host 0.0.0.0 --port 5555

# 도커
docker compose up -d --build

curl http://localhost:5555/health
open http://localhost:5555/docs        # Swagger UI 에서 그대로 눌러 볼 수 있다
```

**반드시 저장소 루트에서 실행한다** (`api.app:app`). `api/` 안에서 실행하면 패키지
임포트가 깨진다.

## GenOS 연동 (`POST /chat/stream`)

GenOS 문서(`mocking-flowise`)의 규약을 그대로 따른다. 워크플로우에서 이 URL 을
flowise 대신 지정하면 된다.

```bash
curl -N -X POST http://localhost:5555/chat/stream \
  -H "Content-Type: application/json" -H "x-request-from: internal" \
  -d '{"question":"중도해지수수료는 얼마인가요?","chatId":"abc123"}'
```

```
data: {"event": "session", "data": {"chatId": "abc123"}}
data: {"event": "reasoning_token", "data": "분류: intent=value field=중도해지수수료 …"}
data: {"event": "reasoning_token", "data": "경로: alias:중도해지수수료 → intent:value(rule) → …"}
data: {"event": "agentFlowExecutedData", "data": {"nodeLabel": "질의 라우팅", …}}
data: {"event": "token", "data": "**중도해지수수료** — …"}
data: {"event": "result", "data": null}
```

| 이벤트 | 담는 것 |
|---|---|
| `session` | 스트림 시작 — `chatId` 통지 |
| `reasoning_token` | **라우터가 실제로 지난 경로.** GenOS 가 "Visible Reasoner" 로 접어 보여준다 |
| `agentFlowExecutedData` | 근거 카드 — `질의 라우팅` / `근거 청크` / `출처` / `문서 목록` |
| `token` | 최종 답변 (마크다운) |
| `error` | 오류 |
| `result` | `null` — 종료 신호 |

10초마다 `: keep-alive` 주석 라인을 보내 프록시가 조용한 연결을 끊지 않게 한다.

**여기서 흘리는 `reasoning_token` 은 모델의 생각이 아니다.** 라우터가 지나간 실제
경로다(`alias:신탁금액 → intent:value(rule) → role:source_of_truth`). 값 질문은 fact 표에서
끝나고 해석 질문만 청크 검색으로 가는데, 그게 화면에 그대로 보인다.
임베딩이 없어 매 단계가 재현 가능하다는 원래 설계를 채팅 UI 에서도 깨지 않는다.

### 채팅이 "어느 계약서"인지 아는 법

채팅은 텍스트 한 줄만 준다. 그래서 파싱된 문서를 보관소에 두고 `chatId` 별로 활성 문서를
기억한다. `POST /v1/parser/parse` 로 PDF 를 올리면 **자동 등록**되고,
컨테이너의 `out/*.chunks.json` 과 골든 쌍도 첫 조회 때 훑어 들어온다.

| 채팅 명령 | 하는 일 |
|---|---|
| `/docs` | 등록된 계약서 목록 |
| `/use <doc_id>` | 이 대화에서 볼 계약서 지정 |
| `/fields` | 별지1 필드 목록 |
| `/help` | 도움말 |

문서가 하나뿐이면 그냥 물어보면 된다. 여러 건이면 목록을 보여주고 고르게 한다.
워크플로우가 문서를 직접 지정할 때는 요청 본문에 `docId` 를 넣으면 된다.

`/chat/stream` 은 `API_TOKEN` 뒤에 두지 않았다 — GenOS 규약에 Bearer 가 없고 내부망
호출을 전제하기 때문이다. 공개망에 노출한다면 네트워크 계층에서 막아야 한다.

## 엔드포인트

| 메서드 | 경로 | 하는 일 | 도클링 | 응답 |
|---|---|---|---|---|
| POST | `/chat/stream` | GenOS 채팅 (SSE) | – | 스트리밍 |
| GET | `/health` | 의존성·엔진 상태 | – | 즉시 |
| POST | `/v1/parser/parse` | PDF → chunks.json (Part A) | **필요** | 작업 (~45초) |
| POST | `/v1/parser/reconcile` | chunks + 요약서 → 리포트 (Part B) | PDF 요약서만 | 작업 (md 는 즉시) |
| POST | `/v1/parser/reconcile/json` | 위와 같되 JSON 입출력 | – | 즉시 |
| POST | `/v1/parser/query` | 질의 → fact 조회 / 청크 검색 (Part D) | – | 즉시 |
| GET/POST | `/v1/parser/documents` | 문서 보관소 — 채팅이 참조하는 것과 같다 | – | 즉시 |
| GET | `/v1/parser/ontology` | 온톨로지 전문 (제약 계층) | – | 즉시 |
| GET | `/v1/parser/fields` | 별지1 필드 목록 | – | 즉시 |
| GET | `/v1/agent/status` | LLM 키·스냅샷 상태 | – | 즉시 |
| GET | `/v1/agent/tags` | 대사 대상 태그 20종 | – | 즉시 |
| POST | `/v1/agent/reconcile` | 계약서 ↔ 핵심상품설명서 대사 | 필요 | 작업 (분 단위) |
| POST | `/v1/agent/bundle` | 위 + 중간 산출물 전부 | 필요 | 작업 |
| GET | `/v1/jobs/{id}` | 작업 상태·결과 | – | 즉시 |
| GET | `/viewer/` | 기존 정적 뷰어 | – | – |

## 응답 규약 — 무거운 엔드포인트는 전부 같다

도클링 파싱은 45초, LLM 대사는 몇 분이 걸린다. 대부분의 프록시는 30~60초에 연결을
끊으므로 **제출 → 폴링**이 기본이다.

```
202 {"status":"queued"|"running", "job_id":"..."}      → GET /v1/jobs/{id} 로 폴링
200 {"status":"done",  "job_id":"...", "result":{...}}
200 {"status":"error", "job_id":"...", "error":"..."}   ← 요청은 성공, 작업이 실패
```

`wait=<초>` 를 주면 그 시간까지 기다렸다가 끝났으면 결과를 동봉한다.
짧게 끝나는 요청은 한 번의 호출로 답이 나오고, 오래 걸리면 자동으로 job id 로 떨어진다.
호출자는 한 가지 처리 방식만 알면 된다.

```bash
# 파싱 — 폴링
JOB=$(curl -s -X POST localhost:5555/v1/parser/parse -F "file=@계약서.pdf" | jq -r .job_id)
curl -s "localhost:5555/v1/jobs/$JOB/wait?timeout=120" | jq '.result.meta'

# 대사 — 마크다운 요약서는 wait 안에 끝난다
curl -s -X POST localhost:5555/v1/parser/reconcile \
     -F "contract=@out/계약서.chunks.json" -F "summary=@요약서.md" -F "wait=30" \
  | jq '.result.stats, .result.text'

# 질의 — 동기
curl -s -X POST localhost:5555/v1/parser/query -H 'Content-Type: application/json' \
     -d "$(jq -n --slurpfile c out/계약서.chunks.json \
              '{chunks:$c[0], question:"중도해지는 어떻게 하나요?"}')" | jq .route.path

# LLM 대사
curl -s -X POST localhost:5555/v1/agent/reconcile \
     -F "contract=@계약서.pdf" -F "statement=@핵심상품설명서.pdf" \
     -F "tags=trust_fee,trust_period" -F "llm_backend=auto" | jq -r .job_id
```

## 환경변수

`api/.env.example` 을 복사해 쓴다. 전부 선택값이고, 기본값으로 그냥 돈다.

| 변수 | 기본 | 설명 |
|---|---|---|
| `PORT` | `5555` | GenOS 예제와 같은 포트 (`python -m api.app` 로 띄울 때) |
| `ANTHROPIC_API_KEY` | – | first-agent 필수. 없으면 스냅샷 재생만 가능 |
| `API_TOKEN` | – | 설정하면 모든 `/v1/*` 에 `Authorization: Bearer <값>` 강제 |
| `CORS_ORIGINS` | `*` | 쉼표로 구분 |
| `MAX_UPLOAD_MB` | `40` | 업로드 상한 |
| `MAX_WAIT_SECONDS` | `240` | `wait` 파라미터의 상한 |
| `PARSER_WORKERS` | `2` | 파싱 동시 실행 수 |
| `AGENT_WORKERS` | `1` | **1 을 권장** — 스냅샷·용어집 파일을 공유한다 |
| `SERVE_VIEWER` | `1` | `/viewer/` 정적 서빙 |

## 배포할 때 알아 둘 것

**이미지가 크다.** docling 이 torch 를 끌고 온다 — CPU 휠로도 2~3GB.
PDF 파싱이 필요 없고 이미 만들어 둔 `chunks.json` 을 넣어 쓸 거라면
`deploy/api/requirements-light.txt` 로 바꾸면 ~150MB 가 된다. 이때 파싱 엔드포인트만 503 을 내고
대사·질의·질의응답은 전부 정상 동작한다.

**첫 파싱 요청이 느리다.** 도클링이 레이아웃 모델을 그때 내려받는다(수백 MB, 네트워크 필요).
`deploy/api/docker-compose.yml` 의 `hf-models` 볼륨이 이걸 재사용한다. 오프라인 배포거나 첫 요청도
빨라야 하면 `deploy/api/Dockerfile` 의 모델 프리페치 주석을 푼다.

**원본 문서는 이미지에 넣지 않는다.** `.dockerignore` 가 `first-agent/dataset/` 과
`trust-parser/data/` 를 제외한다 — 이 브랜치는 실제 은행 계약서를 포함하고 있고,
이미지를 외부 레지스트리로 push 하면 그 문서가 같이 나간다. 대사할 문서는 업로드로 받는다.
`.env` 도 마찬가지로 제외되어 있다 — 키는 환경변수로 주입한다.

**업로드본은 남기지 않는다.** 작업이 끝나면(성공·실패 무관) 임시 디렉토리를 지운다.
결과는 메모리에만 있고 `JOB_TTL_SECONDS`(기본 6시간) 뒤 사라진다.
영속·감사 기록이 필요하면 호출자가 결과를 받아 저장한다.

**공개 배포면 `API_TOKEN` 을 설정한다.** 계약서를 받는 엔드포인트다.

## 이 계층이 하지 않는 것

판정을 다시 쓰거나 요약하지 않는다. `NEEDS_REVIEW` 는 `NEEDS_REVIEW` 로 나간다 —
"최종 판정은 코드 결정론"이라는 원래 설계를 API 가 흐리지 않는다.
`/v1/parser/query` 는 뷰어(`cli serve` 의 `/api/query`)와 **같은 함수**를 부른다.
화면과 API 가 다른 답을 내면 그 자체가 사고이기 때문이다.
