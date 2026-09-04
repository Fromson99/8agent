"""법령 원문에서 구성요건 qualifier의 근거 span을 보수적으로 표시한다.

의미를 새로 생성하지 않는다. 조건·예외·시간·수치·방법·효과를 나타내는 닫힌
표지와 그 표지가 속한 원문 절을 반환한다. 이 결과는 Concept 자동 승격이 아니라
Requirement 후보와 Evidence Auditor 입력을 위한 shadow 자료다.
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence


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


# ADR-0154 research candidate -------------------------------------------------
#
# The source parser already materializes article/paragraph/item/sub-item nodes.
# Do not flatten those nodes to an article root.  The records below add a
# deterministic execution graph around the exact source nodes without changing
# the production graph or inventing legal meaning.

_ARTICLE_FAMILY = re.compile(r"article")
_PARAGRAPH_FAMILIES = frozenset({"circled", "paren_number"})
_ITEM_FAMILY = re.compile(r"(?:dot_number|paren_hangul|paren_korean|number_dot)")
_SUBITEM_FAMILY = re.compile(r"(?:hangul_dot|ga_dot)")
_LOWER_RULE_CUE = re.compile(r"시행세칙|세칙|시행규칙|대통령령|총리령|부령|시행령")
_SOURCE_LOCATOR = re.compile(
    r"제\s*\d+(?:-\d+)?\s*조(?:의\s*\d+)?"
    r"(?:\s*제\s*\d+\s*항)?(?:\s*제\s*\d+\s*호)?"
    r"(?:\s*[가-힣]\s*목)?\s*단서"
)
_CONDITION_END = re.compile(r"경우(?:에는|엔|는|에)?|때(?:에는|는)?|한하여(?:는)?")

_OUTCOME_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EXCLUDES_APPLICATION", re.compile(r"제외|적용하지\s+아니|그러하지\s+아니|예외로")),
    ("DEEMS_AS", re.compile(r"(?:으)?로\s+본다|간주|의제")),
    ("SUBSTITUTES", re.compile(r"갈음|대신|대체")),
    ("EXTENDS_PERIOD", re.compile(r"기간.{0,20}연장|연장할")),
    ("SHORTENS_PERIOD", re.compile(r"기간.{0,20}단축|단축할")),
    ("PROHIBITS", re.compile(r"할\s+수\s+없|하여서는\s+아니|해서는\s+아니")),
    ("PERMITS", re.compile(r"할\s+수\s+있|할\s+수도\s+있")),
    ("REQUIRES", re.compile(r"하여야\s+한다|해야\s+한다|의무보유하여야")),
    ("INCLUDES_SCOPE", re.compile(r"포함한다|포함할")),
    ("APPLIES_RULE", re.compile(r"적용한다|준용한다|따른다")),
    ("SETS_CALCULATION", re.compile(r"산정한다|계산한다")),
    ("SETS_RULE", re.compile(r"정한다")),
)


@dataclass(frozen=True)
class MinimumUnitNode:
    unit_id: str
    doc_id: str
    source_node: int
    parent_unit_id: str | None
    family: str
    level: int
    surface: str
    title: str
    block_start: int
    block_end: int
    locator: str
    is_leaf: bool

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProvisoComponent:
    component_id: str
    proviso_id: str
    kind: str
    text: str
    start: int | None
    end: int | None
    status: str
    source_sha256: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    plane: str
    kind: str
    src: str
    dst: str
    status: str = "ASSERTED"
    evidence: tuple[str, ...] = ()
    properties: tuple[tuple[str, Any], ...] = ()

    def as_dict(self) -> dict:
        value = asdict(self)
        value["properties"] = dict(self.properties)
        return value


@dataclass(frozen=True)
class ExternalRoute:
    proviso_id: str
    condition_id: str
    source_unit_id: str
    source_locator: str
    target_unit_id: str | None
    target_doc_id: str | None
    target_node: int | None
    target_locator: str | None
    status: str
    method: str
    candidate_count: int
    member_unit_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return prefix + ":" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _ordinal(node: Mapping[str, Any]) -> int | None:
    raw = node.get("ordinal")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and raw:
        try:
            return int(raw[0])
        except (TypeError, ValueError):
            return None
    return None


def _locator_piece(node: Mapping[str, Any]) -> str:
    family = str(node.get("family") or "")
    surface = str(node.get("surface") or "").strip()
    ordinal = _ordinal(node)
    if _ARTICLE_FAMILY.search(family):
        return re.sub(r"\s+", "", surface)
    if family in _PARAGRAPH_FAMILIES and ordinal is not None:
        return f"제{ordinal}항"
    if _SUBITEM_FAMILY.search(family):
        label = surface.rstrip(".．)） ")
        return f"{label}목" if label else ""
    if _ITEM_FAMILY.search(family) and ordinal is not None:
        return f"제{ordinal}호"
    return ""


def canonical_locator(node_id: int, nodes_by_id: Mapping[int, Mapping[str, Any]]) -> str:
    chain: list[Mapping[str, Any]] = []
    seen: set[int] = set()
    current = nodes_by_id.get(int(node_id))
    while current is not None:
        current_id = int(current.get("id", -1))
        if current_id in seen:
            break
        seen.add(current_id)
        chain.append(current)
        parent = current.get("parent")
        current = nodes_by_id.get(int(parent)) if parent is not None else None
    pieces = [_locator_piece(row) for row in reversed(chain)]
    return "".join(piece for piece in pieces if piece)


def materialize_minimum_units(doc_id: str, nodes: Iterable[Mapping[str, Any]]) -> tuple[MinimumUnitNode, ...]:
    rows = tuple(nodes)
    by_id = {int(row["id"]): row for row in rows}
    out = []
    for row in sorted(rows, key=lambda item: int(item["id"])):
        node_id = int(row["id"])
        parent = row.get("parent")
        span = row.get("span") if isinstance(row.get("span"), Sequence) else ()
        block_start = int(span[0]) if len(span) >= 2 else int(row.get("block", -1))
        block_end = int(span[1]) if len(span) >= 2 else block_start + 1
        out.append(MinimumUnitNode(
            unit_id=_stable_id("unit", doc_id, node_id),
            doc_id=doc_id,
            source_node=node_id,
            parent_unit_id=(_stable_id("unit", doc_id, int(parent))
                            if parent is not None else None),
            family=str(row.get("family") or ""),
            level=int(row.get("level", 0)),
            surface=str(row.get("surface") or ""),
            title=str(row.get("title") or ""),
            block_start=block_start,
            block_end=block_end,
            locator=canonical_locator(node_id, by_id),
            is_leaf=int(row.get("n_children", 0)) == 0,
        ))
    return tuple(out)


def split_proviso_components(span: ProvisoSpan, source_text: str) -> tuple[ProvisoComponent, ProvisoComponent]:
    """Split a proviso into explicit condition/outcome nodes, fail-closed.

    The last conditional boundary is used because Korean provisos commonly join
    several alternative conditions before a single legal consequence.  If no
    boundary is explicit, an unresolved empty condition is emitted rather than
    treating the outcome as its own condition.
    """
    body = span.body
    terminal_effect = _TERMINAL_EFFECT_CUE.search(span.cue) is not None
    boundaries = tuple(_CONDITION_END.finditer(body))
    usable = tuple(match for match in boundaries if body[match.end():].strip(" ,，") )
    if terminal_effect:
        condition_text = span.parent_text
        outcome_text = span.cue
        condition_start = span.parent_start if condition_text else None
        outcome_start = span.cue_start
        condition_status = "EXPLICIT" if condition_text else "IMPLICIT_OR_UNRESOLVED"
    elif usable:
        boundary = usable[-1]
        condition_text = body[:boundary.end()].strip(" ,，")
        outcome_text = body[boundary.end():].strip(" ,，")
        condition_start = span.body_start + body.find(condition_text)
        outcome_start = span.body_start + body.find(outcome_text, boundary.end())
        condition_status = "EXPLICIT"
    else:
        condition_text = ""
        outcome_text = body.strip()
        condition_start = None
        outcome_start = span.body_start + body.find(outcome_text) if outcome_text else span.body_start
        condition_status = "IMPLICIT_OR_UNRESOLVED"
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    condition = ProvisoComponent(
        component_id=_stable_id("condition", span.proviso_id, condition_start, condition_text),
        proviso_id=span.proviso_id, kind="CONDITION", text=condition_text,
        start=condition_start,
        end=(condition_start + len(condition_text) if condition_start is not None else None),
        status=condition_status, source_sha256=source_hash,
    )
    outcome = ProvisoComponent(
        component_id=_stable_id("outcome", span.proviso_id, outcome_start, outcome_text),
        proviso_id=span.proviso_id, kind="OUTCOME", text=outcome_text,
        start=outcome_start, end=outcome_start + len(outcome_text),
        status="EXPLICIT" if outcome_text else "UNRESOLVED", source_sha256=source_hash,
    )
    return condition, outcome


def classify_outcome(text: str) -> str:
    for kind, pattern in _OUTCOME_RULES:
        if pattern.search(str(text or "")):
            return kind
    return "UNKNOWN"


def legal_effect_family(span: ProvisoSpan, outcome_kind: str) -> str:
    if span.effect_kind in {"EXCEPTION_TO", "OVERRIDES_RULE"}:
        return span.effect_kind
    if outcome_kind == "EXCLUDES_APPLICATION":
        return "EXCEPTION_TO"
    return "QUALIFIES_RULE" if outcome_kind != "UNKNOWN" else "UNKNOWN"


def make_edge(plane: str, kind: str, src: str, dst: str, *,
              status: str = "ASSERTED", evidence: Iterable[str] = (),
              properties: Mapping[str, Any] | None = None) -> GraphEdge:
    props = tuple(sorted((str(key), value) for key, value in (properties or {}).items()))
    return GraphEdge(
        edge_id=_stable_id("edge", plane, kind, src, dst, status, props),
        plane=plane, kind=kind, src=src, dst=dst, status=status,
        evidence=tuple(evidence), properties=props,
    )


def _normalize_locator(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _lower_rule_matches(source_name: str, target_name: str, cue: str) -> bool:
    normalized_source = re.sub(r"\s+", "", source_name)
    normalized_target = re.sub(r"\s+", "", target_name)
    if not normalized_source or not normalized_target.startswith(normalized_source):
        return False
    if "시행세칙" in cue or "세칙" in cue:
        return "세칙" in normalized_target
    if "시행규칙" in cue or "총리령" in cue or "부령" in cue:
        return "시행규칙" in normalized_target
    if "시행령" in cue or "대통령령" in cue:
        return "시행령" in normalized_target
    return False


def _descendant_leaf_units(root_node: int, units: Sequence[MinimumUnitNode]) -> tuple[str, ...]:
    by_parent: dict[str, list[MinimumUnitNode]] = {}
    root_id = next((row.unit_id for row in units if row.source_node == root_node), "")
    for row in units:
        if row.parent_unit_id:
            by_parent.setdefault(row.parent_unit_id, []).append(row)
    descendants: list[str] = []
    stack = list(by_parent.get(root_id, ()))
    while stack:
        row = stack.pop()
        descendants.append(row.unit_id)
        children = by_parent.get(row.unit_id, ())
        if children:
            stack.extend(children)
    return tuple(sorted(descendants))


def build_reverse_locator_index(
        documents: Mapping[str, Mapping[str, Any]],
        units_by_doc: Mapping[str, Sequence[MinimumUnitNode]],
) -> Mapping[str, tuple[tuple[str, int, str, str, tuple[str, ...]], ...]]:
    """Index explicit external receiving clauses by normalized source locator."""
    index: dict[str, list[tuple[str, int, str, str, tuple[str, ...]]]] = {}
    for doc_id in sorted(documents):
        document = documents[doc_id]
        name = str(document.get("doc") or "")
        units = tuple(units_by_doc.get(doc_id, ()))
        unit_by_node = {row.source_node: row for row in units}
        for block in document.get("blocks", ()):
            text = str(block.get("text") or "")
            for match in _SOURCE_LOCATOR.finditer(text):
                raw_node_id = block.get("node")
                if raw_node_id is None:
                    continue
                node_id = int(raw_node_id)
                unit = unit_by_node.get(node_id)
                if unit is None:
                    continue
                locator = _normalize_locator(match.group(0))
                members = _descendant_leaf_units(node_id, units)
                index.setdefault(locator, []).append(
                    (doc_id, node_id, unit.unit_id, name, members))
    return {key: tuple(sorted(values)) for key, values in index.items()}


def resolve_external_route(
        span: ProvisoSpan,
        condition: ProvisoComponent,
        source_unit: MinimumUnitNode,
        source_doc_name: str,
        documents: Mapping[str, Mapping[str, Any]],
        reverse_index: Mapping[str, Sequence[tuple[str, int, str, str, tuple[str, ...]]]],
) -> ExternalRoute | None:
    cue_match = _LOWER_RULE_CUE.search(condition.text or span.body)
    if cue_match is None:
        return None
    source_locator = source_unit.locator + "단서"
    candidates = [row for row in reverse_index.get(_normalize_locator(source_locator), ())
                  if row[0] != span.doc_id and
                  _lower_rule_matches(source_doc_name, row[3], cue_match.group(0))]
    if len(candidates) == 1:
        target_doc, target_node, target_unit, _target_name, members = candidates[0]
        target_locator = next(
            (unit.locator for unit in materialize_minimum_units(
                target_doc, documents[target_doc].get("nodes", ()))
             if unit.source_node == target_node), "")
        return ExternalRoute(
            proviso_id=span.proviso_id, condition_id=condition.component_id,
            source_unit_id=source_unit.unit_id, source_locator=source_locator,
            target_unit_id=target_unit, target_doc_id=target_doc,
            target_node=target_node, target_locator=target_locator,
            status="RESOLVED", method="PARENT_LOCATOR_REVERSE_RECEPTION",
            candidate_count=1, member_unit_ids=members,
        )
    return ExternalRoute(
        proviso_id=span.proviso_id, condition_id=condition.component_id,
        source_unit_id=source_unit.unit_id, source_locator=source_locator,
        target_unit_id=None, target_doc_id=None, target_node=None,
        target_locator=None,
        status="AMBIGUOUS" if candidates else "UNRESOLVED",
        method="PARENT_LOCATOR_REVERSE_RECEPTION",
        candidate_count=len(candidates), member_unit_ids=(),
    )


def build_minimum_unit_proviso_graph(
        documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Compile the frozen structure store into minimum-unit proviso records."""
    units_by_doc = {
        doc_id: materialize_minimum_units(doc_id, document.get("nodes", ()))
        for doc_id, document in sorted(documents.items())
    }
    reverse_index = build_reverse_locator_index(documents, units_by_doc)
    provisos: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    taxonomy: dict[str, int] = {}

    for doc_id, document in sorted(documents.items()):
        units = units_by_doc[doc_id]
        unit_by_node = {row.source_node: row for row in units}
        nodes_by_id = {int(row["id"]): row for row in document.get("nodes", ())}
        for block in sorted(document.get("blocks", ()), key=lambda row: int(row.get("idx", -1))):
            raw_node_id = block.get("node")
            if raw_node_id is None:
                continue
            node_id = int(raw_node_id)
            source_unit = unit_by_node.get(node_id)
            if source_unit is None:
                continue
            article_id = node_id
            while article_id in nodes_by_id and not _ARTICLE_FAMILY.search(
                    str(nodes_by_id[article_id].get("family") or "")):
                parent = nodes_by_id[article_id].get("parent")
                if parent is None:
                    break
                article_id = int(parent)
            text = str(block.get("text") or "")
            for span in extract_provisos(
                    text, doc_id=doc_id, node=node_id, article=article_id,
                    block=int(block.get("idx", -1))):
                condition, outcome = split_proviso_components(span, text)
                outcome_kind = classify_outcome(outcome.text)
                family = legal_effect_family(span, outcome_kind)
                record = span.as_dict()
                record.update({
                    "source_unit_id": source_unit.unit_id,
                    "source_locator": source_unit.locator,
                    "condition_id": condition.component_id,
                    "outcome_id": outcome.component_id,
                    "outcome_kind": outcome_kind,
                    "legal_effect_family": family,
                })
                provisos.append(record)
                components.extend((condition.as_dict(), outcome.as_dict()))
                edges.extend((
                    make_edge("PHYSICAL", "ATTACHED_TO", span.proviso_id,
                              source_unit.unit_id, evidence=(span.source_sha256,)).as_dict(),
                    make_edge("SEMANTIC", "HAS_CONDITION", span.proviso_id,
                              condition.component_id, evidence=(span.source_sha256,)).as_dict(),
                    make_edge("SEMANTIC", "HAS_OUTCOME", span.proviso_id,
                              outcome.component_id, evidence=(span.source_sha256,)).as_dict(),
                    make_edge("LEGAL_EFFECT", family, outcome.component_id,
                              source_unit.unit_id, evidence=(span.source_sha256,),
                              properties={"outcome_kind": outcome_kind}).as_dict(),
                ))
                taxonomy[outcome_kind] = taxonomy.get(outcome_kind, 0) + 1
                route = resolve_external_route(
                    span, condition, source_unit, str(document.get("doc") or ""),
                    documents, reverse_index)
                if route is not None:
                    routes.append(route.as_dict())
                    if route.status == "RESOLVED" and route.target_unit_id:
                        edges.append(make_edge(
                            "ROUTING", "RESOLVED_BY", condition.component_id,
                            route.target_unit_id, status="RESOLVED",
                            properties={"method": route.method,
                                        "source_locator": route.source_locator}).as_dict())
                        edges.append(make_edge(
                            "ROUTING", "RECEIVES_PROVISO_FROM", route.target_unit_id,
                            span.proviso_id, status="RESOLVED",
                            properties={"method": route.method}).as_dict())
                        for member in route.member_unit_ids:
                            edges.append(make_edge(
                                "SEMANTIC", "HAS_CONDITION_MEMBER",
                                condition.component_id, member, status="RESOLVED",
                                properties={"receiver": route.target_unit_id}).as_dict())

    unit_rows = [row.as_dict() for doc_id in sorted(units_by_doc)
                 for row in units_by_doc[doc_id]]
    return {
        "schema_version": "minimum-unit-proviso-graph-v1",
        "units": unit_rows,
        "provisos": sorted(provisos, key=lambda row: row["proviso_id"]),
        "components": sorted(components, key=lambda row: row["component_id"]),
        "edges": sorted(edges, key=lambda row: row["edge_id"]),
        "routes": sorted(routes, key=lambda row: row["proviso_id"]),
        "taxonomy": dict(sorted(taxonomy.items())),
    }
