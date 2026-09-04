# -*- coding: utf-8 -*-
"""아홉 도판을 한 곳에서 — 테마 한 줄을 공유해 아홉이 같은 모양으로 나온다.

쓰지 않는 것:
  <small> 등 HTML 태그  — securityLevel:strict 이면 htmlLabels:false 라 글자로 나온다
  linkStyle <인덱스>     — 간선을 하나 넣으면 번호가 밀려 엉뚱한 선이 칠해진다
모양은 뜻을 따른다:
  [/ /]  입력      [( )]  저장소     ( )  처리(둥근)
  [ ]    데이터    { }    분기       (( ))  합류
"""

INIT = ("%%{init:{'theme':'base','themeVariables':{"
        "'fontFamily':'system-ui, sans-serif','fontSize':'13px',"
        "'primaryColor':'#FFFFFF','primaryTextColor':'#1B1F24','primaryBorderColor':'#C7CFD3',"
        "'lineColor':'#96A0A7','secondaryColor':'#F1F4F5','tertiaryColor':'#FAFBFB',"
        "'clusterBkg':'#F5F8F8','clusterBorder':'#DBE1E3','edgeLabelBackground':'#FCFCFB'},"
        "'flowchart':{'curve':'basis','nodeSpacing':32,'rankSpacing':50,'padding':12}}}%%")

SEAL  = "fill:#F7EAE6,stroke:#B8321C,stroke-width:2px,color:#7E2214"
SEAL3 = "fill:#F7EAE6,stroke:#B8321C,stroke-width:3px,color:#7E2214"
CELA  = "fill:#E3EDEA,stroke:#2C6B60,stroke-width:2px,color:#1E4F46"
MUTE  = "fill:#EEF1F2,stroke:#B6BFC4,color:#69737A"
KEY   = "fill:#FFFFFF,stroke:#6E7A82,stroke-width:2px"

D = {}

D["parsers"] = f"""{INIT}
flowchart LR
  X1[/"law.go.kr 본문 XML"/] --> A1("lawxml<br/>태그를 그대로 옮긴다")
  X2[/"DOCX"/] --> A2("from_styles<br/>Word 스타일을 신뢰")
  X3[/"HWP · PDF"/] --> A3("from_format<br/>연결된 형식대로")
  X3 --> A4("dp · scoring<br/>마커·타이포로 추론")
  A1 --> T[("마디 트리")]
  A2 --> T
  A3 --> T
  A4 --> T
  style A1 {CELA}
  style A4 {SEAL}
  style T {KEY}"""

D["tree"] = f"""{INIT}
flowchart TB
  J["제18조 · 227<br/>목적 외 이용·제공 제한"]
  J --> H1["① · 228"]
  J --> H2["② · 229<br/>각 호는 예외"]
  J --> H3["③ · 240"]
  J --> H4["④ · 246"]
  H2 --> N1["1. · 230<br/>별도 동의"]
  H2 --> N2["2. · 231<br/>다른 법률에 특별한 규정"]
  H2 --> N3["3. · 232<br/>급박한 생명·신체"]
  H2 --> N4["4. · 233<br/>삭제"]
  style J {KEY}
  style N4 {MUTE}"""

D["edges"] = f"""{INIT}
flowchart LR
  subgraph SA["출처 A · API 에서 받는다"]
    direction TB
    API[/"lsDelegated XML<br/>23개 법령분"/] --> AR("양 끝을 창고 마디에 붙인다")
    AR --> AO["위임 간선<br/>시행령 · 인용법령<br/>위임행정규칙 · 시행규칙"]
  end
  subgraph SB["출처 B · 본문에서 파싱한다"]
    direction TB
    TXT[/"조문 본문"/] --> B1("① 표기를 찾는다")
    B1 --> B2("② 실존하는 데까지 내려간다")
    B2 --> B3("③ 열거를 편다")
    B3 --> B4{{"문서 안이냐 사이냐"}}
    B4 --> B5("④ 뒤 술어로 관계를 붙인다")
    B5 --> BO["문면 간선<br/>준용 · 배제 · 의제<br/>수임 · 근거 · 인용"]
  end
  style API {CELA}
  style TXT {CELA}
  style AO {KEY}
  style BO {KEY}"""

