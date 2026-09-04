"""Proof-guided, append-only exploration over a frozen LegalClosure result.

The existing LegalClosure output is an immutable incumbent.  This module keeps
an evidence pool that may grow, but never gives an LLM authority to delete a
coordinate or invent an endpoint.  Search-span signatures are used only to
avoid repeating an already explored direction; a source-grounded witness is a
separate object and is the only positive completion signal.

ADR-0066 keeps this module off the main product path.  It is intentionally a
closed-menu controller around the existing exact, Assertion, BM25, vector,
relation, and structural primitives.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import re
from typing import Iterable

from lawrag.core.domain_graph import requirements as requirement_spans
from lawrag.core.rag import (
    general_search,
    grounded_witness,
    relation_navigation,
    termexplore,
)
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag.index import Index
from lawrag.core.rag.search_trace import SearchTrace


PRODUCT_MODEL = "claude-haiku-4-5-20251001"
POOL_MAX = 64
PRESENTED_MAX = 20
MAX_STEPS = 3
ACTIONS_PER_STEP = 2
HYPOTHESES_MAX = 4
OBLIGATIONS_MAX = 8
WITNESS_EVIDENCE_MAX = 12
OUTPUT_TOKENS_MAX = 8_000
SEARCH_RESULTS_MAX = 16
CARDS_MAX = 48
PREVIEW_CHARS = 360
INSPECTION_TOTAL_CHARS = 12_000
KEYWORDS_MAX = 4

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_ACTION_KINDS = (
    "inspect_seen",
    "relation_expand",
    "structure_expand",
    "exact_search",
    "assertion_search",
    "keyword_search",
    "vector_search",
    "hybrid_search",
    "stop",
)

_SYSTEM = """너는 법률 증거공간을 완성하는 탐색 조정자다.

기존 검색기는 빠른 shortcut이고, 지금 보이는 후보는 selected와 deferred를 포함한 append-only
원장이다. 후보를 keep/reject하지 않는다. 이미 본 증거는 절대 삭제할 수 없고, 존재하지 않는
법령·조문 좌표나 관계 endpoint를 만들 수 없다.

먼저 질문에 답하기 위한 법적 가설과 필수 obligation(주체, 행위·업무유형, 지배규정, 요건,
예외, 효과, 본법-하위법령 companion, 시점)을 적는다. 좌표는 발견했지만 관련 항·호를 충분히
읽지 못했다면 inspect_seen을 고른다. 증거 자체가 없을 때만 expand_unseen lane에서 현재
query/operator trace와 다른 방향을 고른다. relation_expand는 제공된 E id만 열 수 있다.
exact/assertion/keyword/vector 검색에는 법률명을 정답처럼 확정하지 말고 corpus를 찾을
operation·표현만 제안한다.

출력은 가설 최대 4개, obligation 최대 8개, witness evidence 최대 12개로 제한한다.
evidence quote는 필요한 한 문장 또는 연속 구절만 정확히 복사하고 각각 300자를 넘기지 않는다.
actions 배열은 절대로 2개를 넘기지 않고, 각 action의 keywords는 최대 4개만 쓴다.

action마다 반드시 하나의 열린 obligation을 target_obligation에 적는다. 같은 의미의 검색어를
말만 바꾸어 반복하지 않는다. 최대 두 action은 서로 다른 잔여 방향을 collectively span해야
한다. 넓지만 열린 obligation과 무관한 검색은 하지 않는다.

witness.status=complete는 exact evidence quote가 질문의 결론과 필수 요건을 실제로 뒷받침하고,
필요한 companion·예외·시점 확인까지 닫혔을 때만 쓴다. quote는 카드 원문을 그대로 복사하고
입력된 candidate id와 proof edge id만 사용한다. companion quote에는 source_candidate_id와
edge_id를 함께 적는다. 좌표가 있다는 것과 답이 증명됐다는 것을 구분한다.
아직 부족하면 partial로 두고 missing_obligation_ids를 남긴다."""


@dataclass
class EvidenceState:
    row: termexplore.TermBranch
    origins: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    observation_level: int = 1
    inspected_facets: set[str] = field(default_factory=set)

    def observe(self, row: termexplore.TermBranch, *, status: str,
                level: int = 1) -> None:
        if row.origin and row.origin not in self.origins:
            self.origins.append(row.origin)
        if status and status not in self.statuses:
            self.statuses.append(status)
        self.observation_level = max(self.observation_level, level)


@dataclass(frozen=True)
class SpanDelta:
    coordinate_novelty: float = 0.0
    query_novelty: float = 0.0
    operator_novelty: float = 0.0
    semantic_novelty: float = 0.0
    observation_novelty: float = 0.0
    target_alignment: float = 0.0
    closure_gain: int = 0

    def as_dict(self) -> dict:
        return {
            "coordinate_novelty": round(self.coordinate_novelty, 6),
            "query_novelty": round(self.query_novelty, 6),
            "operator_novelty": round(self.operator_novelty, 6),
            "semantic_novelty": round(self.semantic_novelty, 6),
            "observation_novelty": round(self.observation_novelty, 6),
            "target_alignment": round(self.target_alignment, 6),
            "closure_gain": self.closure_gain,
        }


def _clean(value: object, cap: int = 300) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:cap]


def _atoms(value: object) -> tuple[str, ...]:
    text = _clean(value, 1000).casefold()
    values = [token for token in _TOKEN.findall(text) if len(token) >= 2]
    packed = re.sub(r"[^0-9a-z가-힣]", "", text)
    if len(packed) >= 4:
        values.append(packed[:120])
    return tuple(dict.fromkeys(values))


def stable_fingerprint(payload: dict) -> str:
    """Return a stable fingerprint for an operator or graph edge."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def edge_fingerprint(hop: relation_navigation.RelationHop) -> str:
    return stable_fingerprint({
        "source": [hop.source_doc_id, hop.source_node],
        "target": [hop.target_doc_id, hop.target_node],
        "kind": hop.graph_kind,
        "direction": hop.direction,
        "provenance": hop.provenance,
    })


