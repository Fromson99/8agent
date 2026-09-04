# -*- coding: utf-8 -*-
"""RAG 핵심 도판 — 큰 그림 하나 + 도메인 반영 도판들.

규칙은 scripts/arch_diagrams.py 와 같다: HTML 태그 없음 · linkStyle 없음 ·
테마 한 줄 공유 · 모양이 뜻을 따른다.
"""
INIT = ("%%{init:{'theme':'base','themeVariables':{"
        "'fontFamily':'system-ui, sans-serif','fontSize':'13px',"
        "'primaryColor':'#FFFFFF','primaryTextColor':'#1B1F24','primaryBorderColor':'#C7CFD3',"
        "'lineColor':'#96A0A7','secondaryColor':'#F1F4F5','tertiaryColor':'#FAFBFB',"
        "'clusterBkg':'#F5F8F8','clusterBorder':'#DBE1E3','edgeLabelBackground':'#FCFCFB'},"
        "'flowchart':{'curve':'basis','nodeSpacing':30,'rankSpacing':46,'padding':12}}}%%")
# 큰 그림은 여백을 더 준다
INIT_BIG = INIT.replace("'nodeSpacing':30,'rankSpacing':46", "'nodeSpacing':36,'rankSpacing':58")

SEAL  = "fill:#F7EAE6,stroke:#B8321C,stroke-width:2px,color:#7E2214"
SEAL3 = "fill:#F7EAE6,stroke:#B8321C,stroke-width:3px,color:#7E2214"
CELA  = "fill:#E3EDEA,stroke:#2C6B60,stroke-width:2px,color:#1E4F46"
CELA3 = "fill:#E3EDEA,stroke:#2C6B60,stroke-width:3px,color:#1E4F46"
GOLD  = "fill:#FBF3E2,stroke:#9A7522,stroke-width:2px,color:#6B5015"
MUTE  = "fill:#EEF1F2,stroke:#B6BFC4,color:#69737A"
KEY   = "fill:#FFFFFF,stroke:#6E7A82,stroke-width:2px"

D = {}

# ═══ 핵심 큰 그림 ═══
D["core"] = f"""{INIT_BIG}
flowchart TB
  U[/"사용자 질문<br/>구어 · 법령명도 조번호도 없다"/]
  U --> FA("① 사실 확정<br/>주체 · 행위 · 대상")

  FA --> SP("② 쟁점 도출")
  CARD["쟁점 카드 16<br/>트리거 · 판단 축 · 조문 후보"] -.->|"메뉴"| SP
  SP --> ISS["쟁점 하나<br/>question · gate · axis · card"]
  ISS --> QX[("질의 문자열<br/>question + gate")]

  QX --> T1("① 문면 좌표")
  QX --> T2("② 카드 조문 후보")
  QX --> T4("④ 검색")

  T1 --> CO["좌표 직행"]
  T2 --> GK{{"쟁점이 그 법을 말하나"}}
  GK -->|"예"| CO2["카드 좌표"]
  GK -->|"아니오"| DROP["안 연다"]

  T4 --> LEX("어휘 사다리<br/>정확 · 부분 · 본문")
  T4 --> VEC("벡터<br/>조 단위 임베딩 코사인")
  VEC --> ILV(("_interleave<br/>벡터가 앞"))
  LEX --> ILV

  CO --> FLOOR("③ 관계망 한 걸음<br/>위임 · 수임 · 배제 · 준용")
  CO2 --> FLOOR
  EDGE["간선 27,318<br/>위임 API + 문면 파싱"] -.-> FLOOR

  FLOOR --> MERGE(("합류"))
  ILV --> MERGE
  MERGE --> ART("항·호를 조로 올린다")
  ART --> NORM["규범 6 · 상한<br/>조문 마디 전문"]
  MERGE --> GLOSS["용어 정의<br/>상한 밖"]

  NORM --> REQ("요건으로 편다<br/>호 = 요건의 자연 단위")
  REQ --> SUB("④ 포섭<br/>요건마다 사실을 댄다")
  FA -.-> SUB
  SUB --> RQ["충족 · 불충족 · 불명 · 해당없음"]

  RQ --> JD("⑤ 판정")
  STORE[("구조 스토어<br/>마디 66,942")] -->|"마디 전문 · 안 자름"| JD
  GLOSS --> JD
  PRIN["해석원칙 3<br/>문언 · 엄격 · 특별규정"] -.-> JD
  JD --> OUT[("방향 · 근거 좌표 · 이유")]

  RQ -.->|"불명은 다음 쟁점으로"| SP

  style SP {SEAL3}
  style VEC {CELA}
  style FLOOR {CELA}
  style GLOSS {CELA}
  style ART {CELA}
  style DROP {SEAL}
  style CARD {GOLD}
  style PRIN {GOLD}
  style OUT {KEY}
  style NORM {KEY}
  style STORE {KEY}
  style QX {KEY}"""

# ═══ 도메인 반영 도판들 ═══
D["layers"] = f"""{INIT}
flowchart LR
  subgraph L1["법령 원문 — 무엇이라 쓰였나"]
    direction TB
    A1["마디 트리 66,942"]
    A2["간선 27,318"]
  end
  subgraph L2["해석 지식 — 어떻게 읽는가"]
    direction TB
    B1["쟁점 카드 16"]
    B2["해석원칙 3"]
    B3["법령갈래 15"]
  end
  A1 --> R("회수")
  A2 --> R
  B1 -.->|"쟁점 도출의 메뉴"| R
  B2 -.->|"판정의 배경"| R
  B3 -.-> R
  style B1 {GOLD}
  style B2 {GOLD}
  style B3 {GOLD}"""

