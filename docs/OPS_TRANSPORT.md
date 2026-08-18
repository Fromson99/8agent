# 망분리 운반 — 스냅샷 · 아웃박스 · 재생

폐쇄망 플랫폼(GenOS)에 올라간 앱은 브라우저가 닿지 않는다 — 게이트웨이 JSON
호출만 된다. 화면은 이쪽(로컬)에서 띄우고, **상태와 조작을 파일로 나른다**.
구현은 `lawrag/api/ops.py` + 진입점 `service.py`, 시험은 `tests/core/test_ops_api.py`
와 `tests/core/test_service_entry.py`.

## GenOS 계약 — 문은 하나다

GenOS 코드 서빙은 uvicorn 앱을 그대로 서빙하지 않는다. 계약은 저장소 뿌리의
`service.py` 안 `async def service(config, data)` 하나이고, 게이트웨이가

    POST https://<GenOS>/api/gateway/code_serving/<번호>/json
    Authorization: Bearer <인증키>

로 노출한다 (실측: v1.8.4·v1.9.0 문서 usage_code_serving — 같다). 임의 경로도 정적 파일도
그 문으로 못 나가므로, `service.py` 는 `data.op` 봉투로 전부를 태우는 터널이다:

```bash
# 기동·rev 확인
curl -s <게이트웨이> -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"op": "ping"}'
# 임의 API 호출 (JSON 몸통은 json, 파일은 body_b64)
  -d '{"op": "call", "method": "GET", "path": "/v1/structure/folders"}'
# 진단 — 서빙 컨테이너에서 그 경로가 보이는지 (볼륨 공유 판별)
  -d '{"op": "ls", "path": "/mnt/shared"}'
# 스냅샷 반출 — b64 로 받거나(작을 때), 공유 볼륨에 떨구거나(클 때)
  -d '{"op": "snapshot"}'
  -d '{"op": "snapshot_to", "path": "/mnt/shared/snap.tar.gz"}'
# 아웃박스 재생
  -d '{"op": "apply", "tar_b64": "'$(base64 -w0 outbox.tar.gz)'"}'
  -d '{"op": "apply_from", "path": "/mnt/shared/outbox.tar.gz", "force": false}'
```

파일 운반 채널은 **코드 스페이스**(VSCode·Jupyter 웹 IDE + 터미널)다 —
스페이스 터미널에서 게이트웨이를 curl 하고, 떨어진 파일을 IDE 로 내려받고
올린다. 코드 스페이스와 서빙이 공유 볼륨을 같이 물면 `snapshot_to` /
`apply_from` 으로 b64 부풀림 없이 파일이 오간다.

## 첫 반입 — 이메일 45MB 조각으로 데이터를 나른다

코드는 git 이 나르지만 정본 데이터(구조 스토어·용어·간선)는 .gitignore 라
따로 가야 한다. **git 에 문서를 못 올리는 내부 저장소**라면 git 이 나르던 문서류
(위키 raw·골든·해석례 색인·agent6 코퍼스·예시·질문셋)도 같이 실린다 — 목록의
아래 절이 그것이다(중복돼도 해가 없다). 그때 내부 git 에는 문서를 뺀 판을 밀어라:
`git rm -r --cached data/wiki data/review data/expc lawrag/agents/agent6/corpus examples bench`
후 커밋한 가지를 push (이쪽 작업 사본은 그대로 남는다). 첨부 한도가 통당 50MB 라서 `scripts/data_ship.sh` 가 목록
(`scripts/data_ship.list`)을 tar.gz 하나로 묶고 45MB 조각으로 잘라 **조각마다
독립 zip**(+MANIFEST.json)으로 떨군다.

