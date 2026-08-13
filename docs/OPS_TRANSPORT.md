# 망분리 운반 — 스냅샷 · 아웃박스 · 재생

폐쇄망 플랫폼(GenOS)에 올라간 앱은 브라우저가 닿지 않는다 — 게이트웨이 JSON
호출만 된다. 화면은 이쪽(로컬)에서 띄우고, **상태와 조작을 파일로 나른다**.
구현은 `api/ops.py` + 진입점 `service.py`, 시험은 `tests/core/test_ops_api.py`
와 `tests/core/test_service_entry.py`.

## GenOS 계약 — 문은 하나다

GenOS 코드 서빙은 uvicorn 앱을 그대로 서빙하지 않는다. 계약은 저장소 뿌리의
`service.py` 안 `async def service(config, data)` 하나이고, 게이트웨이가

    POST https://<GenOS>/api/gateway/code_serving/<번호>/json
    Authorization: Bearer <인증키>

로 노출한다 (실측: v1.8.4 문서 usage_code_serving). 임의 경로도 정적 파일도
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
`formats` · `registry`(core/registry.yaml — 런타임에 컴파일이 고치는 파일) ·
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
