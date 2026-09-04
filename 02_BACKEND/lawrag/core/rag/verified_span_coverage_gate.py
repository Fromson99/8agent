"""Experiment-only verified-span coverage gate for bounded exploration.

The model may judge whether the current evidence is sufficient and choose one
closed route.  It may not emit legal coordinates, citations, or search text.
All evidence references are server-owned span IDs and all route candidates are
selected by deterministic code before a second verified-span selector may
admit them append-only.
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterable

from lawrag.core.rag import provider_compatible_span_selector
from lawrag.core.rag import verified_span_selector as span_base
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


PRODUCT_MODEL = "claude-haiku-4-5-20251001"
SELECTED_CAP = 20
CURRENT_ROWS_MAX = 20
CURRENT_WINDOW_CHARS = 900
CURRENT_SPAN_CHARS = 450
CURRENT_SPANS_PER_ROW = 2
SUPPORTING_SPANS_MAX = 6
ROUTE_CANDIDATES_MAX = 3
OUTPUT_TOKENS_MAX = 900

DECISIONS = ("answer", "explore", "insufficient")
GAP_TYPES = (
    "none", "governing_rule", "condition", "exception", "definition",
    "delegation", "companion_rule", "authority_or_version", "other",
)
ROUTES = (
    "none", "relation", "document_search", "global_search",
    "structure_move",
)

_SYSTEM = """너는 법률답변 직전의 근거 충분성 판정자다.

현재 근거는 서버가 원문에서 검증한 V span ID로만 제시된다. 질문에 답할 지배규정과 필요한
요건·예외·정의·위임/동반규정이 현재 span에 충분하면 decision=answer로 한다. 결정적 근거가
빠졌고 닫힌 탐색 경로로 보충할 가치가 있으면 decision=explore로 하고 route 하나를 고른다.
현재 근거만으로도 부족하지만 제시된 경로 중 유망한 길이 없으면 decision=insufficient로 한다.

