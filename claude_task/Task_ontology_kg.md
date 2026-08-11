# Task — ontology_kg 구현 계획 (자기진화 용어층 + 질의 루프)

> **진행 기록**
> - 2026-08-10 · **용어 실적(hits/misses) 배선** — 실적 기반 강등(§5.5)의
>   재료 수집 개시. 승인 용어 진입 구역이 답변에 **인용되면 hits+1**, 무관
>   지문을 받으면 **misses+1** (중립은 안 셈 — 애매함을 실적으로 굳히지
>   않는다). 상태는 안 바꾼다 — 세기만 하고, 강등은 사람/Phase 3 게이트의
>   몫. 경로: vecfirst 가 용어 병합키를 경위에 동반 → 합성 인용/지문과 대조
>   → `verdicts.score_terms` 가 glossary.json 갱신. 검수 큐·용어 상세에
>   "실적 N✓ M✗" 표시. **e2e 실증**: "전문금융소비자에게도 설명의무가 있나"
>   → 전문금융소비자(정의 조항 인용) hits+1 · 금융소비자(일반 정의 앵커,
>   무관 지문) misses+1 — 수식·문맥에 따라 용어 진입의 옳고 그름이 실적으로
>   갈리는 것이 확인됨. 부수: 호스트 uvicorn 이 5566 점유해 컨테이너가 죽어
>   있던 것 정리(컨테이너로 일원화). 스위트 317건 통과.
> - 2026-08-10 · **판정 지문 루프** (사용자 결정 — 답변 시점). KG 불완전성의
>   기록화: 합성 LLM 이 답에 쓰지 않은 "잘못 끌려온" 구역을 discard 로 찍는다
>   (무관 | 오참조 — 참조 확장 구역은 어느 간선이 데려왔는지 `ref_src` 좌표
>   동봉, 합성 1콜에 동봉이라 추가 비용 없음). 지문은 `data/rag/verdicts.jsonl`
>   append-only 적재 → RAG 뷰어 **판정 백로그**에서 간선별 묶음으로 사람이
>   승인/기각 → **승인만이 규칙이 된다**: `data/rules/edge_rules.json` 억제
>   간선 등재(증거 qid 동봉), 참조 닫힘(expand_refs)이 해당 간선을 건너뜀.
>   기각은 기록만. 모순 지문(인용한 구역을 discard) · 닫힌 번호 밖은 코드가
>   버림. e2e 실증: "설명의무가 뭐야" → 청약의철회→계약서류제공의무 간선
>   무관 지문 → 백로그 표출. **부수 발견·수리**: 컨테이너(uid 10001)와
>   호스트(jin)의 /data 소유권 혼재로 컨테이너의 지문·검수 승인 쓰기가
>   조용히 막혀 있었음 — 양측 권한 개방 + compose umask 000(개발 설정).
>   테스트 4케이스, 스위트 306건(rag·arch·core) 통과. Phase 3 연결: 승인
>   누적이 도메인/측정기 장부의 첫 실데이터가 된다.
> - 2026-08-10 · **승인 키워드 체계 + 신규 용어 추천 + 관계 보여주기** (사용자).
>   ① 검색 색인에 **활성 용어만** 참여 (색인 용어 360→65 — 잠정은 검수 큐
>   대기, 일반어 오염의 구조적 해결). 벡터 기본 흐름에 **승인 용어 정밀
>   진입** 추가(질의에 활성 용어가 통째로 있으면 그 앵커가 벡터보다 앞선다,
>   자리 상한 2 — 벡터 자리 안 뺏음). ② `python -m core.terms suggest` —
>   질의 로그 명사구를 활성·tombstone 표면형과 임베딩 코사인 대조(NEAR 0.9):
>   기각 계열 제외 / 유사→별칭 후보 / 특이→신규 추천, 결정론 가드(파편·
>   비공허성·lift 컷)를 등재 게이트와 동일 적용, 산출은 잠정 등재 → 검수
>   큐 유입(색인 불참이라 무해). ③ `GET /v1/glossary/relations` + 용어집
>   "관계" 탭 — 계층 후보 93·PROTO_REL candidate·문서 간 확정 참조를 문서
>   맥락과 함께 **보여주기 전용**으로(타이핑은 수요 확인 후). 테스트 3케이스
>   추가, 스위트 527건 통과(agent1 선재 실패 제외).
> - 2026-08-10 · **벡터 기본 전환 + 추출 무병합 결정** (사용자). ① `/ask`
>   기본 mode="vector" (벡터 미스 → 용어 사다리 자동 폴백, 뷰어 토글 기본
>   켜짐). ② **추출은 표면형별 개별 등재** — 임베딩 군집을 케노니컬로
>   병합하던 것을 중단(과병합 실증: 투자업자↔투자자). 군집은 LLM 판정 배치
>   단위로만 남고, 케노니컬·별칭은 검수 큐(사람)와 질의 루프 증거(Phase 3
>   별칭 공리)가 벌어서 만든다 — 별칭 검색의 몫은 벡터 기본이 흡수.
>   기존 데이터 마이그레이션: 통계 행 23건 표면형 축소 + 흡수분 27건 개별
>   분리 + 재훑기(용어 387·출현 20,973) + 재sweep(운용 강등). tier1 괄호약어
>   별칭(저자 선언)은 유지. 무병합 계약 테스트 추가, 스위트 통과.
> - 2026-08-10 · **벡터 우선 모드 추가** (성능 비교 실험, 사용자 요청).
>   용어 사다리는 삭제가 아니라 **모드 스위치**로 갈랐다(`mode:"vector"` —
>   A/B 없이는 성능 체크가 안 된다). 흐름: 벡터로 진입 구역 착지(entry_k=4)
>   → 참조 간선(문서 내 상호참조+links.json)을 **결정론 닫힘**(깊이≤3,
>   상한 12)으로 따라 연결 구역 전부 적재 → **출처는 회수 집합에서 정적**
>   으로 생성(LLM 인용과 무관, `refs`=전체 + `cited`=모델 인용 번호).
>   구현: `core/rag/vecfirst.py`, `/ask`·`/search`의 mode 파라미터, 뷰어
>   "벡터 우선" 토글 + 출처 뱃지(벡터/참조·인용됨), 비교 CLI
>   `python -m core.rag.bench`. 진입 착지는 여전히 `via=벡터` 승격 후보로
>   적재(자기상각 유지). **벤치 실측**: 패러프레이즈 질의에서 벡터 우선이
>   우세("가입할 때 뭘 설명해줘야" — 용어 사다리는 일반어 '가입' 선점으로
>   빈약, 벡터는 금소법 설명의무 조항 착지 + 참조 닫힘으로 청약철회·계약서류
>   제공의무까지 6구역), 정확 용어 질의는 양쪽 동등. 테스트 4케이스 추가,
>   스위트 475건 통과. 판정은 golden 축적 후 — 어느 모드가 기본이 될지는
>   Phase 2 golden 러너가 수치로 정한다.
> - 2026-08-10 · **하이브리드 벡터 단 추가** (결정 1 개정). 공용 인코더
>   `core/embedding.py`(지연 로드), 구역 벡터 컴파일 `python -m core.terms
>   embed-sections`(1,924구역 → `data/embeddings/sections/` 3.6MB, sha1 증분),
>   런타임 `core/rag/vector.py`(코사인 컷 0.45, mtime 캐시, 실패 시 조용히
>   강등). 검색 사다리 ③단을 렉시컬+벡터 **RRF(k=60) 융합**으로 개편 —
>   ①②(용어 단)는 불변, 벡터 색인·모델 없으면 기존 렉시컬 그대로(테스트
>   고정). 벡터가 찾아 답변에 실린 착지는 `via=벡터`로 승격 후보 적재.
>   e2e 실측: "돈을 맡기고 중간에 빼면 불이익이…" → 하이브리드(코사인 0.60)
>   로 중도해지·환매 구역 착지 + 후보 2건 적재. **부수 발견·수리**: 통계
>   잠정 용어 "상품"·"기간" 같은 2글자 일반어가 정확 단을 선점 → 짧은 키
>   lift 컷 강화(≤2자는 5%) + 소급 sweep(`gate.sweep`, 빌드 말미 자동) 으로
>   2건 강등. "가입"류 잔여는 검수 큐/실적 강등의 몫. 아키텍처 테스트 개정:
>   core/rag→core.terms 금지 유지 + 무거운 의존의 모듈 수준 import 금지
>   추가. 테스트 6케이스 추가, 스위트 471건 통과.
> - 2026-08-10 · **Phase 1 완료.** `core/terms/` 에 통계 깔때기 전체 구현:
>   candidates(Kiwi+품사 패턴+공기 쌍 부산물) → stats(C-value·G²·Domain
>   Consensus·헤딩 가중·Borda) → embed(BGE-M3 로컬, fp16 npz 증분 캐시) →
>   cluster(greedy cosine) → judge(haiku 배치 50 + 저신뢰 opus 에스컬레이션)
>   → gate(비공허성·변별력 15%컷·표면형 충돌) → 잠정 등재.
>   설계 개정분 반영: §5.8(a)(b) PROTO_REL 스키마+문장 공기 수집기(나열문장
>   → ⑥ 형제 증거 분기), 엣지 ⑥ 계층 후보(어휘포함+Hearst). CLI:
>   `python -m core.terms build`. **실측(문서 4건)**: 후보 8,573종 → 상위
>   400 → 군집 373 → LLM 인정 283 → 등재 269(잠정)·기각 91, 토큰 146k/36k
>   (calls 10, 에러 0, ≈$1 미만). **커버리지 공백 42%→14%** (1,924구역 중
>   811→260). PROTO_REL 6,980쌍(candidate 157 — 양의 연관만 승격하도록 G²
>   양측성 보정), 계층 후보 93. UI: 용어집 검수 큐(승인→활성/반려→tombstone,
>   `GET /v1/glossary/review`·`PATCH /terms/{key}`) + 커버리지 API. 산출:
>   out/terms/{candidates.tsv, clusters.jsonl, rel_evidence.jsonl,
>   proto_rel.json, hierarchy.json, coverage.json, embeddings/}. 테스트
>   11케이스 추가, 관련 스위트 464건 통과. 백로그: 참조 코퍼스
>   keyness(위키 덤프), Batches API 전환(1만 장 규모), ⑥ LLM 검증 배치.
> - 2026-08-10 · **Phase 0 완료.** 진단 튜플(`core/rag/tuples.py`, `/v1/rag/feedback`·
>   `/v1/rag/tuples`), Tier 1 전사(`core/terms/transcribe.py`, `python -m core.terms
>   transcribe` — 실측 98건 전사·85용어 등재·충돌 9건 게이트 차단), glossary.json
>   생애주기(status/source/scope/confidence/hits, tombstone 강등, 별칭 표면형 색인),
>   fingerprint 원장(`structure_ledger.json`, frame 동결), RAG 뷰어(`/rag/`) +
>   용어집 뱃지 + 구조 뷰어 문서군 표시. 테스트 4개 파일 신설(아키텍처 격리 가드
>   포함), 관련 스위트 454건 통과. 참고: `tests/agent1/test_golden.py` 6건은
>   이 작업 전부터 실패(투자설명서 fixture 적합도 48% 격리 — fitness_gate 선행
>   수정과 얽힘, 본 작업 import 사슬과 무관).

