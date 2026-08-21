"""사용자 표현을 1급 Concept 후보에 공동 정렬한다.

LLM은 Concept ID를 생성하지 않는다. 코드가 만든 닫힌 후보 메뉴의 번호와 허용된
intent/role만 고른다. 이미 같은 active Assertion에 있는 후보 조합은 함께 승점이
올라간다 — 낱말을 서로 독립적으로 고르지 않는 이유다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .tier1 import Tier1Concept, Tier1Registry


INTENTS = (
    "RELATION_BETWEEN_CONCEPTS", "ASSERTIONS_FOR_CONCEPT",
    "ACTOR_OBLIGATIONS", "ACTIONS_ON_OBJECT", "CONCEPT_DEFINITION",
)
QUERY_ROLES = ("actor", "action", "object", "target", "method", "modality", "unknown")

ALIGN_SYSTEM = (
    "너는 사용자 질문을 **승인된 Concept 메뉴**에 정렬한다. 새 용어·Concept ID를 "
    "만들지 말고 메뉴 번호만 고른다. 질문에서 실제로 뜻하는 후보만 picks에 넣고, "
    "각 후보가 맡는 role을 닫힌 목록에서 고른다. 약칭·구어를 표준 Concept에 연결하되 "
    "애매하면 고르지 않는다. intent도 주어진 enum에서만 고른다."
)
ALIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "picks": {"type": "array", "items": {
            "type": "object",
            "properties": {"idx": {"type": "integer"},
                           "role": {"type": "string", "enum": list(QUERY_ROLES)}},
            "required": ["idx", "role"], "additionalProperties": False,
        }},
    },
    "required": ["intent", "picks"], "additionalProperties": False,
}


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def _grams(value: str) -> set[str]:
    value = _pack(value)
    if len(value) < 2:
        return {value} if value else set()
    return {value[i:i + 2] for i in range(len(value) - 1)}


def _spans(question: str) -> list[str]:
    words = re.findall(r"[가-힣A-Za-z0-9]+", question)
    out = list(words)
    for width in (2, 3):
        out.extend(" ".join(words[i:i + width])
                   for i in range(max(0, len(words) - width + 1)))
    out.append(question)
    return list(dict.fromkeys(x for x in out if len(_pack(x)) >= 2))


@dataclass
class Candidate:
    concept_id: str
    label: str
    concept_type: str
    score: float
    matched: str
    via: str
    role: str = "unknown"

    def as_dict(self) -> dict:
        return {"concept_id": self.concept_id, "label": self.label,
                "type": self.concept_type, "score": round(self.score, 3),
                "matched": self.matched, "via": self.via, "role": self.role}


@dataclass
class Alignment:
    question: str
    candidates: list[Candidate] = field(default_factory=list)
    selected: list[Candidate] = field(default_factory=list)
    intent: str = "ASSERTIONS_FOR_CONCEPT"
    via: str = "deterministic"
    ambiguous: bool = False

    def as_dict(self) -> dict:
        return {"intent": self.intent, "via": self.via, "ambiguous": self.ambiguous,
                "candidates": [c.as_dict() for c in self.candidates],
                "selected": [c.as_dict() for c in self.selected]}


class ConceptAligner:
    def __init__(self, registry: Tier1Registry):
        self.registry = registry

    def candidates(self, question: str, cap: int = 24) -> list[Candidate]:
        packed_q, spans = _pack(question), _spans(question)
        out = []
        for concept in self.registry.active_concepts.values():
            negative = [s for s in concept.negative_aliases if _pack(s) in packed_q]
            if negative:
                continue
            best = (0.0, "", "")
            for pos, surface in enumerate(concept.surfaces):
                ps = _pack(surface)
                if len(ps) < 2:
                    continue
                if ps in packed_q:
                    score = 1.0 if pos == 0 else 0.96
                    cand = (score, surface, "label" if pos == 0 else "alias")
                    if cand[0] > best[0]:
                        best = cand
                    continue
                sg = _grams(surface)
                for span in spans:
                    qg = _grams(span)
                    if not qg or not sg:
                        continue
                    containment = len(qg & sg) / len(qg)
                    precision = len(qg & sg) / len(sg)
                    score = 0.62 * containment + 0.38 * precision
                    if score > best[0]:
                        best = (score, surface, "profile")
            if best[0] >= 0.58:
                out.append(Candidate(concept.id, concept.label, concept.type,
                                     best[0], best[1], best[2]))
        # 함께 존재하는 Assertion은 후보 조합의 정합성 신호다. 후보 하나가 같은
        # Assertion 안의 둘 이상의 후보와 이어져도 보너스는 한 번만 준다. 예컨대
        # ``금융투자회사 + 투자 설명서``가 actor/document/action 세 후보를 만들 때
        # 예전 코드는 +graph를 두 번 붙여 약한 action 후보를 1.0으로 만들었다.
        graph_connected = set()
        for i, left in enumerate(out):
            for right in out[i + 1:]:
                if self.registry.shared_assertions({left.concept_id, right.concept_id}):
                    graph_connected.update((left.concept_id, right.concept_id))
        for candidate in out:
            if candidate.concept_id in graph_connected:
                candidate.score = min(1.0, candidate.score + 0.10)
                candidate.via += "+graph"
        out.sort(key=lambda c: (-c.score, c.label, c.concept_id))
        return out[:cap]

    def align(self, question: str, *, llm=None) -> Alignment:
        candidates = self.candidates(question)
        result = Alignment(question, candidates=candidates)
        if not candidates:
            return result

        # 같은 1급 Assertion에 있는 고득점 쌍은 LLM 없이 공동 정렬된다.
        connected = []
        for i, left in enumerate(candidates):
            for right in candidates[i + 1:]:
                if min(left.score, right.score) >= 0.68 and \
                        self.registry.shared_assertions({left.concept_id, right.concept_id}) and \
                        (not left.via.startswith("profile") or
                         not right.via.startswith("profile")):
                    # label/alias로 직접 물린 쌍을 profile 추정 쌍보다 먼저 고른다.
                    # 합산 점수만 보면 그래프 보너스를 받은 약한 세 번째 후보와의
                    # 쌍이 동률이 되어 정상 질의가 '중의적'으로 탈락할 수 있다.
                    anchors = sum(not c.via.startswith("profile") for c in (left, right))
                    connected.append((anchors, left.score + right.score, left, right))
        if connected:
            connected.sort(key=lambda row: (-row[0], -row[1], row[2].concept_id,
                                             row[3].concept_id))
            anchors, joint_score, left, right = connected[0]
            result.selected = [left, right]
            result.intent = "RELATION_BETWEEN_CONCEPTS"
            result.ambiguous = len(connected) > 1 and \
                anchors == connected[1][0] and joint_score - connected[1][1] < 0.08
            return result

        strong = [c for c in candidates if c.score >= 0.90]
        if len(strong) == 1 and (len(candidates) == 1 or strong[0].score - candidates[1].score >= 0.12):
            result.selected = strong
            result.intent = self._intent(question, strong)
            return result

        if llm is not None:
            menu = "\n".join(
                f"{i}. {c.label} | type={c.concept_type} | matched={c.matched} | "
                f"score={c.score:.2f}" for i, c in enumerate(candidates, 1))
            out = llm.structured("rag.concept_alignment", ALIGN_SYSTEM,
                                 f"[질문]\n{question}\n\n[Concept 메뉴]\n{menu}",
                                 ALIGN_SCHEMA, max_tokens=500, effort="low")
            if out is not None:
                selected, seen = [], set()
                for pick in out.get("picks", [])[:6]:
                    idx = pick.get("idx")
                    if not isinstance(idx, int) or not 1 <= idx <= len(candidates) or idx in seen:
                        continue
                    seen.add(idx)
                    cand = candidates[idx - 1]
                    cand.role = pick.get("role") or "unknown"
                    selected.append(cand)
                if selected:
                    result.selected = selected
                    result.intent = out.get("intent") if out.get("intent") in INTENTS \
                        else self._intent(question, selected)
                    result.via = "closed_menu_llm"
                    result.ambiguous = (any(c.score < 0.72 for c in selected)
                                        or all(c.via.startswith("profile") for c in selected))
                    return result

        result.selected = [c for c in candidates if c.score >= 0.90][:4]
        if not result.selected and candidates[0].score >= 0.72 and \
                not candidates[0].via.startswith("profile"):
            result.selected = [candidates[0]]
            result.ambiguous = True
        result.intent = self._intent(question, result.selected)
        return result

    @staticmethod
    def _intent(question: str, selected: list[Candidate]) -> str:
        if len(selected) >= 2:
            return "RELATION_BETWEEN_CONCEPTS"
        if re.search(r"무엇|뭐|뜻|정의", question):
            return "CONCEPT_DEFINITION"
        if re.search(r"의무|해야|하여야|책임", question):
            return "ACTOR_OBLIGATIONS"
        return "ASSERTIONS_FOR_CONCEPT"
