"""Tier 3 — LLM 배치 판정 (ontology_kg §3.4).

클러스터 50개를 한 배치로, 클러스터마다 문맥 스니펫 2~3개를 붙여 묻는다:
진짜 용어인가 / 타입은 / 대표명은 / 별칭들은. 문서 전량 투입은 하지 않는다 —
LLM 이 보는 것은 깔때기를 통과한 후보뿐이다.

모델 운용(계획 §2): 1차는 haiku(대량·닫힌 판정·effort 미지원이라 None),
저신뢰(< 0.7)만 opus 로 재판정한다 — 잘못 등재의 비용이 크므로 애매한 것만
비싼 모델이 본다.

LLM 출력은 전부 **후보**다. 등재는 gate.py 의 결정론 검사만 한다. 특히
canonical(대표명)이 실제 표면형 목록 밖이면 **무시하고 최빈 표면형을 쓴다** —
지어낸 유령 용어가 인덱스를 오염시키는 것이 이 단계 최대 리스크(§3.4).

계획 대비 갈래: Batches API(50% 할인)는 1만 장 규모의 것이다. 현 코퍼스는
배치 몇 개라 동기 호출로 충분하고, 규모가 커지면 이 모듈만 갈아끼운다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

BATCH = 50
CONF_ESCALATE = 0.7
# recover.py 와 같은 규약 — haiku 는 effort 를 받으면 400.
JUDGE_MODEL = "claude-haiku-4-5-20251001"
# 2026-08-11 사용자 결정: 전 경로 하이쿠 — 저신뢰 상향도 당분간 같은 모델로
# 두 번 본다(벤치 국면). 되돌릴 땐 opus 로 올리면 된다.
ESCALATE_MODEL = "claude-haiku-4-5-20251001"

SYSTEM = (
    "너는 도메인 용어 심사자다. 금융·법령 문서 코퍼스에서 통계로 추린 용어 후보 "
    "클러스터들이 주어진다. 각 클러스터는 {id, 표면형들, 빈도, 문서수, 스니펫들}이다.\n"
    "클러스터마다 판정하라:\n"
    "  · is_term — 도메인 용어인가? 우연한 단어 조합·일반어·문장 파편이면 false.\n"
    "  · type — 개념|기관|상품|법령|절차|수치 중 하나.\n"
    "  · canonical — 대표 표면형. **반드시 주어진 표면형 중에서** 골라라. 새로 짓지 마라.\n"
    "  · aliases — 표면형들 중 canonical 의 별칭인 것들.\n"
    "  · confidence — 판정 확신 0~1.\n"
    "모든 클러스터에 답하라. 모르면 is_term=false 에 낮은 confidence 로."
)

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "is_term": {"type": "boolean"},
            "type": {"type": "string",
                     "enum": ["개념", "기관", "상품", "법령", "절차", "수치"]},
            "canonical": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["id", "is_term", "type", "canonical", "aliases",
                     "confidence", "reason"],
        "additionalProperties": False}}},
    "required": ["items"],
    "additionalProperties": False,
}


@dataclass
class Verdict:
    cluster: int
    is_term: bool
    type: str = ""
    canonical: str = ""
    aliases: list = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    model: str = ""


def _payload(cid: int, surfaces: list[str], tf: int, df: int,
             snippets: list[str]) -> dict:
    return {"id": cid, "표면형들": surfaces[:8], "빈도": tf, "문서수": df,
            "스니펫들": snippets[:3]}


def judge(llm, clusters: list[dict]) -> dict[int, Verdict]:
    """clusters: [{id, surfaces, tf, df, snippets}] → {id: Verdict}.
    llm 이 None 이면 빈 결과 — 호출부가 무판정 등재(잠정)로 내려간다."""
    out: dict[int, Verdict] = {}
    if llm is None or not clusters:
        return out

    def ask(batch: list[dict], model: str, effort: Optional[str]) -> None:
        res = llm.structured(
            "용어판정", SYSTEM,
            json.dumps([_payload(c["id"], c["surfaces"], c["tf"], c["df"],
                                 c["snippets"]) for c in batch],
                       ensure_ascii=False),
            SCHEMA, max_tokens=16000, effort=effort, model=model)
        ids = {c["id"] for c in batch}
        for item in (res or {}).get("items", []):
            if item.get("id") not in ids:          # 닫힌 후보 밖 — 버린다
                continue
            out[item["id"]] = Verdict(
                cluster=item["id"], is_term=bool(item.get("is_term")),
                type=item.get("type", ""), canonical=item.get("canonical", ""),
                aliases=list(item.get("aliases") or []),
                confidence=float(item.get("confidence") or 0.0),
                reason=item.get("reason", ""), model=model)

    for i in range(0, len(clusters), BATCH):
        ask(clusters[i:i + BATCH], JUDGE_MODEL, None)

    # 저신뢰·무응답만 opus 재판정 — 애매한 것에만 비싼 모델을 쓴다
    unsure = [c for c in clusters
              if c["id"] not in out or out[c["id"]].confidence < CONF_ESCALATE]
    for i in range(0, len(unsure), BATCH):
        ask(unsure[i:i + BATCH], ESCALATE_MODEL, "high")
    return out
