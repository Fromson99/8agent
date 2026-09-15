"""Scope/quote/bundle legal research profile used by ADR-0116.

ADR-0115 and the legacy integrated profiles are intentionally left intact.
This profile keeps the verified candidate menu but fixes four measured losses:

    explicit market/document scope partition
    -> exact source-span receipts
    -> deterministic protected-prior bundle
    -> one closed-ID exact-quote compiler (no free proposition)
    -> decision-element coverage gate (no gap retry)
    -> adaptive evidence packet

The compiler can select an exact quote and its legal role.  It cannot invent a
corpus coordinate or an intermediate legal proposition.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import re
import time
from typing import Any, Iterable, Mapping, Sequence

from lawrag.core.legal_graph.behavior import RELATION_BEHAVIOR_POLICIES
from lawrag.core.legal_graph.model import RelationPredicate
from lawrag.core.rag import general_search, query_grounding
from lawrag.core.rag.answer import Section
from lawrag.runtime import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.index import Index
from lawrag.research.legacy_rag.legal_research_llm_selector import branches_from_query_plan
from lawrag.research.legacy_rag.legal_research_state import (
    CandidateProvenance,
    CoverageBinding,
    ResearchCoordinate,
    add_candidate_origin,
    build_source_span_verification,
    compile_research_evidence,
    promote_candidate,
    seed_candidate,
    verify_candidate,
)
from lawrag.core.rag.legal_semantic_search import plan_semantic_coordinates
from lawrag.research.legacy_rag.legal_system_entry import scope_alignment
from lawrag.research.legacy_rag import integrated_legal_research as legacy


SHORTLIST_CAP = 48
PRESENTATION_TARGET = 22
HARD_CAP = 28
RELATION_ADDITION_CAP = 12
GAP_ADDITION_CAP = 12
SPAN_CHARS = 2200
PROTECTED_BUNDLE_CAP = 6
_TOKEN = re.compile(r"[0-9A-Za-z가-힣%]{2,}")
_ROLES = (
    "GOVERNING_RULE", "DEFINITION", "CONDITION", "EXCEPTION",
    "PROCEDURE", "SANCTION", "COMPANION", "CONTEXT",
)
_ANSWER_MODES = ("DIRECT_RULE", "CONDITIONAL_APPLICATION", "INSUFFICIENT")
_DECISION_ELEMENTS = (
    "governing_rule", "actor_scope", "operative_effect", "condition",
    "exception", "temporal", "numeric", "definition",
)
_CORE_ELEMENTS = frozenset({"governing_rule", "actor_scope", "operative_effect"})
_ROLE_PRIORITY = {
    "GOVERNING_RULE": 0,
    "DEFINITION": 1,
    "CONDITION": 2,
    "EXCEPTION": 3,
    "COMPANION": 4,
    "PROCEDURE": 5,
    "SANCTION": 6,
    "CONTEXT": 7,
}


COMPILER_SYSTEM = """너는 법률 조사의 scope-aware exact-quote compiler다. 최종 답변이나
법률 명제를 새로 쓰지 않는다. 질문과 현재 코퍼스에서 검증된 조문 span 메뉴를 받는다.
메뉴의 evidence_id, scope_id와 excerpt의 연속 원문 quote만 선택한다.

규칙:
1. 질문이 코스닥·유가증권시장 등 특정 scope를 명시하면 다른 시장의 규범을 섞지 않는다.
2. 질문이 모호해 복수 scope가 필요하면 각각을 별도 선택하되 한 quote를 다른 scope의
   결론 근거로 쓰지 않는다.
3. quote는 excerpt에서 글자를 바꾸지 않은 연속 원문이어야 한다. proposition·요약·효과를
   별도로 쓰지 않는다.
4. governing_rule, actor_scope, operative_effect는 항상 required element다. 질문에 조건,
   예외, 시점, 수치, 정의가 있으면 해당 element도 required_elements에 넣는다.
5. element는 그 값을 직접 증명하는 evidence_id와 exact quote가 있을 때만 낸다.
6. required element가 하나라도 없으면 DIRECT_RULE을 선택하지 않는다. 구체적 사실 포섭이
   더 필요하면 CONDITIONAL_APPLICATION, 지배규범이 없으면 INSUFFICIENT다.