def _action_query_atoms(action: dict) -> tuple[str, ...]:
    values: list[str] = []
    for value in action.get("keywords") or ():
        values.extend(_atoms(value))
    values.extend(_atoms(action.get("query")))
    return tuple(dict.fromkeys(values))


def action_fingerprint(action: dict, *, edge_stable_ids: Iterable[str] = ()) -> str:
    """Fingerprint an application, excluding prose reason and claimed target.

    Excluding ``target_obligation`` prevents the model from repeating the same
    query/path merely by renaming its purpose.
    """
    return stable_fingerprint({
        "kind": str(action.get("kind") or "stop"),
        "query_atoms": sorted(_action_query_atoms(action)),
        "from_ids": sorted(str(value) for value in action.get("from_ids") or ()),
        "edges": sorted(str(value) for value in edge_stable_ids),
    })


def _dedupe(rows: Iterable[termexplore.TermBranch], *, cap: int) \
        -> list[termexplore.TermBranch]:
    if int(cap) <= 0:
        return []
    out, seen = [], set()
    for row in rows:
        if row.coordinate in seen:
            continue
        seen.add(row.coordinate)
        out.append(row)
        if len(out) >= int(cap):
            break
    return out


def _row_from_meta(index: Index, raw: dict, terms: tuple[str, ...], *,
                   default_origin: str) -> termexplore.TermBranch | None:
    if not isinstance(raw, dict):
        return None
    doc_id, node = str(raw.get("doc_id") or ""), raw.get("node")
    origin = str(raw.get("origin") or default_origin)
    row = coordinates.article_branch(
        index, doc_id, node, terms, origin=origin,
        reason=str(raw.get("relation_reason") or raw.get("path") or ""))
    if row is None:
        return None
    return replace(
        row,
        mandatory=bool(raw.get("mandatory", row.mandatory)),
        mandatory_reason=str(raw.get("mandatory_reason")
                             or row.mandatory_reason or ""),
    )


def observed_from_meta(index: Index,
                       initial: list[termexplore.TermBranch],
                       terms: tuple[str, ...], initial_meta: dict, *,
                       cap: int = POOL_MAX) -> list[termexplore.TermBranch]:
    """Reconstruct the pre-top20 candidate ledger available in current meta.

    This is deliberately explicit rather than recursively consuming arbitrary
    coordinates from audit metadata.  Only actual retrieval candidate funnels
    are promoted into the observed ledger.
    """
    groups: list[tuple[Iterable[dict], str]] = []
    primary = initial_meta.get("primary") or {}
    assertion = initial_meta.get("assertion") or {}
    keyword = initial_meta.get("keyword") or {}
    groups.extend([
        (primary.get("review_candidates") or (), "initial-primary-review"),
        (primary.get("selected") or (), "initial-primary-selected"),
        (assertion.get("selected") or (), "initial-assertion"),
        (keyword.get("article_candidates") or (), "initial-keyword"),
        (initial_meta.get("closure") or (), "initial-closure"),
        (initial_meta.get("selected") or (), "initial-selected-meta"),
    ])
    out = list(initial)
    seen = {row.coordinate for row in out}
    for items, origin in groups:
        for raw in items:
            row = _row_from_meta(index, raw, terms, default_origin=origin)
            if row is None or row.coordinate in seen:
                continue
            seen.add(row.coordinate)
            out.append(row)
            if len(out) >= cap:
                return out
    return out


def _initial_query_atoms(meta: dict, terms: tuple[str, ...]) -> set[str]:
    values: list[object] = [*terms]
    primary = meta.get("primary") or {}
    plan = primary.get("term_plan") or {}
    for key in ("used_terms", "used_anchor_terms", "operation_terms",
                "grounded_operation_terms", "condition_terms"):
        values.extend(plan.get(key) or ())
    keyword = meta.get("keyword") or {}
    values.extend(keyword.get("keywords") or ())
    out: set[str] = set()
    for value in values:
        out.update(_atoms(value))
    return out


def _requirement_cards(row: termexplore.TermBranch) -> list[dict]:
    out, seen = [], set()
    for span in requirement_spans.extract(row.body):
        key = (span.kind, span.surface, span.trigger)
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": span.kind, "surface": _clean(span.surface, 160),
                    "trigger": _clean(span.trigger, 80)})
        if len(out) >= 6:
            break
    return out


def _feature_atoms(index: Index, row: termexplore.TermBranch) -> set[str]:
    view = index.docs.get(row.doc_id)
    features = {f"term:{value}" for term in row.terms for value in _atoms(term)}
    features.update(f"requirement:{item['kind']}"
                    for item in _requirement_cards(row))
    origin = row.origin.split(":", 1)[0]
    features.add(f"origin:{origin}")
    if row.mandatory:
        features.add("closure:mandatory")
    if view is not None:
        features.add(f"authority:{getattr(view, 'source_kind', '')}")
        features.add(f"scope:{getattr(view, 'scope_kind', '')}")
        # Document identity is not a coordinate basis; family is useful only as
        # a low-cardinality authority/companion axis.
        family = re.sub(r"(시행령|시행규칙|규정)$", "", view.name).strip()
        if family:
            features.add(f"family:{family[:80]}")
    relation = row.mandatory_reason or row.relation_reason
    if relation:
        features.update(f"relation:{atom}" for atom in _atoms(relation))
    return {value for value in features if not value.endswith(":")}


