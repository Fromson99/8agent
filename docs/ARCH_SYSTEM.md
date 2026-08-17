# 시스템 아키텍처

노션: `···` → **Import** → **Markdown & CSV**

---

## 1. 계층

```mermaid
flowchart TB
  subgraph L0["입력"]
    direction LR
    I1["law.go.kr 본문 XML"]
    I2["HWP · DOCX · PDF"]
    I3["해석례 · 회신 원문"]
  end
  subgraph L1["구조화 · core/structure"]
    direction LR
    A1["lawxml<br/>태그 계층 그대로"]
    A2["from_styles<br/>Word 스타일 신뢰"]
    A3["from_format<br/>형식 바인딩"]
    A4["dp · scoring<br/>마커·타이포 유도"]
  end
  subgraph L2["저장 · data"]
    direction LR
    D1["structure/<br/>마디 트리 42문서"]
    D2["delegation.json<br/>간선 27,318"]
    D3["embeddings/sections<br/>조 단위 벡터"]
    D4["wiki/<br/>raw + 아티클"]
    D5["glossary.json<br/>용어"]
  end
  subgraph L3["질의 · core/rag"]
    direction LR
    R1["index<br/>색인"]
    R2["search<br/>어휘 사다리"]
    R3["vector<br/>의미 검색"]
    R4["graph · delegation · expand<br/>관계망"]
  end
  subgraph L4["검토 · core/casereview"]
    P1["pipeline<br/>5단계"]
  end
  subgraph L5["표면 · api"]
    direction LR
    S1["structure_app<br/>FastAPI"]
    S2["routers/ 13"]
    S3["viewer/ 10"]
  end
  I1 --> A1
  I2 --> A2
  I2 --> A3
  I2 --> A4
  A1 --> D1
  A2 --> D1
  A3 --> D1
  A4 --> D1
  D1 --> D2
  D1 --> D3
  D1 --> D5
  I3 --> D4
  D1 --> R1
  D2 --> R4
  D3 --> R3
  D5 --> R1
  R1 --> R2
  R1 --> R3
  R2 --> P1
  R3 --> P1
  R4 --> P1
  D4 --> P1
  P1 --> S2
  R1 --> S2
  S1 --> S2
  S1 --> S3
```

---

## 2. 저장 계층

```mermaid
flowchart LR
  subgraph FS["data/ — DB 없음. 파일만"]
    direction TB
    subgraph SD["구조"]
      T1["structure/&lt;doc_id&gt;/<br/>마디 트리 · span · path"]
      T2["law_index.json<br/>문서 목록"]
      T3["structure_ledger.json<br/>인제스트 원장"]
    end
    subgraph GD["연결"]
      G1["delegation.json<br/>시행령 · 위임행정규칙<br/>인용법령 · 시행규칙"]
      G2["rules/edge_rules.json<br/>간선 규칙"]
    end
    subgraph VD["검색"]
      V1["embeddings/sections/<br/>조 단위 벡터"]
      V2["glossary.json<br/>용어 1,154"]
      V3["aliases.json<br/>약칭"]
    end
    subgraph WD["해석 지식"]
      W1["wiki/raw/<br/>불변 원문"]
      W2["wiki/wiki/<br/>아티클 34"]
      W3["wiki/ledger.jsonl<br/>적중 원장"]
      W4["expc/index.json<br/>해석례 180"]
    end
    subgraph RD["평가"]
      E1["review/marked.json<br/>정답 66마디"]
      E2["review/golden_v2_run*.json"]
    end
  end
```

| 좌표 규칙 | 내용 |
|---|---|
| 마디 지정 | `(법령명, node_id)` — 법과 시행령은 별개 문서, `node_id`는 문서마다 1부터 |
| 마디 계층 | 편 · 장 · 절 · 조 · 항 · 호 · 목 |
| 부칙 | 본칙과 같은 트리에 들어오며 `path`로 구별 |
| 간선 anchor | 항·호·목까지 (`제2조제1호가목`) |

---

## 3. 모듈

```mermaid
flowchart TB
  subgraph CS["core/structure — 구조화"]
    direction LR
    CS1["pipeline"]
    CS2["lawxml · from_styles · from_format"]
    CS3["dp · scoring · lexicon · title"]
    CS4["registry · resolve · fingerprint"]
    CS5["viewer"]
  end
  subgraph CR["core/rag — 질의"]
    direction LR
    CR1["index"]
    CR2["search · vector · vecfirst"]
    CR3["graph · delegation · expand · refs"]
    CR4["answer · judge · verdicts"]
    CR5["wikictx · wikiledger · wikilife"]
    CR6["switches · rules · oql"]
  end
  subgraph CC["core/casereview — 검토"]
    direction LR
    CC1["pipeline · 5단계"]
    CC2["model · ReviewState"]
    CC3["binding"]
  end
  subgraph CT["core/terms — 용어"]
    direction LR
    CT1["build · candidates · cluster"]
    CT2["embed · embed_sections"]
    CT3["gate · judge · relations"]
  end
  CS1 --> CR1
  CT2 --> CR2
  CR1 --> CC1
  CR2 --> CC1
  CR3 --> CC1
  CR5 --> CC1
  CR6 --> CR3
```

---

## 4. 회수 경로

