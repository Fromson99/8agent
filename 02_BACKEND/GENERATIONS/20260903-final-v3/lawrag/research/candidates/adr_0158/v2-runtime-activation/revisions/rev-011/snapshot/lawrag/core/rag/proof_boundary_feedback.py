"""Single-boundary, source-grounded feedback over a frozen LegalClosure result.

This experiment-only controller deliberately does less than span_feedback:
it freezes one missing claim, executes at most one tool action, and admits only
new coordinates for which a second product call supplies a source-verifiable
quote. Search novelty is a veto, not an answer score.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import re
from typing import Iterable

from lawrag.core.rag import (
    general_search,
    relation_navigation,
    termexplore,
)
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag.index import Index
from lawrag.core.rag.search_trace import SearchTrace


PRODUCT_MODEL = "claude-haiku-4-5-20251001"
PRESENTED_MAX = 20
POOL_MAX = 48
CARDS_MAX = 24
RAW_RESULTS_MAX = 8
ADMISSION_MAX = 3
CARD_CHARS = 1_200
INSPECTION_CHARS = 6_000
OUTPUT_TOKENS_MAX = 2_400
KEYWORDS_MAX = 4

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_ACTION_KINDS = (
    "stop",
    "inspect_seen",
    "relation_expand",
    "exact_search",
    "keyword_search",
    "assertion_search",
    "vector_search",
)

_GATE_SYSTEM = """너는 법률 검색의 단일 증명 경계를 정하는 검사자다.

현재 후보만으로 원질문의 핵심 결론을 직접 뒷받침하는 조문 문구가 있으면 state=supported로
하고, 카드에 실제로 보이는 연속 문구를 evidence quote로 복사한다. 질문이 요구하지 않는 모든
가능한 예외·시점·companion을 전부 닫으려 하지 않는다.

직접 근거가 없다면 missing_claim에는 지금 부족한 법적 명제 하나만 쓴다. 동시에 여러 가설이나
여러 obligation을 만들지 않는다.

- 관련 좌표는 있으나 카드가 잘려 있으면 present_but_unread + inspect_seen
- 본법·하위법령·명시 인용 조문 하나가 빠졌으면 missing_companion + relation_expand
- 지배 업무유형·규율조문 자체가 없으면 missing_rule + exact/keyword/assertion/vector 중 하나

action은 정확히 하나만 제안한다. 검색 query와 keywords는 질문 또는 후보 원문에서 얻은 표현만
사용하고 법령·조문 좌표를 추측하지 않는다. from_id는 입력된 candidate ID만 사용한다."""

_VERIFY_SYSTEM = """너는 단일 missing claim에 대한 신규 법률근거 admission 검사자다.

입력된 closed candidate menu 밖의 ID를 만들지 않는다. missing claim을 실제로 닫는 연속 원문
구절만 quote로 복사한다. 설명을 quote에 섞지 않는다. 기존 후보만으로 닫혀도 괜찮다.