```bash
# 보내는 쪽
scripts/data_ship.sh list                     # 무엇이 실리나
scripts/data_ship.sh pack                     # var/out/ship/8agent-data-<날짜>/  *.p01-of-01.zip …
scripts/data_ship.sh pack --size 35           # 서버가 base64 부풀림까지 셀 때
scripts/data_ship.sh pack --vectors           # 벡터(123M)까지 — 그쪽이 같은 bge-m3 를 쓸 때만 의미
scripts/data_ship.sh pack --pdf --pages       # 검수 화면용 합성 pdf·페이지 PNG 까지
scripts/data_ship.sh pack --corpus            # 원본층(187M)까지

# 받는 쪽 — 첨부 zip 을 한 폴더에 모아 두고 (메일이 이름을 바꿔도 된다)
scripts/data_ship.sh verify ~/inbox           # 조각 sha256·이어붙인 tar 무결성만
scripts/data_ship.sh unpack ~/inbox           # 저장소 뿌리에 제자리 배치 (덮어쓰기)
scripts/data_ship.sh unpack ~/inbox --replace # 기존 것을 .data_ship_backup/<시각>/ 로 옮긴 뒤 교체
scripts/data_ship.sh unpack ~/inbox --dry-run # 펼치지 않고 목록만
```

**무엇을 싣고 무엇을 안 싣나** (2026-08-18 결정·실측). 질의(RAG) 경로가 읽는
것은 `result.json`·`meta.json`·벡터·용어집·간선·프레임·판정 지문이다.

| | 크기 | 기본 | 이유 |
|---|---|---|---|
| `data/structure/*/{result,meta}.json` | 47.8M | 싣는다 | 구조 정본 — 이것 없이는 아무것도 안 된다 |
| `data/structure/*/source.xml` | 23.1M | **싣는다** | law.go.kr 원문. 런타임은 안 읽지만 그쪽에서 재인제스트할 근거다 |
| `data/glossary.json` · `delegation.json` · `law_index.json` · `rag/` · `rules/` · `frames/` | 35M | 싣는다 | 용어·간선·관측 |
| `data/wiki/` · `data/review/` · `data/expc/` · `lawrag/agents/agent6/corpus/` · `examples/` · `data/bench/` | 22M | 싣는다 | git 추적 문서류 — 내부 git 에 문서를 못 올릴 때를 위해 |
| `data/embeddings/` | 123M (압축 0) | **안 싣는다** | 벡터는 **그쪽 모델로 다시 만든다** — 질의 임베딩과 색인이 같은 모델이어야 하므로 이쪽 bge-m3 벡터는 그쪽 모델과 안 맞는다. `--vectors` |
| `data/structure/*/source.pdf` · `parse.json` | 37.6M | 안 싣는다 | lawxml 문서의 pdf 는 검수용 **합성 지면**·파싱 캐시 — 뷰어 재해석·페이지 그림만 쓴다. `--pdf` |
| `data/structure/*/pages/*.png` | 194M | 안 싣는다 | 페이지 렌더 — pdf 에서 재생성. `--pages` |
| `data/corpus/` | 187M | 안 싣는다 | 원본층. 재수집·재인제스트·`core.lawnet` 재생성 때만. `--corpus` |
| `*.bak` | 0.3M | 안 싣는다 | 항상 |

기본값 실측: **압축 후 21.8MB → 1통** (문서류 포함). 새 데이터가 생기면 `scripts/data_ship.list`
에 경로 한 줄. 조각이 하나라도 빠지거나 손상되면 어느 통인지 이름을 대고
멈춘다 — 그 통만 다시 받으면 된다.

**받은 뒤 벡터 만들기** — 그쪽에서 한 번:

```bash
# (a) 그쪽에 sentence-transformers 모델이 있으면
EMBED_MODEL=<모델 이름> python -m lawrag.core.terms embed-sections
# (b) GenOS 임베딩 서빙을 쓰면 (서비스 라우터 "서빙 - Embedding" 엔드포인트)
GENOS_EMBED_URL=https://<GenOS>/api/gateway/rep/serving/<임베딩 서빙 ID> \
GENOS_EMBED_KEY=<키> python -m lawrag.core.terms embed-sections
```