D["nodelay"] = f"""{INIT}
flowchart LR
  T[("마디 트리")] --> X1["색인 9,785항목"]
  T --> X2["조 단위 임베딩"]
  T --> X3["용어 1,154"]
  H[/"해석례 180건"/] --> W1["위키 raw · 불변층"]
  W1 -->|"LLM 세션이 컴파일"| W2["아티클 34<br/>쟁점 카드 16"]
  style T {KEY}
  style X2 {CELA}
  style W2 {CELA}"""

D["stage2"] = f"""{INIT}
flowchart LR
  U[/"사용자 질문<br/>구어 · 좌표 없음"/] --> F("① 사실 확정")
  F --> IS("② 쟁점 도출")
  IS --> RT("③ 규범 조립")
  RT --> SB("④ 포섭")
  SB --> JD("⑤ 판정")
  JD --> O[("방향 + 근거 좌표")]
  style IS {SEAL3}
  style RT {CELA}
  style O {KEY}"""

D["issue"] = f"""{INIT}
flowchart LR
  FA[/"사실"/] --> SP("② spot_issues")
  W["쟁점 카드 16<br/>고를 수 있는 메뉴"] -.-> SP
  SP --> Q1["question<br/>Yes/No 물음"]
  SP --> Q2["gate<br/>어느 법을 볼지 정한다"]
  SP --> Q3["axis<br/>판단 축"]
  SP --> Q4["card<br/>카드 슬러그"]
  Q1 --> QX[("질의 문자열<br/>question + gate")]
  Q2 --> QX
  style Q2 {CELA}
  style QX {KEY}
  style W {MUTE}"""

D["channels"] = f"""{INIT}
flowchart LR
  QX[/"질의 문자열"/]
  QX --> P1("① 문면 좌표")
  QX --> P2("② 카드 후보")
  QX --> P4("④ 검색")
  P1 --> D1["좌표 직행 · 검색 우회"]
  P2 --> GK{{"쟁점이 그 법을 말하나"}}
  GK -->|"예"| D2["카드 좌표"]
  GK -->|"아니오"| XX["안 연다"]
  P4 --> D4["어휘 + 벡터 번갈아"]
  D1 --> FL("③ 관계망 한 걸음<br/>위임·수임·배제·준용")
  D2 --> FL
  FL --> MG(("합류"))
  D4 --> MG
  MG --> K["규범 6 · 상한"]
  MG --> G["용어 정의 · 상한 밖"]
  style FL {CELA}
  style G {CELA}
  style XX {SEAL}
  style K {KEY}"""

D["search"] = f"""{INIT}
flowchart LR
  QX[/"질의 문자열"/] --> L1("정확 일치")
  L1 --> L2("부분 일치")
  L2 --> L3("본문")
  QX --> V1("질의 임베딩")
  V1 --> V2("조 단위 벡터 코사인")
  L3 --> Z(("_interleave"))
  V2 --> Z
  Z --> OUT["벡터가 앞 · 어휘가 뒤"]
  style V2 {CELA}
  style OUT {CELA}"""

D["judge"] = f"""{INIT}
flowchart LR
  N["규범 6"] --> SB("④ subsume")
  FA[/"사실"/] --> SB
  SB --> RQ["요건표<br/>충족 · 불충족 · 불명"]
  RQ --> JD("⑤ interpret_case")
  IDX[("구조 스토어")] -->|"마디 전문 · 안 자름"| JD
  GL["용어 정의"] --> JD
  JD --> O[("방향 · 근거 · 이유")]
  RQ -.->|"불명은 다음 쟁점으로"| SP["② 쟁점"]
  style JD {CELA}
  style O {KEY}
  style SP {MUTE}"""