def _focused_text(body: str, phrases: Iterable[str], *, cap: int) -> str:
    text = str(body or "")
    if len(text) <= cap:
        return text
    windows: list[tuple[int, int]] = []
    for phrase in phrases:
        clean = _clean(phrase, 120)
        if len(clean) < 2:
            continue
        start = text.find(clean)
        if start >= 0:
            windows.append((max(0, start - 350), min(len(text), start + 850)))
    if not windows:
        half = max(1, cap // 2)
        return text[:half] + "\n…\n" + text[-half:]
    out = []
    for lo, hi in windows:
        chunk = text[lo:hi].strip()
        if chunk and chunk not in out:
            out.append(chunk)
        if sum(len(value) for value in out) >= cap:
            break
    return "\n…\n".join(out)[:cap]


def _edge_menu(index: Index, states: list[EvidenceState], *,
               consumed: set[str], cap: int = 36) \
        -> tuple[list[dict], dict[str, tuple[relation_navigation.RelationHop, str]], dict]:
    pool_coordinates = {state.row.coordinate for state in states}
    hops, meta = relation_navigation.neighbors(
        index, [state.row.coordinate for state in states[:CARDS_MAX]],
        direction="both", cap=cap * 2, exclude=pool_coordinates)
    public, by_id = [], {}
    for hop in hops:
        stable = edge_fingerprint(hop)
        if stable in consumed:
            continue
        edge_id = f"E{stable[:10]}"
        if edge_id in by_id:
            continue
        by_id[edge_id] = (hop, stable)
        target = hop.as_dict(index)
        public.append({
            "id": edge_id,
            "source": [hop.source_doc_id, hop.source_node],
            "kind": hop.graph_kind,
            "relation": hop.relation,
            "direction": hop.direction,
            "target": " ▸ ".join(filter(None, (
                target.get("target_doc"), target.get("target_path")))),
            "mandatory": hop.mandatory,
            "provenance": hop.provenance,
        })
        if len(public) >= cap:
            break
    return public, by_id, {**meta, "unopened": len(public)}


def _schema(candidate_ids: list[str], edge_ids: list[str],
            proof_edge_ids: list[str] | None = None) -> dict:
    # Large per-case ID enums can exceed the provider's schema compiler
    # complexity limit. IDs remain a closed menu at runtime: witness and
    # action parsers below accept only keys present in by_id/by_edge/proof_edges.
    candidate = {"type": "string"}
    edge = {"type": "string"}
    proof_edge = {"type": "string"}
    action_kinds = list(_ACTION_KINDS)
    if not edge_ids:
        action_kinds.remove("relation_expand")
    return {
        "type": "object",
        "properties": {
            "hypotheses": {"type": "array", "items": {
                "type": "object", "properties": {
                    "id": {"type": "string"},
                    "legal_operation": {"type": "string"},
                    "possible_conclusion": {"type": "string"},
                }, "required": ["id", "legal_operation", "possible_conclusion"],
                "additionalProperties": False}},
            "open_obligations": {"type": "array", "items": {
                "type": "object", "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string"},
                    "description": {"type": "string"},
                    "required": {"type": "boolean"},
                }, "required": ["id", "kind", "description", "required"],
                "additionalProperties": False}},
            "witness": {"type": "object", "properties": {
                "status": {"type": "string", "enum": ["partial", "complete"]},
                "conclusion": {"type": "string"},
                "evidence": {"type": "array", "items": {
                    "type": "object", "properties": {
                        "candidate_id": candidate,
                        "quote": {"type": "string"},
                        "facet_ids": {"type": "array", "items": {"type": "string"}},
                        "source_candidate_id": candidate,
                        "edge_id": proof_edge,
                    }, "required": ["candidate_id", "quote", "facet_ids"],
                    "additionalProperties": False}},
                "edge_ids": {"type": "array", "items": edge},
                "covered_obligation_ids": {"type": "array", "items": {"type": "string"}},
                "missing_obligation_ids": {"type": "array", "items": {"type": "string"}},
            }, "required": ["status", "conclusion", "evidence", "edge_ids",
                              "covered_obligation_ids", "missing_obligation_ids"],
                "additionalProperties": False},
            "actions": {"type": "array",
                        "items": {"type": "object", "properties": {
                "lane": {"type": "string", "enum": ["revisit_seen", "expand_unseen", "stop"]},
                "kind": {"type": "string", "enum": action_kinds},
                "target_obligation": {"type": "string"},
                "from_ids": {"type": "array", "items": candidate},
                "edge_ids": {"type": "array", "items": edge},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "query": {"type": "string"},
                "reason": {"type": "string"},
            }, "required": ["lane", "kind", "target_obligation", "from_ids",
                              "edge_ids", "keywords", "query", "reason"],
                "additionalProperties": False}},
        },
        "required": ["hypotheses", "open_obligations", "witness", "actions"],
        "additionalProperties": False,
    }