같은 환경변수를 서버에도 주면 질의가 같은 모델로 임베딩된다 — `lawrag/core/embedding.py`
가 `EMBED_BACKEND=local|genos` 를 고른다(비우면 `GENOS_EMBED_URL` 유무로).
GenOS 쪽은 `{URL}/v1/embeddings` 에 OpenAI 형식(`{"model","input":[…]}` →
`{"data":[{"index","embedding"}]}`)으로 보낸다 — 문서(v1.9.0 "서비스 라우터")에
경로만 있고 몸통 스키마는 없어서 **가정**이다. 첫 호출이 400 이면 그때 맞춘다.
만들기 전까지는 벡터 채널만 빠지고 렉시컬·간선·용어·쟁점 채널은 다 돈다.
색인을 다른 모델로 다시 만들 땐 옛 `vectors.npz` 를 지우고 만들어라 —
embed_sections 는 sha1 이 같으면 옛 벡터를 재사용한다.

## LLM — 폐쇄망에서는 GenOS 서빙을 부른다

앱의 LLM 호출은 전부 `lawrag/core/llm.py` 의 `LLM.structured()` 하나를 지난다 (합성·
판정·쟁점·검토·귀납). 그 뒤 백엔드가 둘이고, 환경변수로 갈린다:

| 백엔드 | 언제 | 켜는 변수 |
|---|---|---|
| `anthropic` | 개발망. Anthropic SDK, json_schema 네이티브 | `ANTHROPIC_API_KEY` (`.env`) |
| `genos` | 폐쇄망. GenOS **LLM 서빙**의 OpenAI 호환 REST | `GENOS_LLM_URL` + `GENOS_LLM_KEY` |

고르는 규칙: `LLM_BACKEND=anthropic|genos` 가 있으면 그것, 없으면 `GENOS_LLM_URL`
이 있을 때 genos. 실측 계약(genos-docs v1.9.0 "LLM 서빙 API 사용"):

```
GENOS_LLM_URL = https://<GenOS>/api/gateway/rep/serving/<LLM 서빙 ID>
GET  {GENOS_LLM_URL}/v1/models                 → data[0].id 가 모델 이름
POST {GENOS_LLM_URL}/v1/chat/completions       Authorization: Bearer <인증키>
     {"model": …, "messages": [{"role":"system"…},{"role":"user"…}],
      "stream": true, "response_format": {"type":"json_schema", …}}
```

```bash
export GENOS_LLM_URL="https://<GenOS>/api/gateway/rep/serving/43"
export GENOS_LLM_KEY="<LLM 서빙 인증키>"          # 코드 서빙 키와 다른 키다
# 선택
export GENOS_LLM_MODEL="…"        # 비우면 /v1/models 의 첫 모델
export GENOS_LLM_JSON_MODE=json_schema   # json_schema | json_object | prompt
export GENOS_LLM_TEMPERATURE=0
export GENOS_USER_ID=653          # 이용 로그에 사람을 남기려면 (x-genos-user-id)
```

**JSON 을 받는 길** — 서빙 뒤 엔진(vLLM 계열)이 `response_format=json_schema`
를 받으면 스키마가 강제된다. 400 으로 거부하면 스키마를 시스템 프롬프트에
싣는 `prompt` 모드로 **자동으로 한 단계 내려가 그 프로세스 내내** 그 길로
간다 (`<think>…</think>`·코드 울타리는 벗겨서 파싱). 어느 길이었는지는
`LLM.log` 의 Exchange 와 서버 로그("… 모드로 내려간다")에 남는다.

확인은 이 한 줄이면 된다 — LLM 이 잡히면 검색만이 아니라 답변 합성까지 돈다:

```bash
curl -s localhost:5566/v1/rag/ask -H 'Content-Type: application/json' \
  -d '{"question":"신탁업자가 고유재산과 신탁재산을 구분해야 하는 근거는?"}' | jq .answer
```

시험: `tests/core/test_llm_genos.py` — 가짜 OpenAI 호환 서빙 앞에서 json_schema
경로·400 강등·절단 명명·모델 조회를 지킨다.

