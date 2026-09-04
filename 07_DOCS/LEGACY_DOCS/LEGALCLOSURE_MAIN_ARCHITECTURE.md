# LegalClosure 메인 검색 구조

- 상태: **운영 기본 검색기 — 2026-08-25 배선 완료**
- 검증 프로필: 정확 구조 12 + proof/Assertion 8 + BM25 8 + 관계 폐쇄 6 + 규범참조 검증 → 최종 20
- 검증 결과: 후보 상한 70/70, v2 frozen replay 69/70, 사례 50/51 (ADR-0021)
- 운영 조립: `lawrag/core/rag/legalclosure_runtime.py`
- 검색 정책 정본: `lawrag/core/rag/legalclosure.py`
- 실험 기록: `docs/adr/0011-legal-coordinate-closure.md`

이 문서는 68/70을 만든 **동결 실험 프로필**과 현재 메인 검색기의 구조 계약을 그린다.
`POST /v1/rag/ask`에서 mode를 생략하면 `legalclosure-v2`가 실행된다. 이전
`vecfirst → combination` 경로는 `legacy-vector`와 `legacy-auto`로 보관하며,
`legalclosure_main` 스위치를 끄면 `legacy-vector`로 즉시 롤백한다.

## 1. 전체 구조

```mermaid
flowchart TB
    Q[사용자 질문 원문]
    IDX[(구조 인덱스<br/>현행·구판·조/항/호·참조 간선)]
    S[현행 기본 스코프<br/>구판 진입 제외]

    Q --> S
    IDX --> S

    subgraph A[채널 A — 정확 원문·명시 좌표 구조 탐색]
      direction TB
      A1[질문 원문 구간만 추출<br/>anchor ≤2 · 전체 용어 ≤4]
      A2[anchor 전역 정확검색<br/>조건은 anchor 문서 안에서만]
      A3[2개 이상 교집합 우선<br/>없으면 anchor 단독 완화]
      A4[명시 법령·조문 + 선택 seed 필수 보존]
      A5[입출력 참조·인접 조문 1-hop<br/>필수 관계 보존]
      A6[[정확 구조 결과 ≤12]]
      A1 --> A2 --> A3 --> A4 --> A5 --> A6
    end

    subgraph B[채널 B — proof shortcut + canonical Assertion 구조 탐색]
      direction TB
      B0{schema v1·사람 승인·proof·canonical fingerprint·고유 route 일치?}
      B00[[B0 direct ≤8]]
      B1[Concept 표면형·정의·query cue<br/>정확 구 + Kiwi 형태소]
      B2[정본 관계 1-hop<br/>IS_A · EQUIVALENT_TO · REALIZES · SATISFIES]
      B3[Assertion 근거 좌표]
      B4[문서군 후보 ≤8<br/>LLM 문서군 ≤2 → 문서 ≤2]
      B5[실제 편·장·절·조·항 닫힌 메뉴 ≤32]
      B6[[Assertion 결과 ≤8]]
      B0 -->|예| B00
      B0 -->|아니오| B1 --> B2 --> B3 --> B4 --> B5 --> B6
    end

    subgraph C[채널 C — 표현 누락 보충 BM25]
      direction TB
      C1[A의 검증 용어 + 업무 문맥 원문]
      C2[조사 제거형 추가]
      C3[검색어별 독립 BM25<br/>각 40블록 · 문서당 4]
      C4[조문 루트로 집계<br/>긴 정확 구·커버리지·BM25 순]
      C5[[BM25 조문 ≤8]]
      C1 --> C2 --> C3 --> C4 --> C5
    end

    subgraph D[채널 D — seed별 법률 관계 폐쇄]
      direction TB
      D1[seed: BM25 우선 + Assertion<br/>좌표 중복 제거 ≤16]
      D2[각 seed를 따로 1-hop 확장<br/>seed당 확장 후보 ≤12]
      D3[필수 관계 또는 질문 용어 재적중만 유지]
      D4[첫 seed 4 · 나머지 seed 1씩 우선<br/>잔여 후보 후순위 병합]
      D5[[관계 폐쇄 ≤6]]
      D1 --> D2 --> D3 --> D4 --> D5
    end

    S --> A1
    S --> B1
    A6 --> C1
    B6 --> D1
    C5 --> D1

    M{{조문 좌표 병합<br/>A → B → C → D 순서<br/>동일 doc_id·조문 중복 제거<br/>최대 20}}
    A6 -->|1순위| M
    B6 -->|2순위| M
    C5 -->|3순위| M
    D5 -->|4순위| M

    FULL[선택 조문 Heading + 전체 하위 본문<br/>조·항·호 좌표와 회수 경위]
    ANS[기존 답변 합성<br/>컨텍스트 밖 조문 생성 금지]
    OUT[답변 + 정적 출처 좌표 + 전체 audit]
    M --> FULL --> ANS --> OUT

    classDef exact fill:#e7f4ef,stroke:#26735f,stroke-width:2px,color:#174c3f;
    classDef structural fill:#e9effb,stroke:#3f68a8,stroke-width:2px,color:#27466f;
    classDef lexical fill:#fff4d9,stroke:#9a7522,stroke-width:2px,color:#684f17;
    classDef closure fill:#f4eafa,stroke:#7a4c97,stroke-width:2px,color:#523166;
    classDef seal fill:#fff,stroke:#222,stroke-width:3px,color:#111;
    class A,A1,A2,A3,A4,A5,A6 exact;
    class B,B1,B2,B3,B4,B5,B6 structural;
    class C,C1,C2,C3,C4,C5 lexical;
    class D,D1,D2,D3,D4,D5 closure;
    class M,FULL,ANS,OUT seal;
```