def _candidate_projection(index: Index, states: list[EvidenceState], *,
                          selected: set[tuple], question: str,
                          inspected_budget: int = INSPECTION_TOTAL_CHARS) \
        -> tuple[list[dict], dict[str, EvidenceState], list[dict]]:
    public, by_id, inspected = [], {}, []
    question_atoms = _atoms(question)
    remaining = inspected_budget
    for pos, state in enumerate(states[:CARDS_MAX], start=1):
        cid = f"C{pos}"
        by_id[cid] = state
        row = state.row
        public.append({
            "id": cid, "document": row.doc, "path": row.path,
            "coordinate_status": "selected" if row.coordinate in selected else "deferred",
            "origins": list(state.origins),
            "matched_terms": list(row.terms),
            "mandatory": row.mandatory,
            "observation_level": state.observation_level,
            "requirements": _requirement_cards(row),
            "preview": _focused_text(row.body, (*row.terms, *question_atoms),
                                     cap=PREVIEW_CHARS),
        })
        if state.observation_level < 3 or remaining <= 0:
            continue
        phrases = [*state.inspected_facets, *row.terms, *question_atoms]
        body = _focused_text(row.body, phrases, cap=min(5000, remaining))
        remaining -= len(body)
        inspected.append({
            "candidate_id": cid, "document": row.doc, "path": row.path,
            "target_facets": sorted(state.inspected_facets),
            "exact_article_text": body,
        })
    return public, by_id, inspected


def _validate_witness(index: Index, raw: object,
                      by_id: dict[str, EvidenceState],
                      proof_edges: dict[str, grounded_witness.ClosedEdge],
                      obligations: Iterable[dict]) -> dict:
    witness = raw if isinstance(raw, dict) else {}
    errors, evidence_ids, proposal_rows = [], [], []
    required = []
    for value in [*(witness.get("covered_obligation_ids") or ()),
                  *(witness.get("missing_obligation_ids") or ())]:
        clean = str(value or "").strip()
        if clean and clean not in required:
            required.append(clean)
    if not required:
        for obligation in obligations:
            if not obligation.get("required", True):
                continue
            clean = str(obligation.get("id") or "").strip()
            if clean and clean not in required:
                required.append(clean)
    companion_facets = set()
    for item in (witness.get("evidence") or ())[:WITNESS_EVIDENCE_MAX]:
        cid = str(item.get("candidate_id") or "")
        state = by_id.get(cid)
        quote = _clean(item.get("quote"), 1800)
        if state is None:
            errors.append(f"unknown_candidate:{cid}")
            continue
        if not quote or quote not in state.row.body:
            errors.append(f"quote_not_in_source:{cid}")
            continue
        if cid not in evidence_ids:
            evidence_ids.append(cid)
        full_source = coordinates.subtree_text(
            index.docs[state.row.doc_id], state.row.node, cap=None)
        start = full_source.find(quote)
        if start < 0:
            errors.append(f"quote_not_in_full_source:{cid}")
            continue
        facets = [str(value).strip() for value in item.get("facet_ids") or ()
                  if str(value).strip()]
        if not facets:
            errors.append(f"evidence_without_facet:{cid}")
            continue
        for facet in facets:
            row = {
                "facet": facet, "candidate_id": cid, "quote": quote,
                "source_span": {"start": start, "end": start + len(quote)},
            }
            source_id = str(item.get("source_candidate_id") or "")
            edge_id = str(item.get("edge_id") or "")
            if source_id or edge_id:
                row.update(source_candidate_id=source_id, edge_id=edge_id)
                companion_facets.add(facet)
            proposal_rows.append(row)
    deterministic = grounded_witness.validate_witness(
        index, {cid: state.row for cid, state in by_id.items()}, required,
        {"witnesses": proposal_rows}, closed_edges=proof_edges,
        companion_facets=companion_facets)
    for value in witness.get("edge_ids") or ():
        if str(value) not in proof_edges:
            errors.append(f"unknown_proof_edge:{value}")
    errors.extend(
        f"grounded:{row.get('code', 'invalid')}"
        for row in deterministic.get("errors") or ())
    requested_complete = witness.get("status") == "complete"
    if requested_complete and not evidence_ids:
        errors.append("complete_without_grounded_evidence")
    if requested_complete and witness.get("missing_obligation_ids"):
        errors.append("complete_with_missing_obligations")
    if requested_complete and not _clean(witness.get("conclusion"), 500):
        errors.append("complete_without_conclusion")
    if requested_complete and deterministic.get("status") != "complete":
        errors.append("complete_without_closed_grounded_witness")
    return {
        "requested_status": "complete" if requested_complete else "partial",
        "valid": not errors,
        "complete": requested_complete and not errors,
        "evidence_ids": evidence_ids,
        "edge_ids": [str(value) for value in witness.get("edge_ids") or ()
                     if str(value) in proof_edges],
        "covered_obligation_ids": list(witness.get("covered_obligation_ids") or ()),
        "missing_obligation_ids": list(witness.get("missing_obligation_ids") or ()),
        "conclusion": _clean(witness.get("conclusion"), 600),
        "errors": errors,
        "deterministic": deterministic,
    }


def _branch_for_hop(index: Index, hop: relation_navigation.RelationHop,
                    terms: tuple[str, ...]) -> termexplore.TermBranch | None:
    row = coordinates.article_branch(
        index, hop.target_doc_id, hop.target_node, terms,
        origin=f"span-relation:{hop.graph_kind or hop.relation}",
        reason=f"{hop.provenance}:{hop.direction}:{hop.surface}")
    if row is None:
        return None
    return replace(
        row, mandatory=hop.mandatory,
        mandatory_reason=(f"relation:{hop.graph_kind or hop.relation}"
                          if hop.mandatory else ""),
        source_doc_id=hop.source_doc_id, source_node=hop.source_node)


