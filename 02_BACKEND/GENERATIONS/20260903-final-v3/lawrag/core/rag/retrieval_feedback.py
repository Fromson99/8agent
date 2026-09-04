"""LegalClosure 최종 후보의 충분성 판정과 상태 기반 재회수 루프.

LLM은 좌표를 만들지 않는다. 현재 후보를 닫힌 id 메뉴로 판정하고 다음 행동만
고른다. 행동 실행은 결정론적 도구가 담당한다.

* ``relation_jump``: 통합 관계 소비 어댑터
* ``keyword_jump``: 본문·제목 BM25
* ``vector_jump``: 구역 임베딩 검색
* ``hybrid_jump``: keyword와 vector를 모두 실행
* ``structure_move``: 인접 조문과 확정 참조

각 걸음은 원질문, 채택·탈락 좌표, 새 검색어와 경위를 보존한다. 같은 좌표는 다시
열지 않으며, 탐색 예산이 끝났는데 충분한 지배근거가 없으면 ``sufficient=False``를
호출부에 돌려 답변을 fail-closed 할 수 있게 한다.
"""

from __future__ import annotations

from dataclasses import replace
import json
import re
from typing import Iterable

from lawrag.core.domain_graph import requirements as requirement_spans
from lawrag.core.rag import general_search
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag import relation_navigation
from lawrag.core.rag import termexplore
from lawrag.core.rag import vector as vector_mod
from lawrag.core.rag.index import Index


PRODUCT_MODEL = "claude-haiku-4-5-20251001"
MAX_STEPS = 3
POOL_MAX = 20
JUMP_MAX = 16
CARD_BODY_CHARS = 520
KEYWORDS_MAX = 4
EDGE_CARDS_MAX = 24
FACETS_MAX = 8

_SYSTEM = (
    "너는 법률 조문 회수의 충분성 판정자이자 탐색 조정자다. 후보는 실제 DB 좌표이며 "
    "C id로만 지칭한다. 질문에 직접 답하는 지배규정, 적용요건·예외, 필요한 본법-하위법령 "
    "동반이 있으면 sufficient=true로 하고 실제 필요한 C id만 keep에 둔다. 주제만 비슷하거나 "
    "질문 속 낱말만 나온 조문은 reject에 둔다. 후보 개수는 충분성 기준이 아니다.\n"
    "부족하면 sufficient=false로 하고 missing에 아직 필요한 법적 기능이나 업무유형을 적은 뒤 "
    "다음 행동 하나를 고른다. relation_jump는 현재 카드의 unopened_edges에 실제 존재하는 "
    "E id만 골라 법적 간선을 열고, structure_move는 "
    "인접·계층을, keyword_jump는 새 법률용어를, vector_jump는 새 의미 문장을 검색한다. "
    "표면어가 잘못된 의미권에 갇혔으면 hybrid_jump로 두 검색을 같이 쓴다. 질문에 없는 조문 "
    "좌표나 법률명을 정답처럼 만들지 말고 검색 입력으로만 제안한다. 더 찾을 방향이 없을 때만 "
    "stop을 고른다."
)


def _clean_text(value: object, cap: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:cap]


def _dedupe(branches: Iterable[termexplore.TermBranch], *, cap: int = POOL_MAX) \
        -> list[termexplore.TermBranch]:
    out, seen = [], set()
    for row in branches:
        if row.coordinate in seen:
            continue
        seen.add(row.coordinate)
        out.append(row)
        if len(out) >= cap:
            break
    return out


def _requirement_facets(row: termexplore.TermBranch) -> list[dict]:
    out, seen = [], set()
    for span in requirement_spans.extract(row.body):
        key = (span.kind, span.surface, span.trigger)
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": span.kind, "surface": span.surface,
                    "trigger": span.trigger})
        if len(out) >= FACETS_MAX:
            break
    return out


def _edge_key(hop: relation_navigation.RelationHop) -> tuple:
    return (hop.source_doc_id, hop.source_node, hop.target_doc_id,
            hop.target_node, hop.graph_kind, hop.direction)


