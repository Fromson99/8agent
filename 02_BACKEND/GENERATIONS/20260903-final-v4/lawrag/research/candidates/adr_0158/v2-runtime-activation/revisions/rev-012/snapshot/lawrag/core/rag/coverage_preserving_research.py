"""Coverage-preserving legal research profile used by ADR-0115.

The legacy integrated profile is intentionally left intact.  This profile
keeps its LegalClosure floor but replaces raw closure accumulation and a fixed
28-article fill with a small, source-spanned evidence compilation:

    productive entry candidates
    -> capped planned relation closure
    -> soft actor-aware shortlist
    -> exact source-span receipts
    -> closed-ID claim/coverage compiler
    -> one missing-cell search
    -> adaptive evidence packet

The compiler may select and describe verified evidence.  It cannot invent a
corpus coordinate and it does not itself make a substantive legal decision.
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
from lawrag.core.rag.experiments import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_research_llm_selector import branches_from_query_plan
from lawrag.core.rag.legal_research_state import (
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
from lawrag.core.rag.legal_system_entry import scope_alignment
from lawrag.core.rag import integrated_legal_research as legacy


SHORTLIST_CAP = 48
PRESENTATION_TARGET = 22
HARD_CAP = 28
RELATION_ADDITION_CAP = 12
GAP_ADDITION_CAP = 12
SPAN_CHARS = 2200
_TOKEN = re.compile(r"[0-9A-Za-z가-힣%]{2,}")
_ROLES = (
    "GOVERNING_RULE", "DEFINITION", "CONDITION", "EXCEPTION",
    "PROCEDURE", "SANCTION", "COMPANION", "CONTEXT",
)
_ANSWER_MODES = ("DIRECT_RULE", "CONDITIONAL_APPLICATION", "INSUFFICIENT")
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


COMPILER_SYSTEM = """너는 법률 조사의 중간 evidence compiler다. 최종 답변을 쓰지 않는다.
질문과 현재 법령 코퍼스에서 검증된 조문 span 메뉴를 받는다. 메뉴의 evidence_id만 선택하고,
법률 명제를 정확한 원문 quote에 결속한다.

규칙:
1. 질문에 직접 답하는 지배규범, 정의, 요건, 예외, 절차, 제재와 필수 동반규범만 선택한다.
2. 선택 개수를 채우지 않는다. 필요한 것만 선택하며 보통 4~12개면 충분하다.
3. quote는 메뉴 excerpt에서 글자를 바꾸지 말고 연속된 원문 그대로 복사한다.
4. 같은 조문 안의 시점·수치·주체·항·호를 서로 바꾸어 결합하지 않는다.
5. coverage는 제공된 predicate/coverage_key 조합만 사용하고, 해당 값을 직접 증명하는
   evidence_id와 quote가 있을 때만 낸다.
6. 직접적인 법문 해석으로 답할 수 있으면 DIRECT_RULE, 사용자 사실의 추가 포섭이 필요하면
   CONDITIONAL_APPLICATION, 핵심 규범 자체가 없으면 INSUFFICIENT다.
7. 부족한 경우에만 missing을 내고, search_terms는 질문 또는 excerpt에 근거한 짧은 법률
   표현으로 쓴다. 코퍼스 ID나 법령명을 지어내지 않는다.