> 설계 원문: `ontology_kg.md`. 이 문서는 그 설계를 **현재 코드베이스 위에** 올리는 실행 계획이다.
> 코드-설계 비교 결과(2026-08-10): 루프 1(인제스천 검증·구조 귀납)은 이미 설계 수준 이상,
> 루프 2(질의 구동 진화)는 전무. 따라서 이 계획의 무게중심은 **루프 2와 용어층**이다.

---

## 0. 확정된 결정사항

1. ~~임베딩은 용어 생성 배치에서만 쓴다~~ → **개정(2026-08-10, 사용자 결정):
   질의 시점 벡터 단을 하이브리드로 허용.** 단 규율 유지 — 용어 단(정확·부분)이
   항상 먼저고, 벡터는 ③단에서 렉시컬과 RRF 융합되는 후순위이며, 벡터가 찾은
   착지는 승격 후보로 적재된다(벡터 히트 = 용어의 씨앗, 자기상각 보존).
   벡터는 여전히 DB 없이 파일(`embeddings/sections/*.npz`), 무거운 의존은
   지연 로드만(모델 없으면 렉시컬 단독 — 아키텍처 테스트 강제). 표현의
   어긋남의 **영구 해법은 여전히 별칭 승격 루프**다 — 벡터는 용어가 아직
   태어나지 않은 초반의 대비다.
