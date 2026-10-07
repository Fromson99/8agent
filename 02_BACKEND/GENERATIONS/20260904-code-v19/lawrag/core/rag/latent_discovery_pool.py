"""Experiment-only latent semantic discovery envelope for ADR-0087.

This module deliberately has no gold-aware API.  It turns a question and a
closed semantic plan into corpus-owned article-root coordinates, records every
transition through the shared v4 stage ledger, and returns an append-only pool.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable, Mapping, Sequence

from lawrag.core.rag import (
    assertionfirst,
    general_search,
    legal_coordinates,
    relation_navigation,
    termexplore,
)
from lawrag.core.rag import vector as vector_mod
from lawrag.runtime import retrieval_stage_ledger as ledger
from lawrag.core.rag.index import Index


MODEL = "claude-haiku-4-5-20251001"
POOL_CAP = 512
CHANNEL_LIMIT = 96
PER_DOCUMENT_LIMIT = 12
VECTOR_PER_QUERY = 48
ASSERTION_LIMIT = 96
RELATION_LIMIT = 512
DOCUMENT_MENU_LIMIT = 64
DOCUMENT_HITS_PER_DOC = 12

_ARTICLE_OR_AUTHORITY = re.compile(
    r"제\s*\d+(?:\s*-\s*\d+)?\s*(?:조(?:의\s*\d+)?|항|호)|"
    r"(?:법률|시행령|시행규칙|규정)\s*$"
)

_SEMANTIC_SYSTEM = """너는 법률 discovery pool을 위한 의미 가설 작성기다.

질문의 일상 사실을 법률 문서에서 쓰일 가능성이 있는 업무유형·규율행위로 여러 갈래 번역한다.
정답 법령명·기관명·조문번호를 추측하지 말고 좌표를 만들지 않는다. 한 가설로 성급히 확정하지
말고 주체, 행위, 대상, 조건, 질문이 요구하는 법적 기능을 분리한다.