def _cards(index: Index, branches: list[termexplore.TermBranch], *,
           blocked: set[tuple], visited_edges: set[tuple]) \
        -> tuple[list[dict], dict[str, termexplore.TermBranch],
                 dict[str, relation_navigation.RelationHop], dict]:
    public, by_id = [], {}
    id_by_coordinate = {}
    for pos, row in enumerate(branches[:POOL_MAX], start=1):
        oid = f"C{pos}"
        by_id[oid] = row
        id_by_coordinate[row.coordinate] = oid
        public.append({
            "id": oid, "document": row.doc, "path": row.path,
            "origin": row.origin, "matched_terms": list(row.terms),
            "relation_reason": row.relation_reason,
            "mandatory": row.mandatory,
            "requirements": _requirement_facets(row),
            "unopened_edges": [],
            "body": _clean_text(row.body, CARD_BODY_CHARS),
        })
    hops, edge_meta = relation_navigation.neighbors(
        index, [row.coordinate for row in by_id.values()],
        direction="both", cap=EDGE_CARDS_MAX * 2,
        exclude=blocked | set(id_by_coordinate))
    fresh_hops = [hop for hop in hops
                  if _edge_key(hop) not in visited_edges][:EDGE_CARDS_MAX]
    by_edge = {}
    public_by_id = {row["id"]: row for row in public}
    for pos, hop in enumerate(fresh_hops, start=1):
        hop = replace(hop, edge_id=f"E{pos}")
        by_edge[hop.edge_id] = hop
        source_id = id_by_coordinate.get(
            (hop.source_doc_id, hop.source_node))
        if source_id is None:
            continue
        target = hop.as_dict(index)
        public_by_id[source_id]["unopened_edges"].append({
            "id": hop.edge_id, "kind": hop.graph_kind,
            "relation": hop.relation, "direction": hop.direction,
            "target": " ▸ ".join(filter(None, (
                target.get("target_doc"), target.get("target_path")))),
            "mandatory": hop.mandatory,
        })
    edge_meta = {**edge_meta, "available": len(by_edge)}
    return public, by_id, by_edge, edge_meta


def _schema(ids: list[str], edge_ids: list[str]) -> dict:
    id_items = {"type": "string"}
    if ids:
        id_items["enum"] = ids
    edge_items = {"type": "string"}
    if edge_ids:
        edge_items["enum"] = edge_ids
    action_kinds = [
        "keyword_jump", "vector_jump", "hybrid_jump",
        "structure_move", "stop",
    ]
    if edge_ids:
        action_kinds.insert(0, "relation_jump")
    return {
        "type": "object",
        "properties": {
            "sufficient": {"type": "boolean"},
            "keep": {"type": "array", "items": id_items},
            "reject": {"type": "array", "items": id_items},
            "reason": {"type": "string"},
            "missing": {"type": "array", "items": {"type": "string"}},
            "action": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": action_kinds},
                    "from_ids": {"type": "array", "items": id_items},
                    "edge_ids": {"type": "array", "items": edge_items},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "query": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["kind", "from_ids", "edge_ids",
                             "keywords", "query", "reason"],
                "additionalProperties": False,
            },
        },
        "required": ["sufficient", "keep", "reject", "reason", "missing", "action"],
        "additionalProperties": False,
    }


def _decide(llm, index: Index, question: str,
            branches: list[termexplore.TermBranch], *, rejected: list[dict],
            step: int, blocked: set[tuple], visited_edges: set[tuple]) \
        -> tuple[dict | None, dict[str, termexplore.TermBranch],
                 dict[str, relation_navigation.RelationHop], dict]:
    public, by_id, by_edge, edge_meta = _cards(
        index, branches, blocked=blocked, visited_edges=visited_edges)
    user = (
        f"[원질문]\n{question}\n\n[탐색 걸음]\n{step}/{MAX_STEPS}\n\n"
        f"[현재 후보(JSON)]\n{json.dumps(public, ensure_ascii=False)}\n\n"
        f"[이미 탈락한 좌표와 이유(JSON)]\n"
        f"{json.dumps(rejected[-12:], ensure_ascii=False)}"
    )
    raw = llm.structured(
        "rag.legalclosure.feedback", _SYSTEM, user,
        _schema(list(by_id), list(by_edge)),
        max_tokens=1000, effort=None, model=PRODUCT_MODEL,
    )
    return ((raw if isinstance(raw, dict) else None), by_id, by_edge,
            edge_meta)


def _chosen(values: object, by_id: dict[str, termexplore.TermBranch]) \
        -> list[termexplore.TermBranch]:
    out = []
    for oid in values or ():
        row = by_id.get(str(oid))
        if row is not None and row.coordinate not in {item.coordinate for item in out}:
            out.append(row)
    return out