2. **agent6의 임베딩·형태소 금지는 유지된다.** 신규 모듈은 전부 `core/terms/` (agent6 밖).
   역방향 보호를 위해 아키텍처 테스트 추가: `core/rag`가 `core.terms.embed`를 import하면 실패.
3. **형태소 분석기(kiwipiepy)는 컴파일 전용으로 재도입.** agent6에서 제거된 이유
   ("원금 보장 안 됩니다"→"원금보장안", 런타임 판정 안전)는 여기 해당 없음 —
   후보 생성은 뒤에 결정론 게이트 + LLM 판정 깔때기가 걸러준다. 런타임 경로 반입 금지.
4. **용어집 이원화.** `glossary/*.glossary.yaml`(사람 최우선 입력, 컴파일·구조화용)은 그대로.
   **자라는 용어층은 `data/glossary.json`** — 여기에 생애주기·출처 필드를 추가하고
   Tier1 전사·통계 추출·질의 루프 산출물이 전부 이 파일로 들어간다.
   RAG 색인(`core/rag/index.py`)이 이미 이 파일을 읽으므로 배선 변경 없음.
5. **구조 파서는 `core/structure` 계보 기준.** RAG 소스인 `out/structure/viewer/*/result.json`이
   이 계보 산출물이다. `format_induce`/`structurize` 계보는 agent1 대조 전용으로 현상 유지.