핵심은 네 채널을 점수 하나로 다시 섞지 않는 것이다. 정확 구조 결과를 먼저 보존하고,
Assertion·BM25·관계 폐쇄는 남은 슬롯만 채운다. 그래서 보충 채널의 잡음이 이미 찾은
직접 근거를 밀어낼 수 없다.

## 2. 채널 A — 정확 구조 탐색 상세

```mermaid
flowchart TD
    Q[질문 원문]
    E[LLM 용어 분해]
    V{원문 연속 구간인가?<br/>2자 이상 · 숫자만 아님}
    R[거부 목록에 기록]
    P[anchor ≤2<br/>condition + fallback 포함 전체 ≤4]

    X[DB 구조 해소<br/>법령명·제N조·제N-M조·제N조의M]
    XS[[명시 조문 seed<br/>mandatory]]

    G[anchor 전역 정확 원문 검색]
    GF{anchor 결과가 있는가?}
    FB[fallback을 anchor로 1회 사용]
    SD[anchor가 나온 문서 집합]
    IN[그 문서 안에서만<br/>anchor + condition + fallback 검색]

    DG[문서별 집계<br/>출처종류·시행일·개정일·원문 예시]
    DT[LLM 문서 토너먼트<br/>페이지 12 · 페이지 승자 2 · 최종 문서 3]
    AB[선택 문서 안에서도<br/>anchor가 실제 적중한 조문만]
    I{2개 이상 용어가<br/>같은 조문에 있는가?}
    TWO[교집합 조문 우선]
    ONE[anchor 적중 조문으로 완화]
    ST[LLM seed 선택<br/>페이지 12 · 승자 2 · 최종 seed 4]
    MS[[선택 seed mandatory]]

    EX[각 seed 구조 확장]
    O1[문서 안 outgoing / incoming 참조]
    O2[문서 간 outgoing / incoming 참조]
    O3[바로 앞 조문 / 바로 뒤 조문]
    MR{관계가 배제·수임·위임·준용·근거인가?}
    MUST[[mandatory — LLM 삭제 금지]]
    OPT[선택 본문 전체를 LLM 재검토]
    FINAL[[mandatory 먼저 + optional<br/>동결 실험 상한 12]]

    Q --> E --> V
    V -->|아니오| R
    V -->|예| P
    Q --> X --> XS
    P --> G --> GF
    GF -->|아니오| FB --> G
    GF -->|예| SD
    SD --> IN --> DG --> DT --> AB --> I
    I -->|예| TWO --> ST
    I -->|아니오| ONE --> ST
    ST --> MS
    XS --> EX
    MS --> EX
    EX --> O1 --> MR
    EX --> O2 --> MR
    EX --> O3 --> OPT
    MR -->|예| MUST --> FINAL
    MR -->|아니오| OPT --> FINAL

    classDef mandatory fill:#fbe7e3,stroke:#b8321c,stroke-width:3px,color:#742114;
    classDef select fill:#e7f4ef,stroke:#26735f,stroke-width:2px,color:#174c3f;
    class XS,MS,MUST mandatory;
    class P,SD,IN,TWO,ONE,ST,FINAL select;
```

