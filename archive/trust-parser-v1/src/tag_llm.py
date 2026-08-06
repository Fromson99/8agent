"""T6. (선택) LLM 세부 의미역 태깅 — `--llm-roles` 플래그. 기본 off.

규칙 기반 태깅(role/topic/level/refs)은 이미 결정론적으로 끝나 있다.
여기서는 **그 위에 세부 의미역만 얹는다.** 고정 enum 밖의 값은 버린다.

무엇을 하지 않는가
    · role/topic/article 을 바꾸지 않는다 — 규칙이 정한 것을 LLM 이 뒤집지 않는다.
    · 정합성 판정에 관여하지 않는다(§B11-5).
"""
from __future__ import annotations

from typing import Optional

from ontology import Ontology
from schema import Chunk

# 고정 enum — 이 밖의 라벨은 버린다 (§6 T6 "유효 라벨만 허용")
SEMANTIC_ROLES = ["정의", "의무", "권리", "금지", "절차", "기한", "산식", "예외", "통지", "책임", "기타"]

SYSTEM = """당신은 한국 금융 계약서의 조항에 **세부 의미역** 하나를 붙이는 도구다.

입력 JSON
- chunks: [{chunk_id, article, article_title, clause, text}]
- allowed: 허용된 의미역 목록. **이 밖의 값을 만들지 마라.**

지침
1. 조항이 무엇을 하는 문장인지로 고른다. 주제(무엇에 관한 것인가)가 아니라 **역할**이다.
   "신탁금액은 별지1에 기재된 금액으로 한다" → 정의
   "위탁자는 …하여야 한다" → 의무
   "…할 수 있다" → 권리
   "…하지 아니한다 / 할 수 없다" → 금지
   "다음 각 호의 절차에 따라" → 절차
   "…일 이내에" → 기한
   "= A × B ÷ C" → 산식
   "다만, …인 경우에는 그러하지 아니하다" → 예외
2. 한 조항에 여러 성격이 섞이면 **가장 지배적인 것** 하나만 고른다.
3. 확신이 없으면 "기타" 를 쓰고 confidence 를 낮춘다. 억지로 고르지 마라.
4. rationale 은 한 문장 이내로 짧게.

출력은 아래 JSON 객체 하나만. 코드펜스나 설명 문장을 붙이지 않는다.

{"assignments": [{"chunk_id": "body-a02-p2", "semantic_role": "권리",
                  "confidence": 0.9, "rationale": "근거"}]}"""

BATCH = 20


def enrich(chunks: list[Chunk], onto: Ontology, llm,
           limit: Optional[int] = None) -> tuple[dict[str, dict], list[str]]:
    """→ ({chunk_id: {semantic_role, confidence, rationale}}, 경고)"""
    body_role = onto.default_role()
    targets = [c for c in chunks if c.role == body_role and c.text.strip()]
    if limit:
        targets = targets[:limit]

    out: dict[str, dict] = {}
    warnings: list[str] = []
    allowed = set(SEMANTIC_ROLES)

    for i in range(0, len(targets), BATCH):
        batch = targets[i:i + BATCH]
        payload = {
            "allowed": SEMANTIC_ROLES,
            "chunks": [{"chunk_id": c.chunk_id, "article": c.article,
                        "article_title": c.article_title, "clause": c.clause,
                        "text": c.text[:400]} for c in batch],
        }
        res = llm.call("tag_semantic_role", SYSTEM, payload)
        if not res:
            warnings.append(f"배치 {i // BATCH + 1}: 응답을 파싱하지 못했습니다")
            continue
        for a in res.get("assignments") or []:
            cid, role = a.get("chunk_id"), a.get("semantic_role")
            if not cid:
                continue
            if role not in allowed:
                warnings.append(f"{cid}: enum 밖의 의미역 '{role}' — 버림")
                continue
            out[cid] = {"semantic_role": role,
                        "confidence": float(a.get("confidence") or 0.0),
                        "rationale": a.get("rationale", "")}
    return out, warnings