6. **저장소는 전부 파일** (jsonl/json/npz). DB 도입 없음 — 기존 links.json 방식과 일관.

## 1. 사용할 데이터 (현재 보유분)

| 데이터 | 위치 | 용도 |
|---|---|---|
| 구조화 산출 (RAG 소스) | `out/structure/viewer/*/result.json`, `data/structure/*` | Tier1 전사 입력, 청크 좌표계 |
| 규정 원문 | `agents/agent6/corpus/raw/` (KOFIA-R, KSB, KSB-D-2021) | 통계 코퍼스 |
| 법령 코퍼스 (law-crawler) | `corpus/law/` (금융투자업규정 등 XML/HTML) | 통계 코퍼스 확장 + 정의조항 전사의 노다지 |
| 계약·설명서 | `agents/agent1/data/` (B1055656A 등) | 문서군 다양성 확보 |
| 수기 용어집 | `glossary/*.glossary.yaml` ×6 | 커널 입력·충돌 검사 기준 |
| 뷰어 용어층 | `data/glossary.json` | 확장 대상 (생애주기 필드) |
| 참조 코퍼스 | 없음 | Phase 1은 참조 불필요 지표로 시작, 위키 덤프는 후순위 |

## 2. 모델 운용 계획

| 용도 | 모델 | 호출 방식 | 근거 |
|---|---|---|---|
| Tier 3 용어 배치 판정 (수천 클러스터) | `claude-haiku-4-5` | **Batches API** (50% 할인) + structured outputs | 닫힌 판정(용어인가/타입/대표명), 대량·비대화형. 예상 비용: 현 데이터 규모 $1~2 |
| 판정 에스컬레이션 (저신뢰·충돌 건만) | `claude-opus-5` | Batches | 잘못 등재의 비용이 크므로 애매한 것만 상위 모델 재판정 |
| 책임 귀속(blame, a~d 판정) | `claude-opus-5` | 동기 호출 | 저볼륨·고위험 — (c)인데 KG를 고치면 그래프 훼손 |
| 별칭·규칙 일반화(LGG 제안) | `claude-opus-5` | 동기, 제안만 (승인은 결정론 게이트) | 과잉일반화 비용이 가장 큰 지점 |
| 탐험·링크 판정·형식 유도 (기존) | `claude-opus-5` | 현행 유지 (`core/llm.py` DEFAULT_MODEL) | 변경 없음 |
| 임베딩 (디듀프 클러스터링) | **로컬 BGE-M3** (`BAAI/bge-m3`, sentence-transformers) | 배치 → `.npz` 파일 저장 | **확정(2026-08-10).** 외부 API 의존·비용 0, 한국어 성능 검증된 다국어 모델. torch 의존은 컴파일 국면 전용 — 런타임 미반입을 아키텍처 테스트로 강제. 용어 문자열 수만 건은 CPU 배치로 충분 |

공통 원칙: **LLM 출력은 전부 후보.** 등재는 결정론 게이트(§Phase 1)만 한다. 판정 스키마는
pydantic + structured outputs로 강제해 파싱 오류를 원천 차단.

## 3. 저장소 레이아웃 (신규)

```
data/
  glossary.json            # 확장: 항목별 status/source/scope/confidence/hits 추가
  rag/
    tuples/YYYYMM.jsonl    # 진단 튜플 (질의마다 자동 1건, 피드백이 갱신)
    golden.jsonl           # golden queries 회귀 스위트
    candidates.jsonl       # 승격 후보 (표현→착지 카운트)
  rules/
    aliases.jsonl          # L3 별칭 공리 장부
    routing.jsonl          # L3 라우팅 규칙 장부 (patterns.yaml의 learned 확장)
    domain.jsonl           # L3 도메인 규칙 장부
    instrument.jsonl       # L3 측정기(파서 결함) 장부 — parser_version 스코프 필수
  structure/ledger.json    # fingerprint 원장 영속화 (문서군 바인딩 동결)
out/terms/
  candidates.tsv           # Tier 2 후보 + 지표 점수 (감사용)
  clusters.jsonl           # 임베딩 클러스터 결과
  embeddings/{model}/vectors.npz + meta.jsonl   # 벡터는 여기만, 검색 경로 접근 금지
  tier1.jsonl              # 전사 산출 (등재 전 원본)
```