status=closed는 제시한 exact quote들이 missing claim을 직접 뒷받침할 때만 사용한다. 부족하면
unresolved로 두고 remaining_gap을 구체적으로 쓴다. 모든 가능한 법률문제를 완전탐색했는지는
판단하지 않는다."""


def _clean(value: object, cap: int = 400) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:cap]


def _atoms(value: object) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        token.casefold() for token in _TOKEN.findall(str(value or ""))
        if len(token) >= 2))


def stable_fingerprint(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _dedupe(rows: Iterable[termexplore.TermBranch], *, cap: int) \
        -> list[termexplore.TermBranch]:
    out, seen = [], set()
    for row in rows:
        if row.coordinate in seen:
            continue
        seen.add(row.coordinate)
        out.append(row)
        if len(out) >= max(0, int(cap)):
            break
    return out


def _source(index: Index, row: termexplore.TermBranch) -> str:
    view = index.docs.get(row.doc_id)
    if view is None or row.node not in view.by_id:
        return str(row.body or "")
    return coordinates.subtree_text(view, row.node, cap=None)


def _focused(text: str, phrases: Iterable[str], *, cap: int) -> str:
    text = str(text or "")
    if len(text) <= cap:
        return text
    windows: list[tuple[int, int]] = []
    folded = text.casefold()
    for phrase in phrases:
        value = _clean(phrase, 100)
        if len(value) < 2:
            continue
        start = folded.find(value.casefold())
        if start >= 0:
            windows.append((max(0, start - 260), min(len(text), start + 720)))
    if not windows:
        half = max(1, cap // 2)
        return (text[:half] + "\n…\n" + text[-half:])[:cap]
    chunks = []
    for lo, hi in windows:
        chunk = text[lo:hi].strip()
        if chunk and chunk not in chunks:
            chunks.append(chunk)
        if sum(map(len, chunks)) >= cap:
            break
    return "\n…\n".join(chunks)[:cap]


def _cards(index: Index, rows: list[termexplore.TermBranch], question: str,
           terms: tuple[str, ...], *, prefix: str = "C",
           cap: int = CARDS_MAX, chars: int = CARD_CHARS) \
        -> tuple[list[dict], dict[str, termexplore.TermBranch]]:
    public, by_id = [], {}
    phrases = (question, *terms, *_atoms(question))
    for pos, row in enumerate(rows[:cap], 1):
        cid = f"{prefix}{pos}"
        by_id[cid] = row
        public.append({
            "id": cid,
            "document": row.doc,
            "path": row.path,
            "origin": row.origin,
            "mandatory": bool(row.mandatory),
            "matched_terms": list(row.terms),
            "text": _focused(_source(index, row), phrases, cap=chars),
        })
    return public, by_id


def _gate_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "state": {"type": "string", "enum": [
                "supported", "present_but_unread",
                "missing_companion", "missing_rule", "uncertain"]},
            "answer_claim": {"type": "string"},
            "missing_claim": {"type": "string"},
            "evidence": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["candidate_id", "quote"],
                "additionalProperties": False,
            }},
            "action": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(_ACTION_KINDS)},
                    "from_id": {"type": "string"},
                    "query": {"type": "string"},
                    "keywords": {"type": "array",
                                 "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["kind", "from_id", "query", "keywords", "reason"],
                "additionalProperties": False,
            },
        },
        "required": ["state", "answer_claim", "missing_claim",
                     "evidence", "action"],
        "additionalProperties": False,
    }


def _verify_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["closed", "unresolved"]},
            "conclusion": {"type": "string"},
            "evidence": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "quote": {"type": "string"},
                    "role": {"type": "string", "enum": [
                        "support", "companion", "exception"]},
                },
                "required": ["candidate_id", "quote", "role"],
                "additionalProperties": False,
            }},
            "remaining_gap": {"type": "string"},
        },
        "required": ["status", "conclusion", "evidence", "remaining_gap"],
        "additionalProperties": False,
    }


def _whitespace_match(source: str, quote: object) -> tuple[int, int, str] | None:
    raw = str(quote or "").strip()
    if not raw or len(raw) > 1_200:
        return None
    direct = source.find(raw)
    if direct >= 0:
        return direct, direct + len(raw), raw
    parts = re.split(r"\s+", raw)
    if not parts:
        return None
    pattern = r"\s+".join(re.escape(part) for part in parts if part)
    match = re.search(pattern, source)
    if match is None:
        return None
    return match.start(), match.end(), source[match.start():match.end()]


def _validate_evidence(index: Index, raw: object,
                       by_id: dict[str, termexplore.TermBranch]) \
        -> tuple[list[dict], list[str]]:
    accepted, errors, seen = [], [], set()
    for item in (raw if isinstance(raw, list) else ())[:6]:
        if not isinstance(item, dict):
            errors.append("evidence_not_object")
            continue
        cid = str(item.get("candidate_id") or "")
        row = by_id.get(cid)
        if row is None:
            errors.append(f"unknown_candidate:{cid}")
            continue
        match = _whitespace_match(_source(index, row), item.get("quote"))
        if match is None:
            errors.append(f"quote_not_in_source:{cid}")
            continue
        key = (cid, match[0], match[1])
        if key in seen:
            continue
        seen.add(key)
        accepted.append({
            "candidate_id": cid,
            "coordinate": [row.doc_id, row.node],
            "quote": match[2],
            "source_span": [match[0], match[1]],
            "role": str(item.get("role") or "support"),
        })
    return accepted, errors


def _initial_query_atoms(meta: dict, terms: tuple[str, ...]) -> set[str]:
    values: list[object] = list(terms)
    plan = ((meta.get("primary") or {}).get("term_plan") or {})
    for key in ("used_terms", "used_anchor_terms", "operation_terms",
                "grounded_operation_terms", "condition_terms"):
        values.extend(plan.get(key) or ())
    values.extend(((meta.get("keyword") or {}).get("keywords") or ()))
    return {atom for value in values for atom in _atoms(value)}


def _action_atoms(action: dict) -> set[str]:
    values = [action.get("query"), *(action.get("keywords") or ())]
    return {atom for value in values for atom in _atoms(value)}


def _branch_for_hop(index: Index, hop: relation_navigation.RelationHop,
                    terms: tuple[str, ...]) -> termexplore.TermBranch | None:
    row = coordinates.article_branch(
        index, hop.target_doc_id, hop.target_node, terms,
        origin=f"boundary-relation:{hop.graph_kind or hop.relation}",
        reason=f"{hop.provenance}:{hop.direction}:{hop.surface}")
    if row is None:
        return None
    return replace(
        row, mandatory=hop.mandatory,
        mandatory_reason=(f"relation:{hop.graph_kind or hop.relation}"
                          if hop.mandatory else ""),
        source_doc_id=hop.source_doc_id, source_node=hop.source_node)


def _overlap_score(row: termexplore.TermBranch, target: str) -> float:
    wanted = set(_atoms(target))
    if not wanted:
        return 0.0
    text = " ".join((row.doc, row.path, row.body, row.relation_reason))
    found = set(_atoms(text))
    return len(wanted & found) / len(wanted)


def _relation_rows(index: Index, sources: list[termexplore.TermBranch],
                   target: str, terms: tuple[str, ...],
                   exclude: set[tuple], *, cap: int = RAW_RESULTS_MAX) \
        -> tuple[list[termexplore.TermBranch], dict]:
    hops, meta = relation_navigation.neighbors(
        index, [row.coordinate for row in sources],
        direction="both", cap=32, exclude=exclude)
    packed = []
    for hop in hops:
        row = _branch_for_hop(index, hop, terms)
        if row is None or row.coordinate in exclude:
            continue
        packed.append((int(hop.mandatory), _overlap_score(row, target), row, hop))
    packed.sort(key=lambda item: (item[0], item[1]), reverse=True)
    rows = _dedupe((item[2] for item in packed), cap=cap)
    selected_coordinates = {row.coordinate for row in rows}
    return rows, {
        "tool": "relation_expand",
        "raw_hops": len(hops),
        "selected_hops": [item[3].as_dict(index) for item in packed
                          if item[2].coordinate in selected_coordinates],
        "navigation": meta,
    }


def _automatic_companions(index: Index,
                          seeds: list[termexplore.TermBranch],
                          target: str, terms: tuple[str, ...],
                          exclude: set[tuple], *, cap: int = 3) \
        -> list[termexplore.TermBranch]:
    if not seeds:
        return []
    rows, _meta = _relation_rows(
        index, seeds[:4], target, terms, exclude, cap=cap * 2)
    rows.sort(key=lambda row: (
        int(row.mandatory), _overlap_score(row, target)), reverse=True)
    return _dedupe(rows, cap=cap)


def _execute(index: Index, question: str, action: dict,
             by_id: dict[str, termexplore.TermBranch],
             terms: tuple[str, ...], exclude: set[tuple]) \
        -> tuple[list[termexplore.TermBranch], dict]:
    kind = str(action.get("kind") or "stop")
    source = by_id.get(str(action.get("from_id") or ""))
    query = _clean(action.get("query"), 500)
    keywords = []
    for value in action.get("keywords") or ():
        clean = _clean(value, 120)
        if len(clean.replace(" ", "")) >= 2 and clean not in keywords:
            keywords.append(clean)
        if len(keywords) >= KEYWORDS_MAX:
            break
    merged_terms = tuple(dict.fromkeys((*terms, *keywords)))
    target = query or " ".join(keywords) or question

    if kind == "inspect_seen":
        return ([source] if source is not None else []), {
            "tool": kind, "inspected": source.coordinate if source else None}

    if kind == "relation_expand":
        return _relation_rows(
            index, [source] if source is not None else [],
            target, merged_terms, exclude)

    rows: list[termexplore.TermBranch] = []
    meta: dict = {"tool": kind}
    if kind == "exact_search":
        values = tuple(keywords or ([query] if query else []))
        raw = termexplore.search_all(index, values)
        rows = [replace(row, origin="boundary-exact") for row in raw
                if row.coordinate not in exclude]
        rows.sort(key=lambda row: _overlap_score(row, target), reverse=True)
        meta.update(terms=list(values), raw=len(raw))
    elif kind == "keyword_search":
        result = general_search.search_keywords(
            index, keywords, question=question, limit=16, per_document=3,
            extractor="proof-boundary-feedback")
        for hit in result.hits:
            row = coordinates.article_branch(
                index, hit.doc_id, hit.node, merged_terms,
                origin="boundary-keyword",
                reason=f"matched={','.join(hit.matched)}; score={hit.score}")
            if row is not None and row.coordinate not in exclude:
                rows.append(row)
        meta["search"] = result.as_dict()
    elif kind == "assertion_search":
        try:
            from lawrag.core.rag import assertionfirst, conceptfirst
            registry = conceptfirst.load_registry(conceptfirst.registry_path())
            hits = assertionfirst.current(registry).search(index, query)
        except Exception as exc:
            hits = []
            meta["error"] = type(exc).__name__
        for hit in hits:
            row = coordinates.article_branch(
                index, hit.doc_id, hit.node, merged_terms,
                origin="boundary-assertion",
                reason=f"assertion={hit.assertion_id}; strength={hit.strength}")
            if row is not None and row.coordinate not in exclude:
                rows.append(row)
        meta["hits"] = len(hits)
    elif kind == "vector_search":
        from lawrag.core.rag import vector as vector_mod
        hits = vector_mod.search(query, topk=12, doc_ids=index.scope)
        for doc_id, node, score in hits:
            row = coordinates.article_branch(
                index, doc_id, node, merged_terms,
                origin="boundary-vector",
                reason=f"query={query}; cosine={score}")
            if row is not None and row.coordinate not in exclude:
                rows.append(row)
        meta["hits"] = len(hits)

    rows = _dedupe(rows, cap=RAW_RESULTS_MAX)
    companions = _automatic_companions(
        index, rows, target, merged_terms,
        exclude | {row.coordinate for row in rows}, cap=3)
    returned = _dedupe([*rows, *companions], cap=RAW_RESULTS_MAX)
    meta.update(raw_candidates=len(rows),
                automatic_companions=len(companions))
    return returned, meta


def _pool_rows(rows: list[termexplore.TermBranch]) -> list[dict]:
    return [{
        "doc_id": row.doc_id, "node": row.node,
        "doc": row.doc, "path": row.path,
        "origin": row.origin, "mandatory": bool(row.mandatory),
    } for row in rows]


def run(index: Index, question: str, llm,
        initial: list[termexplore.TermBranch],
        observed: list[termexplore.TermBranch],
        terms: tuple[str, ...], initial_meta: dict, *,
        cap: int = PRESENTED_MAX, pool_cap: int = POOL_MAX) \
        -> tuple[list[termexplore.TermBranch], dict]:
    """Run one support gate and, only if needed, one boundary action."""
    incumbent = _dedupe(initial, cap=max(1, int(cap)))
    incumbent_coordinates = {row.coordinate for row in incumbent}
    pool = _dedupe([*incumbent, *observed],
                   cap=max(len(incumbent), int(pool_cap)))
    pool_coordinates = {row.coordinate for row in pool}
    trace = SearchTrace(question)
    for row in pool:
        trace.observe_coordinate(
            row.coordinate, origin=row.origin or "initial",
            observation_depth=2 if row.coordinate in incumbent_coordinates else 1)
    trace.mark_selected(incumbent_coordinates, stage="initial-incumbent")
    trace.mark_deferred(
        [row.coordinate for row in pool
         if row.coordinate not in incumbent_coordinates],
        stage="initial-observed")

    base_meta = {
        "enabled": True,
        "strategy": "proof-boundary-feedback",
        "baseline_preserved": True,
        "initial_selected_count": len(incumbent),
        "initial_observed_count": len(pool),
        "hard_deletes": 0,
        "rejected": [],
    }
    if llm is None:
        return incumbent, {
            **base_meta, "ran": False, "status": "unavailable",
            "reason": "llm_unavailable", "actions": [],
            "evidence_pool": _pool_rows(pool)}

    cards, by_id = _cards(index, pool, question, terms)
    gate_user = (
        f"[원질문]\n{question}\n\n"
        f"[기존 검색어]\n{json.dumps(sorted(_initial_query_atoms(initial_meta, terms)), ensure_ascii=False)}\n\n"
        f"[selected+deferred 후보]\n{json.dumps(cards, ensure_ascii=False)}"
    )
    gate = llm.structured(
        "rag.legalclosure.proof_boundary_gate",
        _GATE_SYSTEM, gate_user, _gate_schema(),
        max_tokens=OUTPUT_TOKENS_MAX, effort=None, model=PRODUCT_MODEL)
    if not isinstance(gate, dict):
        return incumbent, {
            **base_meta, "ran": True, "status": "unresolved",
            "reason": "gate_unavailable", "actions": [],
            "evidence_pool": _pool_rows(pool)}

    gate_evidence, gate_errors = _validate_evidence(
        index, gate.get("evidence"), by_id)
    state = str(gate.get("state") or "uncertain")
    if state == "supported" and gate_evidence:
        return incumbent, {
            **base_meta, "ran": True, "status": "complete",
            "reason": "existing_grounded_support",
            "boundary": {
                "state": state,
                "answer_claim": _clean(gate.get("answer_claim"), 600),
                "missing_claim": "",
            },
            "gate_evidence": gate_evidence,
            "gate_errors": gate_errors,
            "actions": [],
            "raw_candidate_count": 0,
            "admitted": [],
            "promoted": [],
            "evidence_pool": _pool_rows(pool),
            "search_trace": trace.summary(),
            "search_trace_events": [event.as_dict() for event in trace.events],
        }

    missing_claim = _clean(
        gate.get("missing_claim") or gate.get("answer_claim") or question, 700)
    action = gate.get("action") if isinstance(gate.get("action"), dict) else {}
    kind = str(action.get("kind") or "stop")
    query_atoms = _action_atoms(action)
    used_atoms = _initial_query_atoms(initial_meta, terms)
    fingerprint = stable_fingerprint({
        "kind": kind,
        "from_id": str(action.get("from_id") or ""),
        "query_atoms": sorted(query_atoms),
        "missing_claim": missing_claim,
    })
    receipt = {
        "kind": kind,
        "fingerprint": fingerprint,
        "target_claim": missing_claim,
        "from_id": str(action.get("from_id") or ""),
        "query": _clean(action.get("query"), 500),
        "keywords": list(action.get("keywords") or ())[:KEYWORDS_MAX],
        "skipped": "",
        "raw_count": 0,
        "admitted_count": 0,
    }
    if kind == "stop":
        receipt["skipped"] = "no_action"
        return incumbent, {
            **base_meta, "ran": True, "status": "unresolved",
            "reason": "unsupported_without_action",
            "boundary": {"state": state, "missing_claim": missing_claim},
            "gate_evidence": gate_evidence, "gate_errors": gate_errors,
            "actions": [receipt], "raw_candidate_count": 0,
            "admitted": [], "promoted": [],
            "evidence_pool": _pool_rows(pool)}
    if (kind not in {"inspect_seen", "relation_expand"}
            and query_atoms and not (query_atoms - used_atoms)):
        receipt["skipped"] = "query_inside_initial_trace"
        return incumbent, {
            **base_meta, "ran": True, "status": "unresolved",
            "reason": "novelty_veto",
            "boundary": {"state": state, "missing_claim": missing_claim},
            "gate_evidence": gate_evidence, "gate_errors": gate_errors,
            "actions": [receipt], "duplicate_actions": 0,
            "novelty_vetoes": 1,
            "raw_candidate_count": 0, "admitted": [], "promoted": [],
            "evidence_pool": _pool_rows(pool)}

    trace.record_operator(
        kind, query_fingerprint=fingerprint,
        seeds=[by_id[action["from_id"]].coordinate]
        if action.get("from_id") in by_id else (),
        parameters={"missing_claim": missing_claim},
        call_id="boundary-action")
    raw_rows, tool_meta = _execute(
        index, question, action, by_id, terms, pool_coordinates)
    receipt["raw_count"] = len(raw_rows)
    receipt["tool_meta"] = tool_meta

    if kind == "inspect_seen":
        inspect_rows = raw_rows[:1]
        fresh_rows: list[termexplore.TermBranch] = []
        verify_rows = _dedupe([*inspect_rows, *pool], cap=12)
    else:
        fresh_rows = raw_rows
        existing_focus = [
            row for cid, row in by_id.items()
            if cid == str(action.get("from_id") or "")]
        verify_rows = _dedupe([*fresh_rows, *existing_focus, *incumbent], cap=14)

    verify_cards, verify_by_id = _cards(
        index, verify_rows, question, terms, prefix="V", cap=14,
        chars=(INSPECTION_CHARS if kind == "inspect_seen" else 1_800))
    verify_user = (
        f"[원질문]\n{question}\n\n"
        f"[고정 missing claim]\n{missing_claim}\n\n"
        f"[실행 tool]\n{json.dumps(receipt, ensure_ascii=False)}\n\n"
        f"[closed candidate menu]\n{json.dumps(verify_cards, ensure_ascii=False)}"
    )
    verification = llm.structured(
        "rag.legalclosure.proof_boundary_admission",
        _VERIFY_SYSTEM, verify_user, _verify_schema(),
        max_tokens=OUTPUT_TOKENS_MAX, effort=None, model=PRODUCT_MODEL)
    if not isinstance(verification, dict):
        verification = {
            "status": "unresolved", "conclusion": "",
            "evidence": [], "remaining_gap": "verifier unavailable"}
    accepted, verify_errors = _validate_evidence(
        index, verification.get("evidence"), verify_by_id)
    fresh_coordinates = {row.coordinate for row in fresh_rows}
    accepted_coordinates = {
        tuple(item["coordinate"]) for item in accepted
        if tuple(item["coordinate"]) in fresh_coordinates}
    admitted_rows = _dedupe([
        row for row in fresh_rows if row.coordinate in accepted_coordinates
    ], cap=ADMISSION_MAX)
    remaining_pool = max(0, max(len(pool), int(pool_cap)) - len(pool))
    admitted_rows = admitted_rows[:remaining_pool]
    pool = [*pool, *admitted_rows]
    # A malformed extra citation is ignored; it must not erase another closed,
    # source-verifiable citation. Only accepted rows may be admitted.
    closed = (verification.get("status") == "closed"
              and bool(accepted))
    available = max(0, max(1, int(cap)) - len(incumbent))
    promoted_rows = admitted_rows[:available] if closed else []
    selected = [*incumbent, *promoted_rows]
    receipt["admitted_count"] = len(admitted_rows)
    receipt["closed"] = closed
    for row in admitted_rows:
        trace.observe_coordinate(
            row.coordinate, origin=row.origin or kind,
            observation_depth=4 if row in promoted_rows else 3,
            metadata={"admitted": True, "missing_claim": missing_claim})
    trace.mark_selected(
        [row.coordinate for row in selected], stage="final-presentation")
    trace.mark_deferred(
        [row.coordinate for row in pool
         if row.coordinate not in {item.coordinate for item in selected}],
        stage="final-evidence-pool")
    return selected, {
        **base_meta,
        "ran": True,
        "status": "complete" if closed else "unresolved",
        "reason": "grounded_boundary_closed" if closed
                  else "boundary_not_closed",
        "boundary": {
            "state": state,
            "answer_claim": _clean(gate.get("answer_claim"), 600),
            "missing_claim": missing_claim,
        },
        "gate_evidence": gate_evidence,
        "gate_errors": gate_errors,
        "actions": [receipt],
        "raw_candidate_count": len(raw_rows),
        "verification": {
            "requested_status": verification.get("status"),
            "conclusion": _clean(verification.get("conclusion"), 700),
            "remaining_gap": _clean(verification.get("remaining_gap"), 700),
            "accepted_evidence": accepted,
            "errors": verify_errors,
        },
        "admitted": _pool_rows(admitted_rows),
        "promoted": _pool_rows(promoted_rows),
        "evidence_pool": _pool_rows(pool),
        "duplicate_actions": 0,
        "search_trace": trace.summary(),
        "search_trace_events": [event.as_dict() for event in trace.events],
    }


__all__ = [
    "ADMISSION_MAX",
    "POOL_MAX",
    "PRESENTED_MAX",
    "run",
    "stable_fingerprint",
]
