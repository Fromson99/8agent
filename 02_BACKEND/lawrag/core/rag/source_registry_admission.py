"""Coordinate-first admission over a frozen proof-boundary action.

The controller is intentionally experiment-only.  It does not ask whether a
new article proves the whole answer.  It admits a candidate only when the
current corpus can resolve it to an article root and reproduce its source
text/hash.  The incumbent selection is immutable and fresh coordinates may
only fill unused presentation slots.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Iterable

from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag import proof_boundary_feedback as boundary
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


PRESENTED_MAX = 20
POOL_MAX = 48
ADMISSION_MAX = 3
REPLAYABLE_ACTIONS = {
    "relation_expand", "exact_search", "keyword_search",
    "assertion_search", "vector_search",
}


def _dedupe(rows: Iterable[termexplore.TermBranch], *, cap: int) \
        -> list[termexplore.TermBranch]:
    out: list[termexplore.TermBranch] = []
    seen: set[tuple] = set()
    for row in rows:
        if row.coordinate in seen:
            continue
        seen.add(row.coordinate)
        out.append(row)
        if len(out) >= max(0, int(cap)):
            break
    return out


def _source_record(index: Index, row: termexplore.TermBranch) \
        -> tuple[termexplore.TermBranch | None, dict]:
    """Resolve a candidate against the corpus and issue a source receipt."""
    view = index.docs.get(row.doc_id)
    if view is None or row.node not in view.by_id:
        return None, {
            "coordinate": [row.doc_id, row.node],
            "status": "missing_coordinate",
        }
    root = coordinates.article_root(view, row.node)
    canonical = coordinates.article_branch(
        index, row.doc_id, root, row.terms,
        origin=row.origin or "source-registry",
        reason=row.relation_reason or row.path)
    if canonical is None:
        return None, {
            "coordinate": [row.doc_id, row.node],
            "status": "unresolvable_article_root",
        }
    source = coordinates.subtree_text(view, canonical.node, cap=None)
    if not str(source or "").strip():
        return None, {
            "coordinate": [canonical.doc_id, canonical.node],
            "status": "empty_source",
        }
    canonical = replace(
        canonical,
        mandatory=bool(row.mandatory),
        mandatory_reason=row.mandatory_reason,
        source_doc_id=row.source_doc_id,
        source_node=row.source_node,
    )
    return canonical, {
        "coordinate": [canonical.doc_id, canonical.node],
        "status": "verified",
        "document": canonical.doc,
        "path": canonical.path,
        "origin": canonical.origin,
        "source_chars": len(source),
        "source_sha256": hashlib.sha256(
            source.encode("utf-8")).hexdigest(),
    }


def _pool_rows(rows: Iterable[termexplore.TermBranch]) -> list[dict]:
    return [{
        "doc_id": row.doc_id,
        "node": row.node,
        "doc": row.doc,
        "path": row.path,
        "origin": row.origin,
        "mandatory": bool(row.mandatory),
    } for row in rows]


def run(index: Index, question: str,
        incumbent: list[termexplore.TermBranch],
        evidence_pool: list[termexplore.TermBranch],
        planner_pool: list[termexplore.TermBranch],
        terms: tuple[str, ...], frozen_action: dict | None, *,
        cap: int = PRESENTED_MAX, pool_cap: int = POOL_MAX,
        admission_max: int = ADMISSION_MAX) \
        -> tuple[list[termexplore.TermBranch], dict]:
    """Replay one frozen action and apply coordinate/source-only admission."""
    selected = _dedupe(incumbent, cap=max(1, int(cap)))
    pool = _dedupe(
        [*selected, *evidence_pool], cap=max(len(selected), int(pool_cap)))
    initial_pool_coordinates = {row.coordinate for row in pool}
    action = dict(frozen_action or {})
    kind = str(action.get("kind") or "stop")
    base_meta = {
        "enabled": True,
        "strategy": "source-registry-admission",
        "baseline_preserved": True,
        "initial_selected_count": len(selected),
        "initial_observed_count": len(pool),
        "hard_deletes": 0,
        "rejected": [],
        "frozen_action": action,
        "actions": [],
        "registry_receipts": [],
        "admitted": [],
        "promoted": [],
    }
    if (kind not in REPLAYABLE_ACTIONS or action.get("skipped")):
        return selected, {
            **base_meta,
            "ran": False,
            "status": "unchanged",
            "reason": "no_replayable_parent_action",
            "raw_candidate_count": 0,
            "evidence_pool": _pool_rows(pool),
        }

    _cards, by_id = boundary._cards(
        index, planner_pool, question, terms)
    raw_rows, tool_meta = boundary._execute(
        index, question, action, by_id, terms, initial_pool_coordinates)
    receipts: list[dict] = []
    verified: list[termexplore.TermBranch] = []
    verified_coordinates: set[tuple] = set()
    for raw in raw_rows:
        row, receipt = _source_record(index, raw)
        receipts.append(receipt)
        if (row is None or row.coordinate in initial_pool_coordinates
                or row.coordinate in verified_coordinates):
            continue
        verified.append(row)
        verified_coordinates.add(row.coordinate)

    remaining_pool = max(0, int(pool_cap) - len(pool))
    admitted = verified[:min(max(0, int(admission_max)), remaining_pool)]
    pool = [*pool, *admitted]
    available = max(0, int(cap) - len(selected))
    promoted = admitted[:available]
    selected = [*selected, *promoted]
    replay_receipt = {
        "kind": kind,
        "fingerprint": action.get("fingerprint"),
        "query": action.get("query"),
        "keywords": list(action.get("keywords") or ()),
        "raw_count": len(raw_rows),
        "verified_count": len(verified),
        "admitted_count": len(admitted),
        "promoted_count": len(promoted),
        "tool_meta": tool_meta,
    }
    return selected, {
        **base_meta,
        "ran": True,
        "status": "complete",
        "reason": "coordinate_source_verified",
        "actions": [replay_receipt],
        "raw_candidate_count": len(raw_rows),
        "registry_receipts": receipts,
        "admitted": _pool_rows(admitted),
        "promoted": _pool_rows(promoted),
        "evidence_pool": _pool_rows(pool),
        "duplicate_actions": 0,
    }


__all__ = [
    "ADMISSION_MAX", "POOL_MAX", "PRESENTED_MAX", "run",
]
