"""T17. (선택) 텍스트 공리 추출기 — 본문에서 `axioms_from_text` 후보를 뽑는다 (§C5-4).

본문(role=약관본문)은 TBox 다 — 값이 아니라 **규칙**을 자연어로 서술한다(§C4).
그 규칙을 온톨로지가 쓸 수 있는 형태로 옮기는 것이 이 단계다.

**자동 승인하지 않는다.** 후보는 `approved: false` 로 나오고 사람이 검토해 켠다(§C5).
"""
from __future__ import annotations

from typing import Optional

from ontology import Ontology
from schema import Chunk

AXIOM_KINDS = ["equivalence", "default_value", "constraint", "subsumption", "derivation"]

SYSTEM = """당신은 계약서 본문 조항에서 **기계가 검증에 쓸 수 있는 규칙(공리)** 후보를 뽑는 도구다.

입력 JSON
- chunks: [{chunk_id, article, clause, text}]  — 계약서 본문 조항
- fields: 온톨로지가 이미 아는 별지1 필드명 목록
- kinds:  허용된 공리 종류. **이 밖의 값을 만들지 마라.**

무엇을 뽑는가
- equivalence   "A는 B에 기재된 것으로 한다" → A == B
                예: "신탁금액은 [별지1]에 기재된 금액으로 한다" → 신탁금액 == 별지1.신탁금액
- default_value "다만 기재하지 않을 때에는 X로 본다" → 기본값 규칙
                예: "수익자를 기재하지 않을 때에는 위탁자와 동일한 것으로 본다"
- constraint    값의 제약. 예: "신탁기간 종료일은 시작일보다 늦어야 한다"
- subsumption   "A는 B가 있는 것으로 본다" → A ⊑ B
- derivation    계산으로 유도되는 값. 예: "만기일 = 시작일 + 기간"

무엇을 뽑지 않는가
- 단순 절차·통지 의무처럼 값 검증에 쓸 수 없는 문장
- "특별한 사유가 없는 한" 처럼 정량화할 수 없는 조건만 있는 문장

지침
1. rule 은 **짧고 기계적인 표현**으로 쓴다. 자연어 문장이 아니라 수식·비교식에 가깝게.
   좋음: "신탁금액 == 별지1.신탁금액"   /   "if 수익자 is null then 수익자 := 위탁자"
   나쁨: "신탁금액은 별지1에 기재된 금액과 같아야 한다고 규정하고 있다"
2. quote 에는 근거가 된 원문을 **그대로** 옮긴다. 사람이 대조할 근거다.
3. fields 에 있는 이름을 쓸 수 있으면 그것을 쓴다.
4. 확신이 없으면 아예 만들지 마라. 잘못된 공리는 없는 것보다 나쁘다.

출력은 아래 JSON 객체 하나만. 코드펜스나 설명 문장을 붙이지 않는다.

{"axioms": [{"id": "제2조①-신탁금액정의", "source": "제2조①", "kind": "equivalence",
             "quote": "원문 그대로", "rule": "신탁금액 == 별지1.신탁금액",
             "confidence": 0.9}]}"""

BATCH = 15


def extract(chunks: list[Chunk], onto: Ontology, llm,
            limit: Optional[int] = None) -> tuple[list[dict], list[str]]:
    """→ (공리 후보 목록, 경고). 전부 approved=false 로 나온다."""
    body_role = onto.default_role()
    targets = [c for c in chunks if c.role == body_role and len(c.text) > 20]
    if limit:
        targets = targets[:limit]

    out: list[dict] = []
    warnings: list[str] = []
    known_ids = {a.id for a in onto.axioms_from_text}
    allowed = set(AXIOM_KINDS)

    for i in range(0, len(targets), BATCH):
        batch = targets[i:i + BATCH]
        payload = {
            "kinds": AXIOM_KINDS,
            "fields": list(onto.fields),
            "chunks": [{"chunk_id": c.chunk_id, "article": c.article,
                        "clause": c.clause, "text": c.text[:600]} for c in batch],
        }
        res = llm.call("extract_axioms", SYSTEM, payload)
        if not res:
            warnings.append(f"배치 {i // BATCH + 1}: 응답을 파싱하지 못했습니다")
            continue
        for a in res.get("axioms") or []:
            kind = a.get("kind")
            if kind not in allowed:
                warnings.append(f"{a.get('id')}: enum 밖의 kind '{kind}' — 버림")
                continue
            if not a.get("rule"):
                continue
            out.append({
                "id": a.get("id") or f"후보-{len(out)+1}",
                "source": a.get("source"),
                "quote": a.get("quote", ""),
                "rule": a["rule"],
                "kind": kind,
                "confidence": float(a.get("confidence") or 0.0),
                "approved": False,                      # 사람 검토 전 (§C5)
                "already_in_ontology": (a.get("id") in known_ids),
            })
    return out, warnings


def to_yaml_block(axioms: list[dict]) -> str:
    """온톨로지에 붙여 넣을 수 있는 형태로. 사람이 보고 approved 를 켠다."""
    lines = ["# T17 이 뽑은 후보 — 검토 후 approved: true 로 바꿔 온톨로지에 옮기세요",
             "axioms_from_text_candidates:"]
    for a in sorted(axioms, key=lambda x: -x["confidence"]):
        lines += [
            f"  - id: {a['id']}",
            f"    source: {a.get('source') or 'null'}",
            f"    kind: {a['kind']}",
            f"    confidence: {a['confidence']}",
            f"    quote: \"{a['quote'][:160]}\"",
            f"    rule: \"{a['rule']}\"",
            f"    approved: false",
        ]
    return "\n".join(lines)
