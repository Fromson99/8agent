"""법령 원문에서 구성요건 qualifier의 근거 span을 보수적으로 표시한다.

의미를 새로 생성하지 않는다. 조건·예외·시간·수치·방법·효과를 나타내는 닫힌
표지와 그 표지가 속한 원문 절을 반환한다. 이 결과는 Concept 자동 승격이 아니라
Requirement 후보와 Evidence Auditor 입력을 위한 shadow 자료다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


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


# ADR-0148 research candidate: a selected legal block is executable only after
# every conjunctive predicate has its own closed evidence slot.  This lives in
# the research snapshot; production imports never see it before promotion.
SLOT_STATUSES = frozenset({"true", "false", "unknown"})
BRIDGE_PREDICATES = frozenset({
    "DEFINES", "ALIASES_AS", "DEEMS_AS", "SUBSTITUTES_FOR",
})
PROVISO_CUE = re.compile(
    r"다만|에도\s*불구하고|제외한다|제외되는|그러하지\s*아니하다|예외"
)
_REFERENCE_CUE = re.compile(r"제\s*\d+(?:의\s*\d+)?조")


@dataclass(frozen=True)
class SlotEvidence:
    evidence_id: str
    source_text: str
    start: int
    end: int
    quote: str
    supports_predicates: tuple[str, ...]
    verified: bool = True

    @property
    def exact(self) -> bool:
        return (
            self.verified
            and bool(self.evidence_id)
            and 0 <= self.start < self.end <= len(self.source_text)
            and self.source_text[self.start:self.end] == self.quote
            and bool(self.quote)
        )


@dataclass(frozen=True)
class PredicateBridge:
    bridge_id: str
    kind: str
    source_predicate: str
    target_predicate: str
    evidence_ids: tuple[str, ...]
    verified: bool = True


@dataclass(frozen=True)
class ConditionSlot:
    slot_id: str
    predicate: str
    status: str
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in SLOT_STATUSES:
            raise ValueError(f"invalid slot status: {self.status}")
        if not self.slot_id or not self.predicate:
            raise ValueError("slot_id and predicate are required")


def _verified_bridge(
    source_predicates: Iterable[str],
    target_predicate: str,
    bridges: Iterable[PredicateBridge],
    evidence: Mapping[str, SlotEvidence],
) -> str:
    sources = set(source_predicates)
    for bridge in bridges:
        if (
            bridge.verified
            and bridge.kind in BRIDGE_PREDICATES
            and bridge.source_predicate in sources
            and bridge.target_predicate == target_predicate
            and bridge.evidence_ids
            and all(
                evidence_id in evidence and evidence[evidence_id].exact
                for evidence_id in bridge.evidence_ids
            )
        ):
            return bridge.bridge_id
    return ""


def validate_condition_slots(
    slots: Iterable[ConditionSlot],
    evidence_rows: Iterable[SlotEvidence],
    bridges: Iterable[PredicateBridge] = (),
) -> dict[str, Any]:
    """Fail closed on unsupported true/false without rewriting source meaning.

    Evidence proves only predicates listed in ``supports_predicates``.  Reusing
    an exact fact for a different predicate therefore needs a verified explicit
    definition/deeming/alias/substitution bridge.  Missing proof downgrades the
    assertion to ``unknown``; it never upgrades another slot.
    """

    evidence = {row.evidence_id: row for row in evidence_rows if row.evidence_id}
    bridge_rows = tuple(bridges)
    output: list[ConditionSlot] = []
    violations: list[dict[str, Any]] = []
    seen_slots: set[str] = set()
    for slot in slots:
        if slot.slot_id in seen_slots:
            raise ValueError(f"duplicate slot_id: {slot.slot_id}")
        seen_slots.add(slot.slot_id)
        if slot.status == "unknown":
            output.append(slot)
            continue

        selected = [evidence.get(evidence_id) for evidence_id in slot.evidence_ids]
        invalid_ids = [
            evidence_id for evidence_id, row in zip(slot.evidence_ids, selected)
            if row is None or not row.exact
        ]
        direct = [
            row for row in selected
            if row is not None and row.exact
            and slot.predicate in row.supports_predicates
        ]
        supported_predicates = {
            predicate
            for row in selected if row is not None and row.exact
            for predicate in row.supports_predicates
        }
        bridge_id = _verified_bridge(
            supported_predicates, slot.predicate, bridge_rows, evidence
        )
        if slot.evidence_ids and not invalid_ids and (direct or bridge_id):
            output.append(slot)
            continue

        reasons = []
        if not slot.evidence_ids:
            reasons.append("missing_evidence")
        if invalid_ids:
            reasons.append("unverified_or_nonexact_evidence")
        if slot.evidence_ids and not direct and not bridge_id:
            reasons.append("unsupported_cross_predicate_inference")
        violation = {
            "slot_id": slot.slot_id,
            "predicate": slot.predicate,
            "from_status": slot.status,
            "to_status": "unknown",
            "reasons": reasons,
            "invalid_evidence_ids": invalid_ids,
            "observed_supported_predicates": sorted(supported_predicates),
        }
        violations.append(violation)
        output.append(ConditionSlot(
            slot_id=slot.slot_id,
            predicate=slot.predicate,
            status="unknown",
            evidence_ids=slot.evidence_ids,
            reason=(slot.reason + "; " if slot.reason else "")
            + ",".join(reasons),
        ))
    return {
        "slots": [asdict(row) for row in output],
        "violations": violations,
        "valid": not violations,
        "asserted_count": sum(row.status != "unknown" for row in output),
        "unknown_count": sum(row.status == "unknown" for row in output),
    }


def _article_root(view: Any, node_id: Any) -> Any:
    cur = view.by_id.get(node_id)
    seen = set()
    while cur is not None and cur.get("id") not in seen:
        seen.add(cur.get("id"))
        if re.fullmatch(r"제\s*\d+(?:-\d+)?조(?:의\s*\d+)?",
                        str(cur.get("surface") or "").strip()):
            return cur.get("id")
        cur = view.by_id.get(cur.get("parent"))
    return node_id


def proviso_connection_census(index: Any, delegation_rows: Mapping[Any, Any]) \
        -> dict[str, Any]:
    """Inventory every frozen proviso cue and its observed connection forms."""

    intra = index.ref_edges()
    cross, pending = index.cross_refs()
    cross_by_block: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    pending_by_block: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for row in cross:
        cross_by_block.setdefault((str(row.get("src_doc") or ""), row.get("block")), []).append(row)
    for row in pending:
        pending_by_block.setdefault((str(row.get("src_doc") or ""), row.get("block")), []).append(row)

    occurrences: list[dict[str, Any]] = []
    form_counts: dict[str, int] = {}
    relation_counts: dict[str, int] = {}
    for doc_id, view in sorted(index.docs.items()):
        for block in view.blocks:
            text = str(block.get("text") or "")
            cue_matches = list(PROVISO_CUE.finditer(text))
            if not cue_matches:
                continue
            block_id = block.get("idx")
            owner = block.get("node")
            if owner is None:
                owner = (view.owner(block_id) or {}).get("id")
            article = _article_root(view, owner)
            local_rows = [
                row for row in intra.get(doc_id, ())
                if row.get("block") == block_id
            ]
            cross_rows = cross_by_block.get((doc_id, block_id), [])
            pending_rows = pending_by_block.get((doc_id, block_id), [])
            delegated = list(delegation_rows.get((doc_id, article), ()))
            for ordinal, match in enumerate(cue_matches, 1):
                forms = {"INTERNAL_SAME_BLOCK"}
                if owner != article:
                    forms.add("INTERNAL_CHILD_UNIT")
                if len(cue_matches) > 1:
                    forms.add("NESTED_PROVISO")
                if local_rows:
                    forms.add("INTRA_DOCUMENT_REFERENCE")
                if cross_rows:
                    forms.add("CROSS_DOCUMENT_REFERENCE")
                if pending_rows:
                    forms.add("UNRESOLVED_REFERENCE")
                all_rows = [*local_rows, *cross_rows]
                relation_types = sorted({str(row.get("rel") or "인용") for row in all_rows})
                if delegated or "수임" in relation_types:
                    forms.add("DELEGATION_RECEPTION")
                if len(forms) == 1 and _REFERENCE_CUE.search(text):
                    forms.add("UNRESOLVED_REFERENCE")
                if len(forms) == 1:
                    forms.add("NO_EXPLICIT_LINK")
                for form in forms:
                    form_counts[form] = form_counts.get(form, 0) + 1
                for relation in relation_types:
                    relation_counts[relation] = relation_counts.get(relation, 0) + 1
                occurrences.append({
                    "occurrence_id": f"{doc_id}:{block_id}:{ordinal}",
                    "doc_id": doc_id,
                    "document": view.name,
                    "node": owner,
                    "article_node": article,
                    "block": block_id,
                    "cue": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "quote": text[match.start():match.end()],
                    "forms": sorted(forms),
                    "reference_relations": relation_types,
                    "resolved_reference_count": len(all_rows),
                    "pending_reference_count": len(pending_rows),
                    "delegation_count": len(delegated),
                })
    classified = sum(bool(row["forms"]) for row in occurrences)
    return {
        "summary": {
            "documents": len(index.docs),
            "occurrences": len(occurrences),
            "classified": classified,
            "classification_coverage": classified / len(occurrences) if occurrences else 1.0,
            "form_counts": dict(sorted(form_counts.items())),
            "reference_relation_counts": dict(sorted(relation_counts.items())),
            "unresolved_occurrences": sum(
                "UNRESOLVED_REFERENCE" in row["forms"] for row in occurrences
            ),
            "no_explicit_link_occurrences": sum(
                "NO_EXPLICIT_LINK" in row["forms"] for row in occurrences
            ),
        },
        "occurrences": occurrences,
    }
