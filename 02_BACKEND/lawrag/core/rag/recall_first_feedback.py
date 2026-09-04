"""Recall-first orthogonal retrieval union over an existing LegalClosure trace.

Experiment-only controller for ADR-0068.  No LLM decision can stop retrieval,
and every corpus-grounded coordinate returned by a route is retained in the
append-only evidence pool.  A second LLM call only ranks source-quoted evidence
for the top-20 presentation; it does not control pool admission.
"""

from __future__ import annotations

from collections import Counter
import json
from typing import Iterable

from lawrag.core.rag import proof_boundary_feedback as pb
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


PRODUCT_MODEL = "claude-haiku-4-5-20251001"
PRESENTED_MAX = 20
POOL_MAX = 96
ROUTE_RESULTS_MAX = 8
UNION_MAX = 40
PROMOTION_MAX = 4
PLANNER_CARDS_MAX = 40
SELECTOR_CARDS_MAX = 40
OUTPUT_TOKENS_MAX = 2_800

ROUTE_KINDS = (
    "relation_expand",
    "exact_search",
    "keyword_search",
    "assertion_search",
    "vector_search",
)

_PLANNER_SYSTEM = """너는 법률 검색어와 점프 seed를 만드는 recall planner다.

현재 후보가 충분하다고 보여도 검색 중단을 결정하지 않는다. 원질문의 법적 업무유형과 지배
규율을 나타내는 corpus 검색 표현을 만든다. 질문에 없는 법령명이나 조문 좌표를 추측하지 말고,
입력 카드 ID만 relation seed로 선택한다.

operation_terms에는 사실표현을 법적 업무유형으로 바꾼 짧은 용어를 쓴다. exact_query,
keywords, assertion_query, vector_query는 서로 같은 문장을 반복하지 말고 다음 공간을 직교하게
겨냥한다: 정확한 규율용어, 핵심 키워드 조합, 법적 명제, 의미적 사실관계. 이미 답이 있어
보여도 모든 필드를 작성한다."""

_SELECTOR_SYSTEM = """너는 검색된 신규 법률 좌표의 top-20 우선순위를 정하는 evidence selector다.

최종 답을 조문 하나가 단독으로 완성할 것을 요구하지 않는다. 원질문과 관련된 지배규정,
companion, 조건, 예외, 부분근거이면 선택할 수 있다. closed/complete 판정은 하지 않는다.
closed candidate menu 밖의 ID를 만들지 말고, 각 선택에는 해당 카드 원문에서 짧은 연속 문구를
그대로 복사한다. 생략부호나 요약을 quote에 넣지 않는다. 가장 유용한 좌표를 최대 8개 고른다."""


def _planner_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "issue": {"type": "string"},
            "operation_terms": {"type": "array", "items": {"type": "string"}},
            "relation_seed_ids": {"type": "array", "items": {"type": "string"}},
            "exact_query": {"type": "string"},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "assertion_query": {"type": "string"},
            "vector_query": {"type": "string"},
        },
        "required": [
            "issue", "operation_terms", "relation_seed_ids", "exact_query",
            "keywords", "assertion_query", "vector_query",
        ],
        "additionalProperties": False,
    }


def _selector_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "issue": {"type": "string"},
            "evidence": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "quote": {"type": "string"},
                    "role": {"type": "string", "enum": [
                        "governing", "companion", "condition",
                        "exception", "partial"]},
                },
                "required": ["candidate_id", "quote", "role"],
                "additionalProperties": False,
            }},
            "uncovered": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["issue", "evidence", "uncovered"],
        "additionalProperties": False,
    }


def _short_values(values: Iterable[object], *, cap: int = 4) -> list[str]:
    out: list[str] = []
    for value in values:
        clean = pb._clean(value, 120)
        if len(clean.replace(" ", "")) >= 2 and clean not in out:
            out.append(clean)
        if len(out) >= cap:
            break
    return out


def _trace_summary(rows: list[termexplore.TermBranch], initial_meta: dict,
                   terms: tuple[str, ...]) -> dict:
    return {
        "observed_coordinates": len(rows),
        "selected_coordinates": len(initial_meta.get("selected") or ()),
        "used_query_atoms": sorted(pb._initial_query_atoms(initial_meta, terms)),
        "origins": dict(Counter(row.origin or "unknown" for row in rows)),
        "previous_actions": list(initial_meta.get("actions") or ()),
    }


