"""T21. 질의 정규화·분류 — 벡터 인덱스 없음 (SPEC §D1, §D2-1).

온톨로지 alias 로 질의 속 용어를 정규 필드명으로 치환하고,
값 조회형인지 해석형인지 가른다. 규칙으로 먼저 시도하고, 실패할 때만 LLM 을 부른다.

**LLM 사용은 여기 한 번뿐이며 그마저 선택이다.** 분류에 실패하면 전체 검색으로 폴백한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Optional

import comparators as cmp
from ontology import Ontology

# 값 조회형 신호 — 이 말이 들어가면 fact 직조회로 간다
VALUE_MARKERS = ["얼마", "언제", "누구", "몇", "며칠", "무엇", "뭐", "어디",
                 "금액", "기간", "날짜", "비율", "요율", "번호"]
# 해석형 신호 — 규정·조건·절차를 묻는다
EXPLAIN_MARKERS = ["어떻게", "왜", "조건", "절차", "규정", "방법", "경우",
                   "가능한", "할 수 있", "해야", "기준"]

SYSTEM = """당신은 신탁계약 질의를 라우팅하는 분류기다. 답을 만들지 마라 — **분류만** 한다.

입력 JSON
- query: 사용자 질의
- fields: 온톨로지가 아는 필드명 목록
- topics: 문서에 있는 topic 목록
- roles:  [약관본문, 별지1_입력, 별지2_변경]

지침
1. intent 는 둘 중 하나.
   "value"   — 구체적인 값을 묻는다 (얼마/언제/몇 %). fact 직조회로 답할 수 있다.
   "explain" — 규정·조건·절차를 묻는다. 조항 본문을 찾아야 한다.
2. field 는 fields 목록에 있는 것만. 해당 없으면 null.
3. topic 은 topics 목록에 있는 것만. 해당 없으면 null.
4. role 라우팅: 규정·조건을 물으면 "약관본문", 실제 계약 내용(채워진 값)을 물으면 "별지1_입력".
5. 확신이 없으면 null 로 두고 confidence 를 낮춰라. 억지로 고르면 엉뚱한 곳을 검색한다.

출력은 아래 JSON 객체 하나만. 코드펜스나 설명 문장을 붙이지 않는다.

{"intent": "value", "field": "신탁보수", "topic": null, "role": "별지1_입력",
 "keywords": ["보수", "요율"], "confidence": 0.9}"""


@dataclass
class Route:
    query: str
    intent: str = "explain"            # value | explain
    field: Optional[str] = None
    topic: Optional[str] = None
    role: Optional[str] = None
    keywords: list[str] = dc_field(default_factory=list)
    confidence: float = 0.0
    path: list[str] = dc_field(default_factory=list)     # 감사 추적


def _tokens(q: str) -> list[str]:
    out, buf = [], ""
    for ch in q:
        if ch.isalnum() or "가" <= ch <= "힣":
            buf += ch
        else:
            if len(buf) > 1:
                out.append(buf)
            buf = ""
    if len(buf) > 1:
        out.append(buf)
    return out


def classify(query: str, onto: Ontology, topics: Optional[list[str]] = None,
             llm=None) -> Route:
    r = Route(query=query, keywords=_tokens(query))
    folded = cmp.normalize_text(query)

    # 1) alias 치환 — 온톨로지 어휘로 정규 필드명 찾기 (결정론)
    idx = onto.alias_index()
    best, best_len = None, 0
    for surface, canonical in idx.items():
        if len(surface) >= 2 and surface in folded and len(surface) > best_len:
            best, best_len = canonical, len(surface)
    if best:
        r.field = best
        r.path.append(f"alias:{best}")

    # 2) 의도 판정 (결정론)
    # 해석형 신호를 먼저 본다 — "절차가 뭐야" 는 '뭐' 가 있어도 값 질문이 아니다
    if any(m in query for m in EXPLAIN_MARKERS):
        r.intent, r.confidence = "explain", 0.7
        r.path.append("intent:explain(rule)")
    elif any(m in query for m in VALUE_MARKERS):
        r.intent, r.confidence = "value", 0.8
        r.path.append("intent:value(rule)")

    if r.field and r.intent == "value":
        spec = onto.fields[r.field]
        r.role = spec.source_of_truth
        r.topic = None
        r.path.append("role:source_of_truth")
        return r

    # 3) 규칙으로 안 잡히면 LLM 분류 (선택 — 없으면 전체 검색 폴백)
    if llm is not None:
        res = llm.call("route_query", SYSTEM, {
            "query": query, "fields": list(onto.fields),
            "topics": topics or [], "roles": onto.enum("role")}, max_tokens=512)
        if res:
            if res.get("field") in onto.fields:
                r.field = res["field"]
            if topics and res.get("topic") in topics:
                r.topic = res["topic"]
            if res.get("role") in onto.enum("role"):
                r.role = res["role"]
            if res.get("intent") in ("value", "explain"):
                r.intent = res["intent"]
            r.keywords = [k for k in (res.get("keywords") or []) if k] or r.keywords
            r.confidence = float(res.get("confidence") or r.confidence)
            r.path.append("llm:classified")
        else:
            r.path.append("llm:failed→full_search")
    elif not r.field:
        r.path.append("no_llm→full_search")
    return r