## 가능성 확인 절차 — 어느 길이 열려 있나

세 가지를 순서대로 확인한다. 위가 열릴수록 좋은 길이다.

```bash
GENOS="https://<GenOS 호스트>"; KEY="<인증키>"; N="<코드서빙 번호>"
GW="$GENOS/api/gateway/code_serving/$N/json"
AUTH=(-H "Authorization: Bearer $KEY" -H "Content-Type: application/json")
```

**① 로컬 PC 에서 — 게이트웨이가 이쪽 망에서 열리는가** (열리면 라이브 모드 후보)

```bash
curl -sv --connect-timeout 5 -o /dev/null "$GENOS" 2>&1 \
  | grep -E "Connected to|Could not resolve|timed out|refused"
curl -s --connect-timeout 5 "$GW" "${AUTH[@]}" -d '{"op":"ping"}'
```

JSON 이 오면 라이브 모드 가능(로컬 화면 ↔ 게이트웨이 터널 실시간).
401/403 은 망은 뚫려 있고 키 문제. resolve 실패/timeout 은 망 분리 확정 —
아래 왕복 모델이 본선이다.

**② 코드 스페이스 터미널에서 — 볼륨이 서빙과 공유되는가**

```bash
df -h | grep -vE "overlay|tmpfs|shm"      # 스페이스에 물린 볼륨 찾기
echo "probe-$(date +%s)" > /mnt/<볼륨>/probe.txt
curl -s "$GW" "${AUTH[@]}" -d '{"op":"ls","path":"/mnt/<볼륨>"}'   # 서빙 눈으로 본다
```

`entries` 에 probe.txt 가 보이면 공유 확정 — `snapshot_to`/`apply_from` 으로
b64 부풀림 없이 파일이 오간다. `exists: false` 면 IDE 업/다운로드로 나른다.

**③ 코드 스페이스에서 — Jupyter 프록시로 화면이 열리는가**

```bash
python3 -m http.server 8899 --bind 127.0.0.1 &
# 브라우저: Jupyter 접속 주소에서 /lab·/tree 를 떼고 → …/proxy/8899/
# 열리면 jupyter-server-proxy 있음 — 스페이스에서 uvicorn 을 띄워
# 실데이터 화면을 여는 길이 생긴다 (뷰어 프리픽스-안전화 필요).
# VSCode 접속이라면 하단 PORTS(포트) 탭이 같은 역할이다.
kill %1
```

## 왕복 한 바퀴

```
그쪽(정본)                                이쪽(미러)
────────────────────────────────────────────────────────────────────
① curl -o snap.tar.gz \
     http://…/v1/ops/snapshot
                    ──[망간 자료전송]──▶  ② OPS_RECORD=1 scripts/serve.sh
                                           curl -F file=@snap.tar.gz \
                                             localhost:5566/v1/ops/restore
                                           (OPS_ALLOW_RESTORE=1 필요)
                                        ③ 브라우저로 평소처럼 작업
                                           — 쓰기 조작이 아웃박스에 쌓인다
                                           (상단바에 「기록 N건」 칩)
                                        ④ curl -o outbox.tar.gz \
                                             localhost:5566/v1/ops/outbox/export
                    ◀──[망간 자료전송]──
⑤ curl -F file=@outbox.tar.gz \
     "http://…/v1/ops/apply" -o report.json
⑥ report.json 을 이쪽으로 가져와 건별 결과 확인
   다음 바퀴는 ①의 새 스냅샷부터
```

로컬 기동은 `OPS_RECORD=1 OPS_ALLOW_RESTORE=1 scripts/serve.sh` 처럼 env 만
얹으면 된다. 그쪽 배포에는 아무 env 도 필요 없다 — 기록·복원은 기본 잠김,
스냅샷·재생은 기본 열림.

## 엔드포인트