def _actions(planner: dict, cards_by_id: dict[str, termexplore.TermBranch],
             pool: list[termexplore.TermBranch], question: str) -> list[dict]:
    operation = _short_values(planner.get("operation_terms") or (), cap=4)
    keywords = _short_values(
        [*(planner.get("keywords") or ()), *operation], cap=6)
    seed_ids = [str(value) for value in planner.get("relation_seed_ids") or ()
                if str(value) in cards_by_id]
    if not seed_ids:
        ranked = sorted(cards_by_id.items(), key=lambda item: (
            int(item[1].mandatory), pb._overlap_score(item[1], question)),
                        reverse=True)
        seed_ids = [cid for cid, _row in ranked[:3]]
    return [
        {
            "kind": "relation_expand", "seed_ids": seed_ids[:3],
            "query": pb._clean(planner.get("issue") or question, 500),
            "keywords": keywords[:4],
        },
        {
            "kind": "exact_search", "from_id": seed_ids[0] if seed_ids else "",
            "query": pb._clean(planner.get("exact_query") or question, 500),
            "keywords": _short_values([*operation, *keywords], cap=4),
        },
        {
            "kind": "keyword_search", "from_id": seed_ids[0] if seed_ids else "",
            "query": pb._clean(planner.get("issue") or question, 500),
            "keywords": keywords[:4],
        },
        {
            "kind": "assertion_search", "from_id": seed_ids[0] if seed_ids else "",
            "query": pb._clean(planner.get("assertion_query") or question, 500),
            "keywords": keywords[:4],
        },
        {
            "kind": "vector_search", "from_id": seed_ids[0] if seed_ids else "",
            "query": pb._clean(planner.get("vector_query") or question, 500),
            "keywords": keywords[:4],
        },
    ]


def _execute_union(index: Index, question: str, actions: list[dict],
                   by_id: dict[str, termexplore.TermBranch],
                   terms: tuple[str, ...], exclude: set[tuple]) \
        -> tuple[list[termexplore.TermBranch], list[dict]]:
    union: list[termexplore.TermBranch] = []
    receipts: list[dict] = []
    visited = set(exclude)
    for action in actions:
        kind = action["kind"]
        fingerprint = pb.stable_fingerprint({
            "kind": kind,
            "query": action.get("query"),
            "keywords": action.get("keywords"),
            "seed_ids": action.get("seed_ids") or (),
        })
        if kind == "relation_expand":
            seeds = [by_id[cid] for cid in action.get("seed_ids") or ()
                     if cid in by_id]
            rows, tool_meta = pb._relation_rows(
                index, seeds, action.get("query") or question,
                tuple(dict.fromkeys((*terms, *(action.get("keywords") or ())))),
                visited, cap=ROUTE_RESULTS_MAX)
        else:
            rows, tool_meta = pb._execute(
                index, question, action, by_id, terms, visited)
        rows = pb._dedupe(rows, cap=ROUTE_RESULTS_MAX)
        union.extend(rows)
        visited.update(row.coordinate for row in rows)
        receipts.append({
            "kind": kind,
            "fingerprint": fingerprint,
            "query": action.get("query") or "",
            "keywords": list(action.get("keywords") or ()),
            "seed_ids": list(action.get("seed_ids") or ()),
            "raw_count": len(rows),
            "tool_meta": tool_meta,
            "skipped": "",
        })
    return pb._dedupe(union, cap=UNION_MAX), receipts


def _select_with_exchange(incumbent: list[termexplore.TermBranch],
                          promoted: list[termexplore.TermBranch], *, cap: int) \
        -> tuple[list[termexplore.TermBranch], list[termexplore.TermBranch]]:
    promoted = pb._dedupe(promoted, cap=PROMOTION_MAX)
    existing = {row.coordinate for row in incumbent}
    promoted = [row for row in promoted if row.coordinate not in existing]
    overflow = max(0, len(incumbent) + len(promoted) - cap)
    evictable = [row for row in reversed(incumbent) if not row.mandatory]
    evicted = evictable[:overflow]
    if len(evicted) < overflow:
        promoted = promoted[:max(0, len(promoted) - (overflow - len(evicted)))]
    evicted_coordinates = {row.coordinate for row in evicted}
    kept = [row for row in incumbent if row.coordinate not in evicted_coordinates]
    available = max(0, cap - len(kept))
    promoted = promoted[:available]
    return pb._dedupe([*kept, *promoted], cap=cap), evicted