def _execute_action(index: Index, question: str, action: dict,
                    by_id: dict[str, EvidenceState],
                    by_edge: dict[str, tuple[relation_navigation.RelationHop, str]],
                    terms: tuple[str, ...], *, exclude: set[tuple]) \
        -> tuple[list[termexplore.TermBranch], dict]:
    kind = str(action.get("kind") or "stop")
    sources = [by_id[cid].row for cid in action.get("from_ids") or ()
               if cid in by_id]
    clean_keywords = []
    for value in action.get("keywords") or ():
        clean = _clean(value, 100)
        if len(re.sub(r"\s+", "", clean)) >= 2 and clean not in clean_keywords:
            clean_keywords.append(clean)
        if len(clean_keywords) >= KEYWORDS_MAX:
            break
    query = _clean(action.get("query"), 400)
    merged_terms = tuple(dict.fromkeys((*terms, *clean_keywords)))

    if kind == "relation_expand":
        hops = [by_edge[eid][0] for eid in action.get("edge_ids") or ()
                if eid in by_edge]
        rows = [_branch_for_hop(index, hop, merged_terms) for hop in hops]
        return _dedupe((row for row in rows
                        if row is not None and row.coordinate not in exclude),
                       cap=SEARCH_RESULTS_MAX), {
            "tool": kind, "hops": [hop.as_dict(index) for hop in hops]}

    if kind == "structure_expand":
        expanded, meta = termexplore.expand_structural(
            index, sources, merged_terms, cap=SEARCH_RESULTS_MAX * 2)
        # Relations have their own stable-edge tool.  This lane exposes only
        # actual tree/sibling movement so the same graph operation is not
        # reopened under a different action name.
        rows = [row for row in expanded
                if row.origin.startswith("neighbor:")
                and row.coordinate not in exclude]
        return _dedupe(rows, cap=SEARCH_RESULTS_MAX), {
            "tool": kind, "structural": meta}

    if kind == "exact_search":
        values = tuple(clean_keywords or ([query] if query else []))
        rows = [replace(row, origin="span-exact")
                for row in termexplore.search_all(index, values)
                if row.coordinate not in exclude]
        return _dedupe(rows, cap=SEARCH_RESULTS_MAX), {
            "tool": kind, "terms": list(values), "raw": len(rows)}

    if kind == "assertion_search":
        if not query:
            query = " ".join(clean_keywords)
        try:
            from lawrag.core.rag import assertionfirst, conceptfirst
            registry = conceptfirst.load_registry(conceptfirst.registry_path())
            hits = assertionfirst.current(registry).search(index, query)
        except Exception as exc:  # fail-open to the incumbent
            return [], {"tool": kind, "error": type(exc).__name__}
        rows = []
        for hit in hits:
            row = coordinates.article_branch(
                index, hit.doc_id, hit.node, merged_terms,
                origin="span-assertion",
                reason=f"assertion={hit.assertion_id}; strength={hit.strength}")
            if row is not None and row.coordinate not in exclude:
                rows.append(row)
        return _dedupe(rows, cap=SEARCH_RESULTS_MAX), {
            "tool": kind, "query": query, "hits": len(hits)}

    def keyword_rows() -> tuple[list[termexplore.TermBranch], dict]:
        result = general_search.search_keywords(
            index, clean_keywords, question=question,
            limit=SEARCH_RESULTS_MAX * 2, per_document=4,
            extractor="proof-guided-span")
        rows = []
        for hit in result.hits:
            row = coordinates.article_branch(
                index, hit.doc_id, hit.node, merged_terms,
                origin="span-keyword",
                reason=f"matched={','.join(hit.matched)}; score={hit.score}")
            if row is not None and row.coordinate not in exclude:
                rows.append(row)
        return _dedupe(rows, cap=SEARCH_RESULTS_MAX), result.as_dict()

    def vector_rows() -> tuple[list[termexplore.TermBranch], dict]:
        if not query:
            return [], {"query": "", "hits": 0}
        from lawrag.core.rag import vector as vector_mod
        hits = vector_mod.search(query, topk=SEARCH_RESULTS_MAX,
                                 doc_ids=index.scope)
        rows = []
        for doc_id, node, score in hits:
            row = coordinates.article_branch(
                index, doc_id, node, merged_terms,
                origin="span-vector", reason=f"query={query}; cosine={score}")
            if row is not None and row.coordinate not in exclude:
                rows.append(row)
        return _dedupe(rows, cap=SEARCH_RESULTS_MAX), {
            "query": query, "hits": len(hits),
            "coordinates": [{"doc_id": d, "node": n, "score": score}
                            for d, n, score in hits]}

    if kind == "keyword_search":
        rows, meta = keyword_rows()
        return rows, {"tool": kind, "search": meta}
    if kind == "vector_search":
        rows, meta = vector_rows()
        return rows, {"tool": kind, "search": meta}
    if kind == "hybrid_search":
        left, left_meta = keyword_rows()
        right, right_meta = vector_rows()
        return _dedupe([*left, *right], cap=SEARCH_RESULTS_MAX), {
            "tool": kind, "keyword": left_meta, "vector": right_meta}
    return [], {"tool": kind, "reason": "no_search"}