7. 선택 개수를 채우지 않고 보통 3~10개 quote만 고른다."""


COMPILER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "selected_scope_ids": {"type": "array", "items": {"type": "string"}},
        "quotes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote_id": {"type": "string"},
                    "evidence_id": {"type": "string"},
                    "scope_id": {"type": "string"},
                    "role": {"type": "string", "enum": list(_ROLES)},
                    "quote": {"type": "string"},
                },
                "required": ["quote_id", "evidence_id", "scope_id", "role", "quote"],
                "additionalProperties": False,
            },
        },
        "required_elements": {
            "type": "array", "items": {"type": "string", "enum": list(_DECISION_ELEMENTS)},
        },
        "elements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "element": {"type": "string", "enum": list(_DECISION_ELEMENTS)},
                    "evidence_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["element", "evidence_id", "quote"],
                "additionalProperties": False,
            },
        },
        "answer_mode": {"type": "string", "enum": list(_ANSWER_MODES)},
        "missing_elements": {
            "type": "array", "items": {"type": "string", "enum": list(_DECISION_ELEMENTS)},
        },
        "reason": {"type": "string"},
    },
    "required": ["selected_scope_ids", "quotes", "required_elements", "elements",
                 "answer_mode", "missing_elements", "reason"],
    "additionalProperties": False,
}


_STAGE_SPECS = (
    ("question-source", "source", ()),
    ("closed-grounding-retrieve", "retrieve", ("question-source",)),
    ("legal-system-route-retrieve", "retrieve", ("closed-grounding-retrieve",)),
    ("semantic-card-retrieve", "retrieve", ("legal-system-route-retrieve",)),
    ("baseline-floor-union", "union", ("semantic-card-retrieve",)),
    ("typed-legal-relation-expand", "expand", ("baseline-floor-union",)),
    ("scope-branch-partition", "filter", ("typed-legal-relation-expand",)),
    ("provenance-span-verify", "canonicalize", ("scope-branch-partition",)),
    ("protected-bundle-union", "union", ("provenance-span-verify",)),
    ("quote-entailment-select", "select", ("protected-bundle-union",)),
    ("decision-coverage-gate", "select", ("quote-entailment-select",)),
    ("compiled-evidence-present", "present", ("decision-coverage-gate",)),
)


def _capture(
    index: Index,
    case_id: str,
    arm_id: str,
    snapshots: Mapping[str, Sequence[tuple[str, int]]],
    skips: Mapping[str, str],
) -> dict[str, Any]:
    canonicalize = stage_ledger.index_article_root_canonicalizer(index)
    recorder = stage_ledger.StageLedgerRecorder(case_id, arm_id, canonicalize)
    previous: set[tuple[str, int]] = set()
    reason_by_stage = {
        "scope-branch-partition": "outside_explicit_legal_scope_or_shortlist",
        "quote-entailment-select": "not_selected_or_protected_by_quote_compiler",
        "decision-coverage-gate": "not_in_decision_coverage_packet",
    }
    for stage_id, kind, parents in _STAGE_SPECS:
        after = list(dict.fromkeys(snapshots.get(stage_id, tuple(previous))))
        after_set = set(after)
        skip = str(skips.get(stage_id) or "")
        if parents:
            reason = reason_by_stage.get(stage_id, "stage_pruned")
            recorder.record_stage(
                stage_id,
                kind,
                after,
                parent_stage_ids=parents,
                executed=not bool(skip),
                skip_reason=skip,
                discard_reasons=[(coordinate, reason) for coordinate in sorted(previous - after_set)],
            )
        else:
            recorder.record_stage(stage_id, kind, after)
        previous = after_set
    return recorder.capture()


def _source_span(text: str, question: str, matched: Iterable[str]) -> tuple[int, int, str]:
    terms: list[str] = []
    for raw in (*tuple(matched), *_TOKEN.findall(question)):
        value = str(raw).split(":", 1)[-1].strip()
        if len(value) >= 2 and value not in terms:
            terms.append(value)
    best: tuple[int, int, int] | None = None
    lowered = text.casefold()
    for priority, term in enumerate(terms[:32]):
        position = lowered.find(term.casefold())
        if position < 0:
            continue
        score = len(term) * 100 - priority
        if best is None or score > best[0]:
            best = (score, position, len(term))
    center = best[1] + best[2] // 2 if best is not None else 0
    start = max(0, center - SPAN_CHARS // 3)
    end = min(len(text), start + SPAN_CHARS)
    if end - start < SPAN_CHARS and start:
        start = max(0, end - SPAN_CHARS)
    return start, end, text[start:end]


def _origin_priority(row: Any) -> int:
    origins = set(row.origins)
    if CandidateProvenance.GROUNDED_CONCEPT in origins:
        return 0
    if CandidateProvenance.SYSTEM_PRIOR in origins:
        return 1
    if CandidateProvenance.SEMANTIC_ENTRY in origins:
        return 2
    return 3


def _scope_id(document: str, doc_id: str) -> str:
    """Coarse legal-instrument scope; identity, not a substantive conclusion."""

    value = str(document)
    rules = (
        ("코스닥시장", "MARKET:KOSDAQ"),
        ("유가증권시장", "MARKET:KOSPI"),
        ("코넥스시장", "MARKET:KONEX"),
        ("금융회사의 지배구조", "DOMAIN:FINANCIAL_GOVERNANCE"),
        ("주식회사 등의 외부감사", "DOMAIN:EXTERNAL_AUDIT"),
        ("외부감사 및 회계", "DOMAIN:EXTERNAL_AUDIT"),
        ("상속세 및 증여세", "DOMAIN:INHERITANCE_TAX"),
        ("조세특례제한", "DOMAIN:SPECIAL_TAX"),
        ("자본시장과 금융투자업", "DOMAIN:CAPITAL_MARKETS"),
        ("증권 인수업무", "DOMAIN:UNDERWRITING"),
        ("상법", "DOMAIN:COMMERCIAL_ACT"),
    )
    for surface, scope in rules:
        if surface in value:
            return scope
    return f"INSTRUMENT:{doc_id}"


def _explicit_scopes(question: str) -> frozenset[str]:
    scopes = set()
    if "코스닥" in question:
        scopes.add("MARKET:KOSDAQ")
    if "유가증권시장" in question or "코스피" in question:
        scopes.add("MARKET:KOSPI")
    if "코넥스" in question:
        scopes.add("MARKET:KONEX")
    return frozenset(scopes)


def _scope_partition(
    index: Index,
    question: str,
    coordinates: Sequence[tuple[str, int]],
    floor: set[tuple[str, int]],
) -> tuple[list[tuple[str, int]], dict[str, str], frozenset[str]]:
    scope_by_coordinate = {
        coordinate: _scope_id(index.docs[coordinate[0]].name, coordinate[0])
        for coordinate in coordinates
    }
    explicit = _explicit_scopes(question)
    if not explicit:
        return list(coordinates), scope_by_coordinate, explicit
    market_prefix = "MARKET:"
    selected = [
        coordinate for coordinate in coordinates
        if coordinate in floor
        or not scope_by_coordinate[coordinate].startswith(market_prefix)
        or scope_by_coordinate[coordinate] in explicit
    ]
    return selected, scope_by_coordinate, explicit


def _protected_bundle(
    question: str,
    coordinates: Sequence[tuple[str, int]],
    floor: set[tuple[str, int]],
    candidates: Mapping[tuple[str, int], Any],
    spans: Mapping[tuple[str, int], tuple[int, int, str]],
    explicit_scopes: frozenset[str],
    scope_by_coordinate: Mapping[tuple[str, int], str],
) -> list[tuple[str, int]]:
    tokens = tuple(dict.fromkeys(_TOKEN.findall(question)))
    ranked = []
    for coordinate in coordinates:
        if coordinate in floor:
            continue
        excerpt = spans[coordinate][2]
        lexical = sum(min(len(token), 12) for token in tokens if token in excerpt)
        scope_bonus = 100 if scope_by_coordinate.get(coordinate) in explicit_scopes else 0
        row = candidates[coordinate]
        ranked.append((
            -scope_bonus,
            -lexical,
            -len(row.coverage_keys),
            _origin_priority(row),
            -float(row.score),
            row.source_order,
            coordinate,
        ))
    ranked.sort()
    return [row[-1] for row in ranked[:PROTECTED_BUNDLE_CAP]]


def _shortlist(
    candidates: Mapping[tuple[str, int], Any],
    floor: set[tuple[str, int]],
    query_plan: Mapping[str, Any],
    source_text: Any,
) -> tuple[list[tuple[str, int]], dict[str, Any]]:
    scored: list[tuple[tuple[Any, ...], tuple[str, int], dict[str, Any]]] = []
    for coordinate, row in candidates.items():
        alignment = scope_alignment(query_plan, source_text(coordinate))
        penalty = 220.0 if alignment.get("wrong_actor_delegation") else (
            70.0 if alignment.get("numeric_only") else 0.0
        )
        adjusted = float(row.score) - penalty
        key = (
            0 if coordinate in floor else 1,
            _origin_priority(row),
            -len(row.coverage_keys),
            -adjusted,
            row.source_order,
            coordinate,
        )
        scored.append((key, coordinate, {**alignment, "adjusted_score": adjusted}))
    scored.sort(key=lambda item: item[0])
    selected: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for coordinate in sorted(floor, key=lambda item: candidates[item].source_order):
        selected.append(coordinate)
        seen.add(coordinate)
    branches: set[str] = set()
    for _, coordinate, _ in scored:
        branch = str(candidates[coordinate].branch_id)
        if coordinate in seen or branch in branches or len(selected) >= SHORTLIST_CAP:
            continue
        selected.append(coordinate)
        seen.add(coordinate)
        branches.add(branch)
    for _, coordinate, _ in scored:
        if coordinate in seen or len(selected) >= SHORTLIST_CAP:
            continue
        selected.append(coordinate)
        seen.add(coordinate)
    alignment_rows = {
        f"{coordinate[0]}:{coordinate[1]}": alignment
        for _, coordinate, alignment in scored if coordinate in seen
    }
    return selected, alignment_rows


def _allowed_coverage(predicates: Iterable[str]) -> dict[tuple[str, str], None]:
    allowed: dict[tuple[str, str], None] = {}
    for raw in predicates:
        try:
            predicate = RelationPredicate(raw)
        except ValueError:
            continue
        policy = RELATION_BEHAVIOR_POLICIES.get(predicate)
        if policy is None:
            continue
        for key in policy.required_coverage:
            allowed[(predicate.value, key)] = None
    return allowed


def _menu_rows(
    index: Index,
    question: str,
    coordinates: Sequence[tuple[str, int]],
    candidates: Mapping[tuple[str, int], Any],
    source_cache: Mapping[tuple[str, int], str],
    spans: Mapping[tuple[str, int], tuple[int, int, str]],
) -> list[dict[str, Any]]:
    rows = []
    for coordinate in coordinates:
        row = candidates[coordinate]
        view = index.docs[coordinate[0]]
        start, end, excerpt = spans[coordinate]
        rows.append({
            "evidence_id": legacy._candidate_id(coordinate),
            "coordinate": [coordinate[0], coordinate[1]],
            "document": view.name,
            "path": view.path(coordinate[1]) or view.name,
            "scope_id": _scope_id(view.name, coordinate[0]),
            "origins": sorted(origin.value for origin in row.origins),
            "branch": row.branch_id,
            "coverage_keys": sorted(row.coverage_keys),
            "matched": sorted(row.matched)[:16],
            "span": {"start": start, "end": end, "excerpt": excerpt},
        })
    return rows


def _sanitize_packet(
    raw: Mapping[str, Any] | None,
    menu: Sequence[Mapping[str, Any]],
    *,
    explicit_scopes: Iterable[str] = (),
) -> dict[str, Any]:
    menu_by_id = {str(row["evidence_id"]): row for row in menu}
    menu_scopes = {str(row.get("scope_id") or "") for row in menu}
    explicit_scope_set = {str(value) for value in explicit_scopes}
    forbidden_market_scopes = {
        scope for scope in menu_scopes
        if scope.startswith("MARKET:") and explicit_scope_set and scope not in explicit_scope_set
    }
    selected_scopes = []
    for value in (raw or {}).get("selected_scope_ids") or ():
        scope = str(value)
        if scope in menu_scopes and scope not in selected_scopes:
            selected_scopes.append(scope)
    quotes: list[dict[str, str]] = []
    quote_ids: set[str] = set()
    selected_ids: list[str] = []
    invalid_quote_count = 0
    for number, row in enumerate((raw or {}).get("quotes") or (), 1):
        if not isinstance(row, Mapping):
            invalid_quote_count += 1
            continue
        evidence_id = str(row.get("evidence_id") or "")
        scope_id = str(row.get("scope_id") or "")
        role = str(row.get("role") or "")
        quote = str(row.get("quote") or "").strip()
        menu_row = menu_by_id.get(evidence_id) or {}
        excerpt = str((menu_row.get("span") or {}).get("excerpt") or "")
        if (
            evidence_id not in menu_by_id or role not in _ROLES or not quote
            or quote not in excerpt or scope_id != str(menu_row.get("scope_id") or "")
            or scope_id in forbidden_market_scopes
        ):
            invalid_quote_count += 1
            continue
        quote_id = str(row.get("quote_id") or f"quote-{number}").strip() or f"quote-{number}"
        if quote_id in quote_ids:
            quote_id = f"{quote_id}-{number}"
        quote_ids.add(quote_id)
        if evidence_id not in selected_ids:
            selected_ids.append(evidence_id)
        if scope_id not in selected_scopes:
            selected_scopes.append(scope_id)
        quotes.append({
            "quote_id": quote_id,
            "evidence_id": evidence_id,
            "scope_id": scope_id,
            "role": role,
            "quote": quote[:800],
        })

    required = set(_CORE_ELEMENTS)
    required.update(
        str(value) for value in (raw or {}).get("required_elements") or ()
        if str(value) in _DECISION_ELEMENTS
    )
    elements: list[dict[str, str]] = []
    seen_elements: set[str] = set()
    invalid_element_count = 0
    valid_quote_pairs = {(row["evidence_id"], row["quote"]) for row in quotes}
    for row in (raw or {}).get("elements") or ():
        if not isinstance(row, Mapping):
            invalid_element_count += 1
            continue
        element = str(row.get("element") or "")
        evidence_id = str(row.get("evidence_id") or "")
        quote = str(row.get("quote") or "").strip()
        if (
            element not in _DECISION_ELEMENTS or element in seen_elements
            or (evidence_id, quote) not in valid_quote_pairs
        ):
            invalid_element_count += 1
            continue
        seen_elements.add(element)
        elements.append({
            "element": element,
            "evidence_id": evidence_id,
            "quote": quote[:800],
        })
    missing = set(required) - seen_elements
    missing.update(
        str(value) for value in (raw or {}).get("missing_elements") or ()
        if str(value) in required
    )
    mode = str((raw or {}).get("answer_mode") or "INSUFFICIENT")
    if mode not in _ANSWER_MODES:
        mode = "INSUFFICIENT"
    direct_gate_allowed = not missing and bool(quotes)
    if mode == "DIRECT_RULE" and not direct_gate_allowed:
        mode = "CONDITIONAL_APPLICATION" if quotes else "INSUFFICIENT"
    if not quotes:
        mode = "INSUFFICIENT"
    return {
        "selected_scope_ids": selected_scopes[:3],
        "selected_ids": selected_ids[:18],
        "quotes": quotes[:24],
        "claims": [
            {
                "claim_id": row["quote_id"],
                "evidence_id": row["evidence_id"],
                "scope_id": row["scope_id"],
                "role": row["role"],
                "proposition": row["quote"],
                "quote": row["quote"],
            }
            for row in quotes[:24]
        ],
        "required_elements": sorted(required),
        "elements": elements,
        "coverage": [],
        "answer_mode": mode,
        "missing_elements": sorted(missing),
        "missing": [
            {"coverage_key": element, "search_terms": []}
            for element in sorted(missing)
        ],
        "direct_gate_allowed": direct_gate_allowed,
        "reason": str((raw or {}).get("reason") or "")[:1000],
        "closed_id_violations": [],
        "invalid_quote_count": invalid_quote_count,
        "invalid_element_count": invalid_element_count,
    }


def _compile_packet(
    llm: Any,
    question: str,
    menu: Sequence[Mapping[str, Any]],
    *,
    explicit_scopes: Iterable[str] = (),
) -> dict[str, Any]:
    user = (
        f"[질문]\n{question}\n\n"
        f"[검증 evidence 메뉴]\n{json.dumps(list(menu), ensure_ascii=False)}"
    )
    raw = None if llm is None else llm.structured(
        "rag.scope_entailment_bundle.quote_compiler",
        COMPILER_SYSTEM,
        user,
        COMPILER_SCHEMA,
        max_tokens=5000,
        effort="low",
    )
    return _sanitize_packet(raw, menu, explicit_scopes=explicit_scopes)


def _bindings(
    packet: Mapping[str, Any],
    records: Mapping[str, Any],
) -> dict[RelationPredicate, dict[str, CoverageBinding]]:
    output: dict[RelationPredicate, dict[str, CoverageBinding]] = defaultdict(dict)
    for row in packet.get("coverage") or ():
        evidence_id = str(row["evidence_id"])
        record = records.get(evidence_id)
        if record is None or not record.verified:
            continue
        predicate = RelationPredicate(str(row["predicate"]))
        output[predicate][str(row["coverage_key"])] = CoverageBinding(
            value=str(row["value"]),
            candidate_ids=(evidence_id,),
            evidence_ids=record.evidence_ids,
        )
    return dict(output)


def _fallback(
    index: Index,
    floor: Sequence[Section],
    *,
    case_id: str,
    arm_id: str,
    reason: str,
) -> tuple[list[Section], dict[str, Any]]:
    coordinates = [
        coordinate for section in floor
        if (coordinate := legacy._canonical(index, (section.doc_id, section.node))) is not None
    ]
    coordinates = list(dict.fromkeys(coordinates))
    snapshots = {stage_id: list(coordinates) for stage_id, _, _ in _STAGE_SPECS}
    snapshots["question-source"] = []
    skips = {
        stage_id: reason for stage_id, _, _ in _STAGE_SPECS if stage_id != "question-source"
    }
    for number, section in enumerate(floor, 1):
        section.n = number
    return list(floor), {
        "enabled": True,
        "profile": "scope-entailment-bundle-v2",
        "status": "fallback",
        "fallback": reason,
        "before_count": len(coordinates),
        "after_count": len(coordinates),
        "added_count": 0,
        "baseline_floor_preserved": True,
        "direct_conclusion_allowed": False,
        "deterministic_planning_ms": 0.0,
        "compiler_wall_ms": 0.0,
        "validation": {
            "closed_id_violations": [],
            "generation_violations": [reason],
            "verified_evidence_violations": [],
            "claim_evidence_violations": [],
            "answer_gate_violations": [],
            "protected_bundle_violations": [],
            "scope_violations": [],
            "quote_entailment_violations": [],
        },
        "stage_capture": _capture(index, case_id, arm_id, snapshots, skips),
        "errors": [{"stage": "runtime", "error": reason}],
        "elapsed_ms": 0.0,
    }


def fallback_to_floor(
    index: Index,
    floor: Sequence[Section],
    *,
    case_id: str,
    arm_id: str,
    reason: str,
) -> tuple[list[Section], dict[str, Any]]:
    """Public rollback boundary shared with ``legalclosure_runtime``."""

    return _fallback(index, floor, case_id=case_id, arm_id=arm_id, reason=reason)


def extend_sections(
    index: Index,
    question: str,
    floor_sections: Sequence[Section],
    *,
    llm: Any = None,
    cap: int = 32,
    graph_root: Any = None,
    case_id: str = "runtime-case",
    arm_id: str = "scope-entailment-bundle-compiler",
) -> tuple[list[Section], dict[str, Any]]:
    """Return a verified, compact evidence packet without dropping the floor."""

    started = time.perf_counter()
    if not 1 <= int(cap) <= 32:
        raise ValueError("coverage-preserving evidence cap must be 1..32")
    floor: list[Section] = []
    floor_coordinates: list[tuple[str, int]] = []
    floor_set: set[tuple[str, int]] = set()
    for section in floor_sections:
        coordinate = legacy._canonical(index, (section.doc_id, section.node))
        if coordinate is None or coordinate in floor_set:
            continue
        floor.append(section)
        floor_coordinates.append(coordinate)
        floor_set.add(coordinate)
    if len(floor_coordinates) > min(int(cap), HARD_CAP):
        raise ValueError("baseline floor exceeds coverage-preserving hard cap")

    snapshots: dict[str, list[tuple[str, int]]] = {"question-source": []}
    skips: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    candidates: dict[tuple[str, int], Any] = {}
    query_plan, planner_meta = legacy._question_plan(llm, question)
    try:
        system_runtime, graph_snapshot = legacy._resources(index, graph_root)
    except Exception as exc:
        return _fallback(
            index, floor, case_id=case_id, arm_id=arm_id,
            reason=f"resource_gate:{type(exc).__name__}:{exc}"[:500],
        )

    deterministic_started = time.perf_counter()
    source_cache: dict[tuple[str, int], str] = {}

    def source_text(coordinate: tuple[str, int]) -> str:
        value = source_cache.get(coordinate)
        if value is None:
            value = legacy._source_text(index, coordinate)
            source_cache[coordinate] = value
        return value

    grounding: dict[str, Any] = {}
    try:
        grounding = query_grounding.generate_candidates(
            index, graph_snapshot, None, question, query_plan,
            menu_cap=32,
            include_vector=False,
            include_fulltext=False,
            include_canonical=False,
            use_index_reverse=True,
        )
        for row in grounding.get("evidence_candidates") or ():
            legacy._add(
                candidates,
                legacy._canonical(index, row.get("coordinate") or ()),
                score=400.0 + float(row.get("score") or 0.0),
                branch_id="closed-grounding",
                origin=CandidateProvenance.GROUNDED_CONCEPT,
                coverage_keys=row.get("coverage_keys") or (),
                matched=row.get("matched_terms") or (),
            )
    except Exception as exc:
        errors.append({"stage": "closed-grounding-retrieve", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["closed-grounding-retrieve"] = list(candidates)

    branches = branches_from_query_plan(query_plan)
    entry_plans: tuple[Any, ...] = ()
    try:
        entry_plans = system_runtime.plan(
            question, query_plan, branches, instrument_limit=6, entry_limit=10,
        )
        entry_rows: list[tuple[float, str, Any]] = []
        for plan in entry_plans:
            for instrument_rank, instrument in enumerate(plan.instruments):
                for article_rank, point in enumerate(instrument.entry_points[:5]):
                    score = (
                        700.0 + float(instrument.score) + float(point.score)
                        - instrument_rank * 4 - article_rank
                    )
                    entry_rows.append((score, plan.branch_id, point))
        entry_rows.sort(key=lambda item: (-item[0], item[1], item[2].unit.instrument_id, item[2].unit.node_id))
        branch_seen: set[str] = set()
        admitted: list[tuple[float, str, Any]] = []
        for row in entry_rows:
            if row[1] in branch_seen:
                continue
            admitted.append(row)
            branch_seen.add(row[1])
        for row in entry_rows:
            if row in admitted or len(admitted) >= 24:
                continue
            admitted.append(row)
        for score, branch_id, point in admitted[:24]:
            legacy._add(
                candidates,
                legacy._canonical(index, (point.unit.instrument_id, point.unit.node_id)),
                score=score,
                branch_id=branch_id,
                origin=CandidateProvenance.SYSTEM_PRIOR,
                matched=point.matched_signals,
            )
    except Exception as exc:
        errors.append({"stage": "legal-system-route-retrieve", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["legal-system-route-retrieve"] = list(candidates)

    if system_runtime.semantic_cards is not None:
        terms = tuple(dict.fromkeys(
            str(row.get("surface") or "")
            for row in query_plan.get("mentions") or ()
            if str(row.get("surface") or "").strip()
        )) or tuple(dict.fromkeys(_TOKEN.findall(question)))[:4]
        try:
            preferred = tuple(dict.fromkeys(
                instrument.instrument_id
                for plan in entry_plans for instrument in plan.instruments[:3]
            ))
            cards = list(system_runtime.semantic_cards.search(
                terms[:3], instrument_ids=preferred or None, limit=24,
            ))
            if not cards:
                by_coordinate = {}
                for term in terms[:4]:
                    for card in system_runtime.semantic_cards.search(
                        (term,), instrument_ids=preferred or None, limit=12,
                    ):
                        by_coordinate[card.coordinate] = card
                cards = list(by_coordinate.values())
            for rank, card in enumerate(cards[:24]):
                legacy._add(
                    candidates,
                    legacy._canonical(index, card.coordinate),
                    score=560.0 - rank,
                    branch_id="semantic-card",
                    origin=CandidateProvenance.SEMANTIC_ENTRY,
                    coverage_keys=card.coverage_keys,
                    matched=card.terms[:12],
                )
        except Exception as exc:
            errors.append({"stage": "semantic-card-retrieve", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["semantic-card-retrieve"] = list(candidates)

    for rank, coordinate in enumerate(floor_coordinates):
        legacy._add(
            candidates, coordinate,
            score=1_000_000.0 - rank,
            branch_id="baseline-floor",
            origin=CandidateProvenance.SYSTEM_PRIOR,
            matched=("baseline-floor",),
        )
    snapshots["baseline-floor-union"] = list(candidates)

    active_predicates = tuple(dict.fromkeys(
        str(row.get("predicate") or "")
        for row in query_plan.get("predicate_hypotheses") or ()
        if str(row.get("predicate") or "")
    ))
    family_hints = tuple(dict.fromkeys(
        str(row.get("family_id") or "")
        for row in query_plan.get("family_hypotheses") or ()
        if str(row.get("family_id") or "")
    ))
    semantic_meta: dict[str, Any] = {}
    try:
        planned, semantic_meta = plan_semantic_coordinates(
            index,
            question,
            list(candidates),
            snapshot=graph_snapshot,
            cap=min(96, max(len(candidates) + RELATION_ADDITION_CAP, len(floor_coordinates))),
            family_hints=family_hints,
            predicate_hints=active_predicates,
        )
        additions = 0
        for planned_row in planned:
            coordinate = legacy._canonical(index, planned_row.get("coordinate") or ())
            if coordinate is None or coordinate in candidates:
                continue
            relation_id = "planned-closure:" + hashlib.sha256(
                f"{coordinate[0]}:{coordinate[1]}".encode("utf-8")
            ).hexdigest()[:16]
            legacy._add(
                candidates,
                coordinate,
                score=500.0 + float(planned_row.get("score") or 0.0),
                branch_id="typed-relation-planned",
                origin=CandidateProvenance.RELATION_EXPANDED,
                relation_ids=(relation_id,),
                coverage_keys=planned_row.get("coverage_keys") or (),
                matched=planned_row.get("matched_terms") or (),
            )
            additions += 1
            if additions >= RELATION_ADDITION_CAP:
                break
    except Exception as exc:
        errors.append({"stage": "typed-legal-relation-expand", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["typed-legal-relation-expand"] = list(candidates)

    shortlist, alignment_rows = _shortlist(candidates, floor_set, query_plan, source_text)
    shortlist, scope_by_coordinate, explicit_scopes = _scope_partition(
        index, question, shortlist, floor_set,
    )
    snapshots["scope-branch-partition"] = list(shortlist)

    records: dict[str, Any] = {}
    spans: dict[tuple[str, int], tuple[int, int, str]] = {}
    verified_coordinates: list[tuple[str, int]] = []
    for coordinate in shortlist:
        row = candidates[coordinate]
        candidate_id = legacy._candidate_id(coordinate)
        try:
            text = source_text(coordinate)
            if not text:
                raise ValueError("current article source text is empty")
            start, end, quote = _source_span(text, question, row.matched)
            spans[coordinate] = (start, end, quote)
            ordered_origins = sorted(row.origins, key=lambda value: value.value)
            record = seed_candidate(
                candidate_id,
                ResearchCoordinate(coordinate[0], coordinate[1]),
                ordered_origins[0],
                relation_ids=(row.relation_ids if ordered_origins[0] == CandidateProvenance.RELATION_EXPANDED else ()),
            )
            for origin in ordered_origins[1:]:
                record = add_candidate_origin(
                    record,
                    origin,
                    relation_ids=(row.relation_ids if origin == CandidateProvenance.RELATION_EXPANDED else ()),
                )
            record = promote_candidate(
                record,
                CandidateProvenance.PROTECTED_CANDIDATE,
                reason="coverage shortlist selected for exact matched-span verification",
            )
            receipt = build_source_span_verification(
                candidate_id,
                record.coordinate,
                text,
                authority_generation=index.authority_generation,
                authority_as_of=index.authority_as_of,
                start=start,
                end=end,
            )
            record = verify_candidate(
                record,
                (receipt,),
                source_resolver=lambda value: source_text((value.document_id, int(value.node_id))),
                authority_generation=index.authority_generation,
                authority_as_of=index.authority_as_of,
            )
            records[candidate_id] = record
            verified_coordinates.append(coordinate)
        except Exception as exc:
            errors.append({
                "stage": "provenance-span-verify",
                "coordinate": f"{coordinate[0]}:{coordinate[1]}",
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })
    snapshots["provenance-span-verify"] = list(verified_coordinates)

    protected_coordinates = _protected_bundle(
        question,
        verified_coordinates,
        floor_set,
        candidates,
        spans,
        explicit_scopes,
        scope_by_coordinate,
    )
    snapshots["protected-bundle-union"] = list(verified_coordinates)
    menu = _menu_rows(
        index, question, verified_coordinates, candidates, source_cache, spans
    )
    compiler_started = time.perf_counter()
    packet = _compile_packet(llm, question, menu, explicit_scopes=explicit_scopes)
    compiler_wall_ms = round((time.perf_counter() - compiler_started) * 1000, 3)
    # The compiler may under-select even a verified high-priority prior.  Preserve
    # that small deterministic bundle as exact-source CONTEXT claims so the answer
    # model can use it without receiving a free-form proposition.
    known_claim_ids = {str(row["evidence_id"]) for row in packet["claims"]}
    for bundle_number, coordinate in enumerate(protected_coordinates, 1):
        evidence_id = legacy._candidate_id(coordinate)
        if evidence_id in known_claim_ids:
            continue
        quote = spans[coordinate][2][:800].strip()
        if not quote:
            continue
        scope_id = scope_by_coordinate[coordinate]
        quote_id = f"protected-{bundle_number}-{evidence_id}"
        quote_row = {
            "quote_id": quote_id,
            "evidence_id": evidence_id,
            "scope_id": scope_id,
            "role": "CONTEXT",
            "quote": quote,
        }
        packet["quotes"].append(quote_row)
        packet["claims"].append({
            **quote_row,
            "claim_id": quote_id,
            "proposition": quote,
        })
        if evidence_id not in packet["selected_ids"]:
            packet["selected_ids"].append(evidence_id)
        if scope_id not in packet["selected_scope_ids"]:
            packet["selected_scope_ids"].append(scope_id)
        known_claim_ids.add(evidence_id)
    selected_ids = set(packet["selected_ids"])
    selected_additions = [
        coordinate for coordinate in verified_coordinates
        if coordinate not in floor_set
        and legacy._candidate_id(coordinate) in selected_ids
        and coordinate not in protected_coordinates
    ]
    role_counts = Counter(
        row["evidence_id"] for row in packet.get("claims") or ()
    )
    best_role = {
        evidence_id: min(
            (_ROLE_PRIORITY.get(row["role"], 99) for row in packet.get("claims") or () if row["evidence_id"] == evidence_id),
            default=99,
        )
        for evidence_id in selected_ids
    }
    selected_additions.sort(key=lambda coordinate: (
        best_role.get(legacy._candidate_id(coordinate), 99),
        -role_counts.get(legacy._candidate_id(coordinate), 0),
        -float(candidates[coordinate].score),
        candidates[coordinate].source_order,
    ))
    presentation_cap = min(
        int(cap), HARD_CAP,
        max(PRESENTATION_TARGET, len(floor_coordinates) + len(protected_coordinates)),
    )
    selected_coordinates = list(dict.fromkeys((*floor_coordinates, *protected_coordinates)))
    for coordinate in selected_additions:
        if len(selected_coordinates) >= presentation_cap:
            break
        selected_coordinates.append(coordinate)
    selected_coordinates = list(dict.fromkeys(selected_coordinates))
    snapshots["quote-entailment-select"] = list(selected_coordinates)
    snapshots["decision-coverage-gate"] = list(selected_coordinates)
    snapshots["compiled-evidence-present"] = list(selected_coordinates)
    ready_assessments = int(bool(packet["direct_gate_allowed"]))
    bundle_dict = {
        "profile": "scope-entailment-bundle-v2",
        "required_elements": packet["required_elements"],
        "elements": packet["elements"],
        "missing_elements": packet["missing_elements"],
        "needs_targeted_search": bool(packet["missing_elements"]),
        "direct_conclusion_allowed": False,
    }

    output: list[Section] = []
    floor_by_coordinate = dict(zip(floor_coordinates, floor))
    legal_compilation = {
        "schema_version": "scope-entailment-bundle-evidence-packet-v2",
        "answer_mode": packet["answer_mode"],
        "direct_rule_answer_allowed": (
            packet["answer_mode"] == "DIRECT_RULE" and packet["direct_gate_allowed"]
        ),
        "selected_evidence_ids": [
            legacy._candidate_id(coordinate) for coordinate in selected_coordinates
        ],
        "claims": packet["claims"],
        "coverage": packet["elements"],
        "missing": packet["missing"],
        "selected_scope_ids": packet["selected_scope_ids"],
        "required_elements": packet["required_elements"],
        "decision_elements": packet["elements"],
        "missing_elements": packet["missing_elements"],
        "protected_evidence_ids": [
            legacy._candidate_id(coordinate) for coordinate in protected_coordinates
        ],
        "reason": packet["reason"],
        "ready_assessment_count": ready_assessments,
        "needs_targeted_search": bundle_dict["needs_targeted_search"],
    }
    for number, coordinate in enumerate(selected_coordinates, 1):
        section = floor_by_coordinate.get(coordinate)
        if section is None:
            section = legacy._section(index, coordinate, number, origin="coverage-verified")
        section.n = number
        record = records.get(legacy._candidate_id(coordinate))
        states = sorted(state.value for state in record.states) if record is not None else []
        section.legal_meta = {
            **dict(section.legal_meta or {}),
            "integrated_research": {
                "candidate_id": legacy._candidate_id(coordinate),
                "scope_id": scope_by_coordinate.get(
                    coordinate,
                    _scope_id(index.docs[coordinate[0]].name, coordinate[0]),
                ),
                "states": states,
                "direct_conclusion_allowed": False,
            },
            "legal_compilation": deepcopy(legal_compilation),
        }
        output.append(section)

    capture = _capture(index, case_id, arm_id, snapshots, skips)
    selected_id_set = {legacy._candidate_id(coordinate) for coordinate in selected_coordinates}
    claim_evidence_violations = sorted({
        str(row["evidence_id"]) for row in packet["claims"]
        if str(row["evidence_id"]) not in selected_id_set
    })
    verified_evidence_violations = sorted({
        f"{coordinate[0]}:{coordinate[1]}"
        for coordinate in selected_coordinates
        if legacy._candidate_id(coordinate) not in records
        or not records[legacy._candidate_id(coordinate)].verified
    })
    protected_id_set = {
        legacy._candidate_id(coordinate) for coordinate in protected_coordinates
    }
    protected_bundle_violations = sorted(protected_id_set - selected_id_set)
    scope_violations = sorted({
        str(row.get("scope_id") or "")
        for row in packet["claims"]
        if explicit_scopes
        and str(row.get("scope_id") or "").startswith("MARKET:")
        and str(row.get("scope_id") or "") not in explicit_scopes
    })
    quote_entailment_violations = sorted({
        str(row["claim_id"]) for row in packet["claims"]
        if row["proposition"] != row["quote"]
    })
    decision_gate_violations = []
    if packet["answer_mode"] == "DIRECT_RULE" and not packet["direct_gate_allowed"]:
        decision_gate_violations.append("direct_without_complete_decision_coverage")
    total_planning_ms = (time.perf_counter() - deterministic_started) * 1000
    deterministic_ms = round(max(0.0, total_planning_ms - compiler_wall_ms), 3)
    meta = {
        "enabled": True,
        "profile": "scope-entailment-bundle-v2",
        "status": "extended" if selected_coordinates != floor_coordinates else "unchanged",
        "fallback": "",
        "authority_generation": index.authority_generation,
        "authority_as_of": index.authority_as_of,
        "legal_system_catalog_version": system_runtime.system_map.catalog_version,
        "legal_graph_generation": graph_snapshot.generation_id,
        "before_count": len(floor_coordinates),
        "after_count": len(output),
        "added_count": len(set(selected_coordinates) - floor_set),
        "baseline_floor_preserved": floor_set.issubset(selected_coordinates),
        "final_evidence_cap": min(int(cap), HARD_CAP),
        "presentation_target": PRESENTATION_TARGET,
        "direct_conclusion_allowed": False,
        "answer_gate": {
            "mode": packet["answer_mode"],
            "direct_rule_answer_allowed": legal_compilation["direct_rule_answer_allowed"],
            "violations": decision_gate_violations,
        },
        "deterministic_planning_ms": deterministic_ms,
        "compiler_wall_ms": compiler_wall_ms,
        "validation": {
            "closed_id_violations": [],
            "generation_violations": [],
            "verified_evidence_violations": verified_evidence_violations,
            "claim_evidence_violations": claim_evidence_violations,
            "answer_gate_violations": decision_gate_violations,
            "protected_bundle_violations": protected_bundle_violations,
            "scope_violations": scope_violations,
            "quote_entailment_violations": quote_entailment_violations,
        },
        "query_plan": query_plan,
        "planner": planner_meta,
        "entry_plans": [
            plan.to_dict() if hasattr(plan, "to_dict") else plan for plan in entry_plans
        ],
        "grounding": grounding,
        "semantic": semantic_meta,
        "alignment": alignment_rows,
        "scope_partition": {
            "explicit_scope_ids": sorted(explicit_scopes),
            "scope_ids": sorted(set(scope_by_coordinate.values())),
        },
        "evidence_packet": legal_compilation,
        "coverage_bundle": bundle_dict,
        "final_compilation": {
            "case_id": case_id,
            "selected_coordinates": [f"{doc_id}:{node}" for doc_id, node in selected_coordinates],
            "selected_count": len(selected_coordinates),
            "discarded_coordinates": [
                f"{doc_id}:{node}" for doc_id, node in verified_coordinates
                if (doc_id, node) not in set(selected_coordinates)
            ],
            "unverified_coordinates": [],
            "missing_mandatory_coordinates": [],
            "cap": presentation_cap,
            "ready_for_legal_assessment": bool(ready_assessments),
            "protected_coordinates": [
                f"{doc_id}:{node}" for doc_id, node in protected_coordinates
            ],
        },
        "stage_capture": capture,
        "errors": errors,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return output, meta


__all__ = [
    "COMPILER_SCHEMA",
    "COMPILER_SYSTEM",
    "HARD_CAP",
    "PRESENTATION_TARGET",
    "SHORTLIST_CAP",
    "extend_sections",
    "fallback_to_floor",
]