```mermaid
flowchart TB
  Q["쟁점"]
  Q --> B1["문면 인용 파싱<br/>refs"]
  Q --> B2["쟁점 카드 조문 후보<br/>wikictx"]
  Q --> B4["검색<br/>search + vector"]
  B1 --> C1["좌표 직행"]
  B2 --> C2["카드 좌표"]
  B4 --> L["어휘 사다리<br/>정확 → 부분 → 본문"]
  B4 --> V["의미 검색<br/>조 단위 임베딩"]
  V --> IL["_interleave<br/>의미 우선"]
  L --> IL
  C1 --> FL["관계망 동반<br/>expand_floor"]
  C2 --> FL
  FL --> E1["위임"]
  FL --> E2["수임"]
  FL --> E3["배제"]
  FL --> E4["준용"]
  C1 --> M(("합류"))
  C2 --> M
  E1 --> M
  E2 --> M
  E3 --> M
  E4 --> M
  IL --> M
  M --> AR["_article_of<br/>항·호 → 조 승격"]
  AR --> K["규범 · 상한 6"]
  M --> G["용어 정의<br/>상한 밖 glossary"]
```

| 스위치 | 대상 |
|---|---|
| `floor_delegation` | 위임 동반 |
| `floor_reception` | 수임 동반 |
| `floor_exclusion` | 배제 동반 |
| `floor_junyong` | 준용 동반 |

| 간선 방향 | 순방향 | 역방향 |
|---|---|---|
| 위임 → 시행령 | ○ | ○ |
| 수임 | ○ | ○ |
| 배제 | ○ | ○ |
| 준용 | ○ | 미구현 |

---

## 5. 검토 파이프라인

```mermaid
flowchart LR
  IN["질의 텍스트"] --> S1
  S1["extract_facts"] --> S2["spot_issues"]
  S2 --> S3["build_norms"]
  S3 --> S4["subsume"]
  S4 --> S5["interpret_case"]
  S5 --> OUT["direction<br/>basis · reason"]
  W["위키 쟁점 카드"] -.-> S2
  IDX["구조 스토어 · 색인"] -.-> S3
  NET["관계망"] -.-> S3
  IDX -.->|"마디 전문"| S5
```

| 단계 | 함수 | 입력 → 출력 | 모델 | 예산 |
|---|---|---|---|---|
| ① 사실 | `extract_facts` | 텍스트 → Fact[≤8] | Haiku 4.5 | — |
| ② 쟁점 | `spot_issues` | Fact[] + 카드 → Issue[≤4] | Haiku 4.5 | 8,000 |
| ③ 규범 | `build_norms` | Issue → Section[≤6] + glossary | 없음 | — |
| ④ 포섭 | `subsume` | Section[] + Fact[] → Req[≤18] | Haiku 4.5 | 12,000 |
| ⑤ 판정 | `interpret_case` | ReviewState + 마디 전문 → 방향·근거 | Sonnet 5 | 12,000 |

| 상수 | 값 |
|---|---|
| `NORM_SECTIONS` | 6 |
| `ISSUE_MAX` | 4 |
| `SUB_REQ_CAP` | 18 |
| `REQ_LEAF_CHARS` / `REQ_STEM_CHARS` | 260 / 400 |
| 판정 입력 절단 | 없음 (`cap=10**9`) |
| 클라이언트 타임아웃 | 120초 |

---

## 6. 상태

`ReviewState` 하나가 5단계를 관통한다.

```mermaid
flowchart LR
  subgraph RS["ReviewState"]
    direction TB
    F1["facts[]"]
    F2["issues[]"]
    F3["norms{issue: Section[]}"]
    F4["glossary[]  ← 상한 밖"]
    F5["reqs[]"]
    F6["overall{direction, basis, reason}"]
  end
  S1["① 사실"] --> F1
  S2["② 쟁점"] --> F2
  S3["③ 규범"] --> F3
  S3 --> F4
  S4["④ 포섭"] --> F5
  S5["⑤ 판정"] --> F6
  F1 -.-> S2
  F2 -.-> S3
  F3 -.-> S4
  F4 -.-> S5
  F5 -.-> S5
```

---

## 7. API 표면

```mermaid
flowchart LR
  subgraph APP["api/structure_app.py · FastAPI"]
    direction TB
    subgraph RT["routers/"]
      direction LR
      T1["/v1/structure"]
      T2["/v1/rag"]
      T3["/v1/review"]
      T4["/v1/expc"]
      T5["/v1/glossary"]
      T6["/v1/golden"]
      T7["/v1/lineage"]
      T8["/v1/formats"]
      T9["/v1/parser"]
      T10["/v1/agent · /v1/agent6"]
      T11["/v1/jobs · /v1/logs"]
    end
    subgraph VW["viewer/ · StaticFiles"]
      direction LR
      V1["/rag"]
      V2["/glossary"]
      V3["/expc"]
      V4["/golden"]
      V5["/rules"]
      V6["/links"]
      V7["/bindings"]
      V8["/agent6"]
      V9["/logs"]
      V10["/ui"]
    end
  end
  CL["브라우저 · curl"] --> RT
  CL --> VW
```

| 배포 | 내용 |
|---|---|
| 실행 | `scripts/serve.sh` + uvicorn 재시작 |
| 컨테이너 | 쓰지 않음 (`docker build` 금지) |
| 포트 | 5566 |
| DB | 없음 — `data/` 파일이 전부 |
| 스토어 위치 | `STRUCTURE_STORE` 환경변수 |

---

## 8. 규모

| 계층 | 수 |
|---|---|
| 문서 | 42 (법률 15 · 시행령 11 · 규정 9 · 시행세칙 6 · 시행규칙 1) |
| 마디 | 66,942 |
| 색인 항목 | 9,785 |
| 간선 | 27,318 (인용법령 23,352 · 시행령 2,283 · 위임행정규칙 1,251 · 시행규칙 129) |
| 위키 아티클 | 34 (쟁점 16 · 법령갈래 15 · 해석원칙 3) |
| 해석례 | 180 |
| 용어 | 1,154 |
| 라우터 · 화면 | 13 · 10 |