def _mandatory_companions(index: Index,
                          seeds: list[termexplore.TermBranch],
                          terms: tuple[str, ...], *, exclude: set[tuple],
                          cap: int = 8) \
        -> tuple[list[termexplore.TermBranch], list[dict]]:
    if not seeds:
        return [], []
    hops, _meta = relation_navigation.neighbors(
        index, [row.coordinate for row in seeds], direction="both",
        cap=cap * 3, exclude=exclude)
    selected = [hop for hop in hops if hop.mandatory][:cap]
    rows = [_branch_for_hop(index, hop, terms) for hop in selected]
    return _dedupe((row for row in rows if row is not None), cap=cap), [
        {**hop.as_dict(index), "stable_edge_id": edge_fingerprint(hop)}
        for hop in selected]


def _span_delta(index: Index, rows: list[termexplore.TermBranch], *,
                before_coordinates: set[tuple], before_query_atoms: set[str],
                query_atoms: set[str], before_features: set[str],
                target: str, inspected_new: int = 0,
                operator_new: bool = True) -> tuple[SpanDelta, set[str]]:
    coordinates_all = {row.coordinate for row in rows}
    features = set().union(*(_feature_atoms(index, row) for row in rows)) if rows else set()
    target_atoms = set(_atoms(target))
    aligned = 0
    for row in rows:
        body_atoms = set(_atoms(row.body))
        if target_atoms and target_atoms.intersection(body_atoms):
            aligned += 1
    return SpanDelta(
        coordinate_novelty=(len(coordinates_all - before_coordinates)
                            / max(1, len(coordinates_all))),
        query_novelty=(len(query_atoms - before_query_atoms)
                       / max(1, len(query_atoms))),
        operator_novelty=1.0 if operator_new else 0.0,
        semantic_novelty=(len(features - before_features)
                          / max(1, len(features))),
        observation_novelty=1.0 if inspected_new else 0.0,
        target_alignment=aligned / max(1, len(rows)),
        closure_gain=sum(row.mandatory for row in rows),
    ), features


def _json_rows(states: list[EvidenceState]) -> list[dict]:
    return [{
        "doc_id": state.row.doc_id, "node": state.row.node,
        "doc": state.row.doc, "path": state.row.path,
        "origins": list(state.origins), "statuses": list(state.statuses),
        "observation_level": state.observation_level,
        "inspected_facets": sorted(state.inspected_facets),
        "mandatory": state.row.mandatory,
    } for state in states]