| 메서드·경로 | 하는 일 | 어느 쪽 |
|---|---|---|
| `GET /v1/ops/snapshot` | 상태 전부를 tar.gz 하나로 | 그쪽 |
| `POST /v1/ops/restore` | 스냅샷으로 상태를 통째로 교체 (`OPS_ALLOW_RESTORE=1` 필요) | 이쪽 |
| `GET /v1/ops/outbox` | 쌓인 조작 목록 (몸통 제외) | 이쪽 |
| `DELETE /v1/ops/outbox/{op_id}` | 조작 하나 빼기 (실수한 조작 반출 전 제거) | 이쪽 |
| `POST /v1/ops/outbox/clear` | 아웃박스 비우기 — `ops/history/` 로 보존 | 이쪽 |
| `GET /v1/ops/outbox/export` | 아웃박스를 tar.gz 로 반출 | 이쪽 |
| `POST /v1/ops/apply?force=&stop_on_error=` | 묶음을 이 서버에 재생, 건별 리포트 | 그쪽 |
| `GET /v1/ops/status` | record 여부·rev·아웃박스 수·기준 스냅샷 | 둘 다 |

## 무엇이 나르고 무엇이 남는가

스냅샷 키: `structure`(문서 스토어, pages/ 렌더 캐시 제외 — 원본에서 다시
그려진다) · `glossary` · `links` · `bindings` · `canvas` · `ledger` · `fixes` ·
`custom`(표면 규칙) · `rules`(간선 규칙) · `rag`(튜플·판정) · `embeddings` ·
`formats` · `registry`(lawrag/core/registry.yaml — 런타임에 컴파일이 고치는 파일) ·
`agent6_items`. 경로의 정본은 각 소유 모듈이고 ops 는 빌려 읽는다
(`_state_targets()`).

기록 대상은 화면 여섯이 쓰는 라우터의 쓰기 메서드뿐이다:
`/v1/structure` `/v1/formats` `/v1/glossary` `/v1/rag` `/v1/agent6`.
GET·4xx·재생(x-ops-replay)은 기록하지 않는다. 5xx 는 기록한다 — "로컬에
LLM 키가 없어 실패했으니 그쪽에서 실행"이 바로 이 길이다. 앱 로그(`logs/`)는
관측이지 큐레이션이 아니라 나르지 않는다.

## 안전장치 셋

- **멱등** — 조작마다 id, 적용된 id 는 `ops/applied.jsonl` 에 남아 재적용을
  건너뛴다. 같은 파일을 두 번 돌려도 안전하다. 실패한 조작은 등록하지
  않는다 — 고쳐서 다시 보내면 그것만 재시도된다.
- **기준(rev)** — 큐레이션 쓰기마다 rev 가 오른다 (`/v1/rag/ask`·`feedback`
  은 제외 — 조회·라벨은 충돌 근거가 아니다). 아웃박스는 복원 때 받은 기준
  rev 를 들고 가고, 그쪽 rev 와 다르면 409 — 낡은 스냅샷 보고 내린 결정이
  정본을 덮지 못한다. 감수하고 덮으려면 `force=1`.
- **정직한 재생** — LLM 이 개입하는 조작(규칙 시험 `rules/try`, 참조 정리
  `links/settle`, 표제 수집)은 재생 때 **그쪽에서 다시 실행**된다. 로컬에서
  본 결과와 다를 수 있고(규칙 id 가 달라져 `rules/decide` 가 404 날 수도),
  건별 리포트가 그대로 보여 준다. 결과를 위조해 맞추지 않는다.

## RAG 질의는 배치로

실시간 대화는 구조적으로 안 된다. 로컬에서 `/rag/` 화면으로 질문하면 —
로컬에 색인·키가 있으면 로컬 답이 바로 나오고, 없으면 5xx 로 기록만 남아
재생 때 그쪽이 계산한다. 어느 쪽이든 질문·피드백 튜플은 재생을 통해 그쪽
진단 로그에 남는다 (백로그·판정 루프가 정본 쪽에서 돈다).

