"""법령 원문에서 구성요건 qualifier의 근거 span을 보수적으로 표시한다.

의미를 새로 생성하지 않는다. 조건·예외·시간·수치·방법·효과를 나타내는 닫힌
표지와 그 표지가 속한 원문 절을 반환한다. 이 결과는 Concept 자동 승격이 아니라
Requirement 후보와 Evidence Auditor 입력을 위한 shadow 자료다.
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import asdict, dataclass, field
from typing import Iterable


KINDS = ("CONDITION", "EXCEPTION", "TIME", "QUANTITY", "METHOD", "EFFECT")

_TRIGGERS = {
    "CONDITION": re.compile(r"경우|때에는|때에는|때|한하여|요건|요구되는|해당하면|해당하는"),
    "EXCEPTION": re.compile(r"다만|에도 불구하고|제외한다|제외되는|그러하지 아니하다|예외"),
    "METHOD": re.compile(r"서면|전자문서|전자우편|신고서|제출하여|제출해야|결의|승인|인가|통지|공시"),
    "EFFECT": re.compile(r"무효|취소|효력이|효력을|로 본다|으로 본다|간주|책임을 진다|과태료|벌금|처분할 수"),
}
_QUANTITY = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:퍼센트|%|원|만원|억원|조원|명|인|회|개|주|일|개월|년)"
    r"|\d+분의\s*\d+|100분의\s*\d+|과반수|3분의\s*2|3분의\s*1)"
)
_TIME = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:일|개월|년)\s*(?:이내|이상|이하|전|후|동안|경과)?"
    r"|기준일|시행일|영업일|과세기간|사업연도|회계연도|납입기일|제출기한)"
)
_BOUNDARY = re.compile(r"[\n。]|(?<=[다요])\.(?=\s|$)|(?<=한다)\.(?=\s|$)")

# 단서는 단순 EXCEPTION 키워드보다 좁은 구조 단위다. 원문 offset을 잃지 않은 채
# 물리적 부착 범위와 법적 효과를 따로 발행한다. ``에도 불구하고``는 앞 문장을
# 뒤집을 수 있고, ``다만``은 뒤 본문을 읽어야 효과가 정해지므로 cue와 effect를
# 분리한다.
_PROVISO_CUE = re.compile(
    r"다만(?:\s*[,，])?|(?:그럼에도\s+)?불구하고|"
    r"그러하지\s+아니하(?:다|며|고)|예외로\s+한다|제외한다"
)
_SENTENCE_END = re.compile(r"(?:한다|된다|아니하다|있다|없다|본다|따른다|정한다|"
                           r"제외한다|갈음한다|적용한다|준용한다)[.。](?=\s|$)")
_EXCLUSION_EFFECT = re.compile(
    r"제외|그러하지\s+아니|적용하지\s+아니|의무보유하지\s+아니|예외"
)
_OVERRIDE_EFFECT = re.compile(r"불구하고")
_TERMINAL_EFFECT_CUE = re.compile(r"그러하지|예외로|제외한다")


@dataclass(frozen=True)
class RequirementSpan:
    kind: str
    surface: str
    start: int
    end: int
    trigger: str
    trigger_start: int
    trigger_end: int

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProvisoSpan:
    """원문 블록 안의 단서와 그 부착 범위.

    ``parent_*``는 원문상 붙는 주된 규율의 가장 좁은 보수적 span이다. 문장 처음의
    ``다만``처럼 같은 문장 안에 앞부분이 없으면 직전 문장을 사용한다. 같은 절에
    cue가 둘 이상이면 실제 중첩을 추정하지 않고 ``ambiguous_multiple_cues``로 남긴다.
    """

    proviso_id: str
    doc_id: str
    node: object
    article: object
    block: object
    cue: str
    cue_start: int
    cue_end: int
    body: str
    body_start: int
    body_end: int
    parent_text: str
    parent_start: int
    parent_end: int
    effect_kind: str
    scope_status: str
    scope_depth: int
    source_sha256: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SlotEvidence:
    evidence_id: str
    text: str
    doc_id: str = ""
    node: object | None = None
    block: object | None = None
    start: int | None = None
    end: int | None = None
    predicates: tuple[str, ...] = ()


@dataclass(frozen=True)
class PredicateBridge:
    source_predicate: str
    target_predicate: str
    relation: str
    evidence_id: str
    verified: bool = False


@dataclass(frozen=True)
class ConditionSlot:
    slot_id: str
    predicate: str
    expected: bool = True
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlotJudgement:
    slot_id: str
    predicate: str
    value: str
    evidence_ids: tuple[str, ...] = ()
    bridge_ids: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class SlotGateResult:
    judgements: tuple[SlotJudgement, ...]
    proposed_values: tuple[tuple[str, str], ...]
    overridden_slot_ids: tuple[str, ...]
    unknown_slot_ids: tuple[str, ...]
    presentation_allowed: bool
    answer_mode: str


_BRIDGE_ALLOWLIST = frozenset({
    "DEFINES", "ALIASES_AS", "DEEMS_AS", "SUBSTITUTES_FOR",
})


def _clauses(text: str):
    start = 0
    for match in _BOUNDARY.finditer(text or ""):
        end = match.start()
        if (text[start:end]).strip():
            yield start, end, text[start:end]
        start = match.end()
    if (text[start:]).strip():
        yield start, len(text), text[start:]


def _trim(source: str, start: int, end: int) -> tuple[int, int, str]:
    raw = source[start:end]
    left = len(raw) - len(raw.lstrip())
    right = len(raw.rstrip())
    start += left
    end = start + max(0, right - left)
    return start, end, source[start:end]


def _sentence_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges, start = [], 0
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        if text[start:end].strip():
            ranges.append((start, end))
        start = end
    if text[start:].strip():
        ranges.append((start, len(text)))
    return tuple(ranges)


def _effect(cue: str, body: str) -> str:
    value = f"{cue} {body}"
    if _OVERRIDE_EFFECT.search(cue):
        return "OVERRIDES_RULE"
    if _EXCLUSION_EFFECT.search(value):
        return "EXCEPTION_TO"
    return "QUALIFIES_RULE"


def extract_provisos(text: str, *, doc_id: str, node: object, article: object,
                     block: object) -> tuple[ProvisoSpan, ...]:
    """블록 원문에서 단서 cue/body/부착 parent의 정확 offset을 반환한다."""
    text = str(text or "")
    raw_matches = list(_PROVISO_CUE.finditer(text))
    if not raw_matches:
        return ()
    sentences = _sentence_ranges(text)
    matches = []
    for match in raw_matches:
        sent_lo, _sent_hi = next(
            ((lo, hi) for lo, hi in sentences if lo <= match.start() < hi),
            (0, len(text)))
        # ``다만 ... 제외한다``의 끝말은 새로운 단서가 아니라 앞 cue의 효과다.
        if (_TERMINAL_EFFECT_CUE.search(match.group(0))
                and any(sent_lo <= prior.start() < match.start()
                        for prior in raw_matches)):
            continue
        matches.append(match)
    out: list[ProvisoSpan] = []
    for position, cue_match in enumerate(matches):
        sentence_index = next(
            (i for i, (lo, hi) in enumerate(sentences)
             if lo <= cue_match.start() < hi), len(sentences) - 1)
        sent_lo, sent_hi = sentences[sentence_index]
        next_cue = matches[position + 1].start() if position + 1 < len(matches) else sent_hi
        body_end = min(sent_hi, next_cue)
        body_start, body_end, body = _trim(text, cue_match.end(), body_end)

        # cue 앞에 같은 문장의 실질 문면이 있으면 그것이 가장 좁은 parent다.
        # 문장 첫머리의 단서는 직전 문장에 붙이고, 그것도 없으면 구조 node 자체에
        # 붙도록 빈 span을 명시한다.
        parent_start, parent_end, parent_text = _trim(
            text, sent_lo, cue_match.start())
        if not parent_text and sentence_index > 0:
            parent_start, parent_end = sentences[sentence_index - 1]
            parent_start, parent_end, parent_text = _trim(
                text, parent_start, parent_end)

        cue_count = sum(1 for item in matches if sent_lo <= item.start() < sent_hi)
        status = "ambiguous_multiple_cues" if cue_count > 1 else (
            "attached_previous_sentence" if cue_match.start() == sent_lo or not
            text[sent_lo:cue_match.start()].strip() else "attached_same_sentence")
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        pid_payload = "\x1f".join(map(str, (
            doc_id, node, block, cue_match.start(), cue_match.end(), source_hash)))
        proviso_id = "proviso:" + hashlib.sha256(
            pid_payload.encode("utf-8")).hexdigest()[:24]
        out.append(ProvisoSpan(
            proviso_id=proviso_id, doc_id=doc_id, node=node, article=article,
            block=block, cue=cue_match.group(0), cue_start=cue_match.start(),
            cue_end=cue_match.end(), body=body, body_start=body_start,
            body_end=body_end, parent_text=parent_text,
            parent_start=parent_start, parent_end=parent_end,
            effect_kind=_effect(cue_match.group(0), body),
            scope_status=status, scope_depth=1, source_sha256=source_hash,
        ))
    return tuple(out)


def validate_condition_slots(
        slots: Iterable[ConditionSlot], evidence: Iterable[SlotEvidence],
        bridges: Iterable[PredicateBridge] = ()) -> tuple[SlotJudgement, ...]:
    """결합요건을 독립 판정한다. 명시 근거·검증 bridge가 없으면 ``unknown``이다."""
    evidence_by_id = {row.evidence_id: row for row in evidence}
    bridge_rows = tuple(bridges)
    out = []
    for slot in slots:
        cited = tuple(row for row in (evidence_by_id.get(key)
                                      for key in slot.evidence_ids) if row is not None)
        direct = tuple(row.evidence_id for row in cited
                       if slot.predicate in row.predicates)
        used_bridges = []
        bridged_evidence = []
        if not direct:
            available = {predicate for row in cited for predicate in row.predicates}
            for bridge in bridge_rows:
                if (bridge.verified and bridge.relation in _BRIDGE_ALLOWLIST
                        and bridge.source_predicate in available
                        and bridge.target_predicate == slot.predicate
                        and bridge.evidence_id in evidence_by_id
                        and bridge.evidence_id in slot.evidence_ids):
                    used_bridges.append(bridge.evidence_id)
                    bridged_evidence.append(bridge.evidence_id)
        supporting = direct or tuple(dict.fromkeys(bridged_evidence))
        value = ("true" if slot.expected else "false") if supporting else "unknown"
        reason = ("exact_predicate_evidence" if direct else
                  "verified_predicate_bridge" if supporting else
                  "no_exact_evidence_or_verified_bridge")
        out.append(SlotJudgement(
            slot_id=slot.slot_id, predicate=slot.predicate, value=value,
            evidence_ids=tuple(supporting),
            bridge_ids=tuple(dict.fromkeys(used_bridges)), reason=reason))
    return tuple(out)


def apply_slot_post_gate(
        proposed_values: dict[str, str], slots: Iterable[ConditionSlot],
        evidence: Iterable[SlotEvidence],
        bridges: Iterable[PredicateBridge] = ()) -> SlotGateResult:
    """LLM slot 값을 신뢰하지 않고 동일 입력에서 결정론적으로 다시 판정한다.

    제안값은 감사용으로만 보존한다. definitive 답변은 모든 slot이 exact evidence나
    검증된 명시 bridge로 ``true``/``false``가 된 경우에만 허용한다.
    """
    normalized = {
        str(slot_id): str(value).strip().casefold()
        for slot_id, value in proposed_values.items()
    }
    judgements = validate_condition_slots(tuple(slots), tuple(evidence), tuple(bridges))
    overridden = tuple(
        row.slot_id for row in judgements
        if normalized.get(row.slot_id, "unknown") != row.value
    )
    unknown = tuple(row.slot_id for row in judgements if row.value == "unknown")
    allowed = bool(judgements) and not unknown
    if not allowed:
        mode = "conditional"
    elif any(row.value == "false" for row in judgements):
        mode = "definitive_not_applicable"
    else:
        mode = "definitive_applicable"
    return SlotGateResult(
        judgements=judgements,
        proposed_values=tuple(sorted(normalized.items())),
        overridden_slot_ids=overridden,
        unknown_slot_ids=unknown,
        presentation_allowed=allowed,
        answer_mode=mode,
    )


def extract(text: str) -> tuple[RequirementSpan, ...]:
    """동일 원문 절의 정확 offset을 가진 qualifier 후보를 반환한다."""
    text = str(text or "")
    out: list[RequirementSpan] = []
    seen = set()
    for clause_start, clause_end, clause in _clauses(text):
        start, end, surface = _trim(text, clause_start, clause_end)
        if not surface:
            continue
        matches = []
        for kind, pattern in _TRIGGERS.items():
            matches.extend((kind, match) for match in pattern.finditer(surface))
        matches.extend(("QUANTITY", match) for match in _QUANTITY.finditer(surface))
        matches.extend(("TIME", match) for match in _TIME.finditer(surface))
        for kind, match in matches:
            key = (kind, start, end)
            if key in seen:
                continue
            seen.add(key)
            out.append(RequirementSpan(
                kind=kind, surface=surface, start=start, end=end,
                trigger=match.group(0),
                trigger_start=start + match.start(),
                trigger_end=start + match.end(),
            ))
    return tuple(sorted(out, key=lambda row: (row.start, KINDS.index(row.kind))))


_QUESTION_CUES = {
    "CONDITION": re.compile(r"요건|기준|경우|해당|전제"),
    "EXCEPTION": re.compile(r"예외|제외|단서|불구하고"),
    "TIME": re.compile(r"언제|기간|기한|기준일|이내|이후|이전|며칠|몇\s*년"),
    "QUANTITY": re.compile(r"얼마|몇\s*(?:명|개|주|회|일|개월|년)|비율|한도|수량|100분|퍼센트|%"),
    "METHOD": re.compile(r"어떻게|절차|방법|제출|신고|승인|결의|어디에|누구에게"),
    "EFFECT": re.compile(r"효력|무효|취소|책임|제재|처분|결과|어떻게 되는"),
}


def requested_kinds(question: str) -> tuple[str, ...]:
    return tuple(kind for kind in KINDS
                 if _QUESTION_CUES[kind].search(str(question or "")))