def run(index: Index, question: str, llm,
        initial: list[termexplore.TermBranch],
        observed: list[termexplore.TermBranch],
        terms: tuple[str, ...], initial_meta: dict, *,
        cap: int = PRESENTED_MAX, pool_cap: int = POOL_MAX,
        max_steps: int = MAX_STEPS) \
        -> tuple[list[termexplore.TermBranch], dict]:
    """Expand an immutable incumbent and fill only its unused top-20 slots."""
    incumbent = _dedupe(initial, cap=max(1, int(cap)))
    incumbent_coordinates = {row.coordinate for row in incumbent}
    trace = SearchTrace(question)
    states: list[EvidenceState] = []
    state_by_coordinate: dict[tuple, EvidenceState] = {}

    def add(row: termexplore.TermBranch, *, status: str, level: int = 1) -> bool:
        state = state_by_coordinate.get(row.coordinate)
        if state is not None:
            state.observe(row, status=status, level=level)
            trace.observe_coordinate(
                row.coordinate, origin=row.origin or status,
                observation_depth=level, metadata={"status": status})
            return False
        if len(states) >= max(len(incumbent), int(pool_cap)):
            return False
        state = EvidenceState(row=row, origins=[], statuses=[],
                              observation_level=level)
        state.observe(row, status=status, level=level)
        state_by_coordinate[row.coordinate] = state
        states.append(state)
        trace.observe_coordinate(
            row.coordinate, origin=row.origin or status,
            observation_depth=level, metadata={"status": status})
        return True

    for row in incumbent:
        add(row, status="selected", level=2)
    for row in observed:
        add(row, status=("selected" if row.coordinate in incumbent_coordinates
                         else "deferred"), level=2 if row.coordinate in incumbent_coordinates else 1)
    trace.mark_selected(incumbent_coordinates, stage="initial-incumbent")
    trace.mark_deferred(
        [state.row.coordinate for state in states
         if state.row.coordinate not in incumbent_coordinates],
        stage="initial-pre-top20-trace")

    if llm is None:
        return incumbent, {
            "enabled": True, "ran": False, "strategy": "proof-guided-span",
            "status": "unavailable", "baseline_preserved": True,
            "reason": "llm_unavailable", "hard_deletes": 0,
            "evidence_pool": _json_rows(states),
            "search_trace": trace.summary(),
            "search_trace_events": [event.as_dict() for event in trace.events],
        }

    used_query_atoms = _initial_query_atoms(initial_meta, terms)
    for atom in sorted(used_query_atoms):
        trace.record_query(atom, role="initial-shortcut")
    used_action_fingerprints: set[str] = set()
    consumed_edges: set[str] = set()
    feature_span = set().union(*(
        _feature_atoms(index, state.row) for state in states)) if states else set()
    promoted: list[termexplore.TermBranch] = []
    fresh_order: list[termexplore.TermBranch] = []
    trail: list[dict] = []
    witnesses: list[dict] = []
    duplicate_actions = 0
    status, reason = "unresolved", "budget_exhausted"

    for step in range(1, max(1, int(max_steps)) + 1):
        selected_coordinates = incumbent_coordinates | {
            row.coordinate for row in promoted}
        cards, by_id, inspected = _candidate_projection(
            index, states, selected=selected_coordinates, question=question)
        proof_edges = grounded_witness.build_closed_edge_menu(
            index, {cid: state.row for cid, state in by_id.items()})
        proof_edge_cards = [row.as_dict() for row in proof_edges.values()]
        edges, by_edge, edge_meta = _edge_menu(
            index, states, consumed=consumed_edges)
        public_trace = {
            "initial_selected_count": len(incumbent),
            "observed_count": len(states),
            "used_query_atoms": sorted(used_query_atoms)[:120],
            "used_operator_fingerprints": sorted(used_action_fingerprints),
            "consumed_edge_fingerprints": sorted(consumed_edges),
            "previous_steps": [{
                "step": row["step"], "actions": [
                    {"kind": action["kind"],
                     "target_obligation": action["target_obligation"],
                     "fingerprint": action["fingerprint"],
                     "added": action["added"]}
                    for action in row["actions"]]
            } for row in trail],
        }
        user = (
            f"[원질문]\n{question}\n\n"
            f"[걸음]\n{step}/{max_steps}\n\n"
            f"[초기 및 누적 trace(JSON)]\n{json.dumps(public_trace, ensure_ascii=False)}\n\n"
            f"[후보 원장(JSON)]\n{json.dumps(cards, ensure_ascii=False)}\n\n"
            f"[full inspection 원문(JSON)]\n{json.dumps(inspected, ensure_ascii=False)}\n\n"
            f"[현재 후보 내부의 확정 proof 간선(JSON)]\n"
            f"{json.dumps(proof_edge_cards, ensure_ascii=False)}\n\n"
            f"[미개방 탐색 관계 간선(JSON)]\n{json.dumps(edges, ensure_ascii=False)}"
        )
        raw = llm.structured(
            "rag.legalclosure.proof_guided_span", _SYSTEM, user,
            _schema(list(by_id), list(by_edge), list(proof_edges)),
            max_tokens=OUTPUT_TOKENS_MAX,
            effort=None, model=PRODUCT_MODEL)
        if not isinstance(raw, dict):
            reason = "planner_unavailable"
            break

        witness = _validate_witness(
            index, raw.get("witness"), by_id, proof_edges,
            (raw.get("open_obligations") or ())[:OBLIGATIONS_MAX])
        witnesses.append({"step": step, **witness,
                          "hypotheses": (raw.get("hypotheses") or ())[:HYPOTHESES_MAX],
                          "open_obligations": (raw.get("open_obligations") or ())[:OBLIGATIONS_MAX]})
        for cid in witness["evidence_ids"]:
            row = by_id[cid].row
            if (row.coordinate not in incumbent_coordinates
                    and row.coordinate not in {item.coordinate for item in promoted}):
                promoted.append(row)
                by_id[cid].observe(row, status="witness", level=4)
        if witness["complete"]:
            status, reason = "complete", "grounded_witness"
            trail.append({"step": step, "actions": [], "edge_menu": edge_meta,
                          "witness": witness})
            break

        step_receipts, any_progress = [], False
        for action in (raw.get("actions") or ())[:ACTIONS_PER_STEP]:
            kind = str(action.get("kind") or "stop")
            lane = str(action.get("lane") or "")
            target = _clean(action.get("target_obligation"), 240)
            chosen_edges = [by_edge[eid] for eid in action.get("edge_ids") or ()
                            if eid in by_edge]
            stable_edges = [stable for _hop, stable in chosen_edges]
            fingerprint = action_fingerprint(action, edge_stable_ids=stable_edges)
            receipt = {
                "kind": kind, "lane": lane,
                "target_obligation": target,
                "fingerprint": fingerprint,
                "from_ids": list(action.get("from_ids") or ()),
                "edge_ids": list(action.get("edge_ids") or ()),
                "keywords": list(action.get("keywords") or ())[:KEYWORDS_MAX],
                "query": _clean(action.get("query"), 400),
                "reason": _clean(action.get("reason"), 400),
                "added": 0, "rediscovered": 0, "skipped": "",
                "span_delta": SpanDelta().as_dict(), "tool_meta": {},
            }
            if kind == "stop":
                receipt["skipped"] = "stop"
                step_receipts.append(receipt)
                continue
            expected_lane = ("revisit_seen" if kind == "inspect_seen"
                             else "expand_unseen")
            if lane != expected_lane or not target:
                receipt["skipped"] = "invalid_lane_or_missing_target"
                step_receipts.append(receipt)
                continue
            if fingerprint in used_action_fingerprints:
                duplicate_actions += 1
                receipt["skipped"] = "duplicate_operator_fingerprint"
                step_receipts.append(receipt)
                continue

            query_atoms = set(_action_query_atoms(action))
            if (kind in {"exact_search", "assertion_search", "keyword_search",
                         "vector_search", "hybrid_search"}
                    and query_atoms and not (query_atoms - used_query_atoms)):
                duplicate_actions += 1
                receipt["skipped"] = "query_inside_existing_span"
                step_receipts.append(receipt)
                continue
            used_action_fingerprints.add(fingerprint)
            query_fingerprint = ""
            if query_atoms:
                query_fingerprint = trace.record_query(
                    " ".join(sorted(query_atoms)), role=target,
                    parameters={"kind": kind}, call_id=f"step-{step}")
            trace.record_operator(
                kind, query_fingerprint=query_fingerprint,
                seeds=[by_id[cid].row.coordinate
                       for cid in action.get("from_ids") or () if cid in by_id],
                scope=sorted(index.scope) if index.scope is not None else None,
                parameters={"fingerprint": fingerprint,
                            "target_obligation": target},
                call_id=f"step-{step}")

            if kind == "inspect_seen":
                inspected_new = 0
                for cid in action.get("from_ids") or ():
                    state = by_id.get(cid)
                    if state is None or target in state.inspected_facets:
                        continue
                    state.inspected_facets.add(target)
                    state.observation_level = max(state.observation_level, 3)
                    state.observe(state.row, status="inspected", level=3)
                    trace.mark_inspected(
                        state.row.coordinate, facet_ids=[target],
                        observation_depth=3, call_id=f"step-{step}")
                    inspected_new += 1
                delta, _features = _span_delta(
                    index, [], before_coordinates=set(state_by_coordinate),
                    before_query_atoms=used_query_atoms,
                    query_atoms=set(), before_features=feature_span,
                    target=target, inspected_new=inspected_new)
                receipt["added"] = 0
                receipt["span_delta"] = delta.as_dict()
                any_progress = any_progress or bool(inspected_new)
                step_receipts.append(receipt)
                continue

            before_coordinates = set(state_by_coordinate)
            rows, tool_meta = _execute_action(
                index, question, action, by_id, by_edge, terms,
                exclude=before_coordinates)
            companions, companion_meta = _mandatory_companions(
                index, rows, terms, exclude=before_coordinates | {
                    row.coordinate for row in rows})
            returned = _dedupe([*rows, *companions], cap=SEARCH_RESULTS_MAX + 8)
            added = 0
            for row in returned:
                if add(row, status="discovered", level=1):
                    added += 1
                    fresh_order.append(row)
            rediscovered = len(returned) - added
            delta, new_features = _span_delta(
                index, returned, before_coordinates=before_coordinates,
                before_query_atoms=used_query_atoms,
                query_atoms=query_atoms, before_features=feature_span,
                target=target, operator_new=True)
            used_query_atoms.update(query_atoms)
            feature_span.update(new_features)
            if kind == "relation_expand":
                consumed_edges.update(stable_edges)
                for hop, _stable in chosen_edges:
                    trace.record_edge(
                        (hop.source_doc_id, hop.source_node), hop.target,
                        relation=hop.graph_kind or hop.relation,
                        direction=hop.direction, provenance=hop.provenance,
                        state="consumed", call_id=f"step-{step}")
            consumed_edges.update(row["stable_edge_id"] for row in companion_meta)
            for row in companion_meta:
                trace.record_edge(
                    (row["source_doc_id"], row["source_node"]),
                    (row["target_doc_id"], row["target_node"]),
                    relation=row.get("graph_kind") or row.get("relation") or "",
                    direction=row.get("direction") or "",
                    provenance=row.get("provenance") or "",
                    state="mandatory-closure", call_id=f"step-{step}")
            receipt.update({
                "added": added, "rediscovered": rediscovered,
                "span_delta": delta.as_dict(),
                "tool_meta": {**tool_meta,
                              "mandatory_companions": companion_meta},
            })
            any_progress = any_progress or bool(added)
            step_receipts.append(receipt)

        trail.append({"step": step, "actions": step_receipts,
                      "edge_menu": edge_meta, "witness": witness})
        if not any_progress:
            reason = "no_admissible_frontier_progress"
            break

    available = max(0, max(1, int(cap)) - len(incumbent))
    additions = _dedupe([
        *[row for row in promoted if row.coordinate not in incumbent_coordinates],
        *[row for row in fresh_order if row.coordinate not in incumbent_coordinates],
    ], cap=available)
    selected = [*incumbent, *additions]

    # The core safety property is checked at runtime, not merely documented.
    pool_coordinates = set(state_by_coordinate)
    if not incumbent_coordinates.issubset(pool_coordinates):
        selected = list(incumbent)
        status, reason = "invalid", "append_only_invariant_violation"
    if selected[:len(incumbent)] != incumbent:
        selected = list(incumbent)
        status, reason = "invalid", "incumbent_floor_violation"

    trace.mark_selected(
        [row.coordinate for row in selected], stage="final-presentation")
    trace.mark_deferred(
        [state.row.coordinate for state in states
         if state.row.coordinate not in {row.coordinate for row in selected}],
        stage="final-evidence-pool")

    return selected, {
        "enabled": True, "ran": True,
        "strategy": "proof-guided-span",
        "status": status, "reason": reason,
        "baseline_preserved": True,
        "initial_selected_count": len(incumbent),
        "initial_observed_count": len(observed),
        "evidence_pool_count": len(states),
        "presented_count": len(selected),
        "steps": len(trail), "trail": trail,
        "witnesses": witnesses,
        "used_query_atoms": sorted(used_query_atoms),
        "used_operator_fingerprints": sorted(used_action_fingerprints),
        "consumed_edge_fingerprints": sorted(consumed_edges),
        "duplicate_actions": duplicate_actions,
        "hard_deletes": 0, "rejected": [],
        "promoted": [{"doc_id": row.doc_id, "node": row.node,
                      "doc": row.doc, "path": row.path}
                     for row in additions],
        "evidence_pool": _json_rows(states),
        "search_trace": trace.summary(),
        "search_trace_events": [event.as_dict() for event in trace.events],
        "model": PRODUCT_MODEL,
    }