### 채널 A 불변식

1. LLM이 만든 동의어·법령명·조문은 사용하지 않는다. 질문에 실제 포함된 문자열만
   검색어로 통과한다.
2. 조건어는 전역 문서를 열지 않는다. anchor가 먼저 연 문서 안에서만 작동한다.
3. 명시 조문과 선택을 통과한 정확 seed는 마지막 본문 검토자가 삭제하지 못한다.
4. 필수 법률 관계는 검색어가 직접 없더라도 보존한다.
5. `제2-4조`와 `제2조의4`는 서로 다른 좌표다.

## 3. 채널 B — Assertion 구조 탐색 상세

```mermaid
flowchart TD
    Q[질문 원문]
    S[명시 문서·조문 구조 해소]
    PIN{명시 좌표가<br/>확정됐는가?}
    CS[확정 좌표와 하위 구조로 범위 제한]

    CI[(active Concept<br/>label · alias · definition)]
    AI[(active Assertion<br/>query cue · role · source coordinate)]
    T[질문 정확 구 + Kiwi 내용 형태소]
    H1[Concept 적중]
    H2[query cue 적중]
    REL[정본 Concept 관계 1-hop]
    AH[Concept → Assertion 또는 cue → Assertion]
    COORD[Assertion source 조문 좌표]

    ROUTE{명시 구조가 있는가?}
    PF[명시 문서군·문서 고정]
    RF[독립 신호 희소도 + 역할 커버리지<br/>법·시행령·시행규칙을 문서군으로 묶음]
    TOP[문서군 후보 상위 8]
    LF[LLM 문서군 선택 ≤2]
    LD[LLM 문서 선택 ≤2]
    TREE[실제 편→장→절→조→항 트리 탐색<br/>호출당 닫힌 메뉴 ≤32]
    OUT[[선택 조·항 전체 하위 본문 ≤8]]
    REBIND[구판 내용해시 좌표이면<br/>같은 법령 현행본의 동일 조번호로 재결합]

    Q --> S --> PIN
    PIN -->|예| CS --> ROUTE
    PIN -->|아니오| ROUTE
    Q --> T
    CI --> H1
    AI --> H2
    T --> H1
    T --> H2
    H1 --> REL --> AH
    H1 --> AH
    H2 --> AH
    AI --> AH --> COORD
    CS -.->|범위 제한| COORD
    COORD --> ROUTE
    ROUTE -->|예| PF --> TREE
    ROUTE -->|아니오| RF --> TOP --> LF --> LD --> TREE
    TREE --> OUT --> REBIND

    classDef store fill:#eef1f2,stroke:#6e7a82,color:#39434a;
    classDef route fill:#e9effb,stroke:#3f68a8,stroke-width:2px,color:#27466f;
    class CI,AI store;
    class CS,AH,COORD,PF,RF,TOP,LF,LD,TREE,OUT,REBIND route;
```

Assertion 채널은 원문 BM25와 임베딩을 사용하지 않는다. 질문에서 추측한 역할이 아니라
DB Assertion에 저장된 역할과 근거 좌표만 따라간다. 명시 구조가 있으면 문서군 라우팅보다
그 좌표가 우선한다.

## 4. 채널 C·D와 최종 병합 상세