def _relation_candidates(index: Index,
                         hops: list[relation_navigation.RelationHop],
                         terms: tuple[str, ...], *, exclude: set[tuple]) \
        -> tuple[list[termexplore.TermBranch], dict]:
    out = []
    for hop in hops:
        row = coordinates.article_branch(
            index, hop.target_doc_id, hop.target_node, terms,
            origin=f"feedback-relation:{hop.relation}",
            reason=(f"{hop.provenance}:{hop.direction} "
                    f"{hop.surface or hop.graph_kind or hop.relation}"))
        if row is None:
            continue
        out.append(replace(
            row, mandatory=hop.mandatory,
            mandatory_reason=(f"relation:{hop.relation}" if hop.mandatory else ""),
            source_doc_id=hop.source_doc_id, source_node=hop.source_node))
    return _dedupe(out, cap=JUMP_MAX), {
        "source": "selected_edge_ids",
        "selected_count": len(hops),
        "hops": [hop.as_dict(index) for hop in hops],
    }


def _keyword_candidates(index: Index, question: str, keywords: list[str],
                        terms: tuple[str, ...], *, exclude: set[tuple]) \
        -> tuple[list[termexplore.TermBranch], dict]:
    clean = []
    for value in keywords:
        text = _clean_text(value, 80)
        if len(re.sub(r"\s+", "", text)) >= 2 and text not in clean:
            clean.append(text)
        if len(clean) >= KEYWORDS_MAX:
            break
    result = general_search.search_keywords(
        index, clean, question=question, limit=JUMP_MAX * 2,
        per_document=4, extractor="feedback-loop")
    out = []
    merged_terms = tuple(dict.fromkeys((*terms, *clean)))
    for hit in result.hits:
        row = coordinates.article_branch(
            index, hit.doc_id, hit.node, merged_terms,
            origin="feedback-keyword",
            reason=f"matched={','.join(hit.matched)}; score={hit.score}")
        if row is not None and row.coordinate not in exclude:
            out.append(row)
    return _dedupe(out, cap=JUMP_MAX), result.as_dict()


def _vector_candidates(index: Index, query: str, terms: tuple[str, ...], *,
                       exclude: set[tuple]) \
        -> tuple[list[termexplore.TermBranch], dict]:
    clean = _clean_text(query, 300)
    if not clean:
        return [], {"query": "", "hits": 0}
    hits = vector_mod.search(clean, topk=JUMP_MAX, doc_ids=index.scope)
    out = []
    for doc_id, node, score in hits:
        row = coordinates.article_branch(
            index, doc_id, node, terms, origin="feedback-vector",
            reason=f"query={clean}; cosine={score}")
        if row is not None and row.coordinate not in exclude:
            out.append(row)
    return _dedupe(out, cap=JUMP_MAX), {
        "query": clean, "hits": len(hits),
        "coordinates": [{"doc_id": d, "node": n, "score": s}
                        for d, n, s in hits],
    }


def _structure_candidates(index: Index, sources: list[termexplore.TermBranch],
                          terms: tuple[str, ...], *, exclude: set[tuple]) \
        -> tuple[list[termexplore.TermBranch], dict]:
    rows, meta = termexplore.expand_structural(
        index, sources, terms, cap=JUMP_MAX * 2)
    return _dedupe(
        (row for row in rows if row.coordinate not in exclude), cap=JUMP_MAX), meta


def _execute(index: Index, question: str, action: dict,
             by_id: dict[str, termexplore.TermBranch],
             by_edge: dict[str, relation_navigation.RelationHop],
             kept: list[termexplore.TermBranch], terms: tuple[str, ...], *,
             exclude: set[tuple]) -> tuple[list[termexplore.TermBranch], dict]:
    kind = str(action.get("kind") or "stop")
    sources = _chosen(action.get("from_ids"), by_id) or kept
    if kind == "relation_jump":
        hops = [by_edge[edge_id] for edge_id in action.get("edge_ids") or ()
                if edge_id in by_edge][:JUMP_MAX]
        return _relation_candidates(index, hops, terms, exclude=exclude)
    if kind == "structure_move":
        return _structure_candidates(index, sources, terms, exclude=exclude)
    keywords = list(action.get("keywords") or ())
    query = str(action.get("query") or "")
    if kind == "keyword_jump":
        return _keyword_candidates(index, question, keywords, terms, exclude=exclude)
    if kind == "vector_jump":
        return _vector_candidates(index, query, terms, exclude=exclude)
    if kind == "hybrid_jump":
        keyword, kmeta = _keyword_candidates(
            index, question, keywords, terms, exclude=exclude)
        vector, vmeta = _vector_candidates(index, query, terms, exclude=exclude)
        return _dedupe([*keyword, *vector], cap=JUMP_MAX), {
            "keyword": kmeta, "vector": vmeta,
        }
    return [], {"reason": "stop"}