relation은 현재 조문의 법적 관계, document_search는 현재 법령 안의 다른 조문,
global_search는 전체 corpus 검색 결과, structure_move는 인접·계층·참조 구조를 뜻한다.
supporting_span_ids에는 현재 판단을 실제로 떠받치는 V ID만 복사한다. 새 조문 좌표·법률명·
인용문·검색어를 만들지 않는다. missing에는 부족한 법적 기능만 짧게 적고, reason에는 판정
근거만 적는다. answer이면 route=none, explore이면 route는 none이 아니어야 한다."""


def _schema(span_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": list(DECISIONS)},
            "supporting_span_ids": {
                "type": "array",
                "items": {"type": "string", "enum": list(span_ids)},
            },
            "gap_type": {"type": "string", "enum": list(GAP_TYPES)},
            "route": {"type": "string", "enum": list(ROUTES)},
            "missing": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": [
            "decision", "supporting_span_ids", "gap_type", "route",
            "missing", "reason",
        ],
        "additionalProperties": False,
    }


def _dedupe(rows: Iterable[termexplore.TermBranch], *, cap: int) \
        -> list[termexplore.TermBranch]:
    return span_base._dedupe(rows, cap=cap)


def _current_spans(index: Index, rows: list[termexplore.TermBranch],
                   question: str) -> tuple[list[dict], dict[str, dict]]:
    public: list[dict] = []
    by_id: dict[str, dict] = {}
    serial = 1
    for row in _dedupe(rows, cap=CURRENT_ROWS_MAX):
        source = span_base._source(index, row)
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        start, end = span_base._window(
            source, question, cap=CURRENT_WINDOW_CHARS)
        ranges = span_base._chunk_ranges(
            source, start, end, cap=CURRENT_SPAN_CHARS)
        for span_start, span_end in ranges[:CURRENT_SPANS_PER_ROW]:
            span_id = f"V{serial:03d}"
            serial += 1
            record = {
                "span_id": span_id,
                "coordinate": [row.doc_id, row.node],
                "document": row.doc,
                "path": row.path,
                "origin": row.origin,
                "source_sha256": source_hash,
                "start": span_start,
                "end": span_end,
                "text": source[span_start:span_end],
                "row": row,
            }
            by_id[span_id] = record
            public.append({
                key: value for key, value in record.items()
                if key not in {"row", "coordinate"}
            })
    return public, by_id


def _validate_decision(raw: object, by_id: dict[str, dict]) -> tuple[dict, list[str]]:
    errors: list[str] = []
    value = raw if isinstance(raw, dict) else {}
    decision = str(value.get("decision") or "insufficient")
    route = str(value.get("route") or "none")
    gap_type = str(value.get("gap_type") or "other")
    if decision not in DECISIONS:
        errors.append(f"decision_outside_menu:{decision}")
        decision = "insufficient"
    if route not in ROUTES:
        errors.append(f"route_outside_menu:{route}")
        route = "none"
    if gap_type not in GAP_TYPES:
        errors.append(f"gap_type_outside_menu:{gap_type}")
        gap_type = "other"
    if decision == "answer" and route != "none":
        errors.append("answer_route_must_be_none")
        route = "none"
    if decision == "explore" and route == "none":
        errors.append("explore_route_must_not_be_none")
        decision = "insufficient"

    accepted: list[dict] = []
    seen: set[str] = set()
    for item in value.get("supporting_span_ids") or ():
        span_id = str(item)
        if span_id in seen:
            continue
        seen.add(span_id)
        record = by_id.get(span_id)
        if record is None:
            errors.append(f"span_outside_menu:{span_id}")
            continue
        accepted.append({
            key: item for key, item in record.items() if key != "row"
        })
        if len(accepted) >= SUPPORTING_SPANS_MAX:
            break
    missing = [str(item).strip()[:160]
               for item in value.get("missing") or () if str(item).strip()][:6]
    return {
        "decision": decision,
        "supporting_span_ids": [item["span_id"] for item in accepted],
        "supporting_spans": accepted,
        "gap_type": gap_type,
        "route": route,
        "missing": missing,
        "reason": str(value.get("reason") or "")[:600],
    }, errors


def judge(index: Index, question: str, llm,
          incumbent: list[termexplore.TermBranch]) -> tuple[dict, dict]:
    """Judge current evidence once using only server-owned span IDs."""
    spans, by_id = _current_spans(index, incumbent, question)
    base_meta = {
        "model": PRODUCT_MODEL,
        "verified_spans": spans,
        "presented_span_count": len(spans),
        "current_coordinate_count": len(_dedupe(incumbent, cap=SELECTED_CAP)),
    }
    if llm is None or not spans:
        return {
            "decision": "insufficient", "supporting_span_ids": [],
            "supporting_spans": [], "gap_type": "other", "route": "none",
            "missing": ["판정 가능한 현재 원문 근거"],
            "reason": "llm_or_verified_span_unavailable",
        }, {**base_meta, "ran": False, "validation_errors": []}
    user = (
        f"[원질문]\n{question}\n\n"
        f"[현재 verified span — V ID 전용]\n"
        f"{json.dumps(spans, ensure_ascii=False)}"
    )
    raw = llm.structured(
        "rag.legalclosure.verified_span_coverage_gate", _SYSTEM, user,
        _schema(list(by_id)), max_tokens=OUTPUT_TOKENS_MAX, effort=None,
        model=PRODUCT_MODEL,
    )
    decision, errors = _validate_decision(raw, by_id)
    return decision, {
        **base_meta, "ran": True, "raw_output": raw,
        "validation_errors": errors,
    }


def _route_match(row: termexplore.TermBranch, route: str,
                 incumbent_docs: set[str]) -> bool:
    origin = str(row.origin or "").lower()
    if route == "relation":
        return "relation" in origin or bool(row.source_doc_id)
    if route == "document_search":
        return row.doc_id in incumbent_docs
    if route == "structure_move":
        return any(token in origin for token in (
            "structural", "structure", "reference", "requirement",
            "companion", "adjacent",
        ))
    if route == "global_search":
        return True
    return False


def route_candidates(pool: list[termexplore.TermBranch],
                     incumbent: list[termexplore.TermBranch], route: str,
                     *, cap: int = ROUTE_CANDIDATES_MAX) \
        -> list[termexplore.TermBranch]:
    """Deterministically expose a bounded route slice, never gold-aware."""
    selected = {row.coordinate for row in incumbent}
    incumbent_docs = {row.doc_id for row in incumbent}
    rows = [
        row for row in pool
        if row.coordinate not in selected
        and _route_match(row, route, incumbent_docs)
    ]
    return _dedupe(rows, cap=max(0, int(cap)))


def explore(index: Index, question: str, llm,
            incumbent: list[termexplore.TermBranch],
            evidence_pool: list[termexplore.TermBranch], decision: dict,
            *, cap: int = SELECTED_CAP) -> tuple[list[termexplore.TermBranch], dict]:
    """Execute at most one route and admit only verified spans append-only."""
    selected = _dedupe(incumbent, cap=cap)
    route = str(decision.get("route") or "none")
    candidates = route_candidates(evidence_pool, selected, route)
    base_meta = {
        "strategy": "verified-span-coverage-routed-explore",
        "decision": decision,
        "route": route,
        "route_candidates": span_base._pool_rows(candidates),
        "initial_selected_count": len(selected),
        "hard_deletes": 0,
        "baseline_preserved": True,
    }
    if decision.get("decision") != "explore":
        return selected, {
            **base_meta, "ran": False, "reason": "gate_did_not_explore",
            "selector": None, "promoted": [], "validation_errors": [],
        }
    if len(selected) >= cap:
        return selected, {
            **base_meta, "ran": False, "reason": "no_vacancy",
            "selector": None, "promoted": [], "validation_errors": [],
        }
    if not candidates:
        return selected, {
            **base_meta, "ran": False, "reason": "route_returned_no_candidate",
            "selector": None, "promoted": [], "validation_errors": [],
        }
    target = "; ".join(decision.get("missing") or ()) or question
    result, selector_meta = provider_compatible_span_selector.run(
        index, question, llm, selected, evidence_pool, candidates, target,
        cap=cap, pool_cap=max(len(evidence_pool), len(selected)),
    )
    promoted = [
        row for row in result if row.coordinate not in
        {item.coordinate for item in selected}
    ]
    return result, {
        **base_meta, "ran": True,
        "reason": "route_executed_then_verified_span_selector",
        "selector": selector_meta,
        "promoted": span_base._pool_rows(promoted),
        "validation_errors": list(selector_meta.get("validation_errors") or ()),
    }


__all__ = [
    "DECISIONS", "GAP_TYPES", "PRODUCT_MODEL", "ROUTES", "SELECTED_CAP",
    "explore", "judge", "route_candidates",
]
