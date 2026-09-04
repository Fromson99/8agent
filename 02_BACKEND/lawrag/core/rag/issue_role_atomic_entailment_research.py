"""Issue-role atomic entailment research profile used by ADR-0117.

ADR-0116 and the legacy integrated profiles are intentionally left intact.
This profile keeps the verified candidate pool but changes the selection unit:

    explicit scope partition -> exact source-span receipts
    -> question-span issue/requirement plan
    -> issue-role exact-quote units
    -> deterministic branch-role quota
    -> atomic claim+evidence cap
    -> proposition entailment gate

The compiler cannot invent a corpus coordinate or an intermediate legal
proposition.  Requirements must point back to an exact question span and legal
support must be an exact source quote.
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
from lawrag.core.rag import query_grounding
from lawrag.core.rag.answer import Section
from lawrag.core.rag.experiments import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_research_llm_selector import branches_from_query_plan
from lawrag.core.rag.legal_research_state import (
    CandidateProvenance,
    ResearchCoordinate,
    add_candidate_origin,
    build_source_span_verification,
    promote_candidate,
    seed_candidate,
    verify_candidate,
)
from lawrag.core.rag.legal_semantic_search import plan_semantic_coordinates
from lawrag.core.rag.legal_system_entry import scope_alignment
from lawrag.core.rag import integrated_legal_research as legacy


SHORTLIST_CAP = 48
PRESENTATION_TARGET = 18
HARD_CAP = 22
RELATION_ADDITION_CAP = 12
GAP_ADDITION_CAP = 12
SPAN_CHARS = 2200
ISSUE_CAP = 4
_TOKEN = re.compile(r"[0-9A-Za-z가-힣%]{2,}")
_ROLES = (
    "GOVERNING_RULE", "DEFINITION", "CONDITION", "EXCEPTION",
    "PROCEDURE", "SANCTION", "COMPANION", "CONTEXT",
)
_ANSWER_MODES = ("DIRECT_RULE", "CONDITIONAL_APPLICATION", "INSUFFICIENT")
_REQUIREMENT_KINDS = (
    "governing_rule", "actor_scope", "operative_effect", "condition",
    "exception", "temporal", "numeric", "definition", "procedure", "sanction",
)
_ENTAILMENT_STRENGTHS = ("DIRECT_TEXT", "NEEDS_INFERENCE", "CONTRADICTED", "UNRESOLVED")
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


COMPILER_SYSTEM = """너는 법률 조사의 issue-role atomic entailment compiler다. 최종 답변이나
법률 명제를 새로 쓰지 않는다. 질문과 검증된 조문 span 메뉴를 받는다. issue와 requirement는
질문의 연속 원문 span에 묶고, 법적 지지는 메뉴의 연속 원문 quote에만 묶는다.

규칙:
1. 질문의 독립 법률쟁점을 최대 4개 issue로 나눈다. question_span은 질문에서 글자를 바꾸지
   않은 연속 부분이어야 한다. 각 issue는 GOVERNING_RULE을 항상 요구하고 실제 질문에 필요한
   DEFINITION·CONDITION·EXCEPTION·PROCEDURE·SANCTION 역할만 더 요구한다.
2. requirement도 질문의 exact span에 묶고 governing_rule/actor_scope/operative_effect/
   condition/exception/temporal/numeric/definition/procedure/sanction 중 하나로 분류한다.
3. unit은 닫힌 evidence_id·scope_id, issue_id, legal role과 excerpt의 연속 exact quote만 낸다.
   proposition·요약·법률효과를 새로 쓰지 않는다.
4. entailment는 requirement와 unit 사이가 그 quote 문언만으로 직접 지지되면 DIRECT_TEXT,
   해석·추가 사실이 필요하면 NEEDS_INFERENCE, 반대면 CONTRADICTED, 없으면 UNRESOLVED다.
