"""Bounded, add-only recovery for delegated companions and governing-law gaps.

The functions in this module never mutate the corpus or the incumbent candidate
set.  Official delegation relations are consumed from ``RelationBundle`` and a
negative-answer feedback signal may open a second, issue-axis search.  Wiki card
provisions and body text are deliberately excluded from candidate generation.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import re
from typing import Iterable

from lawrag.core.rag import (
    general_search,
    legal_coordinates as coordinates,
    relation_navigation,
    wikictx,
)
from lawrag.core.rag.index import Index
from lawrag.core.rag.termexplore import TermBranch


_PARTICLES = (
    "으로부터", "에게서", "에서는", "으로", "에서", "에게", "까지", "부터",
    "처럼", "보다", "과", "와", "의", "을", "를", "이", "가", "은", "는",
    "에", "로",
)
_STOP = frozenset({
    "해당", "여부", "관한", "경우", "내용", "등의", "업무", "기준", "개별",
    "판단", "본연", "최종적", "단독적", "있는지", "한다", "된다", "필요",
})
_ROLE_TERMS = (
    "준법감시인", "위험관리책임자", "대표이사", "사외이사", "상근감사",
    "감사위원", "임원", "이사", "감사", "대주주", "주요주주",
    "금융투자업자", "금융회사", "상호저축은행",
)
_PREDICATE_PATTERNS = {
    "role_compatibility": (
        "겸직", "겸임", "수행할수", "할수있는지", "맡을수", "관할",
        "의사결정", "업무를수행", "업무수행",
    ),
}
_PREDICATE_EVIDENCE = {
    "role_compatibility": (
        "겸직", "겸임", "금지", "업무", "수행", "이해상충", "관할",
        "의사결정",
    ),
}
_PROVISION_RE = re.compile(r"「(?P<law>[^」]+)」\s*(?P<coord>.*)")
_ARTICLE_RE = re.compile(r"제\d+(?:-\d+)?조(?:의\d+)?")


def _pack(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _tokens(*values: object, cap: int = 12) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        for raw in re.findall(r"[가-힣A-Za-z0-9]{2,}", str(value or "")):
            word = raw
            for suffix in _PARTICLES:
                if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                    word = word[:-len(suffix)]
                    break
            if word in _STOP or len(word) < 2 or word in out:
                continue
            out.append(word)
            if len(out) >= cap:
                return tuple(out)
    return tuple(out)


def _merge_floor(
    floor: Iterable[tuple[str, int]],
    additions: Iterable[tuple[str, int]],
    *,
    cap: int = 20,
) -> list[tuple[str, int]]:
    """Preserve every incumbent coordinate and fill only remaining slots."""
    base = list(dict.fromkeys((str(doc), int(node)) for doc, node in floor))
    if len(base) > cap:
        raise ValueError("immutable floor exceeds final cap")
    seen = set(base)
    for doc_id, node in additions:
        coordinate = (str(doc_id), int(node))
        if coordinate in seen:
            continue
        if len(base) >= cap:
            break
        seen.add(coordinate)
        base.append(coordinate)
    return base


def bounded_delegation_hop(
    index: Index,
    seeds: Iterable[tuple[str, int]],
    query: str,
    *,
    exclude: Iterable[tuple[str, int]] = (),
    cap: int = 2,
) -> tuple[list[TermBranch], dict]:
    """Open one additional outgoing official-delegation hop.

    Only ``DELEGATES_TO`` edges exposed by the unified relation bundle are
    eligible.  A target must share at least one query/issue term, preventing a
    definition article with several delegated clauses from admitting every
    implementing decree article.
    """
    seed_rows = list(dict.fromkeys((str(doc), int(node)) for doc, node in seeds))
    blocked = set((str(doc), int(node)) for doc, node in exclude) | set(seed_rows)
    terms = _tokens(query, cap=16)
    hops, navigation = relation_navigation.neighbors(
        index,
        seed_rows,
        direction="out",
        cap=max(8, cap * 4),
        exclude=blocked,
        kinds={"DELEGATES_TO"},
    )
    ranked: list[tuple[tuple, TermBranch, dict]] = []
    rejected = []
    for hop in hops:
        if hop.graph_kind != "DELEGATES_TO" or not hop.mandatory:
            rejected.append({**hop.as_dict(index), "reason": "not_official_delegation"})
            continue
        branch = coordinates.article_branch(
            index,
            hop.target_doc_id,
            hop.target_node,
            terms,
            origin="bounded-delegation-second-hop",
            reason=f"{hop.provenance}:{hop.surface or hop.graph_kind}",
        )
        if branch is None:
            rejected.append({**hop.as_dict(index), "reason": "unresolved_target"})
            continue
        matched = tuple(branch.terms)
        title = index.docs[branch.doc_id].path(branch.node) or branch.path
        title_hits = tuple(term for term in terms if _pack(term) in _pack(title))
        if not matched and not title_hits:
            rejected.append({**hop.as_dict(index), "reason": "query_axis_mismatch"})
            continue
        branch = replace(
            branch,
            mandatory=True,
            mandatory_reason="relation:위임:bounded-second-hop",
            source_doc_id=hop.source_doc_id,
            source_node=hop.source_node,
        )
        score = (-len(title_hits), -len(matched), branch.doc, branch.path)
        ranked.append((score, branch, {
            **hop.as_dict(index),
            "matched_terms": list(matched),
            "title_hits": list(title_hits),
        }))
    ranked.sort(key=lambda row: row[0])
    selected = ranked[:max(0, int(cap))]
    return [row[1] for row in selected], {
        "policy": "official-DELEGATES_TO + query-axis-match + bounded-one-hop",
        "seed_coordinates": [list(row) for row in seed_rows],
        "query_terms": list(terms),
        "navigation": navigation,
        "candidates": [row[2] for row in ranked],
        "selected": [row[2] for row in selected],
        "rejected": rejected,
        "cap": max(0, int(cap)),
    }


def _issue_axis_spots(question: str) -> list[dict]:
    """Return the only Wiki fields permitted to influence retrieval."""
    safe = []
    for spot in wikictx.spot(question):
        safe.append({
            "slug": str(spot.get("slug") or ""),
            "title": str(spot.get("title") or ""),
            "axis": str(spot.get("axis") or ""),
            "matched_triggers": [str(value) for value in spot.get("why") or ()],
        })
    return safe


def _predicate_families(question: str) -> tuple[str, ...]:
    packed = _pack(question)
    return tuple(
        family for family, patterns in _PREDICATE_PATTERNS.items()
        if any(pattern in packed for pattern in patterns)
    )


def _role_hits(question: str, matched_triggers: Iterable[str]) -> tuple[str, ...]:
    packed = _pack(question)
    triggers = {_pack(value): str(value) for value in matched_triggers}
    out = []
    for role in _ROLE_TERMS:
        if _pack(role) not in packed:
            continue
        # A role must have actually participated in card routing, either as an
        # exact trigger or as the more specific form of a matched role trigger.
        if any(key == _pack(role) or key in _pack(role) or _pack(role) in key
               for key in triggers):
            out.append(role)
    return tuple(out)


def _resolve_provision(
    index: Index,
    provision: str,
    preferred_document_ids: Iterable[str] = (),
) -> tuple[TermBranch | None, dict]:
    match = _PROVISION_RE.match(str(provision or "").strip())
    if not match:
        return None, {"provision": provision, "reason": "invalid_provision_syntax"}
    article = _ARTICLE_RE.search(match.group("coord"))
    if article is None:
        return None, {"provision": provision, "reason": "article_label_missing"}
    law_name = match.group("law").strip()
    want_buchik = "부칙" in match.group("coord")
    preferred = list(dict.fromkeys(str(value) for value in preferred_document_ids))
    preferred_rank = {doc_id: rank for rank, doc_id in enumerate(preferred)}
    documents = [
        (doc_id, view) for doc_id, view in index.docs.items()
        if view.name == law_name and (
            doc_id in preferred_rank or doc_id in index.entry_docs)
    ]
    documents.sort(key=lambda row: (
        0 if row[0] in preferred_rank else 1,
        preferred_rank.get(row[0], len(preferred_rank)), row[0]))
    if not documents:
        return None, {
            "provision": provision, "law": law_name,
            "article": article.group(0), "reason": "law_not_in_entry_scope",
        }
    candidates = []
    for doc_id, view in documents:
        for node_id in view.by_id:
            root = coordinates.article_root(view, node_id)
            if root != node_id:
                continue
            item = view.by_id[root]
            surface = str(item.get("surface") or "").strip()
            if surface != article.group(0):
                continue
            path = view.path(root) or ""
            if ("부칙" in path) != want_buchik:
                continue
            candidates.append((doc_id, view, root))
    if not candidates:
        return None, {
            "provision": provision, "law": law_name,
            "article": article.group(0), "reason": "article_not_resolved",
        }
    doc_id, view, root = candidates[0]
    branch = coordinates.article_branch(
        index, doc_id, root, (), origin="role-predicate-governing-hypothesis",
        reason=f"wiki-provision-hypothesis:{provision}")
    if branch is None:
        return None, {
            "provision": provision, "law": law_name,
            "article": article.group(0), "reason": "article_branch_failed",
        }
    return branch, {
        "provision": provision, "law": law_name,
        "article": article.group(0), "doc_id": branch.doc_id,
        "node": branch.node, "path": branch.path, "reason": "resolved",
    }


def _validate_role_predicate_source(
    index: Index,
    branch: TermBranch,
    roles: tuple[str, ...],
    families: tuple[str, ...],
) -> dict:
    view = index.docs[branch.doc_id]
    source = " ".join((
        view.path(branch.node) or branch.path,
        coordinates.subtree_text(view, branch.node, cap=12000),
    ))
    packed = _pack(source)
    actor_hits = [role for role in roles if _pack(role) in packed]
    predicate_hits = {
        family: [term for term in _PREDICATE_EVIDENCE.get(family, ())
                 if _pack(term) in packed]
        for family in families
    }
    predicate_hits = {key: value for key, value in predicate_hits.items() if value}
    return {
        "accepted": bool(actor_hits and predicate_hits),
        "actor_hits": actor_hits,
        "predicate_hits": predicate_hits,
        "source_chars_checked": len(source),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }


def role_predicate_governing_feedback(
    index: Index,
    question: str,
    *,
    answer_incorrect: bool,
    exclude: Iterable[tuple[str, int]] = (),
    preferred_document_ids: Iterable[str] = (),
    card_limit: int = 2,
    addition_cap: int = 4,
) -> tuple[list[TermBranch], dict]:
    """Resolve a bare-negative feedback signal through a governing-law gate.

    Unlike :func:`governing_axis_feedback`, this path does no general lexical
    search.  Existing issue-card provisions are hypotheses only: a role trigger
    and a compatible legal predicate must both occur in the question, and the
    resolved source article must independently contain role and predicate
    evidence before it can enter the add-only bundle.  Card body text is not
    consumed by this function.
    """
    blocked = {(str(doc), int(node)) for doc, node in exclude}
    if not answer_incorrect:
        return [], {
            "ran": False, "reason": "negative_feedback_absent",
            "input_fields_used": [], "forbidden_fields_used": [],
        }
    spots = wikictx.spot(question, limit=card_limit)
    families = _predicate_families(question)
    accepted: list[TermBranch] = []
    cards = []
    seen = set()
    for spot in spots:
        roles = _role_hits(question, spot.get("why") or ())
        card = {
            "slug": str(spot.get("slug") or ""),
            "title": str(spot.get("title") or ""),
            "matched_triggers": [str(value) for value in spot.get("why") or ()],
            "axis": str(spot.get("axis") or ""),
            "provisions": [str(value) for value in spot.get("provisions") or ()],
            "actor_roles": list(roles),
            "predicate_families": list(families),
            "gate_open": bool(roles and families),
            "hypotheses": [],
        }
        if card["gate_open"]:
            for provision in card["provisions"]:
                branch, resolution = _resolve_provision(
                    index, provision, preferred_document_ids)
                hypothesis = {"resolution": resolution, "validation": None}
                if branch is not None:
                    validation = _validate_role_predicate_source(
                        index, branch, roles, families)
                    hypothesis["validation"] = validation
                    if (validation["accepted"] and branch.coordinate not in blocked
                            and branch.coordinate not in seen):
                        seen.add(branch.coordinate)
                        accepted.append(branch)
                card["hypotheses"].append(hypothesis)
        cards.append(card)
    selected = accepted[:max(0, int(addition_cap))]
    return selected, {
        "ran": True,
        "reason": (
            "validated_role_predicate_bundle" if selected
            else "no_validated_governing_hypothesis"),
        "input_fields_used": [
            "question", "answer_incorrect", "spot.slug", "spot.title",
            "spot.why", "spot.axis", "spot.provisions",
            "preferred_document_ids", "resolved_article.path",
            "resolved_article.source_text",
        ],
        "forbidden_fields_used": [],
        "general_lexical_search_calls": 0,
        "predicate_families": list(families),
        "cards": cards,
        "selected": [
            {"doc_id": row.doc_id, "node": row.node, "doc": row.doc,
             "path": row.path, "origin": row.origin}
            for row in selected
        ],
        "caps": {"cards": card_limit, "additions": addition_cap},
    }


def governing_axis_feedback(
    index: Index,
    question: str,
    *,
    answer_incorrect: bool,
    exclude: Iterable[tuple[str, int]] = (),
    direct_cap: int = 3,
    companion_cap: int = 2,
) -> tuple[list[TermBranch], dict]:
    """Add governing-law candidates after a bare negative-answer signal.

    The feedback signal contains no location.  Issue cards contribute only
    their title, judgment axis, and triggers already present in the question.
    ``provisions`` and card body text are never read here.  Direct lexical
    landings are followed by one bounded official-delegation hop.
    """
    blocked = set((str(doc), int(node)) for doc, node in exclude)
    if not answer_incorrect:
        return [], {
            "ran": False,
            "reason": "negative_feedback_absent",
            "input_fields_used": [],
        }
    spots = _issue_axis_spots(question)
    if not spots:
        return [], {
            "ran": True,
            "reason": "no_issue_axis_match",
            "input_fields_used": ["question", "answer_incorrect"],
            "spots": [],
        }
    terms = _tokens(
        question,
        *(value for spot in spots for value in (
            spot["title"], spot["axis"], *spot["matched_triggers"])),
        cap=16,
    )
    grouped: dict[tuple[str, int], dict] = {}
    searches = []
    for term in terms:
        result = general_search.search_keywords(
            index,
            [term],
            question=question,
            limit=32,
            per_document=4,
            extractor="governing-axis-negative-feedback",
        )
        searches.append({"term": term, "hits": len(result.hits),
                         "unmatched": list(result.unmatched)})
        for hit in result.hits:
            view = index.docs.get(hit.doc_id)
            if view is None or hit.node not in view.by_id:
                continue
            root = coordinates.article_root(view, hit.node)
            coordinate = (hit.doc_id, int(root))
            if coordinate in blocked:
                continue
            row = grouped.setdefault(coordinate, {
                "matched": set(), "max_score": 0.0, "sum_score": 0.0,
            })
            row["matched"].update(str(value) for value in hit.matched)
            row["max_score"] = max(row["max_score"], float(hit.score))
            row["sum_score"] += float(hit.score)

    ranked = []
    for coordinate, score in grouped.items():
        branch = coordinates.article_branch(
            index,
            coordinate[0],
            coordinate[1],
            terms,
            origin="governing-axis-negative-feedback",
            reason="issue title/axis/matched-trigger lexical landing",
        )
        if branch is None:
            continue
        matched = tuple(sorted(score["matched"]))
        title = index.docs[branch.doc_id].path(branch.node) or branch.path
        title_hits = tuple(term for term in terms if _pack(term) in _pack(title))
        ranked.append((
            (-len(title_hits), -len(matched), -score["max_score"],
             -score["sum_score"], branch.doc, branch.path),
            branch,
            {"doc_id": branch.doc_id, "node": branch.node,
             "doc": branch.doc, "path": branch.path,
             "matched_terms": list(matched), "title_hits": list(title_hits),
             "max_score": score["max_score"]},
        ))
    ranked.sort(key=lambda row: row[0])
    direct_rows = ranked[:max(0, int(direct_cap))]
    direct = [row[1] for row in direct_rows]
    direct_coordinates = [row.coordinate for row in direct]
    issue_query = " ".join(terms)
    companions, companion_meta = bounded_delegation_hop(
        index,
        direct_coordinates,
        issue_query,
        exclude=blocked | set(direct_coordinates),
        cap=companion_cap,
    )
    combined = []
    seen = set()
    for row in (*direct, *companions):
        if row.coordinate not in seen:
            seen.add(row.coordinate)
            combined.append(row)
    return combined, {
        "ran": True,
        "reason": "bare-negative-governing-axis-search",
        "input_fields_used": [
            "question", "answer_incorrect", "spot.title", "spot.axis",
            "spot.matched_triggers",
        ],
        "forbidden_fields_used": [],
        "spots": spots,
        "query_terms": list(terms),
        "searches": searches,
        "direct_candidates": [row[2] for row in ranked],
        "direct_selected": [row[2] for row in direct_rows],
        "companion": companion_meta,
        "selected": [
            {"doc_id": row.doc_id, "node": row.node, "doc": row.doc,
             "path": row.path, "origin": row.origin}
            for row in combined
        ],
        "caps": {"direct": direct_cap, "companion": companion_cap},
    }


def add_only_coordinates(
    floor: Iterable[tuple[str, int]],
    additions: Iterable[TermBranch | tuple[str, int]],
    *,
    cap: int = 20,
) -> list[tuple[str, int]]:
    values = [
        row.coordinate if isinstance(row, TermBranch) else row
        for row in additions
    ]
    return _merge_floor(floor, values, cap=cap)