장부 공통 스키마: `{id, scope, provenance, confidence, evidence:[튜플id], hits, misses,
status(잠정|활성|비활성|tombstone), created, updated}`. instrument에는 `parser_version` 추가
(`ParseResult.parser` 문자열에서 추출) — 파서 업그레이드 시 자동 은퇴의 전제.

---

## Phase 0 — 배선: 첫날부터 데이터가 쌓이게 (1~2주, LLM 비용 0)

설계 문서 스스로 가장 강조한 항목: "루프는 나중에 만들어도 데이터는 첫날부터 쌓여야 한다."

### 0-1. 진단 튜플 로깅
- `core/rag/tuples.py` 신설. `/v1/rag/ask`가 **지금 만들어서 버리는** 진단 정보
  (`ladder`, `recovery.trail/path/rungs_fired`, `filter`, `refs`, `usage`)를 qid 발급 후
  `data/rag/tuples/`에 append. 응답에 qid 포함.
- `POST /v1/rag/feedback` 신설: `{qid, 판정(정답|오답), 기대: {doc,node}?, 메모?}` →
  해당 튜플에 기대_출력·실패_원인(미판정) 기록. **여기가 루프 2 전체의 입구다.**
- 탐험 성공 시 `data/rag/candidates.jsonl`에 (질의 표현 정규형 → 착지 좌표) 적재.
  즉시 승격 금지 — 적재만 한다 (표본 1 과잉일반화 방지, 설계 §5.5).

### 0-2. Tier 1 전사 (`core/terms/transcribe.py`)
입력: `out/structure/viewer/*/result.json` 블록 + `corpus/law/` 조문. 정규식 3종:
- 정의 조항 구획: 제목 `제N조(정의)` 마디 하위 항들을 정의 항목으로 파싱
- 정의 술어: `X(이)란 … 를/을 말한다`, `X(이)라 함은 … 를 말한다`
- 괄호 별칭: `본문어(약칭)`, `…(이하 "Y"라 한다)` → **문서 스코프 별칭**으로 등재
산출: `out/terms/tier1.jsonl` → 게이트(충돌 검사만) → `data/glossary.json`
등재(status=활성, source=tier1, confidence=high, scope=문서). 기존 `_scan()`으로 출현 좌표 부착.

### 0-3. glossary.json 스키마 확장
항목별 `{status, source(수기|tier1|통계|질의루프), scope, confidence, hits, misses, created}`.
기존 항목은 `source=수기, status=활성`으로 마이그레이션. `DELETE`는 실삭제 대신
`status=tombstone` (수기 입력 항목만 실삭제 허용).

### 0-4. fingerprint 원장 영속화
`data/structure/ledger.json` 신설. `api/routers/structure.py._interpret`가 ledger를
로드·전달·저장하도록 수정 (현재 미전달 → tier 항상 warm인 버그성 공백).
`may_freeze()` 소비: 동일 fingerprint 2회 관측 + fitness 통과 시 사다리(frame)를 원장에 동결,
3회째부터는 동결된 바인딩을 힌트로 주입. 힌트↔관측 불일치 경고는 기존 코드가 이미 냄.

### Phase 0 UI
- **RAG 뷰어 신설** (`api/viewer/rag/` — 현재 없음): 질의 입력 → 답변 + 근거 딥링크(기존
  구조 뷰어 딥링크 재사용) + **경로 패널**(사다리 어느 단에서 잡혔나, 탐험 시 하강 trail을
  트리로 표시) + **피드백 버튼 2개**("맞아요" → golden 후보 / "이게 아니에요" → 구조 뷰어
  트리에서 기대 구역을 클릭해 지정 → feedback POST).
- 용어집 뷰어: 항목에 생애주기 뱃지(잠정/활성/tombstone)·출처 칩 표시, 출처별 필터.
- 구조 뷰어: 문서 헤더에 fingerprint 키·관측 횟수·tier(hot/warm/cold)·동결 여부 표시.

### 완료 기준
질의 10건을 날리면 튜플 10건이 파일에 있고, 피드백 1건이 튜플을 갱신하며,
law 코퍼스에서 정의조항 용어가 자동 등재되어 검색에 잡힌다.

---

## Phase 1 — 통계 깔때기 + 임베딩 디듀프 + LLM 판정 (2~3주)

설계 §3.2 [C][D] + §4.9 스택. 전부 `core/terms/` 신설, CLI: `python -m core.terms build`.