```mermaid
flowchart TD
    AT[채널 A에서 검증된 used_terms]
    CT[질문의 업무 문맥 구간]
    PS[한국어 조사 제거형<br/>으로·에서·에게·과·와·의·을·를·이·가·은·는·에·로 등]
    KW[중복 없는 검색어 목록]
    EACH[검색어를 하나씩 독립 검색]
    BM[BM25 각 40블록<br/>문서당 최대 4블록]
    AR[블록 → 소유 조문 루트]
    FORM{질문이 서식·첨부·제출을 묻는가?}
    DROP[별표·서식 후보 제외]
    KEEP[서식 후보 허용]
    RANK[일반 질문 순위<br/>긴 정확 법률구 → 정확 구 개수<br/>→ 매칭 검색어 수 → max/sum BM25]
    FRANK[서식 질문 순위<br/>max BM25 → 매칭 검색어 수 → sum BM25]
    K8[[BM25 조문 ≤8]]

    AS[Assertion 조문 ≤8]
    SEED[BM25 → Assertion 순으로 중복 제거<br/>폐쇄 seed ≤16]
    PER[seed마다 독립적으로 구조 확장 ≤12]
    EDGES[문서 안/밖 입출력 참조 + 인접 조문]
    GATE{필수 관계인가<br/>또는 질문 용어가 본문에 재적중하는가?}
    NO[폐쇄 후보에서 제외]
    SORT[mandatory 우선<br/>그다음 적중 용어 수]
    FAIR[첫 seed 4개<br/>나머지 seed 각 1개 우선<br/>잔여 후보는 후순위]
    C6[[관계 폐쇄 ≤6]]

    A12[정확 구조 ≤12]
    MERGE{{A 정확 구조<br/>→ B Assertion<br/>→ C BM25<br/>→ D 관계 폐쇄}}
    DEDUP[동일 doc_id·조문 좌표 중복 제거]
    CAP[[최종 최대 20조문]]

    AT --> KW
    CT --> PS --> KW
    KW --> EACH --> BM --> AR --> FORM
    FORM -->|아니오| DROP --> RANK
    FORM -->|예| KEEP --> FRANK
    RANK --> K8
    FRANK --> K8
    K8 --> SEED
    AS --> SEED
    SEED --> PER --> EDGES --> GATE
    GATE -->|아니오| NO
    GATE -->|예| SORT --> FAIR --> C6
    A12 --> MERGE
    AS --> MERGE
    K8 --> MERGE
    C6 --> MERGE
    MERGE --> DEDUP --> CAP

    classDef lexical fill:#fff4d9,stroke:#9a7522,stroke-width:2px,color:#684f17;
    classDef closure fill:#f4eafa,stroke:#7a4c97,stroke-width:2px,color:#523166;
    classDef seal fill:#fff,stroke:#222,stroke-width:3px,color:#111;
    class AT,CT,PS,KW,EACH,BM,AR,FORM,DROP,KEEP,RANK,FRANK,K8 lexical;
    class SEED,PER,EDGES,GATE,SORT,FAIR,C6 closure;
    class MERGE,DEDUP,CAP seal;
```

## 5. 후보 예산과 우선순위 계약

| 단계 | 상한 | 선택 방식 | 최종 병합 우선순위 |
|---|---:|---|---:|
| 정확 구조 | 12 | 명시/정확 seed 필수 + 선택 본문 LLM | 1 |
| Assertion | 8 | canonical 신호 + 닫힌 계층 메뉴 LLM | 2 |
| 균등 BM25 | 8 | 검색어별 quota 후 결정론 정렬 | 3 |
| 관계 폐쇄 | 6 | seed별 1-hop, 필수/재적중 후보 | 4 |
| 최종 | 20 | 조문 좌표 중복 제거 | - |

상한은 독립 합계 34개를 모두 출력한다는 뜻이 아니다. `A → B → C → D` 순으로
좌표를 넣다가 20개에서 닫는다. A가 12개를 사용하면 B·C·D가 경쟁하는 슬롯은 8개다.

## 6. 메인 운영 배선 목표

