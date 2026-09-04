"""Frame/Assertion 표면형이 실제 근거 마디에서 왔는지 검증한다.

이 모듈은 Concept label의 의미가 옳다고 판정하지 않는다. Frame 추출기가 남긴
``candidate_basis.raw_slots``의 문자열이 ``source.doc_id/node`` 원문에 실제로
존재하는지만 검사한다. 따라서 canonical Concept 정렬과 source grounding은 서로
독립적인 두 게이트로 유지된다.

현재 코퍼스 크기에서는 FM-index 대신 원문 offset을 보존하는 정규화 문자열 색인을
쓴다. 판정 계약은 나중에 FM-index로 바꾸더라도 동일하다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Iterable


SLOT_ROLES = {
    "HAS_ACTOR": "ACTOR",
    "HAS_ACTION": "PREDICATE",
    "HAS_OBJECT": "OBJECT",
    "HAS_TARGET": "TARGET",
}
GRADE_RANK = {"G0": 0, "G1": 1, "G2": 2, "G3": 3}
_OPEN = {"(": ")", "[": "]", "{": "}", "（": "）", "［": "］", "｛": "｝"}
_CLOSE = set(_OPEN.values())


@dataclass(frozen=True)
class EvidenceSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class GroundingMatch:
    value: str
    role: str
    grade: str
    method: str
    spans: tuple[EvidenceSpan, ...] = ()
    confidence: float = 0.0
    source_scope: str = "node"

    def as_dict(self) -> dict:
        return asdict(self)


def _packed_with_offsets(text: str, *, drop_parenthetical: bool = False) \
        -> tuple[str, list[int]]:
    """검색용 문자열과 각 문자의 원문 offset을 함께 만든다.

    공백·문장부호·기호는 표기 차이로 보고 제거한다. NFKC/casefold 결과가 여러
    문자로 늘어나도 모두 같은 원문 offset을 가리키므로 근거 좌표를 잃지 않는다.
    ``drop_parenthetical``은 법률 술어 중간의 정의·예시 삽입만 건너뛴다.
    """
    chars: list[str] = []
    offsets: list[int] = []
    stack: list[str] = []
    for pos, original in enumerate(text or ""):
        if drop_parenthetical:
            if original in _OPEN:
                stack.append(_OPEN[original])
                continue
            if stack:
                if original == stack[-1]:
                    stack.pop()
                continue
            if original in _CLOSE:
                continue
        for char in unicodedata.normalize("NFKC", original).casefold():
            category = unicodedata.category(char)
            if char.isspace() or category[0] in {"P", "S", "Z", "C"}:
                continue
            chars.append(char)
            offsets.append(pos)
    return "".join(chars), offsets


def _segments(source: str, offsets: list[int]) -> tuple[EvidenceSpan, ...]:
    """정규화 매칭 offset을 연속된 원문 span들로 되돌린다."""
    if not offsets:
        return ()
    unique = list(dict.fromkeys(offsets))
    groups: list[tuple[int, int]] = []
    start = previous = unique[0]
    for pos in unique[1:]:
        if pos == previous + 1:
            previous = pos
            continue
        groups.append((start, previous + 1))
        start = previous = pos
    groups.append((start, previous + 1))
    return tuple(EvidenceSpan(start, end, source[start:end]) for start, end in groups)


def _packed_match(value: str, source: str, *, drop_parenthetical: bool = False) \
        -> tuple[EvidenceSpan, ...]:
    needle, _ = _packed_with_offsets(value)
    haystack, offsets = _packed_with_offsets(
        source, drop_parenthetical=drop_parenthetical)
    if not needle:
        return ()
    at = haystack.find(needle)
    if at < 0:
        return ()
    return _segments(source, offsets[at:at + len(needle)])


def _enumeration_match(value: str, source: str) -> tuple[EvidenceSpan, ...]:
    """쉼표로 명시된 추출 목록의 각 항목을 원문 순서대로 찾는다.

    조문의 ``1. A 2. B 3. C``를 Frame이 ``A, B, C``로 합친 경우를 위한
    다중-span 검사다. 임의 토큰 subsequence는 허용하지 않고, 최소 두 조각과
    충분한 전체 길이가 모두 같은 source node에 같은 순서로 존재해야 한다.
    """
    fragments = [part.strip() for part in re.split(r"[,，]", value or "")
                 if part.strip()]
    if len(fragments) < 2:
        return ()
    needles = [_packed_with_offsets(fragment)[0] for fragment in fragments]
    # 열거 내부의 ``종류, 수량, 가액``처럼 짧지만 법적으로 구별되는 항목은
    # 허용한다. 대신 목록 전체가 충분히 길고 모든 항목이 두 글자 이상이어야 한다.
    if sum(map(len, needles)) < 12 or any(len(needle) < 2 for needle in needles):
        return ()
    haystack, offsets = _packed_with_offsets(source)
    cursor = 0
    matched_offsets: list[int] = []
    for needle in needles:
        at = haystack.find(needle, cursor)
        if at < 0:
            return ()
        matched_offsets.extend(offsets[at:at + len(needle)])
        cursor = at + len(needle)
    return _segments(source, matched_offsets)


def grade_surface(value: str, source: str, *, role: str) -> GroundingMatch:
    """하나의 Frame 표면형을 같은 source node 원문에서 등급화한다.

    G3는 원문 연속 문자열, G2는 공백·문장부호·호환문자만 접은 연속 문자열이다.
    G1은 PREDICATE에 한해 괄호 삽입부를 건너뛴 동일 순서 문자열이다. 명사 역할에
    G1을 허용하면 서로 떨어진 단어를 하나의 행위자/대상으로 조립할 수 있어 막는다.
    """
    value = str(value or "").strip()
    source = str(source or "")
    if not value or not source:
        return GroundingMatch(value, role, "G0", "ungrounded")

    at = source.find(value)
    if at >= 0:
        span = EvidenceSpan(at, at + len(value), source[at:at + len(value)])
        return GroundingMatch(value, role, "G3", "exact", (span,), 1.0)

    spans = _packed_match(value, source)
    if spans:
        return GroundingMatch(value, role, "G2", "normalized", spans, 0.95)

    if role == "PREDICATE":
        spans = _packed_match(value, source, drop_parenthetical=True)
        if spans:
            return GroundingMatch(
                value, role, "G1", "parenthetical_gap", spans, 0.75)

    if role in {"PREDICATE", "OBJECT"}:
        spans = _enumeration_match(value, source)
        if spans:
            return GroundingMatch(
                value, role, "G1", "enumeration_spans", spans, 0.8)

    return GroundingMatch(value, role, "G0", "ungrounded")


def raw_slots(assertion) -> dict[str, str]:
    if isinstance(assertion, dict):
        basis = assertion.get("candidate_basis") or {}
    else:
        basis = getattr(assertion, "candidate_basis", None) or \
            (assertion.source or {}).get("candidate_basis") or {}
    rows = basis.get("raw_slots") or {}
    return {
        SLOT_ROLES[key]: str(rows.get(key) or "").strip()
        for key in SLOT_ROLES if str(rows.get(key) or "").strip()
    }


def grade_assertion(assertion, source_text: str) -> dict[str, GroundingMatch]:
    return {
        role: grade_surface(value, source_text, role=role)
        for role, value in raw_slots(assertion).items()
    }


def eligible(matches: dict[str, GroundingMatch], profile: str = "grounded") -> bool:
    """Assertion을 증명 가능한 shortcut으로 쓸 수 있는가.

    모든 추출 슬롯을 보존해야 A-B-C를 A-C로 줄일 때 조건이 사라지지 않는다.
    PREDICATE 외에 최소 하나의 명사 역할도 있어야 단순 행위 표면형 하나가 전역
    shortcut이 되는 것을 막는다.
    """
    if "PREDICATE" not in matches or len(matches) < 2:
        return False
    if profile == "exact":
        return all(match.grade == "G3" for match in matches.values())
    if profile == "grounded":
        return all(GRADE_RANK[match.grade] >= 2 for match in matches.values())
    if profile == "tolerant_action":
        return all(
            GRADE_RANK[match.grade] >= (1 if role == "PREDICATE" else 2)
            for role, match in matches.items())
    if profile == "evidence_spans":
        return all(
            GRADE_RANK[match.grade] >= (1 if role in {"PREDICATE", "OBJECT"} else 2)
            for role, match in matches.items())
    if profile == "predicate_pair":
        return (GRADE_RANK[matches["PREDICATE"].grade] >= 1
                and any(role != "PREDICATE" and GRADE_RANK[match.grade] >= 2
                        for role, match in matches.items()))
    raise ValueError(f"unknown grounding profile: {profile}")


def found_in_other_node(value: str, nodes: Iterable[tuple[object, str]], *,
                        exclude_node: object) -> bool:
    """로컬 G0가 같은 문서의 엉뚱한 조문에서 온 값인지 진단한다."""
    needle, _ = _packed_with_offsets(value)
    if not needle:
        return False
    for node, text in nodes:
        if node == exclude_node:
            continue
        haystack, _ = _packed_with_offsets(text)
        if needle in haystack:
            return True
    return False