def run(index: Index, question: str, llm,
        initial: list[termexplore.TermBranch],
        observed: list[termexplore.TermBranch],
        terms: tuple[str, ...], initial_meta: dict, *,
        cap: int = PRESENTED_MAX, pool_cap: int = POOL_MAX) \
        -> tuple[list[termexplore.TermBranch], dict]:
    incumbent = pb._dedupe(initial, cap=max(1, int(cap)))
    pool = pb._dedupe([*incumbent, *observed],
                      cap=max(len(incumbent), int(pool_cap)))
    pool_coordinates = {row.coordinate for row in pool}
    base_meta = {
        "enabled": True,
        "strategy": "recall-first-orthogonal-union",
        "baseline_preserved_in_pool": True,
        "initial_selected_count": len(incumbent),
        "initial_observed_count": len(pool),
        "hard_deletes": 0,
        "rejected": [],
    }
    if llm is None:
        return incumbent, {
            **base_meta, "ran": False, "status": "unavailable",
            "reason": "llm_unavailable", "actions": [],
            "retained": [], "verified_evidence": [], "promoted": [],
            "evidence_pool": pb._pool_rows(pool),
        }

    cards, by_id = pb._cards(
        index, pool, question, terms, cap=PLANNER_CARDS_MAX, chars=1_200)
    trace = _trace_summary(pool, initial_meta, terms)
    planner_user = (
        f"[원질문]\n{question}\n\n"
        f"[기존 검색 전체 trace 요약]\n{json.dumps(trace, ensure_ascii=False)}\n\n"
        f"[selected+deferred 전체 좌표 카드]\n{json.dumps(cards, ensure_ascii=False)}")
    planner = llm.structured(
        "rag.legalclosure.recall_first_planner",
        _PLANNER_SYSTEM, planner_user, _planner_schema(),
        max_tokens=OUTPUT_TOKENS_MAX, effort=None, model=PRODUCT_MODEL)
    if not isinstance(planner, dict):
        planner = {
            "issue": question, "operation_terms": list(terms)[:4],
            "relation_seed_ids": [], "exact_query": question,
            "keywords": list(terms)[:4], "assertion_query": question,
            "vector_query": question,
        }

    actions = _actions(planner, by_id, pool, question)
    raw_rows, receipts = _execute_union(
        index, question, actions, by_id, terms, pool_coordinates)
    remaining = max(0, int(pool_cap) - len(pool))
    retained = raw_rows[:remaining]
    pool = pb._dedupe([*pool, *retained], cap=int(pool_cap))

    verify_cards, verify_by_id = pb._cards(
        index, retained, question,
        tuple(dict.fromkeys((*terms, *_short_values(
            planner.get("operation_terms") or (), cap=4)))),
        prefix="N", cap=SELECTOR_CARDS_MAX, chars=1_500)
    if verify_cards:
        selector_user = (
            f"[원질문]\n{question}\n\n"
            f"[법적 쟁점]\n{pb._clean(planner.get('issue') or question, 700)}\n\n"
            f"[방문한 직교 route]\n{json.dumps(receipts, ensure_ascii=False)}\n\n"
            f"[closed candidate menu]\n{json.dumps(verify_cards, ensure_ascii=False)}")
        selector = llm.structured(
            "rag.legalclosure.recall_first_selector",
            _SELECTOR_SYSTEM, selector_user, _selector_schema(),
            max_tokens=OUTPUT_TOKENS_MAX, effort=None, model=PRODUCT_MODEL)
    else:
        selector = {"issue": planner.get("issue") or question,
                    "evidence": [], "uncovered": ["no fresh coordinate"]}
    if not isinstance(selector, dict):
        selector = {"issue": "", "evidence": [],
                    "uncovered": ["selector unavailable"]}
    accepted, selector_errors = pb._validate_evidence(
        index, selector.get("evidence"), verify_by_id)
    retained_by_coordinate = {row.coordinate: row for row in retained}
    promoted_rows = pb._dedupe([
        retained_by_coordinate[tuple(item["coordinate"])]
        for item in accepted
        if tuple(item["coordinate"]) in retained_by_coordinate
    ], cap=PROMOTION_MAX)
    selected, evicted = _select_with_exchange(
        incumbent, promoted_rows, cap=max(1, int(cap)))

    return selected, {
        **base_meta,
        "ran": True,
        "status": "expanded",
        "reason": "budgeted_orthogonal_routes_complete",
        "planner": {
            "issue": pb._clean(planner.get("issue"), 700),
            "operation_terms": _short_values(
                planner.get("operation_terms") or (), cap=4),
            "relation_seed_ids": list(planner.get("relation_seed_ids") or ())[:3],
        },
        "coverage_ledger": {
            "required_routes": list(ROUTE_KINDS),
            "visited_routes": [item["kind"] for item in receipts],
            "unvisited_routes": [kind for kind in ROUTE_KINDS
                                 if kind not in {x["kind"] for x in receipts}],
            "stop_reason": "route_budget_exhausted",
        },
        "available_initial_trace": trace,
        "actions": receipts,
        "raw_candidate_count": sum(item["raw_count"] for item in receipts),
        "union_candidate_count": len(raw_rows),
        "retained": pb._pool_rows(retained),
        "verified_evidence": accepted,
        "selector_errors": selector_errors,
        "selector_uncovered": list(selector.get("uncovered") or ()),
        "promoted": pb._pool_rows(promoted_rows),
        "evicted_from_top20": pb._pool_rows(evicted),
        "evidence_pool": pb._pool_rows(pool),
        "duplicate_actions": len(receipts) - len({x["fingerprint"] for x in receipts}),
    }


__all__ = [
    "POOL_MAX", "PRESENTED_MAX", "PROMOTION_MAX", "ROUTE_KINDS",
    "run",
]
