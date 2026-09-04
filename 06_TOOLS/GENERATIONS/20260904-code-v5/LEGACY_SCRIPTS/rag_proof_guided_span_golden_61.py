#!/usr/bin/env python3
"""ADR-0066: 동결한 ADR-0064 초기 상태에서 proof-guided span feedback을 비교한다.

이 실행기는 기존 LegalClosure를 다시 호출하지 않는다. ADR-0064의 frozen case와
``run-001`` baseline 상태를 SHA-256으로 검증한 뒤 baseline arm은 그대로 재사용하고,
candidate arm에서는 그 상태를 ``span_feedback.run``에 전달한다. 기준답변과 gold
좌표는 candidate 호출이 끝난 뒤에만 exact-coordinate 채점에 사용한다.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Iterable


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
for _key, _relative in (
    ("STRUCTURE_STORE", "01_DATA/structure"),
    ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
    ("GLOSSARY_STORE", "01_DATA/glossary.json"),
    ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ("RAG_DELEGATION_STORE", "01_DATA/delegation.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))


MODEL = "claude-haiku-4-5-20251001"
ARMS = ("baseline", "proof-guided-span")
ADR_ID = "ADR-0066"
RUN_ID = "run-007"
CAP = 20
POOL_CAP = 64
MAX_STEPS = 3

PARENT_ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0064-feedback-explore-golden-61"
PARENT_FROZEN = PARENT_ADR / "artifacts/frozen-cases.json"
PARENT_RUN = PARENT_ADR / "artifacts/run-001.json"
PARENT_MANIFEST = PARENT_ADR / "실험/manifest.json"
PARENT_FROZEN_SHA256 = (
    "393ced7e9428aea5d6cbc7ed3383fe10dda199da1cc1bf7fcf0fd57edff9b0cb"
)
PARENT_RUN_SHA256 = (
    "ef19a2fe0d56c446310096a69d3d8539bc79d35b06c353f41dc4ff6ba8a013f0"
)
PARENT_MANIFEST_SHA256 = (
    "33bbbe46d079500f1dd00d3554d7e44f223ed5af0e8c14fe93853186cbb4aa9b"
)
DIRECT_PARENT_EXPERIMENT = "ADR-0065-experiment-v1"
DIRECT_PARENT_ARM = "uncertainty-aware-bindings"
DIRECT_PARENT_MANIFEST = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0065-uncertainty-aware-semantic-bindings/실험/manifest.json"
)
DIRECT_PARENT_MANIFEST_SHA256 = (
    "2f72b2ab89a6e2703740707a50f3ae7ad98b163838d521e9d494274d9c0169c2"
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _repair_trailing_commas(text: str) -> tuple[str, int]:
    """Remove only commas before ]/} while outside JSON strings."""
    out: list[str] = []
    in_string = False
    escaped = False
    repaired = 0
    for idx, char in enumerate(str(text or "")):
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            out.append(char)
            continue
        if char == ",":
            cursor = idx + 1
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor < len(text) and text[cursor] in "]}":
                repaired += 1
                continue
        out.append(char)
    return "".join(out), repaired


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1,
                       max(0, round((len(ordered) - 1) * ratio)))]


def _article_roots(index) -> int:
    return sum(
        node.get("family") == "kr_article"
        and "부칙" not in (view.path(node_id) or "")
        for view in index.docs.values()
        for node_id, node in view.by_id.items()
    )


def _coordinate(value: object) -> tuple[str, object] | None:
    if hasattr(value, "doc_id") and hasattr(value, "node"):
        doc_id, node = str(getattr(value, "doc_id") or ""), getattr(value, "node")
        return (doc_id, node) if doc_id and node is not None else None
    if isinstance(value, dict):
        if value.get("doc_id") and value.get("node") is not None:
            return str(value["doc_id"]), value["node"]
        nested = value.get("coordinate")
        if nested is not None:
            return _coordinate(nested)
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return str(value[0]), value[1]
    return None


def _coordinate_records(index, values: object) -> list[dict]:
    if isinstance(values, dict):
        for key in ("items", "coordinates", "rows", "pool"):
            if isinstance(values.get(key), list):
                values = values[key]
                break
        else:
            values = list(values.values())
    out, seen = [], set()
    for rank, value in enumerate(values or (), 1):
        coord = _coordinate(value)
        if coord is None:
            continue
        doc_id, node = coord
        key = (doc_id, node)
        if key in seen:
            continue
        seen.add(key)
        record = dict(value) if isinstance(value, dict) else {}
        view = index.docs.get(doc_id)
        record.update({"rank": len(out) + 1, "doc_id": doc_id, "node": node})
        if view is not None and node in view.by_id:
            record.setdefault("doc", view.name)
            record.setdefault("path", view.path(node))
        out.append(record)
    return out


def _terms(meta: dict) -> tuple[str, ...]:
    plan = ((meta.get("primary") or {}).get("term_plan") or {})
    values = list(plan.get("used_terms") or ())
    values.extend(((meta.get("keyword") or {}).get("keywords") or ()))
    return tuple(dict.fromkeys(
        str(value).strip() for value in values if str(value).strip()))


def _restore_branch(index, row: dict, terms: tuple[str, ...], *,
                    default_origin: str):
    from lawrag.core.rag import legal_coordinates

    doc_id = str(row.get("doc_id") or "")
    node = row.get("node")
    branch = legal_coordinates.article_branch(
        index, doc_id, node, terms,
        origin=str(row.get("origin") or default_origin),
        reason=str(row.get("relation_reason") or row.get("reason")
                   or row.get("path") or ""))
    if branch is None:
        raise ValueError(f"cannot restore frozen coordinate: {doc_id}:{node}")
    # Frozen trace menus may contain a paragraph/item coordinate while the
    # retrieval unit is an article root.  Permit only that deterministic,
    # same-document canonicalization.  Cross-document/version rebinding stays
    # forbidden so a frozen observation cannot silently move to new evidence.
    view = index.docs.get(doc_id)
    canonical = (doc_id, legal_coordinates.article_root(view, node)) \
        if view is not None and node in view.by_id else (doc_id, node)
    if branch.coordinate != canonical:
        raise ValueError(
            f"frozen coordinate rebound is not allowed: {doc_id}:{node} "
            f"-> {branch.doc_id}:{branch.node}")
    return replace(
        branch,
        mandatory=bool(row.get("mandatory", branch.mandatory)),
        mandatory_reason=str(row.get("mandatory_reason")
                             or branch.mandatory_reason),
        source_doc_id=str(row.get("source_doc_id")
                          or branch.source_doc_id),
        source_node=(row.get("source_node")
                     if row.get("source_node") is not None
                     else branch.source_node),
    )


def _initial_branches(index, baseline: dict, terms: tuple[str, ...]) -> list:
    out, seen = [], set()
    hints = {}
    meta = baseline.get("retrieval_meta") or {}
    for row in list(meta.get("closure") or ()):
        coord = _coordinate(row)
        if coord is not None:
            hints[coord] = row
    for row in baseline.get("selected") or ():
        coord = _coordinate(row)
        if coord is None or coord in seen:
            continue
        merged = {**dict(hints.get(coord) or {}), **dict(row)}
        branch = _restore_branch(
            index, merged, terms, default_origin="frozen-baseline-selected")
        out.append(branch)
        seen.add(branch.coordinate)
    if len(out) != int(baseline.get("selected_count", len(out))):
        raise ValueError("frozen baseline selected count mismatch")
    return out


def _observed_branches(index, baseline: dict, initial: list,
                       terms: tuple[str, ...]) -> list:
    """ADR-0064의 실제 candidate menus를 닫힌 observed branch로 복원한다."""
    meta = baseline.get("retrieval_meta") or {}
    sources = [
        ("baseline-selected", baseline.get("selected") or ()),
        ("primary-review", ((meta.get("primary") or {})
                            .get("review_candidates") or ())),
        ("primary-selected", ((meta.get("primary") or {})
                              .get("selected") or ())),
        ("keyword-article", ((meta.get("keyword") or {})
                             .get("article_candidates") or ())),
        ("closure", meta.get("closure") or ()),
        ("assertion-selected", ((meta.get("assertion") or {})
                                .get("selected") or ())),
        ("selected-meta", meta.get("selected") or ()),
    ]
    by_coordinate = {row.coordinate: row for row in initial}
    order = [row.coordinate for row in initial]
    for origin, rows in sources:
        for item in rows:
            coord = _coordinate(item)
            if coord is None or coord in by_coordinate:
                continue
            branch = _restore_branch(
                index, dict(item), terms, default_origin=f"observed:{origin}")
            if branch.coordinate in by_coordinate:
                continue
            by_coordinate[branch.coordinate] = branch
            order.append(branch.coordinate)
    return [by_coordinate[coord] for coord in order]


def _branch_dump(row) -> dict:
    return {
        "doc_id": row.doc_id, "node": row.node,
        "doc": row.doc, "path": row.path,
        "terms": list(row.terms), "excerpts": list(row.excerpts),
        "body": row.body, "body_chars": row.body_chars,
        "origin": row.origin, "relation_reason": row.relation_reason,
        "mandatory": row.mandatory,
        "mandatory_reason": row.mandatory_reason,
        "source_doc_id": row.source_doc_id,
        "source_node": row.source_node,
    }


def _selected(branches: Iterable) -> list[dict]:
    return [{
        "rank": rank, "doc_id": row.doc_id, "node": row.node,
        "doc": row.doc, "path": row.path, "origin": row.origin,
        "mandatory": bool(row.mandatory),
        "mandatory_reason": row.mandatory_reason,
    } for rank, row in enumerate(branches, 1)]


def _grade(case: dict, selected: list[dict], pool: list[dict]) \
        -> tuple[list[dict], bool | None, bool | None]:
    selected_ranks = {
        (str(row["doc_id"]), row["node"]): row["rank"] for row in selected}
    pool_ranks = {
        (str(row["doc_id"]), row["node"]): row["rank"] for row in pool}
    results = []
    for item in case.get("expected_articles") or ():
        scorable = (item.get("corpus_status") == "present"
                    and item.get("node") is not None)
        key = (str(item.get("doc_id") or ""), item.get("node"))
        rank = selected_ranks.get(key) if scorable else None
        pool_rank = pool_ranks.get(key) if scorable else None
        results.append({
            **item, "scorable": scorable,
            "hit": rank is not None if scorable else None, "rank": rank,
            "internal_pool_hit": pool_rank is not None if scorable else None,
            "internal_pool_rank": pool_rank,
        })
    scored = [item for item in results if item["scorable"]]
    if not scored:
        return results, None, None
    return (results, all(item["hit"] for item in scored),
            all(item["internal_pool_hit"] for item in scored))


def _usage(calls: list[dict], *, runtime_error: str = "") -> dict:
    provider_errors = sum(bool((row.get("provider") or {}).get("error"))
                          for row in calls)
    recovered_errors = sum(
        bool((row.get("deterministic_repair") or {}).get("success"))
        for row in calls)
    runtime_errors = int(bool(runtime_error))
    return {
        "calls": len(calls),
        "input_tokens": sum(int(((row.get("provider") or {}).get("usage")
                                 or {}).get("input_tokens", 0)) for row in calls),
        "output_tokens": sum(int(((row.get("provider") or {}).get("usage")
                                  or {}).get("output_tokens", 0)) for row in calls),
        "duration_ms": sum(int((row.get("provider") or {}).get("dur_ms", 0))
                           for row in calls),
        "errors": provider_errors + runtime_errors,
        "provider_errors": provider_errors,
        "recovered_errors": recovered_errors,
        "unrecovered_errors": max(0, provider_errors - recovered_errors)
                              + runtime_errors,
    }


def _sum_usage(left: dict, right: dict) -> dict:
    keys = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors",
            "provider_errors", "recovered_errors", "unrecovered_errors")
    return {key: int(left.get(key, 0)) + int(right.get(key, 0)) for key in keys}


def _audit_call(kind, system, user, schema, max_tokens, effort, model,
                result, exchange) -> dict:
    return {
        "kind": kind, "system": system, "user": user, "schema": schema,
        "max_tokens": max_tokens, "effort": effort,
        "requested_model": model or MODEL,
        "provider": exchange.dump() if exchange is not None else {},
        "structured_output": result,
    }


class RecordingLLM:
    def __init__(self, real):
        self.real = real
        self.model = real.model
        self.audit: list[dict] = []
        self.log = real.log

    def structured(self, kind, system, user, schema, max_tokens=16000,
                   effort="high", images=None, model=None):
        before = len(self.real.log)
        try:
            result = self.real.structured(
                kind, system, user, schema, max_tokens=max_tokens, effort=effort,
                images=images, model=model)
        except Exception:
            exchange = self.real.log[before] if len(self.real.log) > before else None
            self.audit.append(_audit_call(
                kind, system, user, schema, max_tokens, effort, model,
                None, exchange))
            raise
        else:
            exchange = self.real.log[before] if len(self.real.log) > before else None
            repair = None
            if (result is None and exchange is not None
                    and str(exchange.error).startswith("JSONDecodeError:")
                    and exchange.raw_response):
                fixed, count = _repair_trailing_commas(exchange.raw_response)
                if count:
                    try:
                        parsed = json.loads(fixed)
                    except json.JSONDecodeError as exc:
                        repair = {"kind": "trailing_comma", "success": False,
                                  "count": count, "error": str(exc)}
                    else:
                        if isinstance(parsed, dict):
                            result = parsed
                            repair = {"kind": "trailing_comma", "success": True,
                                      "count": count,
                                      "repaired_sha256": hashlib.sha256(
                                          fixed.encode("utf-8")).hexdigest()}
            call = _audit_call(
                kind, system, user, schema, max_tokens, effort, model,
                result, exchange)
            if repair is not None:
                call["deterministic_repair"] = repair
            self.audit.append(call)
            return result


def _action_rows(meta: dict) -> list[dict]:
    containers = [
        meta.get("trail"), meta.get("actions"), meta.get("steps"),
        (meta.get("trace") or {}).get("actions")
        if isinstance(meta.get("trace"), dict) else None,
    ]
    for rows in containers:
        if isinstance(rows, list) and rows:
            flattened = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                actions = row.get("actions")
                if isinstance(actions, list):
                    flattened.extend(action for action in actions
                                     if isinstance(action, dict))
                else:
                    flattened.append(row)
            return flattened
    return []


def _action_fingerprint(row: dict) -> str:
    for key in ("fingerprint", "action_fingerprint", "query_fingerprint"):
        if row.get(key):
            return str(row[key])
    action = row.get("action") if isinstance(row.get("action"), dict) else row
    payload = {
        key: action.get(key) for key in (
            "kind", "mode", "tool", "target_facet", "query", "keywords",
            "from_ids", "edge_ids", "candidate_ids", "coordinates")
        if action.get(key) not in (None, "", [], {})
    }
    return _json_sha(payload) if payload else ""


def _declared_duplicate_fingerprints(meta: object) -> int:
    if isinstance(meta, dict):
        count = 0
        for key, value in meta.items():
            lowered = str(key).lower()
            if "duplicate" in lowered and "fingerprint" in lowered:
                if isinstance(value, list):
                    count = max(count, len(value))
                elif isinstance(value, bool):
                    count = max(count, int(value))
                elif isinstance(value, (int, float)):
                    count = max(count, int(value))
            count = max(count, _declared_duplicate_fingerprints(value))
        return count
    if isinstance(meta, list):
        return max((_declared_duplicate_fingerprints(value) for value in meta),
                   default=0)
    return 0


def _fingerprint_audit(meta: dict) -> dict:
    fingerprints = [value for value in (
        _action_fingerprint(row) for row in _action_rows(meta)) if value]
    computed = len(fingerprints) - len(set(fingerprints))
    declared = max(
        _declared_duplicate_fingerprints(meta),
        int(meta.get("duplicate_actions") or 0),
    )
    return {
        "fingerprints": fingerprints,
        "computed_duplicate_count": computed,
        "declared_duplicate_count": declared,
        "duplicate_count": max(computed, declared),
    }


def _append_only_audit(observed: list[dict], selected: list[dict],
                       pool: list[dict], meta: dict) -> dict:
    observed_coords = {(row["doc_id"], row["node"]) for row in observed}
    selected_coords = {(row["doc_id"], row["node"]) for row in selected}
    pool_coords = {(row["doc_id"], row["node"]) for row in pool}
    observed_missing = sorted(observed_coords - pool_coords, key=str)
    selected_missing = sorted(selected_coords - pool_coords, key=str)
    hard_deletes = int(meta.get("hard_deletes") or 0)
    rejected = list(meta.get("rejected") or ())
    return {
        "initial_observed_count": len(observed_coords),
        "pool_count": len(pool_coords),
        "initial_observed_missing_from_pool": [list(row)
                                                for row in observed_missing],
        "selected_missing_from_pool": [list(row) for row in selected_missing],
        "declared_hard_deletes": hard_deletes,
        "declared_rejected": rejected,
        "passed": (not observed_missing and not selected_missing
                   and hard_deletes == 0 and not rejected),
    }


def _baseline_arm(index, case: dict, parent: dict, observed: list) -> dict:
    selected = deepcopy(parent.get("selected") or [])
    pool = _coordinate_records(index, observed)
    gold, all_hit, pool_all_hit = _grade(case, selected, pool)
    stored = [item for item in parent.get("gold_results") or ()
              if item.get("scorable")]
    recomputed = [item for item in gold if item.get("scorable")]
    if [(item.get("doc_id"), item.get("node"), item.get("hit"))
            for item in stored] != [
                (item.get("doc_id"), item.get("node"), item.get("hit"))
                for item in recomputed]:
        raise ValueError(f"{case['id']}: parent baseline grading mismatch")
    return {
        "arm": "baseline", "source": "ADR-0064/run-001/baseline",
        "selected": selected, "selected_count": len(selected),
        "internal_pool": pool, "internal_pool_count": len(pool),
        "gold_results": gold, "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": deepcopy(parent.get("retrieval_meta") or {}),
        "llm_calls": deepcopy(parent.get("llm_calls") or []),
        "provider_usage": deepcopy(parent.get("provider_usage") or {}),
        "wall_ms": float(parent.get("wall_ms") or 0),
        "parent_state_sha256": _json_sha(parent),
        "runtime_error": "",
    }


def _candidate_arm(index, case: dict, baseline: dict, initial: list,
                   observed: list, terms: tuple[str, ...], llm) -> dict:
    from lawrag.core.rag import span_feedback

    recording = RecordingLLM(llm)
    started = time.perf_counter()
    runtime_error = ""
    meta: dict = {}
    try:
        candidate, raw_meta = span_feedback.run(
            index, case["question"], recording, list(initial), list(observed),
            terms, deepcopy(baseline["retrieval_meta"]),
            cap=CAP, pool_cap=POOL_CAP,
            max_steps=MAX_STEPS)
        meta = dict(raw_meta or {})
    except Exception as exc:  # 실행 오류도 arm 결과로 보존하고 baseline으로 fail-open한다.
        runtime_error = f"{type(exc).__name__}: {exc}"
        candidate = list(initial)
        meta = {
            "enabled": True, "ran": True, "runtime_error": runtime_error,
            "evidence_pool": [_branch_dump(row) for row in initial],
        }
    incremental_wall_ms = (time.perf_counter() - started) * 1000
    selected = _selected(candidate)
    if "evidence_pool" not in meta:
        raise ValueError(
            f"{case['id']}: span_feedback meta must contain evidence_pool")
    pool = _coordinate_records(index, meta.get("evidence_pool"))
    gold, all_hit, pool_all_hit = _grade(case, selected, pool)
    incremental_usage = _usage(recording.audit, runtime_error=runtime_error)
    effective_usage = _sum_usage(baseline["provider_usage"], incremental_usage)
    append_only = _append_only_audit(
        baseline["internal_pool"], selected, pool, meta)
    fingerprints = _fingerprint_audit(meta)
    return {
        "arm": "proof-guided-span",
        "selected": selected, "selected_count": len(selected),
        "internal_pool": pool, "internal_pool_count": len(pool),
        "gold_results": gold, "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": meta,
        "llm_calls": recording.audit,
        "reused_initial_llm_calls_ref": "arms.baseline.llm_calls",
        "provider_usage": effective_usage,
        "incremental_provider_usage": incremental_usage,
        "wall_ms": round(baseline["wall_ms"] + incremental_wall_ms, 3),
        "incremental_wall_ms": round(incremental_wall_ms, 3),
        "append_only_audit": append_only,
        "fingerprint_audit": fingerprints,
        "runtime_error": runtime_error,
    }


def _paired(baseline: dict, candidate: dict) -> dict:
    selected, pool = [], []
    for left, right in zip(baseline["gold_results"], candidate["gold_results"]):
        if not left["scorable"]:
            selected_status = pool_status = "unscorable"
        else:
            selected_status = (
                "both" if left["hit"] and right["hit"] else
                "candidate_only" if right["hit"] else
                "baseline_only" if left["hit"] else "neither")
            pool_status = (
                "both" if (left["internal_pool_hit"]
                           and right["internal_pool_hit"]) else
                "candidate_only" if right["internal_pool_hit"] else
                "baseline_only" if left["internal_pool_hit"] else "neither")
        base = {
            "doc_id": left.get("doc_id"), "node": left.get("node"),
            "law": left.get("law"), "article": left.get("article"),
        }
        selected.append({**base, "status": selected_status})
        pool.append({**base, "status": pool_status})
    case = (
        "unscorable" if baseline["case_all_gold_hit"] is None else
        "both" if (baseline["case_all_gold_hit"]
                   and candidate["case_all_gold_hit"]) else
        "candidate_only" if candidate["case_all_gold_hit"] else
        "baseline_only" if baseline["case_all_gold_hit"] else "neither")
    pool_case = (
        "unscorable" if baseline["case_all_gold_internal_pool_hit"] is None else
        "both" if (baseline["case_all_gold_internal_pool_hit"]
                   and candidate["case_all_gold_internal_pool_hit"]) else
        "candidate_only" if candidate["case_all_gold_internal_pool_hit"] else
        "baseline_only" if baseline["case_all_gold_internal_pool_hit"] else
        "neither")
    return {
        "selected_articles": selected, "internal_pool_articles": pool,
        "case_all_gold": case, "case_all_gold_internal_pool": pool_case,
    }


def _status_counts(rows: list[dict], key: str) -> dict:
    if key.endswith("articles"):
        values = [item["status"] for row in rows for item in row["paired"][key]]
    else:
        values = [row["paired"][key] for row in rows]
    return {name: values.count(name) for name in (
        "candidate_only", "baseline_only", "both", "neither", "unscorable")}


def _arm_summary(rows: list[dict], arm: str, corpus: int) -> dict:
    values = [row["arms"][arm] for row in rows]
    scored = [gold for row in values for gold in row["gold_results"]
              if gold["scorable"]]
    case_rows = [row for row in values if row["case_all_gold_hit"] is not None]
    pool_case_rows = [row for row in values
                      if row["case_all_gold_internal_pool_hit"] is not None]
    selected_counts = [row["selected_count"] for row in values]
    pool_counts = [row["internal_pool_count"] for row in values]
    walls = [row["wall_ms"] for row in values]
    usage = {key: sum(int((row.get("provider_usage") or {}).get(key, 0))
                      for row in values)
             for key in ("calls", "input_tokens", "output_tokens",
                         "duration_ms", "errors", "provider_errors",
                         "recovered_errors", "unrecovered_errors")}
    incremental = {key: sum(int((row.get("incremental_provider_usage") or {})
                                .get(key, 0)) for row in values)
                   for key in usage}
    hits = sum(bool(gold["hit"]) for gold in scored)
    pool_hits = sum(bool(gold["internal_pool_hit"]) for gold in scored)
    return {
        "scorable_cases": len(case_rows),
        "case_all_gold_hits": sum(bool(row["case_all_gold_hit"])
                                  for row in case_rows),
        "case_all_gold_recall_at_20": round(
            sum(bool(row["case_all_gold_hit"]) for row in case_rows)
            / len(case_rows), 6) if case_rows else 0,
        "case_all_gold_internal_pool_hits": sum(
            bool(row["case_all_gold_internal_pool_hit"])
            for row in pool_case_rows),
        "gold_article_instances": len(scored),
        "gold_article_hits": hits,
        "article_instance_recall_at_20": round(hits / len(scored), 6)
        if scored else 0,
        "internal_pool_gold_hits": pool_hits,
        "internal_pool_recall": round(pool_hits / len(scored), 6)
        if scored else 0,
        "selected_mean": round(statistics.mean(selected_counts), 3)
        if selected_counts else 0,
        "selected_p50": statistics.median(selected_counts)
        if selected_counts else 0,
        "selected_p95": _percentile(selected_counts, .95),
        "internal_pool_mean": round(statistics.mean(pool_counts), 3)
        if pool_counts else 0,
        "internal_pool_p50": statistics.median(pool_counts) if pool_counts else 0,
        "internal_pool_p95": _percentile(pool_counts, .95),
        "mean_selectivity": round(statistics.mean(selected_counts) / corpus, 8)
        if selected_counts and corpus else 0,
        "internal_pool_selectivity": round(
            statistics.mean(pool_counts) / corpus, 8)
        if pool_counts and corpus else 0,
        "wall_ms_p50": round(statistics.median(walls), 3) if walls else 0,
        "wall_ms_p95": round(_percentile(walls, .95), 3),
        "provider_usage": usage,
        "incremental_provider_usage": incremental,
    }


def _summary(rows: list[dict], corpus: int) -> dict:
    result = {
        "cases": len(rows), "corpus_article_roots": corpus,
        "arms": {arm: _arm_summary(rows, arm, corpus) for arm in ARMS},
        "paired_selected_articles": _status_counts(rows, "selected_articles"),
        "paired_internal_pool_articles": _status_counts(
            rows, "internal_pool_articles"),
        "paired_cases": _status_counts(rows, "case_all_gold"),
        "paired_internal_pool_cases": _status_counts(
            rows, "case_all_gold_internal_pool"),
        "suites": {},
    }
    for suite in sorted({row["suite"] for row in rows}):
        suite_rows = [row for row in rows if row["suite"] == suite]
        result["suites"][suite] = {
            "cases": len(suite_rows),
            "arms": {arm: _arm_summary(suite_rows, arm, corpus)
                     for arm in ARMS},
            "paired_selected_articles": _status_counts(
                suite_rows, "selected_articles"),
            "paired_cases": _status_counts(suite_rows, "case_all_gold"),
        }
    baseline = result["arms"]["baseline"]
    candidate = result["arms"]["proof-guided-span"]
    result["criteria"] = {
        "candidate_only_articles_at_least_2": (
            result["paired_selected_articles"]["candidate_only"] >= 2),
        "selected_article_regression_zero": (
            result["paired_selected_articles"]["baseline_only"] == 0),
        "selected_case_regression_zero": (
            result["paired_cases"]["baseline_only"] == 0),
        "append_only_zero_violations": all(
            row["arms"]["proof-guided-span"]["append_only_audit"]["passed"]
            for row in rows),
        "duplicate_action_fingerprints_zero": all(
            row["arms"]["proof-guided-span"]["fingerprint_audit"]
            ["duplicate_count"] == 0 for row in rows),
        "selected_cap_20": all(
            row["arms"][arm]["selected_count"] <= CAP
            for row in rows for arm in ARMS),
        "internal_pool_cap_64": all(
            row["arms"]["proof-guided-span"]["internal_pool_count"] <= POOL_CAP
            for row in rows),
        "incremental_calls_at_most_3_per_case": all(
            row["arms"]["proof-guided-span"]["incremental_provider_usage"]
            ["calls"] <= MAX_STEPS for row in rows),
        "provider_and_runtime_errors_zero": (
            candidate["incremental_provider_usage"]["errors"] == 0),
        "estimated_latency_p95_at_most_3x": (
            candidate["wall_ms_p95"] <= baseline["wall_ms_p95"] * 3
            if baseline["wall_ms_p95"] else False),
    }
    result["target_pass"] = bool(rows) and all(result["criteria"].values())
    return result


def _question_markdown(case: dict, row: dict, input_state: dict) -> str:
    baseline = row["arms"]["baseline"]
    candidate = row["arms"]["proof-guided-span"]
    grading = {
        "baseline": baseline["gold_results"],
        "proof-guided-span": candidate["gold_results"],
        "paired": row["paired"],
    }
    final = {
        "baseline_selected": baseline["selected"],
        "baseline_internal_pool": baseline["internal_pool"],
        "candidate_selected": candidate["selected"],
        "candidate_internal_pool": candidate["internal_pool"],
        "candidate_meta": candidate["retrieval_meta"],
        "append_only_audit": candidate["append_only_audit"],
        "fingerprint_audit": candidate["fingerprint_audit"],
        "usage": {
            "baseline": baseline["provider_usage"],
            "candidate_effective": candidate["provider_usage"],
            "candidate_incremental": candidate["incremental_provider_usage"],
        },
        "latency_ms": {
            "baseline": baseline["wall_ms"],
            "candidate_effective": candidate["wall_ms"],
            "candidate_incremental": candidate["incremental_wall_ms"],
        },
    }
    return f"""# ADR-0066 질문 {case['number']:03d}: {case['id']}