```mermaid
flowchart LR
    API[/POST /v1/rag/ask/]
    SCOPE[사용자 scope/documents 해소<br/>없으면 현행 기본 스코프]
    FLAG{retriever 설정}
    LC[LegalClosure<br/>검증 프로필 12·8·8·6→20]
    OLD[기존 combination 경로<br/>롤백·A/B용]
    ZERO{최종 조문이 0개인가?}
    REC[기존 회복 루프<br/>법 스코프 깔때기]
    CTX[전체 조문 본문 + 좌표 + origin + mandatory]
    ANS[답변 합성<br/>일반 관련성 필터로 다시 삭제하지 않음]
    REF[정적 출처 좌표]
    AUDIT[채널별 후보·선택·호출·토큰·지연 기록]

    API --> SCOPE --> FLAG
    FLAG -->|main| LC
    FLAG -->|rollback| OLD
    LC --> ZERO
    ZERO -->|예| REC --> CTX
    ZERO -->|아니오| CTX
    CTX --> ANS --> REF
    LC --> AUDIT
    ANS --> AUDIT

    classDef main fill:#e7f4ef,stroke:#26735f,stroke-width:3px,color:#174c3f;
    classDef rollback fill:#eef1f2,stroke:#6e7a82,color:#39434a;
    class LC,CTX,ANS,REF main;
    class OLD rollback;
```

운영 전환은 기존 `mode="vector"` 이름 아래 조용히 바꾸지 않았다. 응답의
`retriever.id=legalclosure-v2`, `status=main`에 실제 전략을 남긴다. 기존 경로는
`legacy-vector`·`legacy-auto`이며, 독립 `legalclosure_main` 스위치가 즉시 롤백을
담당한다. 옛 클라이언트의 `vector`·`auto` 값은 호환 별칭으로 받지만 결과에는
`status=archived`가 표시된다.

## 7. 운영 배선에서 해소한 코드 차이

68/70 동결 실험과 운영 호출 사이의 차이를 다음과 같이 해소했다.

1. 채널 A를 `PRIMARY_CAP=12`로 분리했다.
2. API가 적용한 사용자 scope가 있으면 `legalclosure`와 `termexplore`가 그대로 보존한다.
3. 일반 관련성 필터는 LegalClosure 좌표에 재적용하지 않는다.
4. 관계 폐쇄의 출발 좌표를 `ref_src`로 보존해 scope 밖 조문은 동반으로만 남긴다.
5. 응답·로그에 retriever ID, 채널별 선택, 모델, 토큰·지연을 남긴다.
6. 승인된 proof shortcut만 Assertion B0에서 열고 miss·중의·fingerprint 불일치는 B1로 내린다.
7. 준용·위임 질문은 선택된 `준용` 표제 조문의 직접 참조 중 질문 표제 일치가 고유한 조문만 보충한다.
8. 각 조문에 조건·예외·시점·수량·방법·효과 span과 authority/as-of 검증을 관측 메타로 붙인다.

남은 검증은 실시간 51건의 확률 단계 재실행과 자연어 답변 정답률이다. 운영 승격의
근거 수치는 frozen-stage 68/70이며, 이는 답변 정답률이 아니라 조문 회수율이다.

## 8. 코드 대응표

| 다이어그램 영역 | 코드 |
|---|---|
| 운영 의존성 조립 | `lawrag/core/rag/legalclosure_runtime.py` |
| 채널 실행·최종 병합 | `lawrag/core/rag/legalclosure.py` |
| 조문 좌표·현행본 재결합 | `lawrag/core/rag/legal_coordinates.py` |
| 채널 A 정확 구조 | `lawrag/core/rag/termexplore.py` |
| 명시 법령·조문 해소 | `lawrag/core/domain_graph/spanparts.py` |
| 채널 B Assertion | `lawrag/core/rag/assertionfirst.py` |
| B0 증명 단축경로 | `lawrag/core/rag/assertion_shortcuts.py` |
| 준용·위임 참조 verifier | `lawrag/core/rag/legal_references.py` |
| 좌표별 규범·시점 주석 | `lawrag/core/rag/legal_evidence.py` |
| 규범요건 span | `lawrag/core/domain_graph/requirements.py` |
| 시점·법원성 검증 | `lawrag/core/rag/legal_validity.py` |
| 채널 C BM25 | `lawrag/core/rag/general_search.py` |
| 참조 문법·관계 라벨 | `lawrag/core/rag/refs.py` |
| 구조·현행 스코프·간선 인덱스 | `lawrag/core/rag/index.py` |
| 답변 합성·정적 인용 | `lawrag/core/rag/answer.py` |
| API 응답 표현 | `lawrag/api/legalclosure_presenter.py` |
| API 전환 지점 | `lawrag/api/routers/rag.py` |