D["card"] = f"""{INIT}
flowchart LR
  RAW[/"법제처 해석례 12건<br/>10-0236 … 25-0554"/] --> CP("LLM 세션이 컴파일")
  CP --> C1["트리거<br/>다른 법률 · 특별한 규정 · 근거<br/>목적 외 · 과세정보 · 비밀"]
  CP --> C2["판단 축<br/>정보의 종류·범위와 요건을<br/>명시하는가"]
  CP --> C3["조문 후보<br/>개보법 18조2항2호<br/>국기법 81조의13"]
  CP --> C4["판단 기준<br/>기각된 조문 9개 · 인정 1개"]
  C1 -->|"질의에 낱말이 물면"| SP("쟁점을 세운다")
  C2 -->|"판정의 잣대"| JD("판정")
  C3 -->|"사안이 그 법을 말하면"| RT("회수")
  C4 --> JD
  style C1 {GOLD}
  style C2 {GOLD}
  style C3 {GOLD}
  style C4 {GOLD}"""

D["vertical"] = f"""{INIT}
flowchart TB
  L["법 제35조제5항<br/>대통령령으로 정한다"]
  E["시행령 제41조제2항제1호<br/>정보주체가 쉽게 활용할 수 있는 방법"]
  R["감독규정<br/>금융위가 정하여 고시하는 것"]
  L -->|"위임 · lsDelegated API"| E
  E -->|"위임행정규칙 · 문서 수준까지만"| R
  R -->|"수임 · 제N조에서 …이란"| E
  E -.->|"역방향 색인"| L
  style E {CELA}
  style R {GOLD}"""

D["exclusion"] = f"""{INIT}
flowchart LR
  Q[/"질의"/] --> H["착지 조문<br/>제42조"]
  H --> A1["제42조만 읽으면<br/>적용된다"]
  X["제51조제1항 후단<br/>제42조를 적용하지 아니한다"] -.->|"역방향 배제 색인"| H
  X --> A2["배제 조항까지 읽으면<br/>적용되지 않는다"]
  A1 --> W["반대 답"]
  A2 --> C["옳은 답"]
  style W {SEAL3}
  style C {CELA}
  style X {CELA}"""

D["term"] = f"""{INIT}
flowchart LR
  T["공시대상기업집단<br/>법률용어 한 낱말"]
  T --> G("쟁점이 원문 표기 그대로 옮기면") --> G2["공시대상기업집단에 속하는<br/>회사의 부당한 이익제공 금지"] --> GO["제47조 회수"]
  T --> B("쪼개 풀어 쓰면") --> B2["공시 대상 기업집단의<br/>기업집단현황 공시 의무"] --> BO["제35조 · 제28조<br/>공시 조문으로 갔다"]
  style GO {CELA}
  style BO {SEAL}
  style G2 {CELA}
  style B2 {SEAL}"""

D["req"] = f"""{INIT}
flowchart LR
  J["제18조 조문 마디"] --> H2["② 각 호의 어느 하나"]
  H2 --> N1["1호 별도 동의"]
  H2 --> N2["2호 다른 법률에 특별한 규정"]
  H2 --> N3["3호 급박한 생명·신체"]
  N1 --> R1{{"사실을 댄다"}}
  N2 --> R2{{"사실을 댄다"}}
  N3 --> R3{{"사실을 댄다"}}
  R1 --> O1["불충족"]
  R2 --> O2["불명"]
  R3 --> O3["해당없음"]
  O2 --> FB["다음 회차 쟁점으로 승격"]
  style N2 {CELA}
  style O2 {CELA}
  style FB {GOLD}"""

D["gap"] = f"""{INIT}
flowchart TB
  J["국세기본법 제81조의13제1항제9호<br/>다른 법률의 규정에 따라 과세정보를 요구하는 경우"]
  J --> A["18-0413 공정위<br/>부정"]
  J --> B["18-0783 남양주시<br/>부정"]
  J --> C["19-0473 감사원<br/>긍정"]
  P1["선례 09-0365<br/>세무관서·과세정보를 명시해야"] -.-> A
  P1 -.-> B
  P2["선례 18-0798<br/>요구 규정은 요청과 다른 특별규정"] -.-> C
  P1 --- Z["조문에 적혀 있지 않다"]
  P2 --- Z
  style C {SEAL}
  style Z {SEAL3}
  style P1 {GOLD}
  style P2 {GOLD}"""

D["issue"] = f"""{INIT}
flowchart LR
  FA[/"사실<br/>주체 · 행위 · 대상"/] --> SP("② 쟁점 도출")
  CARD["쟁점 카드 16<br/>고를 수 있는 메뉴"] -.->|"트리거가 물면"| SP
  SP --> Q1["question<br/>Yes/No 물음"]
  SP --> Q2["gate<br/>어느 법을 볼지"]
  SP --> Q3["axis<br/>판단 축 · 카드에서"]
  SP --> Q4["regulation<br/>수평 · 수직 · 충돌"]
  SP --> Q5["confidence<br/>핵심 · 부수"]
  Q1 --> QX[("질의 문자열<br/>question + gate")]
  Q2 --> QX
  Q3 -.->|"판정의 잣대"| JD["⑤ 판정"]
  Q5 -.->|"부수는 무게를 낮춘다"| JD
  QX --> RT["③ 회수"]
  style Q1 {CELA}
  style Q2 {CELA}
  style QX {KEY}
  style CARD {GOLD}
  style Q3 {GOLD}"""