def run(index: Index, question: str, llm,
        initial: list[termexplore.TermBranch], terms: tuple[str, ...], *,
        cap: int = POOL_MAX, max_steps: int = MAX_STEPS) \
        -> tuple[list[termexplore.TermBranch], dict]:
    """최종 후보를 판정하고 부족할 때만 점프 도구를 반복 호출한다."""
    if llm is None:
        return initial, {"enabled": True, "ran": False, "reason": "llm_unavailable"}
    pool = _dedupe(initial, cap=cap)
    best = list(pool)
    visited: set[tuple] = set()
    rejected_coords: set[tuple] = set()
    visited_edges: set[tuple] = set()
    rejected_audit: list[dict] = []
    trail: list[dict] = []
    final_reason, missing = "", []

    for step in range(1, max(1, int(max_steps)) + 1):
        decision, by_id, by_edge, edge_meta = _decide(
            llm, index, question, pool, rejected=rejected_audit, step=step,
            blocked=rejected_coords, visited_edges=visited_edges)
        visited.update(row.coordinate for row in by_id.values())
        if decision is None:
            final_reason = "judge_unavailable"
            break
        kept = _chosen(decision.get("keep"), by_id)
        rejected = _chosen(decision.get("reject"), by_id)
        final_reason = _clean_text(decision.get("reason"), 500)
        missing = [_clean_text(value, 100) for value in decision.get("missing") or ()][:8]
        for row in rejected:
            rejected_coords.add(row.coordinate)
            rejected_audit.append({
                "doc_id": row.doc_id, "node": row.node,
                "doc": row.doc, "path": row.path, "reason": final_reason,
            })
        if decision.get("sufficient") and (kept or pool):
            selected = kept or [row for row in pool if row.coordinate not in rejected_coords]
            selected = _dedupe(selected, cap=cap)
            return selected, {
                "enabled": True, "ran": True, "sufficient": True,
                "steps": step, "reason": final_reason, "missing": missing,
                "trail": trail, "rejected": rejected_audit,
                "selected": [{"doc_id": row.doc_id, "node": row.node,
                              "doc": row.doc, "path": row.path}
                             for row in selected],
                "model": PRODUCT_MODEL,
            }
        action = decision.get("action") or {}
        action_kind = str(action.get("kind") or "stop")
        if action_kind == "stop":
            trail.append({"step": step, "action": "stop", "added": 0,
                          "reason": _clean_text(action.get("reason"), 300)})
            best = kept or [row for row in pool if row.coordinate not in rejected_coords]
            break
        base = kept or [row for row in pool
                        if row.coordinate not in rejected_coords and row.mandatory]
        if not base:
            base = [row for row in pool if row.coordinate not in rejected_coords][:4]
        selected_edges = [by_edge[edge_id]
                          for edge_id in action.get("edge_ids") or ()
                          if edge_id in by_edge]
        if action_kind == "relation_jump":
            visited_edges.update(_edge_key(hop) for hop in selected_edges)
        fresh, action_meta = _execute(
            index, question, action, by_id, by_edge, base, terms,
            exclude=visited | rejected_coords)
        fresh = [row for row in fresh if row.coordinate not in visited
                 and row.coordinate not in rejected_coords]
        trail.append({
            "step": step, "action": action_kind,
            "from": list(action.get("from_ids") or ()),
            "edge_ids": list(action.get("edge_ids") or ()),
            "keywords": list(action.get("keywords") or ())[:KEYWORDS_MAX],
            "query": _clean_text(action.get("query"), 300),
            "reason": _clean_text(action.get("reason"), 300),
            "added": len(fresh), "available_edges": edge_meta,
            "meta": action_meta,
        })
        best = _dedupe([*base, *fresh], cap=cap)
        if not fresh:
            final_reason = "jump_returned_no_new_coordinates"
            break
        pool = best

    selected = _dedupe(
        [row for row in best if row.coordinate not in rejected_coords], cap=cap)
    return selected, {
        "enabled": True, "ran": True, "sufficient": False,
        "steps": len(trail) or 1, "reason": final_reason,
        "missing": missing, "trail": trail, "rejected": rejected_audit,
        "selected": [{"doc_id": row.doc_id, "node": row.node,
                      "doc": row.doc, "path": row.path} for row in selected],
        "model": PRODUCT_MODEL, "exhausted": len(trail) >= max_steps,
    }