## 정적 현황 리포트 — 최후의 관측 수단

위 길이 전부 막혀도 "지금 데이터가 어떤 상태인가"는 본다. `GET /v1/ops/report`
(또는 게이트웨이 봉투 `{"op":"report"}`)가 **서버 없이 브라우저로만 여는
HTML 한 장**을 만든다 — 문서·폴더 표, 용어 검수대기·참조·판정 백로그 수,
rev, 그리고 원본 JSON 접기. 스크립트 없는 순수 정적 파일이라 어디로 보내도
열린다. 화면(뷰어)의 대체가 아니라 현황판이다 — 조작은 여전히 왕복으로 한다.

```bash
# 그쪽 터미널에서 한 장 떨구기
curl -s "$GW" "${AUTH[@]}" -d '{"op":"report"}' | jq -r .html > 현황.html
# 공유 볼륨이 있으면 파일로 직접
curl -s "$GW" "${AUTH[@]}" -d '{"op":"report","path":"/mnt/shared/현황.html"}'
# 로컬 미러에서는 그냥
curl -s localhost:5566/v1/ops/report > 현황.html
```

## 반입 폴더 감시 (선택)

망간 전송이 파일을 그쪽 서버의 특정 경로에 떨어뜨려 줄 수 있으면 curl 조차
필요 없다: `OPS_INBOX_DIR=/경로` 로 띄우면 `*.tar.gz` 도착 즉시 적용하고
`done/<이름>.report.json` 을 옆에 쓴다. 폴링 주기는 `OPS_INBOX_POLL`(초,
기본 10).

## env 정리

| 변수 | 기본 | 뜻 |
|---|---|---|
| `OPS_DIR` | `<STRUCTURE_STORE 부모>/ops` | rev·아웃박스·리포트가 사는 곳 |
| `OPS_RECORD` | 꺼짐 | 1 이면 쓰기 조작을 아웃박스에 기록 (이쪽 전용) |
| `OPS_ALLOW_RESTORE` | 꺼짐 | 1 이어야 `/v1/ops/restore` 가 열린다 (이쪽 전용) |
| `OPS_INBOX_DIR` | 없음 | 반입 폴더 감시 경로 (그쪽 선택) |
| `OPS_INBOX_POLL` | 10 | 감시 주기(초) |
| `LLM_BACKEND` | 자동 | `anthropic` \| `genos` — 비우면 `GENOS_LLM_URL` 유무로 |
| `GENOS_LLM_URL` | 없음 | GenOS LLM 서빙 게이트웨이 (`…/api/gateway/rep/serving/<ID>`) |
| `GENOS_LLM_KEY` | 없음 | 그 서빙의 인증키 (Bearer) |
| `GENOS_LLM_MODEL` | `/v1/models` 첫 모델 | 모델 이름 고정 |
| `GENOS_LLM_JSON_MODE` | `json_schema` | `json_schema` \| `json_object` \| `prompt` — 400 이면 자동 강등 |
| `GENOS_LLM_TEMPERATURE` | 0 | 결정성 |
| `GENOS_USER_ID` | 없음 | `x-genos-user-id` — 이용 로그에 사람을 남긴다 |
| `EMBED_BACKEND` | 자동 | `local` \| `genos` — 비우면 `GENOS_EMBED_URL` 유무로 |
| `EMBED_MODEL` | `BAAI/bge-m3` | local 백엔드의 sentence-transformers 모델 |
| `GENOS_EMBED_URL` | 없음 | GenOS 임베딩 서빙 엔드포인트 (`/v1/embeddings` 앞까지) |
| `GENOS_EMBED_KEY` | `GENOS_LLM_KEY` | 그 서빙의 인증키 (비우면 LLM 키를 같이 쓴다) |
| `GENOS_EMBED_MODEL` | `/v1/models` 첫 모델 | 모델 이름 고정 |
| `GENOS_EMBED_BATCH` | 64 | 한 요청에 보내는 문장 수 |