operation_hypotheses는 최대 6개의 짧은 정식 업무유형 후보다. exact_surfaces는 법령 본문에
그대로 등장할 만한 짧은 표현, keyword_queries는 BM25용 낱말·짧은 구, vector_queries는 서로
다른 의미권을 겨냥하는 자연어 문장이다. 모든 값은 질문의 사실에서 설명 가능해야 한다."""

_SEMANTIC_SCHEMA = {
    "type": "object",
    "properties": {
        "factual_slots": {"type": "array", "items": {"type": "string"}},
        "operation_hypotheses": {"type": "array", "items": {"type": "string"}},
        "exact_surfaces": {"type": "array", "items": {"type": "string"}},
        "keyword_queries": {"type": "array", "items": {"type": "string"}},
        "vector_queries": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "factual_slots", "operation_hypotheses", "exact_surfaces",
        "keyword_queries", "vector_queries",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class DiscoveryPlan:
    mode: str
    factual_slots: tuple[str, ...]
    operation_hypotheses: tuple[str, ...]
    exact_surfaces: tuple[str, ...]
    keyword_queries: tuple[str, ...]
    vector_queries: tuple[str, ...]
    rejected: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def semantic_prompt(question: str) -> tuple[str, str, dict[str, Any]]:
    return _SEMANTIC_SYSTEM, f"[질문]\n{question}", _SEMANTIC_SCHEMA


def _clean_values(values: object, *, cap: int, allow_authority: bool = False) \
        -> tuple[tuple[str, ...], tuple[str, ...]]:
    out: list[str] = []
    rejected: list[str] = []
    for raw in values or ():
        value = re.sub(r"\s+", " ", str(raw or "")).strip()[:160]
        key = re.sub(r"\s+", "", value).casefold()
        bad = (
            len(key) < 2
            or key in {re.sub(r"\s+", "", item).casefold() for item in out}
            or (not allow_authority and bool(_ARTICLE_OR_AUTHORITY.search(value)))
        )
        if bad:
            if value and value not in rejected:
                rejected.append(value)
            continue
        out.append(value)
        if len(out) >= cap:
            break
    return tuple(out), tuple(rejected)


def baseline_plan(llm, question: str) -> DiscoveryPlan:
    """Use the current TermExplore planner without its lossy document selector."""

    current = termexplore.extract_terms(llm, question)
    exact = tuple(dict.fromkeys((
        *current.anchor_terms,
        *current.condition_terms,
        *current.fallback_terms,
        *current.operation_terms,
    )))
    keyword = tuple(dict.fromkeys((
        *general_search.fallback_keywords(question),
        *current.anchor_terms,
        *current.condition_terms,
        *current.operation_terms,
    )))[:8]
    vectors = tuple(dict.fromkeys((question, *current.operation_terms)))[:4]
    return DiscoveryPlan(
        mode="current-termexplore-envelope",
        factual_slots=tuple((*current.anchor_terms, *current.condition_terms)),
        operation_hypotheses=current.operation_terms,
        exact_surfaces=exact[:12],
        keyword_queries=keyword,
        vector_queries=vectors,
        rejected=current.rejected,
    )


def semantic_plan(llm, question: str) -> DiscoveryPlan:
    system, user, schema = semantic_prompt(question)
    raw = llm.structured(
        "rag.legalclosure.latent_seed_lattice",
        system,
        user,
        schema,
        max_tokens=1800,
        effort=None,
        model=MODEL,
    )
    if not isinstance(raw, Mapping):
        raw = {}
    rejected: list[str] = []

    def values(key: str, cap: int) -> tuple[str, ...]:
        accepted, dropped = _clean_values(raw.get(key), cap=cap)
        rejected.extend(item for item in dropped if item not in rejected)
        return accepted

    factual = values("factual_slots", 8)
    operations = values("operation_hypotheses", 6)
    exact = values("exact_surfaces", 6)
    keywords = values("keyword_queries", 8)
    vectors = values("vector_queries", 4)
    if not keywords:
        keywords = tuple(general_search.fallback_keywords(question))[:8]
    if not vectors:
        vectors = (question,)
    return DiscoveryPlan(
        mode="semantic-seed-lattice",
        factual_slots=factual,
        operation_hypotheses=operations,
        exact_surfaces=tuple(dict.fromkeys((*exact, *operations)))[:12],
        keyword_queries=tuple(dict.fromkeys((*keywords, *operations)))[:8],
        vector_queries=tuple(dict.fromkeys((*vectors, question)))[:4],
        rejected=tuple(rejected),
    )


def _canonical(index: Index, coordinate: tuple[str, object]) -> tuple[str, int] | None:
    doc_id, node = coordinate
    view = index.docs.get(str(doc_id))
    if view is None or node not in view.by_id:
        return None
    root = legal_coordinates.article_root(view, node)
    if root not in view.by_id:
        return None
    return str(doc_id), int(root)


def ordered_unique(index: Index, values: Iterable[tuple[str, object]]) \
        -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for value in values:
        coordinate = _canonical(index, value)
        if coordinate is None or coordinate in seen:
            continue
        seen.add(coordinate)
        out.append(coordinate)
    return out


def _channel_exact(index: Index, plan: DiscoveryPlan) -> tuple[list[tuple[str, object]], dict]:
    rows = termexplore.search_all(index, plan.exact_surfaces)
    rows = rows[:CHANNEL_LIMIT]
    return [(row.doc_id, row.node) for row in rows], {
        "terms": list(plan.exact_surfaces),
        "raw_rows": len(rows),
        "rows": [
            {"doc_id": row.doc_id, "node": row.node, "doc": row.doc,
             "path": row.path, "matched": list(row.terms)}
            for row in rows
        ],
    }


def _channel_keyword(index: Index, question: str, plan: DiscoveryPlan, *,
                     doc_ids: set[str] | None = None,
                     limit: int = CHANNEL_LIMIT) -> tuple[list[tuple[str, object]], dict]:
    target = index.scoped(doc_ids, name="adr-0087-document") if doc_ids is not None else index
    result = general_search.search_keywords(
        target,
        plan.keyword_queries,
        question=question,
        limit=limit,
        per_document=(DOCUMENT_HITS_PER_DOC if doc_ids is not None else PER_DOCUMENT_LIMIT),
        extractor="adr-0087-latent-discovery",
    )
    return [(hit.doc_id, hit.node) for hit in result.hits if hit.node is not None], result.as_dict()


def _channel_vector(index: Index, question: str, plan: DiscoveryPlan) \
        -> tuple[list[tuple[str, object]], dict]:
    occurrences: list[tuple[str, object]] = []
    routes: list[dict[str, Any]] = []
    for query in plan.vector_queries[:4]:
        hits = vector_mod.search(
            query,
            topk=VECTOR_PER_QUERY,
            doc_ids=index.scope,
            minimum=-1.0,
        )
        occurrences.extend((doc_id, node) for doc_id, node, _score in hits)
        routes.append({
            "query": query,
            "hits": [
                {"doc_id": doc_id, "node": node, "score": score}
                for doc_id, node, score in hits
            ],
        })
    return occurrences, {"question": question, "routes": routes}


def _channel_assertion(index: Index, question: str, plan: DiscoveryPlan, registry) \
        -> tuple[list[tuple[str, object]], dict]:
    engine = assertionfirst.current(registry)
    queries = tuple(dict.fromkeys((
        question,
        *(f"{question} {operation}" for operation in plan.operation_hypotheses[:4]),
    )))
    occurrences: list[tuple[str, object]] = []
    routes: list[dict[str, Any]] = []
    remaining = ASSERTION_LIMIT
    for query in queries:
        if remaining <= 0:
            break
        hits = engine.search(index, query)[:remaining]
        remaining -= len(hits)
        occurrences.extend((hit.doc_id, hit.node) for hit in hits)
        routes.append({
            "query": query,
            "hits": [
                {"doc_id": hit.doc_id, "node": hit.node,
                 "assertion_id": hit.assertion_id, "strength": hit.strength,
                 "roles": list(hit.roles), "concepts": list(hit.concepts)}
                for hit in hits
            ],
        })
    return occurrences, {"routes": routes}


def retrieve_channels(index: Index, question: str, plan: DiscoveryPlan, registry) \
        -> tuple[dict[str, list[tuple[str, object]]], dict[str, Any]]:
    exact, exact_meta = _channel_exact(index, plan)
    keyword, keyword_meta = _channel_keyword(index, question, plan)
    vector, vector_meta = _channel_vector(index, question, plan)
    assertion, assertion_meta = _channel_assertion(index, question, plan, registry)
    return {
        "exact": exact,
        "keyword": keyword,
        "vector": vector,
        "assertion": assertion,
    }, {
        "exact": exact_meta,
        "keyword": keyword_meta,
        "vector": vector_meta,
        "assertion": assertion_meta,
    }


def relation_coordinates(index: Index, seeds: Sequence[tuple[str, int]], *,
                         mandatory_only: bool) \
        -> tuple[list[tuple[str, object]], dict[str, Any]]:
    hops, meta = relation_navigation.neighbors(
        index,
        seeds,
        direction="both",
        cap=RELATION_LIMIT,
        exclude=seeds,
    )
    selected = [hop for hop in hops if hop.mandatory or not mandatory_only]
    return [(hop.target_doc_id, hop.target_node) for hop in selected], {
        **meta,
        "mandatory_only": mandatory_only,
        "selected_after_mandatory_filter": len(selected),
        "hops": [hop.as_dict(index) for hop in selected],
    }


def document_scoped_coordinates(index: Index, question: str, plan: DiscoveryPlan,
                                doc_ids: Sequence[str]) \
        -> tuple[list[tuple[str, object]], dict[str, Any]]:
    chosen = list(dict.fromkeys(str(value) for value in doc_ids))[:DOCUMENT_MENU_LIMIT]
    occurrences: list[tuple[str, object]] = []
    routes: list[dict[str, Any]] = []
    for doc_id in chosen:
        rows, meta = _channel_keyword(
            index,
            question,
            plan,
            doc_ids={doc_id},
            limit=DOCUMENT_HITS_PER_DOC,
        )
        occurrences.extend(rows)
        routes.append({"doc_id": doc_id, "result": meta})
    return occurrences, {"documents": chosen, "routes": routes}


def residual_global_vector(index: Index, question: str, plan: DiscoveryPlan) \
        -> tuple[list[tuple[str, object]], dict[str, Any]]:
    query = " ".join(dict.fromkeys((
        question,
        *plan.factual_slots,
        *plan.operation_hypotheses,
        "적용요건 예외 절차 산정 겸직 신고",
    )))[:900]
    hits = vector_mod.search(query, topk=CHANNEL_LIMIT, doc_ids=index.scope, minimum=-1.0)
    return [(doc_id, node) for doc_id, node, _score in hits], {
        "query": query,
        "hits": [
            {"doc_id": doc_id, "node": node, "score": score}
            for doc_id, node, score in hits
        ],
    }


def _discard_rows(values: Iterable[tuple[str, int]], reason: str) -> list[dict[str, Any]]:
    return [{"coordinate": coordinate, "reason": reason} for coordinate in values]


def record_simple_capture(index: Index, case_id: str, arm_id: str,
                          channels: Mapping[str, Sequence[tuple[str, object]]],
                          relation_occurrences: Sequence[tuple[str, object]], *,
                          prefix: str) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    canonicalizer = ledger.index_article_root_canonicalizer(index)
    recorder = ledger.StageLedgerRecorder(case_id, arm_id, canonicalizer)
    recorder.record_stage(f"{prefix}00-source", "source", [])
    stage_ids = []
    all_occurrences: list[tuple[str, object]] = []
    for pos, name in enumerate(("exact", "keyword", "vector", "assertion"), start=1):
        stage_id = f"{prefix}{pos}0-{name}"
        values = list(channels.get(name) or ())
        stage_ids.append(stage_id)
        all_occurrences.extend(values)
        recorder.record_stage(
            stage_id,
            "retrieve",
            values,
            parent_stage_ids=[f"{prefix}00-source"],
            after_occurrence_count=len(values),
        )
    union = ordered_unique(index, all_occurrences)
    recorder.record_stage(
        f"{prefix}50-union",
        "union",
        union,
        parent_stage_ids=stage_ids,
        after_occurrence_count=len(all_occurrences),
    )
    recorder.record_stage(
        f"{prefix}60-canonicalize",
        "canonicalize",
        union,
        parent_stage_ids=[f"{prefix}50-union"],
        after_occurrence_count=len(union),
    )
    expanded = ordered_unique(index, [*union, *relation_occurrences])
    recorder.record_stage(
        f"{prefix}70-relation-closure",
        "expand",
        expanded,
        parent_stage_ids=[f"{prefix}60-canonicalize"],
        after_occurrence_count=len(union) + len(relation_occurrences),
    )
    final = expanded[:POOL_CAP]
    recorder.record_stage(
        f"{prefix}80-pool-cap",
        "select",
        final,
        parent_stage_ids=[f"{prefix}70-relation-closure"],
        discard_reasons=_discard_rows(expanded[POOL_CAP:], "pool_cap_512"),
    )
    recorder.record_stage(
        f"{prefix}90-present",
        "present",
        final,
        parent_stage_ids=[f"{prefix}80-pool-cap"],
    )
    return recorder.capture(), final


def record_residual_capture(
    index: Index,
    case_id: str,
    channels: Mapping[str, Sequence[tuple[str, object]]],
    mandatory_relations: Sequence[tuple[str, object]],
    residual_relations: Sequence[tuple[str, object]],
    document_occurrences: Sequence[tuple[str, object]],
    global_vector_occurrences: Sequence[tuple[str, object]],
    final_relations: Sequence[tuple[str, object]],
) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    prefix = "r"
    canonicalizer = ledger.index_article_root_canonicalizer(index)
    recorder = ledger.StageLedgerRecorder(
        case_id, "seed-residual-discovery", canonicalizer)
    recorder.record_stage("r00-source", "source", [])
    channel_stage_ids: list[str] = []
    all_occurrences: list[tuple[str, object]] = []
    for pos, name in enumerate(("exact", "keyword", "vector", "assertion"), start=1):
        stage_id = f"r{pos}0-{name}"
        values = list(channels.get(name) or ())
        channel_stage_ids.append(stage_id)
        all_occurrences.extend(values)
        recorder.record_stage(
            stage_id, "retrieve", values,
            parent_stage_ids=["r00-source"],
            after_occurrence_count=len(values),
        )
    pool = ordered_unique(index, all_occurrences)
    recorder.record_stage(
        "r50-union", "union", pool,
        parent_stage_ids=channel_stage_ids,
        after_occurrence_count=len(all_occurrences),
    )
    recorder.record_stage(
        "r60-canonicalize", "canonicalize", pool,
        parent_stage_ids=["r50-union"], after_occurrence_count=len(pool),
    )

    def append(stage_id: str, kind: str, occurrences: Sequence[tuple[str, object]],
               parent: str) -> None:
        nonlocal pool
        before_count = len(pool)
        pool = ordered_unique(index, [*pool, *occurrences])
        recorder.record_stage(
            stage_id, kind, pool, parent_stage_ids=[parent],
            after_occurrence_count=before_count + len(occurrences),
        )

    append("r70-relation-closure", "expand", mandatory_relations, "r60-canonicalize")
    append("r80-residual-relation", "expand", residual_relations, "r70-relation-closure")
    append("r90-document-search", "retrieve", document_occurrences, "r80-residual-relation")
    append("r100-global-vector", "retrieve", global_vector_occurrences, "r90-document-search")
    append("r110-final-relation", "expand", final_relations, "r100-global-vector")
    recorder.record_stage(
        "r120-canonicalize", "canonicalize", pool,
        parent_stage_ids=["r110-final-relation"], after_occurrence_count=len(pool),
    )
    final = pool[:POOL_CAP]
    recorder.record_stage(
        "r130-pool-cap", "select", final,
        parent_stage_ids=["r120-canonicalize"],
        discard_reasons=_discard_rows(pool[POOL_CAP:], "pool_cap_512"),
    )
    recorder.record_stage(
        "r140-present", "present", final,
        parent_stage_ids=["r130-pool-cap"],
    )
    return recorder.capture(), final


def run_simple_arm(index: Index, case_id: str, question: str,
                   plan: DiscoveryPlan, registry, *, arm_id: str, prefix: str) \
        -> tuple[dict[str, Any], dict[str, Any]]:
    channels, channel_meta = retrieve_channels(index, question, plan, registry)
    base = ordered_unique(
        index, (value for rows in channels.values() for value in rows))
    relations, relation_meta = relation_coordinates(index, base, mandatory_only=True)
    capture, final = record_simple_capture(
        index, case_id, arm_id, channels, relations, prefix=prefix)
    return capture, {
        "plan": plan.as_dict(),
        "channels": channel_meta,
        "relation_closure": relation_meta,
        "final_coordinates": [
            {"doc_id": doc_id, "node": node} for doc_id, node in final
        ],
    }


def run_residual_arm(index: Index, case_id: str, question: str,
                     plan: DiscoveryPlan, registry) \
        -> tuple[dict[str, Any], dict[str, Any]]:
    channels, channel_meta = retrieve_channels(index, question, plan, registry)
    base = ordered_unique(
        index, (value for rows in channels.values() for value in rows))
    mandatory, mandatory_meta = relation_coordinates(index, base, mandatory_only=True)
    after_mandatory = ordered_unique(index, [*base, *mandatory])
    residual, residual_meta = relation_coordinates(
        index, after_mandatory, mandatory_only=False)
    existing_docs = {doc_id for doc_id, _node in after_mandatory}
    entered_docs = [
        doc_id for doc_id, _node in ordered_unique(index, residual)
        if doc_id not in existing_docs
    ]
    document_rows, document_meta = document_scoped_coordinates(
        index, question, plan, entered_docs)
    global_rows, global_meta = residual_global_vector(index, question, plan)
    before_final_relation = ordered_unique(
        index, [*after_mandatory, *residual, *document_rows, *global_rows])
    final_relations, final_relation_meta = relation_coordinates(
        index, before_final_relation, mandatory_only=True)
    capture, final = record_residual_capture(
        index, case_id, channels, mandatory, residual, document_rows,
        global_rows, final_relations)
    return capture, {
        "plan": plan.as_dict(),
        "channels": channel_meta,
        "relation_closure": mandatory_meta,
        "residual_relation": residual_meta,
        "document_search": document_meta,
        "global_vector": global_meta,
        "final_relation": final_relation_meta,
        "final_coordinates": [
            {"doc_id": doc_id, "node": node} for doc_id, node in final
        ],
    }


__all__ = [
    "ASSERTION_LIMIT", "CHANNEL_LIMIT", "DiscoveryPlan", "MODEL", "POOL_CAP",
    "baseline_plan", "ordered_unique", "record_residual_capture",
    "record_simple_capture", "run_residual_arm", "run_simple_arm",
    "semantic_plan", "semantic_prompt",
]