8. 관련 있어 보인다는 이유만으로 CONTEXT를 늘리지 않는다."""


COMPILER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "selected_ids": {"type": "array", "items": {"type": "string"}},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "evidence_id": {"type": "string"},
                    "role": {"type": "string", "enum": list(_ROLES)},
                    "proposition": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": [
                    "claim_id", "evidence_id", "role", "proposition", "quote"
                ],
                "additionalProperties": False,
            },
        },
        "coverage": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "predicate": {"type": "string"},
                    "coverage_key": {"type": "string"},
                    "evidence_id": {"type": "string"},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": [
                    "predicate", "coverage_key", "evidence_id", "value", "quote"
                ],
                "additionalProperties": False,
            },
        },
        "answer_mode": {"type": "string", "enum": list(_ANSWER_MODES)},
        "missing": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "coverage_key": {"type": "string"},
                    "search_terms": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["coverage_key", "search_terms"],
                "additionalProperties": False,
            },
        },
        "reason": {"type": "string"},
    },
    "required": [
        "selected_ids", "claims", "coverage", "answer_mode", "missing", "reason"
    ],
    "additionalProperties": False,
}


_STAGE_SPECS = (
    ("question-source", "source", ()),
    ("closed-grounding-retrieve", "retrieve", ("question-source",)),
    ("legal-system-route-retrieve", "retrieve", ("closed-grounding-retrieve",)),
    ("semantic-card-retrieve", "retrieve", ("legal-system-route-retrieve",)),
    ("baseline-floor-union", "union", ("semantic-card-retrieve",)),
    ("typed-legal-relation-expand", "expand", ("baseline-floor-union",)),
    ("candidate-shortlist-filter", "filter", ("typed-legal-relation-expand",)),
    ("provenance-span-verify", "canonicalize", ("candidate-shortlist-filter",)),
    ("claim-span-coverage-select", "select", ("provenance-span-verify",)),
    ("targeted-gap-retrieve", "retrieve", ("claim-span-coverage-select",)),
    ("final-coverage-compile", "select", ("targeted-gap-retrieve",)),
    ("compiled-evidence-present", "present", ("final-coverage-compile",)),
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
        "candidate-shortlist-filter": "not_in_coverage_shortlist",
        "claim-span-coverage-select": "not_selected_by_claim_span_compiler",
        "final-coverage-compile": "not_selected_by_final_coverage_compiler",
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
    allowed_coverage: Mapping[tuple[str, str], None],
) -> dict[str, Any]:
    menu_by_id = {str(row["evidence_id"]): row for row in menu}
    selected = []
    for value in (raw or {}).get("selected_ids") or ():
        evidence_id = str(value)
        if evidence_id in menu_by_id and evidence_id not in selected:
            selected.append(evidence_id)
    claims: list[dict[str, str]] = []
    claim_ids: set[str] = set()
    for number, row in enumerate((raw or {}).get("claims") or (), 1):
        if not isinstance(row, Mapping):
            continue
        evidence_id = str(row.get("evidence_id") or "")
        role = str(row.get("role") or "")
        quote = str(row.get("quote") or "").strip()
        proposition = str(row.get("proposition") or "").strip()
        excerpt = str(((menu_by_id.get(evidence_id) or {}).get("span") or {}).get("excerpt") or "")
        if (
            evidence_id not in menu_by_id or role not in _ROLES or not proposition
            or not quote or quote not in excerpt
        ):
            continue
        claim_id = str(row.get("claim_id") or f"claim-{number}").strip() or f"claim-{number}"
        if claim_id in claim_ids:
            claim_id = f"{claim_id}-{number}"
        claim_ids.add(claim_id)
        if evidence_id not in selected:
            selected.append(evidence_id)
        claims.append({
            "claim_id": claim_id,
            "evidence_id": evidence_id,
            "role": role,
            "proposition": proposition[:800],
            "quote": quote[:800],
        })
    coverage: list[dict[str, str]] = []
    seen_coverage: set[tuple[str, str]] = set()
    for row in (raw or {}).get("coverage") or ():
        if not isinstance(row, Mapping):
            continue
        predicate = str(row.get("predicate") or "")
        coverage_key = str(row.get("coverage_key") or "")
        evidence_id = str(row.get("evidence_id") or "")
        value = str(row.get("value") or "").strip()
        quote = str(row.get("quote") or "").strip()
        excerpt = str(((menu_by_id.get(evidence_id) or {}).get("span") or {}).get("excerpt") or "")
        pair = (predicate, coverage_key)
        if (
            pair not in allowed_coverage or pair in seen_coverage
            or evidence_id not in menu_by_id or not value or not quote or quote not in excerpt
        ):
            continue
        seen_coverage.add(pair)
        if evidence_id not in selected:
            selected.append(evidence_id)
        coverage.append({
            "predicate": predicate,
            "coverage_key": coverage_key,
            "evidence_id": evidence_id,
            "value": value[:800],
            "quote": quote[:800],
        })
    missing: list[dict[str, Any]] = []
    for row in (raw or {}).get("missing") or ():
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("coverage_key") or "").strip()[:120]
        terms: list[str] = []
        for raw_term in row.get("search_terms") or ():
            term = str(raw_term).strip()[:80]
            if len(term) >= 2 and term not in terms:
                terms.append(term)
            if len(terms) >= 6:
                break
        if key and terms:
            missing.append({"coverage_key": key, "search_terms": terms})
        if len(missing) >= 8:
            break
    mode = str((raw or {}).get("answer_mode") or "INSUFFICIENT")
    if mode not in _ANSWER_MODES:
        mode = "INSUFFICIENT"
    if mode == "DIRECT_RULE" and not any(
        row["role"] in {"GOVERNING_RULE", "DEFINITION"} for row in claims
    ):
        mode = "INSUFFICIENT"
    if not claims:
        mode = "INSUFFICIENT"
    return {
        "selected_ids": selected[:18],
        "claims": claims[:32],
        "coverage": coverage,
        "answer_mode": mode,
        "missing": missing,
        "reason": str((raw or {}).get("reason") or "")[:1000],
        "closed_id_violations": [],
        "invalid_claim_count": max(0, len((raw or {}).get("claims") or ()) - len(claims)),
        "invalid_coverage_count": max(
            0, len((raw or {}).get("coverage") or ()) - len(coverage)
        ),
    }


def _compile_packet(
    llm: Any,
    question: str,
    menu: Sequence[Mapping[str, Any]],
    allowed: Mapping[tuple[str, str], None],
) -> dict[str, Any]:
    allowed_rows = [
        {"predicate": predicate, "coverage_key": key}
        for predicate, key in sorted(allowed)
    ]
    user = (
        f"[질문]\n{question}\n\n"
        f"[허용 coverage 조합]\n{json.dumps(allowed_rows, ensure_ascii=False)}\n\n"
        f"[검증 evidence 메뉴]\n{json.dumps(list(menu), ensure_ascii=False)}"
    )
    raw = None if llm is None else llm.structured(
        "rag.coverage_preserving.evidence_compiler",
        COMPILER_SYSTEM,
        user,
        COMPILER_SCHEMA,
        max_tokens=5000,
        effort="low",
    )
    return _sanitize_packet(raw, menu, allowed)


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


def fallback_to_floor(
    index: Index,
    floor: Sequence[Section],
    *,
    case_id: str,
    arm_id: str,
    reason: str,
) -> tuple[list[Section], dict[str, Any]]:
    """Public rollback boundary shared with ``legalclosure_runtime``."""

    return _fallback(
        index, floor, case_id=case_id, arm_id=arm_id, reason=reason,
    )
    for number, section in enumerate(floor, 1):
        section.n = number
    return list(floor), {
        "enabled": True,
        "profile": "coverage-preserving-v1",
        "status": "fallback",
        "fallback": reason,
        "before_count": len(coordinates),
        "after_count": len(coordinates),
        "added_count": 0,
        "baseline_floor_preserved": True,
        "direct_conclusion_allowed": False,
        "deterministic_planning_ms": 0.0,
        "validation": {
            "closed_id_violations": [],
            "generation_violations": [reason],
            "verified_evidence_violations": [],
            "claim_evidence_violations": [],
            "answer_gate_violations": [],
        },
        "stage_capture": _capture(index, case_id, arm_id, snapshots, skips),
        "errors": [{"stage": "runtime", "error": reason}],
        "elapsed_ms": 0.0,
    }


def extend_sections(
    index: Index,
    question: str,
    floor_sections: Sequence[Section],
    *,
    llm: Any = None,
    cap: int = 32,
    graph_root: Any = None,
    case_id: str = "runtime-case",
    arm_id: str = "coverage-preserving-compiler",
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
    snapshots["candidate-shortlist-filter"] = list(shortlist)

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

    semantic_predicates = tuple(
        str(value) for value in semantic_meta.get("allowed_predicates") or ()
    )
    relation_predicates = tuple(dict.fromkeys((*active_predicates, *semantic_predicates)))
    allowed = _allowed_coverage(relation_predicates)
    menu = _menu_rows(
        index, question, verified_coordinates, candidates, source_cache, spans
    )
    packet = _compile_packet(llm, question, menu, allowed)
    selected_ids = set(packet["selected_ids"])
    claim_selected = [
        coordinate for coordinate in verified_coordinates
        if coordinate in floor_set or legacy._candidate_id(coordinate) in selected_ids
    ]
    snapshots["claim-span-coverage-select"] = list(claim_selected)

    gap_coordinates: list[tuple[str, int]] = []
    search_terms = tuple(dict.fromkeys(
        str(term)
        for row in packet.get("missing") or ()
        for term in row.get("search_terms") or ()
        if str(term).strip()
    ))[:8]
    if search_terms:
        try:
            gap_result = general_search.search_keywords(
                index,
                search_terms,
                question=question,
                limit=GAP_ADDITION_CAP,
                per_document=2,
                extractor="coverage-gap",
            )
            for rank, hit in enumerate(gap_result.hits):
                coordinate = legacy._canonical(index, (hit.doc_id, hit.node))
                if coordinate is None or coordinate in candidates:
                    continue
                legacy._add(
                    candidates,
                    coordinate,
                    score=620.0 + float(hit.score) - rank,
                    branch_id="coverage-gap",
                    origin=CandidateProvenance.GROUNDED_CONCEPT,
                    coverage_keys=tuple(
                        str(row.get("coverage_key") or "")
                        for row in packet.get("missing") or ()
                    ),
                    matched=hit.matched,
                )
                row = candidates[coordinate]
                text = source_text(coordinate)
                start, end, quote = _source_span(text, question, row.matched)
                spans[coordinate] = (start, end, quote)
                candidate_id = legacy._candidate_id(coordinate)
                record = seed_candidate(
                    candidate_id,
                    ResearchCoordinate(coordinate[0], coordinate[1]),
                    CandidateProvenance.GROUNDED_CONCEPT,
                )
                record = promote_candidate(
                    record,
                    CandidateProvenance.PROTECTED_CANDIDATE,
                    reason="targeted missing-cell result selected for span verification",
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
                gap_coordinates.append(coordinate)
        except Exception as exc:
            errors.append({"stage": "targeted-gap-retrieve", "error": f"{type(exc).__name__}: {exc}"[:500]})
    targeted_union = list(dict.fromkeys((*claim_selected, *gap_coordinates)))
    snapshots["targeted-gap-retrieve"] = targeted_union

    if gap_coordinates:
        recompile_coordinates = list(dict.fromkeys((
            *floor_coordinates,
            *(coordinate for coordinate in verified_coordinates if legacy._candidate_id(coordinate) in selected_ids),
            *gap_coordinates,
        )))[:SHORTLIST_CAP]
        menu = _menu_rows(
            index, question, recompile_coordinates, candidates, source_cache, spans
        )
        packet = _compile_packet(llm, question, menu, allowed)
        selected_ids = set(packet["selected_ids"])

    selected_additions = [
        coordinate for coordinate in candidates
        if coordinate not in floor_set
        and legacy._candidate_id(coordinate) in selected_ids
        and legacy._candidate_id(coordinate) in records
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
    presentation_cap = min(int(cap), HARD_CAP, max(len(floor_coordinates), PRESENTATION_TARGET))
    selected_coordinates = list(floor_coordinates)
    for coordinate in selected_additions:
        if len(selected_coordinates) >= presentation_cap:
            break
        selected_coordinates.append(coordinate)
    selected_coordinates = list(dict.fromkeys(selected_coordinates))
    snapshots["final-coverage-compile"] = list(selected_coordinates)
    snapshots["compiled-evidence-present"] = list(selected_coordinates)

    bindings = _bindings(packet, records)
    predicate_values = {item.value for item in RelationPredicate}
    active_for_bundle = tuple(
        predicate
        for value in relation_predicates
        if value in predicate_values
        for predicate in (RelationPredicate(value),)
        if predicate in RELATION_BEHAVIOR_POLICIES
    )
    evidence_bundle = compile_research_evidence(
        question,
        records,
        relation_predicates=active_for_bundle,
        bindings_by_predicate=bindings,
    )
    bundle_dict = evidence_bundle.to_dict()
    ready_assessments = sum(
        bool(row.get("ready_for_assessment"))
        for row in bundle_dict.get("compilations", {}).values()
    )

    output: list[Section] = []
    floor_by_coordinate = dict(zip(floor_coordinates, floor))
    legal_compilation = {
        "schema_version": "coverage-preserving-evidence-packet-v1",
        "answer_mode": packet["answer_mode"],
        "direct_rule_answer_allowed": packet["answer_mode"] == "DIRECT_RULE",
        "selected_evidence_ids": [
            legacy._candidate_id(coordinate) for coordinate in selected_coordinates
        ],
        "claims": packet["claims"],
        "coverage": packet["coverage"],
        "missing": packet["missing"],
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
    deterministic_ms = round((time.perf_counter() - deterministic_started) * 1000, 3)
    meta = {
        "enabled": True,
        "profile": "coverage-preserving-v1",
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
            "direct_rule_answer_allowed": packet["answer_mode"] == "DIRECT_RULE",
            "violations": [],
        },
        "deterministic_planning_ms": deterministic_ms,
        "validation": {
            "closed_id_violations": [],
            "generation_violations": [],
            "verified_evidence_violations": verified_evidence_violations,
            "claim_evidence_violations": claim_evidence_violations,
            "answer_gate_violations": [],
        },
        "query_plan": query_plan,
        "planner": planner_meta,
        "entry_plans": [
            plan.to_dict() if hasattr(plan, "to_dict") else plan for plan in entry_plans
        ],
        "grounding": grounding,
        "semantic": semantic_meta,
        "alignment": alignment_rows,
        "evidence_packet": legal_compilation,
        "coverage_bundle": bundle_dict,
        "final_compilation": {
            "case_id": case_id,
            "selected_coordinates": [f"{doc_id}:{node}" for doc_id, node in selected_coordinates],
            "selected_count": len(selected_coordinates),
            "discarded_coordinates": [
                f"{doc_id}:{node}" for doc_id, node in snapshots["targeted-gap-retrieve"]
                if (doc_id, node) not in set(selected_coordinates)
            ],
            "unverified_coordinates": [],
            "missing_mandatory_coordinates": [],
            "cap": presentation_cap,
            "ready_for_legal_assessment": bool(ready_assessments),
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