### 1-1. 후보 생성 (`core/terms/candidates.py`)
- kiwipiepy 형태소 → 품사 패턴 화이트리스트: `NNG(+NNG)*`, `NNP`, `SL`(영문약어), `N+의+N`
- 복합명사 띄어쓰기 변이는 기존 `core/normalize.normalize_text` 정규형으로 접기
- 사용자 사전 주입: 수기 용어집 + Tier1 산출을 kiwi 사전에 넣어 도메인 용어 쪼개짐 방지

### 1-2. 점수화 (`core/terms/stats.py`) — 참조 코퍼스 불필요 지표부터
- Unithood: **C-value**(중첩 보정 — 법령 용어 지옥에 필수) + **G²**(저빈도 보완)
- 분포: Raw TF, DF(doc_coverage — 스코프 자동 판정 입력), Domain Consensus(문서 분포 엔트로피)
- 구조 가중: L1 heading 등장 후보 보너스 (TermExtractor 방식 — 우리 구조화의 고유 이점)
- 결합: **Borda 랭킹 앙상블** (가중 튜닝 대신 순위 투표)
- 후순위(백로그): 위키 덤프 확보 후 LL keyness + Log Ratio 추가
- 산출: `out/terms/candidates.tsv` (점수 근거 전부 컬럼으로 — 감사 가능)

### 1-3. 임베딩 디듀프 (`core/terms/embed.py`, `cluster.py`)
- 상위 후보 표면형을 **로컬 BGE-M3**(`BAAI/bge-m3`, sentence-transformers, CPU, dense 1024차원,
  normalize)로 배치 임베딩 → `out/terms/embeddings/bge-m3/vectors.npz` (float16 저장으로 절반 크기,
  + `meta.jsonl`: 표면형·해시·모델·일시). **재실행 시 해시 대조로 증분 임베딩.**
- 의존성은 `requirements.txt`에 "용어 추출 (컴파일 국면)" 섹션 신설: `kiwipiepy`,
  `sentence-transformers`(torch 동반), `numpy`. 런타임·배포 이미지(deploy/)에는 넣지 않는다.
  최초 실행 시 모델 가중치 ~2.3GB 다운로드(HF 캐시) — CI에서는 임베딩 단계 스킵 가능하게 플래그.
- greedy cosine threshold 클러스터링(numpy만) → `out/terms/clusters.jsonl`
- 검색 경로 격리: `tests/architecture/`에 "core/rag는 core.terms.embed를 import하지 않는다" 추가

### 1-4. LLM 배치 판정 (`core/terms/judge.py`)
- 클러스터 50개/배치 + 클러스터당 문맥 스니펫 2~3개(출현 좌표에서 절취)
- 판정 스키마(structured outputs): `{용어인가, 타입, 대표명, 별칭들, confidence, 사유}`
- 1차: haiku-4-5 + Batches. `confidence < 0.7` 또는 기존 용어와 충돌 → opus-5 재판정 큐
- **문서 전량 투입 금지** — 후보 클러스터만 본다 (기존 코드 철학과 동일)

### 1-5. 결정론 게이트 (`core/terms/gate.py`) — 등재의 유일한 문
- 비공허성: 이 용어로 실제 도달되는 청크가 존재하는가 (`_scan` 재사용)
- 변별력(lift): 후보의 출현 분포가 청크 구분에 기여하는가 — "규정"·"관리" 류 차단
- 충돌: 정규형 충돌 검사 (기존 `core/glossary.py` 표면형 충돌 로직 이식)
- 통과 → `data/glossary.json` 등재 **status=잠정**, source=통계, scope는 doc_coverage가 결정
- 잠정 용어는 검색에 참여하되 hits/misses가 쌓인다 (Phase 3 승격/강등의 연료)

### 1-6. 커버리지 공백 지도
청크당 용어 수 / 용어당 앵커 수 집계 → `out/terms/coverage.json`.
공백 크기가 곧 탐험 루프가 감당할 몫 (설계 Phase 1 검증 실험).

### Phase 1 UI
- 용어집 뷰어에 **후보 검수 큐** 탭: 클러스터 대표명 + 구성 표면형 + 문맥 스니펫 +
  지표 점수 근거 + LLM 판정 사유. 승인/거부/병합/분할 버튼 (거부=tombstone, 감사 가능).
- **커버리지 히트맵**: 문서×구역 격자에 청크당 용어 수 (구현 시 dataviz 스킬 로드).
- 잠정 용어는 뷰어에서 점선 테두리 등으로 시각 구분.