## 1. 실행 메타

- run: `{RUN_ID}`
- arms: `baseline`, `proof-guided-span`
- phase: `probe/in_sample`
- product/controller model: `{MODEL}`
- selected cap: `{CAP}`
- internal pool cap: `{POOL_CAP}`
- parent frozen SHA-256: `{PARENT_FROZEN_SHA256}`
- parent run SHA-256: `{PARENT_RUN_SHA256}`
- baseline state SHA-256: `{baseline['parent_state_sha256']}`
- baseline source: ADR-0064의 검증된 저장 상태 재사용

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

{case.get('reference_answer', '')}

## 4. 제품 입력을 구성한 원값

아래 값에는 기준답변과 expected article 좌표가 들어 있지 않다.

```json
{json.dumps(input_state, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### baseline — ADR-0064 저장 원문

```json
{json.dumps(baseline['llm_calls'], ensure_ascii=False, indent=2)}
```

### proof-guided-span — 증분 controller 호출

```json
{json.dumps(candidate['llm_calls'], ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

candidate 호출 목록에 span feedback의 실제 system, user, schema, provider 원응답,
structured output을 호출 순서대로 보존했다. baseline 초기 호출은 재실행하지 않았으며 위
baseline 원문과 상태를 hash 검증해 사용했다.

## 7. 채점 호출과 반복 판정

judge LLM은 없다. candidate 호출 완료 뒤 `doc_id + article root node` exact match로
최종 top-20과 내부 evidence pool을 각각 채점했다.

```json
{json.dumps(grading, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

```json
{json.dumps(final, ensure_ascii=False, indent=2)}
```
"""


def _load_parent() -> tuple[dict, dict, dict]:
    expected = (
        (PARENT_FROZEN, PARENT_FROZEN_SHA256),
        (PARENT_RUN, PARENT_RUN_SHA256),
        (PARENT_MANIFEST, PARENT_MANIFEST_SHA256),
    )
    for path, digest in expected:
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = _sha(path)
        if actual != digest:
            raise ValueError(
                f"parent artifact SHA mismatch: {path.relative_to(ROOT)} "
                f"expected={digest} actual={actual}")
    frozen = json.loads(PARENT_FROZEN.read_text(encoding="utf-8"))
    run = json.loads(PARENT_RUN.read_text(encoding="utf-8"))
    manifest = json.loads(PARENT_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("dataset", {}).get("sha256") != PARENT_FROZEN_SHA256:
        raise ValueError("parent manifest frozen SHA mismatch")
    parent_run = next((item for item in manifest.get("runs") or ()
                       if item.get("id") == "run-001"), None)
    if not parent_run or parent_run.get("sha256") != PARENT_RUN_SHA256:
        raise ValueError("parent manifest run SHA mismatch")
    if run.get("frozen_sha256") != PARENT_FROZEN_SHA256:
        raise ValueError("parent run frozen lineage mismatch")
    cases = list(frozen.get("cases") or ())
    rows = list(run.get("rows") or ())
    if len(cases) != 61 or len(rows) != 61:
        raise ValueError("expected 61 frozen cases and 61 parent rows")
    if [case.get("id") for case in cases] != [row.get("case_id") for row in rows]:
        raise ValueError("parent run case order mismatch")
    gold = sum(len(case.get("expected_articles") or ()) for case in cases)
    scorable = sum(
        item.get("corpus_status") == "present" and item.get("node") is not None
        for case in cases for item in case.get("expected_articles") or ())
    if gold != 85 or scorable != 83:
        raise ValueError("expected 85 gold / 83 corpus-present instances")
    return frozen, run, manifest


def _validate_adr_manifest(adr: Path, *, require_frozen: bool) -> dict:
    path = adr / "실험/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID} manifest")
    if (not DIRECT_PARENT_MANIFEST.is_file()
            or _sha(DIRECT_PARENT_MANIFEST) != DIRECT_PARENT_MANIFEST_SHA256):
        raise ValueError("direct parent manifest file/hash mismatch")
    parents = (manifest.get("lineage") or {}).get("parents") or []
    parent = next((item for item in parents
                   if item.get("experiment_id") == DIRECT_PARENT_EXPERIMENT
                   and item.get("arm_id") == DIRECT_PARENT_ARM), None)
    if parent is None or parent.get("manifest_sha256") != DIRECT_PARENT_MANIFEST_SHA256:
        raise ValueError("ADR-0066 direct parent arm/hash mismatch")
    arm_ids = {item.get("id") for item in
               (manifest.get("design") or {}).get("arms") or ()}
    if set(ARMS) - arm_ids:
        raise ValueError("ADR-0066 arms mismatch")
    calls = (manifest.get("llm_policy") or {}).get("llm_calls") or []
    if any(item.get("model") != MODEL for item in calls):
        raise ValueError("all declared LLM calls must use product Haiku")
    if any(item.get("class") != "product" for item in calls):
        raise ValueError("retrieval exact grading must not declare a judge LLM")
    if require_frozen:
        design = manifest.get("design") or {}
        if not design.get("criteria_frozen_before_run"):
            raise ValueError("criteria_frozen_before_run must be true")
        dataset_sha = str((manifest.get("dataset") or {}).get("sha256") or "")
        if dataset_sha != PARENT_FROZEN_SHA256:
            raise ValueError("ADR-0066 frozen dataset SHA mismatch")
        run = next((item for item in manifest.get("runs") or ()
                    if item.get("id") == RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("ADR-0066 run-001 must be planned or running")
    return manifest


def _save(out: Path, adr: Path, frozen: dict, rows: list[dict], corpus: int) -> None:
    result = {
        "schema_version": "proof-guided-span-golden-61-run-v1",
        "adr_id": ADR_ID, "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lineage": {
            "frozen_path": str(PARENT_FROZEN.relative_to(ROOT)),
            "frozen_sha256": PARENT_FROZEN_SHA256,
            "parent_run_path": str(PARENT_RUN.relative_to(ROOT)),
            "parent_run_sha256": PARENT_RUN_SHA256,
            "parent_manifest_path": str(PARENT_MANIFEST.relative_to(ROOT)),
            "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
            "direct_parent": f"{DIRECT_PARENT_EXPERIMENT}/{DIRECT_PARENT_ARM}",
            "direct_parent_manifest_sha256": DIRECT_PARENT_MANIFEST_SHA256,
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "model_policy": {
            "product_model": MODEL, "judge": None,
            "temperature": "provider default / omitted",
        },
        "contract": {
            "selected_cap": CAP, "internal_pool_cap": POOL_CAP,
            "max_feedback_steps": MAX_STEPS,
            "initial_state": "ADR-0064 baseline exact reuse",
            "gold_hidden_from_product": True,
        },
        "summary": _summary(rows, corpus), "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")


def _validate_resume(blob: dict) -> list[dict]:
    if blob.get("schema_version") != "proof-guided-span-golden-61-run-v1":
        raise ValueError("resume artifact schema mismatch")
    lineage = blob.get("source_lineage") or {}
    if (lineage.get("frozen_sha256") != PARENT_FROZEN_SHA256
            or lineage.get("parent_run_sha256") != PARENT_RUN_SHA256):
        raise ValueError("resume artifact parent lineage mismatch")
    if blob.get("runner_sha256") != _sha(Path(__file__).resolve()):
        raise ValueError("resume requires the exact same runner SHA")
    rows = list(blob.get("rows") or ())
    case_ids = [row.get("case_id") for row in rows]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("resume artifact has duplicate case IDs")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--validate-only", action="store_true",
        help="부모 artifact·좌표·ADR 계보만 검사하고 LLM은 호출하지 않는다")
    args = parser.parse_args()

    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    out = args.out or adr / "artifacts/run-001.json"
    out = out if out.is_absolute() else ROOT / out
    frozen, parent_run, _parent_manifest = _load_parent()
    _validate_adr_manifest(adr, require_frozen=not args.validate_only)

    from lawrag.core.rag import index as index_mod

    index = index_mod.current().scoped(None)
    corpus = _article_roots(index)
    parent_by_case = {row["case_id"]: row for row in parent_run["rows"]}
    prepared = {}
    for case in frozen["cases"]:
        parent = parent_by_case[case["id"]]["arms"]["baseline"]
        terms = _terms(parent.get("retrieval_meta") or {})
        initial = _initial_branches(index, parent, terms)
        observed = _observed_branches(index, parent, initial, terms)
        prepared[case["id"]] = (parent, terms, initial, observed)

    if args.validate_only:
        print(json.dumps({
            "valid": True,
            "cases": len(frozen["cases"]),
            "gold_total": 85, "gold_scorable": 83,
            "corpus_article_roots": corpus,
            "parent_frozen_sha256": PARENT_FROZEN_SHA256,
            "parent_run_sha256": PARENT_RUN_SHA256,
            "observed_total": sum(len(value[3]) for value in prepared.values()),
            "llm_calls": 0,
        }, ensure_ascii=False, indent=2))
        return 0

    from lawrag.core import llm as llm_mod

    llm_mod.load_env()
    if not llm_mod.available():
        raise RuntimeError("configured product LLM is unavailable")
    real = llm_mod.LLM(model=MODEL)
    if real.model != MODEL:
        raise RuntimeError(f"model policy mismatch: {real.model}")

    rows = []
    if args.resume and out.exists():
        rows = _validate_resume(json.loads(out.read_text(encoding="utf-8")))
    completed = {row["case_id"] for row in rows}
    for case in frozen["cases"]:
        if case["id"] in completed:
            continue
        parent, terms, initial, observed = prepared[case["id"]]
        baseline = _baseline_arm(index, case, parent, observed)
        input_state = {
            "question": case["question"],
            "initial": [_branch_dump(row) for row in initial],
            "observed": [_branch_dump(row) for row in observed],
            "terms": list(terms),
            "initial_meta": baseline["retrieval_meta"],
            "cap": CAP, "pool_cap": POOL_CAP, "max_steps": MAX_STEPS,
        }
        candidate = _candidate_arm(
            index, case, baseline, initial, observed, terms, real)
        row = {
            "number": case["number"], "case_id": case["id"],
            "suite": case["suite"], "question": case["question"],
            "initial_state_sha256": _json_sha(input_state),
            "input_state": input_state,
            "arms": {"baseline": baseline, "proof-guided-span": candidate},
            "paired": _paired(baseline, candidate),
        }
        question_path = adr / "실험" / (
            f"질문-{case['number']:03d}-{case['id']}.md")
        question_path.write_text(
            _question_markdown(case, row, input_state), encoding="utf-8")
        rows.append(row)
        rows.sort(key=lambda value: value["number"])
        _save(out, adr, frozen, rows, corpus)
        base_hits = sum(g["hit"] for g in baseline["gold_results"]
                        if g["scorable"])
        cand_hits = sum(g["hit"] for g in candidate["gold_results"]
                        if g["scorable"])
        pool_hits = sum(g["internal_pool_hit"] for g in candidate["gold_results"]
                        if g["scorable"])
        total = sum(g["scorable"] for g in baseline["gold_results"])
        print(
            f"[{case['number']:02d}/61] {case['id']} "
            f"baseline={base_hits}/{total} candidate={cand_hits}/{total} "
            f"pool={pool_hits}/{total} "
            f"calls={candidate['incremental_provider_usage']['calls']}",
            flush=True)
        if candidate["incremental_provider_usage"]["unrecovered_errors"]:
            raise RuntimeError(
                f"{case['id']}: provider/runtime error; aborting the run "
                "because the frozen success contract requires zero errors")
    summary = _summary(rows, corpus)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