5. 질문이 특정 시장 scope를 명시하면 다른 시장 규범을 섞지 않는다. 공통 상위법은 가능하다.
6. 모든 requirement가 DIRECT_TEXT이고 issue별 GOVERNING_RULE이 있을 때만 DIRECT_RULE이다.
   지배규범은 있으나 사실 포섭이 남으면 CONDITIONAL_APPLICATION, 지배규범 자체가 없으면
   INSUFFICIENT다. 보통 issue 1~3개, evidence unit 4~14개만 선택한다."""


COMPILER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string"},
                    "question_span": {"type": "string"},
                    "required_roles": {"type": "array", "items": {"type": "string", "enum": list(_ROLES)}},
                    "requirements": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "requirement_id": {"type": "string"},
                            "kind": {"type": "string", "enum": list(_REQUIREMENT_KINDS)},
                            "question_span": {"type": "string"},
                        },
                        "required": ["requirement_id", "kind", "question_span"],
                        "additionalProperties": False,
                    }},
                },
                "required": ["issue_id", "question_span", "required_roles", "requirements"],
                "additionalProperties": False,
            },
        },
        "units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "unit_id": {"type": "string"},
                    "evidence_id": {"type": "string"},
                    "scope_id": {"type": "string"},
                    "issue_ids": {"type": "array", "items": {"type": "string"}},
                    "role": {"type": "string", "enum": list(_ROLES)},
                    "quote": {"type": "string"},
                },
                "required": ["unit_id", "evidence_id", "scope_id", "issue_ids", "role", "quote"],
                "additionalProperties": False,
            },
        },
        "entailments": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "requirement_id": {"type": "string"},
                "unit_id": {"type": "string"},
                "strength": {"type": "string", "enum": list(_ENTAILMENT_STRENGTHS)},
            },
            "required": ["requirement_id", "unit_id", "strength"],
            "additionalProperties": False,
        }},
        "answer_mode": {"type": "string", "enum": list(_ANSWER_MODES)},
        "reason": {"type": "string"},
    },
    "required": ["issues", "units", "entailments", "answer_mode", "reason"],
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
    ("issue-role-unit-compile", "select", ("provenance-span-verify",)),
    ("atomic-quota-select", "select", ("issue-role-unit-compile",)),
    ("proposition-entailment-gate", "select", ("atomic-quota-select",)),
    ("compiled-evidence-present", "present", ("proposition-entailment-gate",)),
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
        "issue-role-unit-compile": "not_selected_by_issue_role_compiler",
        "atomic-quota-select": "outside_atomic_issue_role_quota",
        "proposition-entailment-gate": "not_in_proposition_entailment_basis",
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


def _inferred_role(text: str) -> str:
    """Coarse fallback role used only after the closed compiler units.

    This does not assert a legal proposition.  It merely determines which
    branch-role quota receives the already verified source coordinate.
    """

    if any(token in text for token in ("정의", "이란", "란", "뜻한다")):
        return "DEFINITION"
    if any(token in text for token in ("다만", "제외", "불구하고", "예외")):
        return "EXCEPTION"
    if any(token in text for token in ("과태료", "벌칙", "처벌", "제재")):
        return "SANCTION"
    if any(token in text for token in ("신고", "승인", "결의", "절차", "통지")):
        return "PROCEDURE"
    if any(token in text for token in ("경우", "요건", "조건", "한하여")):
        return "CONDITION"
    return "GOVERNING_RULE"


def _prune_packet_atomic(
    packet: Mapping[str, Any], selected_ids: Sequence[str]
) -> dict[str, Any]:
    """Prune evidence, units, claims and entailments as one atomic operation."""

    output = deepcopy(dict(packet))
    selected = set(selected_ids)
    output["units"] = [
        row for row in output.get("units") or ()
        if str(row.get("evidence_id") or "") in selected
    ]
    unit_ids = {str(row["unit_id"]) for row in output["units"]}
    output["claims"] = [
        row for row in output.get("claims") or ()
        if str(row.get("evidence_id") or "") in selected
        and str(row.get("claim_id") or "") in unit_ids
    ]
    output["entailments"] = [
        row for row in output.get("entailments") or ()
        if str(row.get("unit_id") or "") in unit_ids
    ]
    requirement_ids = {
        str(requirement["requirement_id"])
        for issue in output.get("issues") or ()
        for requirement in issue.get("requirements") or ()
    }
    direct_ids = {
        str(row["requirement_id"])
        for row in output["entailments"]
        if row.get("strength") == "DIRECT_TEXT"
    }
    missing = sorted(requirement_ids - direct_ids)
    governed = {
        str(issue_id)
        for unit in output["units"] if unit.get("role") == "GOVERNING_RULE"
        for issue_id in unit.get("issue_ids") or ()
    }
    every_issue_governed = all(
        str(issue.get("issue_id") or "") in governed
        for issue in output.get("issues") or ()
    )
    output["selected_ids"] = list(selected_ids)
    output["selected_scope_ids"] = list(dict.fromkeys(
        str(row.get("scope_id") or "") for row in output["units"]
        if str(row.get("scope_id") or "")
    ))
    output["coverage"] = [
        row for row in output["entailments"]
        if row.get("strength") == "DIRECT_TEXT"
    ]
    output["missing_requirements"] = missing
    output["missing"] = [
        {"coverage_key": requirement_id, "search_terms": []}
        for requirement_id in missing
    ]
    output["direct_gate_allowed"] = not missing and every_issue_governed
    output["answer_mode"] = (
        "DIRECT_RULE" if output["direct_gate_allowed"] else
        "CONDITIONAL_APPLICATION" if every_issue_governed else
        "INSUFFICIENT"
    )
    return output


def _atomic_quota_select(
    question: str,
    packet: Mapping[str, Any],
    verified_coordinates: Sequence[tuple[str, int]],
    floor: set[tuple[str, int]],
    candidates: Mapping[tuple[str, int], Any],
    spans: Mapping[tuple[str, int], tuple[int, int, str]],
    explicit_scopes: frozenset[str],
    scope_by_coordinate: Mapping[tuple[str, int], str],
    *,
    cap: int,
) -> tuple[list[tuple[str, int]], dict[str, Any]]:
    """Select by (issue, role) quota, never by one global protected list."""

    by_id = {legacy._candidate_id(value): value for value in verified_coordinates}
    units_by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for unit in packet.get("units") or ():
        units_by_id[str(unit.get("evidence_id") or "")].append(unit)
    required_keys = [
        (str(issue["issue_id"]), str(role))
        for issue in packet.get("issues") or ()
        for role in issue.get("required_roles") or ()
    ]
    direct_units = {
        str(row.get("unit_id") or "")
        for row in packet.get("entailments") or ()
        if row.get("strength") == "DIRECT_TEXT"
    }
    selected: list[tuple[str, int]] = []
    selected_set: set[tuple[str, int]] = set()
    satisfied: set[tuple[str, str]] = set()

    def add(coordinate: tuple[str, int]) -> None:
        if coordinate in selected_set or len(selected) >= cap:
            return
        selected.append(coordinate)
        selected_set.add(coordinate)
        evidence_id = legacy._candidate_id(coordinate)
        for unit in units_by_id.get(evidence_id, ()):
            for issue_id in unit.get("issue_ids") or ():
                satisfied.add((str(issue_id), str(unit.get("role") or "")))

    # First preserve evidence which directly entails a question requirement.
    for unit in packet.get("units") or ():
        if str(unit.get("unit_id") or "") in direct_units:
            coordinate = by_id.get(str(unit.get("evidence_id") or ""))
            if coordinate is not None:
                add(coordinate)
    # Then fill every compiler-declared (issue, legal role) cell once.
    for key in required_keys:
        if key in satisfied:
            continue
        for unit in packet.get("units") or ():
            if (
                key[0] in {str(value) for value in unit.get("issue_ids") or ()}
                and str(unit.get("role") or "") == key[1]
            ):
                coordinate = by_id.get(str(unit.get("evidence_id") or ""))
                if coordinate is not None:
                    add(coordinate)
                    break
    # Remaining compiler units are still more authoritative than heuristic fill.
    for unit in packet.get("units") or ():
        coordinate = by_id.get(str(unit.get("evidence_id") or ""))
        if coordinate is not None:
            add(coordinate)

    tokens = tuple(dict.fromkeys(_TOKEN.findall(question)))
    ranked = []
    for coordinate in verified_coordinates:
        if coordinate in selected_set:
            continue
        excerpt = spans[coordinate][2]
        role = _inferred_role(excerpt)
        lexical = sum(min(len(token), 12) for token in tokens if token in excerpt)
        scope_bonus = 1 if scope_by_coordinate.get(coordinate) in explicit_scopes else 0
        row = candidates[coordinate]
        ranked.append((
            0 if coordinate in floor else 1,
            -scope_bonus,
            _ROLE_PRIORITY.get(role, 99),
            -lexical,
            -len(row.coverage_keys),
            _origin_priority(row),
            -float(row.score),
            row.source_order,
            coordinate,
        ))
    ranked.sort()
    # Fill to the presentation target while avoiding a single-role monopoly.
    role_counts = Counter(
        str(unit.get("role") or "")
        for coordinate in selected
        for unit in units_by_id.get(legacy._candidate_id(coordinate), ())
    )
    deferred = []
    target = min(cap, PRESENTATION_TARGET)
    for row in ranked:
        coordinate = row[-1]
        role = _inferred_role(spans[coordinate][2])
        if role_counts[role] >= 4:
            deferred.append(coordinate)
            continue
        add(coordinate)
        role_counts[role] += 1
        if len(selected) >= target:
            break
    for coordinate in deferred:
        if len(selected) >= target:
            break
        add(coordinate)
    working_packet = deepcopy(dict(packet))
    existing_evidence = {
        str(row.get("evidence_id") or "") for row in working_packet.get("units") or ()
    }
    first_issue = str((working_packet.get("issues") or [{}])[0].get("issue_id") or "I1")
    for number, coordinate in enumerate(selected, 1):
        evidence_id = legacy._candidate_id(coordinate)
        if evidence_id in existing_evidence:
            continue
        quote = spans[coordinate][2][:800].strip()
        if not quote:
            continue
        unit_id = f"FALLBACK-U{number}-{evidence_id}"
        unit = {
            "unit_id": unit_id,
            "evidence_id": evidence_id,
            "scope_id": scope_by_coordinate[coordinate],
            "issue_ids": [first_issue],
            "role": _inferred_role(quote),
            "quote": quote,
        }
        working_packet.setdefault("units", []).append(unit)
        working_packet.setdefault("claims", []).append({
            "claim_id": unit_id,
            "evidence_id": evidence_id,
            "scope_id": unit["scope_id"],
            "role": unit["role"],
            "proposition": quote,
            "quote": quote,
        })
    pruned = _prune_packet_atomic(
        working_packet, [legacy._candidate_id(value) for value in selected]
    )
    pruned["quota"] = {
        "required": [f"{issue_id}|{role}" for issue_id, role in required_keys],
        "satisfied": [f"{issue_id}|{role}" for issue_id, role in sorted(satisfied)],
        "missing": [
            f"{issue_id}|{role}" for issue_id, role in required_keys
            if (issue_id, role) not in satisfied
        ],
    }
    return selected, pruned


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
    question: str,
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
    issues: list[dict[str, Any]] = []
    issue_ids: set[str] = set()
    requirement_ids: set[str] = set()
    invalid_issue_count = 0
    for number, row in enumerate((raw or {}).get("issues") or (), 1):
        if not isinstance(row, Mapping):
            invalid_issue_count += 1
            continue
        question_span = str(row.get("question_span") or "").strip()
        if not question_span or question_span not in question:
            invalid_issue_count += 1
            continue
        issue_id = str(row.get("issue_id") or f"I{number}").strip() or f"I{number}"
        if issue_id in issue_ids:
            issue_id = f"I{number}"
        issue_ids.add(issue_id)
        roles = ["GOVERNING_RULE"]
        for value in row.get("required_roles") or ():
            role = str(value)
            if role in _ROLES and role not in roles:
                roles.append(role)
        requirements: list[dict[str, str]] = []
        for offset, requirement in enumerate(row.get("requirements") or (), 1):
            if not isinstance(requirement, Mapping):
                continue
            kind = str(requirement.get("kind") or "")
            span = str(requirement.get("question_span") or "").strip()
            requirement_id = str(
                requirement.get("requirement_id") or f"{issue_id}-R{offset}"
            ).strip()
            if (
                kind not in _REQUIREMENT_KINDS or not span or span not in question
                or not requirement_id or requirement_id in requirement_ids
            ):
                continue
            requirement_ids.add(requirement_id)
            requirements.append({
                "requirement_id": requirement_id,
                "kind": kind,
                "question_span": span,
            })
        if not any(row["kind"] == "governing_rule" for row in requirements):
            requirement_id = f"{issue_id}-GOVERNING"
            while requirement_id in requirement_ids:
                requirement_id += "-X"
            requirement_ids.add(requirement_id)
            requirements.insert(0, {
                "requirement_id": requirement_id,
                "kind": "governing_rule",
                "question_span": question_span,
            })
        issues.append({
            "issue_id": issue_id,
            "question_span": question_span[:500],
            "required_roles": roles,
            "requirements": requirements[:8],
        })
        if len(issues) >= ISSUE_CAP:
            break
    if not issues:
        fallback_span = question.strip()[:500] or "질문"
        issues = [{
            "issue_id": "I1",
            "question_span": fallback_span,
            "required_roles": ["GOVERNING_RULE"],
            "requirements": [{
                "requirement_id": "I1-GOVERNING",
                "kind": "governing_rule",
                "question_span": fallback_span,
            }],
        }]
        issue_ids = {"I1"}
        requirement_ids = {"I1-GOVERNING"}

    units: list[dict[str, Any]] = []
    unit_ids: set[str] = set()
    invalid_quote_count = 0
    for number, row in enumerate((raw or {}).get("units") or (), 1):
        if not isinstance(row, Mapping):
            invalid_quote_count += 1
            continue
        evidence_id = str(row.get("evidence_id") or "")
        scope_id = str(row.get("scope_id") or "")
        role = str(row.get("role") or "")
        linked_issues = list(dict.fromkeys(
            str(value) for value in row.get("issue_ids") or ()
            if str(value) in issue_ids
        ))
        quote = str(row.get("quote") or "").strip()
        menu_row = menu_by_id.get(evidence_id) or {}
        excerpt = str((menu_row.get("span") or {}).get("excerpt") or "")
        if (
            evidence_id not in menu_by_id or role not in _ROLES or not quote or not linked_issues
            or quote not in excerpt or scope_id != str(menu_row.get("scope_id") or "")
            or scope_id in forbidden_market_scopes
        ):
            invalid_quote_count += 1
            continue
        unit_id = str(row.get("unit_id") or f"U{number}").strip() or f"U{number}"
        if unit_id in unit_ids:
            unit_id = f"U{number}"
        unit_ids.add(unit_id)
        units.append({
            "unit_id": unit_id,
            "evidence_id": evidence_id,
            "scope_id": scope_id,
            "issue_ids": linked_issues,
            "role": role,
            "quote": quote[:800],
        })

    entailments: list[dict[str, str]] = []
    seen_entailments: set[tuple[str, str]] = set()
    invalid_entailment_count = 0
    for row in (raw or {}).get("entailments") or ():
        if not isinstance(row, Mapping):
            invalid_entailment_count += 1
            continue
        requirement_id = str(row.get("requirement_id") or "")
        unit_id = str(row.get("unit_id") or "")
        strength = str(row.get("strength") or "")
        key = (requirement_id, unit_id)
        if (
            requirement_id not in requirement_ids or unit_id not in unit_ids
            or strength not in _ENTAILMENT_STRENGTHS or key in seen_entailments
        ):
            invalid_entailment_count += 1
            continue
        seen_entailments.add(key)
        entailments.append({
            "requirement_id": requirement_id,
            "unit_id": unit_id,
            "strength": strength,
        })
    direct_requirement_ids = {
        row["requirement_id"] for row in entailments if row["strength"] == "DIRECT_TEXT"
    }
    missing = sorted(requirement_ids - direct_requirement_ids)
    governing_issue_ids = {
        issue_id
        for unit in units if unit["role"] == "GOVERNING_RULE"
        for issue_id in unit["issue_ids"]
    }
    every_issue_governed = all(row["issue_id"] in governing_issue_ids for row in issues)
    direct_gate_allowed = not missing and every_issue_governed
    mode = (
        "DIRECT_RULE" if direct_gate_allowed else
        "CONDITIONAL_APPLICATION" if every_issue_governed else
        "INSUFFICIENT"
    )
    selected_ids = list(dict.fromkeys(row["evidence_id"] for row in units))
    selected_scopes = list(dict.fromkeys(row["scope_id"] for row in units))
    return {
        "issues": issues,
        "units": units[:32],
        "entailments": entailments[:64],
        "selected_scope_ids": selected_scopes,
        "selected_ids": selected_ids,
        "claims": [
            {
                "claim_id": row["unit_id"],
                "evidence_id": row["evidence_id"],
                "scope_id": row["scope_id"],
                "role": row["role"],
                "proposition": row["quote"],
                "quote": row["quote"],
            }
            for row in units[:32]
        ],
        "coverage": [row for row in entailments if row["strength"] == "DIRECT_TEXT"],
        "answer_mode": mode,
        "missing_requirements": missing,
        "missing": [
            {"coverage_key": requirement_id, "search_terms": []}
            for requirement_id in missing
        ],
        "direct_gate_allowed": direct_gate_allowed,
        "reason": str((raw or {}).get("reason") or "")[:1000],
        "closed_id_violations": [],
        "invalid_issue_count": invalid_issue_count,
        "invalid_quote_count": invalid_quote_count,
        "invalid_entailment_count": invalid_entailment_count,
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
    return _sanitize_packet(raw, menu, question, explicit_scopes=explicit_scopes)


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
        "profile": "issue-role-atomic-entailment-v3",
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
            "atomic_unit_violations": [],
            "atomic_entailment_violations": [],
            "issue_coverage_violations": [],
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
    arm_id: str = "issue-role-atomic-entailment-compiler",
) -> tuple[list[Section], dict[str, Any]]:
    """Return a verified issue-role packet under one atomic evidence cap."""

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

    menu = _menu_rows(
        index, question, verified_coordinates, candidates, source_cache, spans
    )
    compiler_started = time.perf_counter()
    packet = _compile_packet(llm, question, menu, explicit_scopes=explicit_scopes)
    compiler_wall_ms = round((time.perf_counter() - compiler_started) * 1000, 3)
    compiler_coordinates = list(dict.fromkeys(
        coordinate
        for unit in packet.get("units") or ()
        if (coordinate := next(
            (
                value for value in verified_coordinates
                if legacy._candidate_id(value) == str(unit.get("evidence_id") or "")
            ),
            None,
        )) is not None
    ))
    snapshots["issue-role-unit-compile"] = compiler_coordinates
    presentation_cap = min(int(cap), HARD_CAP)
    selected_coordinates, packet = _atomic_quota_select(
        question,
        packet,
        verified_coordinates,
        floor_set,
        candidates,
        spans,
        explicit_scopes,
        scope_by_coordinate,
        cap=presentation_cap,
    )
    snapshots["atomic-quota-select"] = list(selected_coordinates)
    snapshots["proposition-entailment-gate"] = list(selected_coordinates)
    snapshots["compiled-evidence-present"] = list(selected_coordinates)
    ready_assessments = int(bool(packet["direct_gate_allowed"]))
    bundle_dict = {
        "profile": "issue-role-atomic-entailment-v3",
        "issues": packet["issues"],
        "requirements": [
            requirement
            for issue in packet["issues"]
            for requirement in issue.get("requirements") or ()
        ],
        "entailments": packet["entailments"],
        "missing_requirements": packet["missing_requirements"],
        "needs_targeted_search": bool(packet["missing_requirements"]),
        "direct_conclusion_allowed": False,
    }

    output: list[Section] = []
    floor_by_coordinate = dict(zip(floor_coordinates, floor))
    legal_compilation = {
        "schema_version": "issue-role-atomic-entailment-evidence-packet-v3",
        "answer_mode": packet["answer_mode"],
        "direct_rule_answer_allowed": (
            packet["answer_mode"] == "DIRECT_RULE" and packet["direct_gate_allowed"]
        ),
        "selected_evidence_ids": [
            legacy._candidate_id(coordinate) for coordinate in selected_coordinates
        ],
        "issues": packet["issues"],
        "units": packet["units"],
        "entailments": packet["entailments"],
        "claims": packet["claims"],
        "coverage": packet["coverage"],
        "missing": packet["missing"],
        "missing_requirements": packet["missing_requirements"],
        "selected_scope_ids": packet["selected_scope_ids"],
        "quota": packet["quota"],
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
    unit_evidence_violations = sorted({
        str(row["evidence_id"]) for row in packet["units"]
        if str(row["evidence_id"]) not in selected_id_set
    })
    unit_ids = {str(row["unit_id"]) for row in packet["units"]}
    atomic_entailment_violations = sorted({
        str(row["unit_id"]) for row in packet["entailments"]
        if str(row["unit_id"]) not in unit_ids
    })
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
    issue_ids = {str(row["issue_id"]) for row in packet["issues"]}
    issue_coverage_violations = sorted({
        str(issue_id) for row in packet["units"] for issue_id in row["issue_ids"]
        if str(issue_id) not in issue_ids
    })
    decision_gate_violations = []
    if packet["answer_mode"] == "DIRECT_RULE" and not packet["direct_gate_allowed"]:
        decision_gate_violations.append("direct_without_complete_decision_coverage")
    total_planning_ms = (time.perf_counter() - deterministic_started) * 1000
    deterministic_ms = round(max(0.0, total_planning_ms - compiler_wall_ms), 3)
    meta = {
        "enabled": True,
        "profile": "issue-role-atomic-entailment-v3",
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
            "atomic_unit_violations": unit_evidence_violations,
            "atomic_entailment_violations": atomic_entailment_violations,
            "issue_coverage_violations": issue_coverage_violations,
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
            "quota": packet["quota"],
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