### 완료 기준
현 코퍼스에서 후보→클러스터→판정→게이트를 통과한 잠정 용어가 등재되고,
그 용어로 기존에 안 잡히던 질의가 빠른 경로에서 잡히는 사례를 3개 이상 시연.

---

## Phase 2 — 질의 루프 배선: 탐험이 자산을 낳게 (2~3주)

### 2-1. 탐험 트리거 교정
현재: `not sections`(조립 공집합)일 때만 탐험 → 렉시컬 폴백이 아무거나 잡으면 영원히 안 돎.
변경: 사다리 ①(정확)·②(부분) 미스이고 ③(본문 tf·idf)만 잡은 경우, 응답에
`weak_match=true`를 표시하고 필터 결과가 부실하면(생존 구역 0~1) 탐험을 병행 발화.
탐험 결과가 더 나으면 교체. — "용어 미스가 신호를 낳는" 설계 §1.1 복원.

### 2-2. 탐험 성공 → 후보 적재 강화 (Phase 0-1 확장)
`recover.py` 성공 경로에서 `{질의 정규형, 탐험 경로(trail), 착지 좌표, 발화 단}` 을
candidates.jsonl에 적재. 같은 (정규형, 착지) 쌍이면 count 증가 + 문서 집합 갱신.

### 2-3. golden queries (`core/rag/golden.py`)
- 적재: 피드백 "맞아요" / 승격 통과 질의 자동 등재 → `data/rag/golden.jsonl`
- 러너: `python -m core.rag.golden run` — 전 질의 재실행, 기대 refs 대조, 회귀 리포트
- 승격 게이트와 CI에서 호출 (질의 = 테스트, 설계 §5.2)

### 2-4. 책임 귀속 (`core/rag/blame.py`)
피드백(오답)이 도착하면:
1. 결정론 선별: (a) 기대 좌표를 어떤 등재 용어도 커버 안 함 → 추출 누락 후보 /
   (b) 노드는 있는데 참조·용어 연결 없음 → 연결 오류 후보 / 기대 좌표로 재검색 성공 → (c) 해석 오류 후보
2. 애매하면 opus-5 판정(닫힌 선택지 a/b/c/d + 사유), 충돌 피드백(한 사용자 정답=다른 사용자 오답)은
   자동 처리 금지 → 충돌 큐 (설계 Q&A: 충돌은 "숨은 조건 분기" 신호)
3. 판정 결과를 튜플에 기록 — **여기서 KG를 바로 고치지 않는다**

### Phase 2 UI
- RAG 뷰어에 **튜플 브라우저**: 기간·실패원인(a~d)·발화 단 필터, 튜플 클릭 →
  질의/기대/관측/탐험경로 상세. 충돌 큐 별도 탭.
- **golden 대시보드**: 총 건수, 최근 실행 pass/fail, 깨진 질의 목록(원인 튜플 링크).
- 탐험 발화율·성공률·평균 걸음 수 통계 카드 (자기상각이 되는지 눈으로 확인하는 지표).

### 완료 기준
같은 질문을 이틀 연속 던졌을 때: 첫날은 탐험(느림), 둘째 날 candidates에 적재돼 있고,
피드백 → blame → 튜플 완성까지 사람 손 없이 기록이 남는다.

---

## Phase 3 — 승격 파이프라인 + 4장부 (3~4주, 완성)

### 3-1. 승격 게이트 (`core/terms/promote.py`)
candidates.jsonl 을 배치로 돌며, 전부 통과해야 승격:
1. 동형 착지 N≥2 (질의 유래는 직접 교정보다 신호가 약함 — 설계 §5.5)
2. 변별력(lift): Phase 1 게이트 재사용
3. golden 회귀: 승격 시뮬레이션 후 전 golden 재실행, 하나라도 깨지면 반려
4. 스코프: doc_coverage가 결정 (한 문서 몰림→문서 스코프, 여러 문서군→상위)
통과 → `data/rules/aliases.jsonl` 기록 + `data/glossary.json` 별칭 등재(status=활성,
source=질의루프) + **소급 적용**: 전 문서 `_scan` 재실행으로 미신고 유사 결함 선제 수리.
군집 키는 (착지 동일성 × 원인유형 × 표면 정규형) 우선. 질의 임베딩 군집은
동일 착지에 표현이 5개 이상 쌓일 때만 배치로 수행(용어 생성 배치이므로 임베딩 허용 범위,
파일 저장 동일) — LGG 원칙: 공유하는 것만 일반화.

### 3-2. 강등 (`core/terms/demote.py`)
- 검색 히트가 필터에서 살아남으면 해당 용어 hits+1, 걸러지거나 오답 피드백 원인이면 misses+1
- `misses/(hits+misses)` 임계 초과 → status=비활성(tombstone) + 검수 큐 알림
- 승격만 있고 강등 없는 인덱스 = 과적합 캐시 (설계 '하지 말 것' 5번)

### 3-3. 4장부 완성
- **별칭 공리**: 3-1 산출
- **라우팅 규칙**: 착지가 특정 청크가 아니라 구조 패턴 공유("벌칙은 마지막 장") 군집 →
  opus-5가 규칙 초안 제안 → 사람 승인 게이트 → `patterns.yaml` learned 섹션 +
  `data/rules/routing.jsonl` (OQL 로더가 learned도 읽도록 확장, 신뢰도·강등 필드 부착)
- **도메인 규칙**: 라우팅으로 환원 안 되는 문서군 규칙 — 초기엔 수동 등재 + 장부 스키마만
- **측정기 규칙**: 탐험도 실패했는데 답이 문서에 실재(blame 결과 파서 결함) →
  `data/rules/instrument.jsonl` + 재파싱 트리거. `custom/*.yaml` 스키마에
  `parser_version` 추가, 파서 버전 변경 감지 시 해당 규칙 자동 비활성 + 재검증 큐

### Phase 3 UI
- **규칙 장부 뷰어** (RAG 뷰어 탭 또는 신설): 4장부 탭, 규칙별 신뢰도 게이지·hits/misses·
  근거 튜플 링크·스코프. 측정기 장부는 parser_version과 은퇴 상태 표시.
- **승격 보드**: 후보별 게이트 4단계 진행률(착지 카운트 n/2, lift ✓/✗, golden ✓/✗, 스코프),
  승격/반려 이력.
- 데모 화면: "어제 탐험 20초 → 오늘 빠른 경로 0.5초" 비교 + 시스템이 스스로 등재한
  용어·별칭 목록 (설계 Phase 3 데모 스토리).

### 완료 기준
오답 피드백 1건이 (튜플 → blame → 군집 → 게이트 → 별칭 등재 → 소급 적용 → golden 등재)
전 구간을 통과하고, 이후 동형 질의가 빠른 경로에서 잡힌다. 반증 도착 시 자동 강등이 동작한다.

---

## 관통 원칙 (전 Phase, 설계 §6과 동일 + 레포 관례)

1. 제안자/검증자 분리 — LLM 출력은 후보, 승인은 결정론 게이트 (기존 `core/llm.py` 계약 유지)
2. 두 장부 — domain / instrument 스키마 분리, 후자는 parser_version 스코프
3. 표본 1 일반화 금지 — 즉시 반영은 candidates 적재까지
4. 모든 자산에 provenance/scope/confidence — 스코프는 doc_coverage가 정한다
5. 모든 신규 모듈에 아키텍처 테스트 — 임베딩의 런타임 반입 금지, agent6 금지 유지

## 하지 않는 것

- ~~질의 시점 임베딩·벡터 검색~~ (개정 — 결정 1 참조. 여전히 안 하는 것:
  용어 단보다 벡터를 앞세우기, 벡터 DB 도입, 승격 루프 없는 벡터 단독 검색)
- DB 도입 (전부 파일)
- 문서당 LLM 전량 정독, 범용 서브그래프 마이닝(gSpan류)
- 탐험 1회 성공 즉시 전역 승격, 강등 없는 승격
- 완벽한 초기 온톨로지 추구 — 잠정 등재 후 사용이 판정

## 리스크와 대비

| 리스크 | 대비 |
|---|---|
| 질의 트래픽이 없어 루프 2 연료 부족 | Phase 2 완료 시 golden 시드 20~30건을 팀이 직접 작성(코퍼스 기반), 탐험·피드백 경로를 인위 구동 |
| kiwi가 도메인 복합어를 쪼갬 | 사용자 사전에 수기 용어집+Tier1 선주입, 쪼개진 후보는 C-value 중첩 보정이 흡수 |
| torch·모델 가중치(~2.3GB)가 환경을 무겁게 함 | 컴파일 국면 전용 의존으로 격리(런타임·배포 이미지 미포함), 임베딩 호출은 embed.py 인터페이스 뒤에 숨겨 모델 교체 가능하게, CI는 임베딩 스킵 플래그 |
| LLM 유령 용어 등재 | 게이트 비공허성 검사가 차단 (도달 청크 0이면 반려) — 설계가 지목한 이 단계 최대 리스크 |
| 참조 코퍼스 부재로 termhood 약함 | Domain Consensus + 구조 가중으로 시작, 위키 덤프는 백로그 |
