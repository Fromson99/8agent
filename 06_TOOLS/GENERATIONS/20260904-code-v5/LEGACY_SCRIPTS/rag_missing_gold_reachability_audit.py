#!/usr/bin/env python3
"""ADR-0074: frozen baseline에서 누락된 gold의 채널별 도달가능성을 감사한다.

gold 좌표는 검색 질의 생성에 전달하지 않는다. 질문 원문, ADR-0064 동결 검색어,
ADR-0067/0068이 이미 생성한 검색 trace만으로 각 채널의 순위를 먼저 만든 뒤, 그
결과에 gold 좌표를 사후 대조한다. 제품 LLM 호출과 제품 배선 변경은 없다.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Iterable


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

from scripts import rag_proof_guided_span_golden_61 as base


ADR_ID = "ADR-0074"
RUN_ID = "run-001"
ARMS = ("baseline-miss", "reachability-matrix")
MAX_RANK = 500
RELATION_DEPTH = 3
RELATION_VISITED_CAP = 50_000
EXPECTED_CASE_IDS = (
    "cm-004", "cm-011", "cm-016", "cm-031", "cm-039", "cm-040",
    "cm-041", "cm-042", "cm-043", "cm-044", "cm-046", "cm-048",
    "cm-050", "fsc-hard-003", "fsc-hard-004", "fsc-hard-009",
)
EXPECTED_MISSING_GOLD = 19

ADR0068_RUN = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0068-recall-first-orthogonal-union/artifacts/run-001.json")
ADR0068_RUN_SHA256 = (
    "d751f88febc98a1537083dd5a4e93ebc2cfc40b40137a451fa359badc648d38b")
ADR0068_MANIFEST = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0068-recall-first-orthogonal-union/실험/manifest.json")
ADR0068_MANIFEST_SHA256 = (
    "889255d1753ab9e1b9817fbcf5e7bc2af8eac29c4e7ab0019908ef1dda7d0779")
ADR0067_RUN = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0067-proof-boundary-feedback/artifacts/run-001.json")

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")
_SPACE = re.compile(r"\s+")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str).encode("utf-8")).hexdigest()


def _clean(value: object) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def _dedupe_strings(values: Iterable[object], *, limit: int = 24) -> list[str]:
    out, seen = [], set()
    for raw in values:
        value = _clean(raw)
        key = value.casefold()
        if len(value) < 2 or key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def _fallback_terms(question: str) -> list[str]:
    stop = {"어떻게", "무엇", "관련", "여부", "있는지", "알려줘", "질의드립니다"}
    return _dedupe_strings(
        token for token in _TOKEN.findall(question)
        if len(token) >= 2 and token not in stop)


def _planner_output(arm: dict) -> dict:
    for call in arm.get("llm_calls") or ():
        if call.get("kind") == "rag.legalclosure.recall_first_planner":
            return dict(call.get("structured_output") or {})
    return {}


def build_query_variants(question: str, frozen_terms: Iterable[str],
                         adr0068_arm: dict, adr0067_arm: dict) -> dict:
    """gold를 인자로 받지 않는 폐쇄형 query builder."""
    planner = _planner_output(adr0068_arm)
    action68 = list((adr0068_arm.get("retrieval_meta") or {}).get("actions") or ())
    action67 = list((adr0067_arm.get("retrieval_meta") or {}).get("actions") or ())

    phrase_rows = [("question", question)]
    for key in ("issue", "exact_query", "assertion_query", "vector_query"):
        if planner.get(key):
            phrase_rows.append((f"adr0068_{key}", planner[key]))
    for pos, action in enumerate(action67, 1):
        if action.get("query"):
            phrase_rows.append((f"adr0067_action_{pos}_{action.get('kind')}",
                                action["query"]))
    for pos, action in enumerate(action68, 1):
        if action.get("query"):
            phrase_rows.append((f"adr0068_action_{pos}_{action.get('kind')}",
                                action["query"]))

    phrase_seen, phrases = set(), []
    for label, value in phrase_rows:
        value = _clean(value)
        if len(value) < 2 or value.casefold() in phrase_seen:
            continue
        phrase_seen.add(value.casefold())
        phrases.append({"id": label, "query": value})

    term_rows = [
        ("question_tokens", _fallback_terms(question)),
        ("frozen_terms", list(frozen_terms)),
        ("adr0068_operation_terms", planner.get("operation_terms") or ()),
        ("adr0068_keywords", planner.get("keywords") or ()),
    ]
    for pos, action in enumerate(action67, 1):
        term_rows.append((f"adr0067_action_{pos}_{action.get('kind')}",
                          action.get("keywords") or ()))
    for pos, action in enumerate(action68, 1):
        term_rows.append((f"adr0068_action_{pos}_{action.get('kind')}",
                          action.get("keywords") or ()))

    terms, term_seen = [], set()
    for label, values in term_rows:
        clean = _dedupe_strings(values, limit=12)
        key = tuple(value.casefold() for value in clean)
        if not clean or key in term_seen:
            continue
        term_seen.add(key)
        terms.append({"id": label, "terms": clean})
    return {"phrases": phrases, "term_sets": terms}


def _article_root(index, coordinate: tuple[str, object]) -> tuple[str, object] | None:
    from lawrag.core.rag import legal_coordinates

    doc_id, node = coordinate
    view = index.docs.get(doc_id)
    if view is None or node not in view.by_id:
        return None
    root = legal_coordinates.article_root(view, node)
    return (doc_id, root) if root in view.by_id else None


def _ranked_roots(index, coordinates: Iterable[tuple[str, object]],
                  *, limit: int | None = None) -> list[tuple[str, object]]:
    out, seen = [], set()
    for coordinate in coordinates:
        root = _article_root(index, coordinate)
        if root is None or root in seen:
            continue
        seen.add(root)
        out.append(root)
        if limit is not None and len(out) >= limit:
            break
    return out


def rank_coordinate(ranked: Iterable[tuple[str, object]],
                    gold: tuple[str, object]) -> int | None:
    for rank, coordinate in enumerate(ranked, 1):
        if coordinate == gold:
            return rank
    return None


def rank_document(ranked: Iterable[tuple[str, object]], doc_id: str) -> int | None:
    seen = set()
    for coordinate in ranked:
        current = coordinate[0]
        if current in seen:
            continue
        seen.add(current)
        if current == doc_id:
            return len(seen)
    return None


def _family_name(name: str) -> str:
    value = re.sub(r"[\s·ㆍ]+", "", name or "")
    value = re.split(r"[_\[(]", value, maxsplit=1)[0]
    for suffix in ("시행규칙", "시행령", "시행세칙"):
        if value.endswith(suffix) and len(value) > len(suffix) + 2:
            return value[:-len(suffix)]
    return value


def rank_document_family(index, ranked: Iterable[tuple[str, object]],
                         gold_doc_id: str) -> int | None:
    gold_view = index.docs.get(gold_doc_id)
    if gold_view is None:
        return None
    target = _family_name(gold_view.name)
    seen = set()
    for coordinate in ranked:
        doc_id = coordinate[0]
        if doc_id in seen or doc_id not in index.docs:
            continue
        seen.add(doc_id)
        if _family_name(index.docs[doc_id].name) == target:
            return len(seen)
    return None


def _rank_record(index, ranked: list[tuple[str, object]],
                 gold: tuple[str, object], *, available: bool = True,
                 error: str = "") -> dict:
    return {
        "available": available,
        "result_count": len(ranked),
        "article_rank": rank_coordinate(ranked, gold),
        "document_rank": rank_document(ranked, gold[0]),
        "document_family_rank": rank_document_family(index, ranked, gold[0]),
        "error": error,
    }


def _exact_matrix(index, variants: dict, gold: tuple[str, object], cache: dict) -> list[dict]:
    from lawrag.core.rag import termexplore

    out = []
    for variant in variants["term_sets"]:
        terms = tuple(variant["terms"])
        key = ("exact", terms)
        started = time.perf_counter()
        error = ""
        try:
            if key not in cache:
                cache[key] = _ranked_roots(
                    index, (hit.coordinate for hit in termexplore.search_all(index, terms)))
            ranked = cache[key]
        except Exception as exc:
            ranked, error = [], f"{type(exc).__name__}: {exc}"
        out.append({"variant": variant, **_rank_record(
            index, ranked, gold, available=not error, error=error),
                    "wall_ms": round((time.perf_counter() - started) * 1000, 3)})
    return out


def _keyword_matrix(index, variants: dict, gold: tuple[str, object], cache: dict) -> list[dict]:
    from lawrag.core.rag import general_search

    out = []
    for variant in variants["term_sets"]:
        terms = tuple(variant["terms"])
        key = ("keyword", terms)
        started = time.perf_counter()
        error = ""
        try:
            if key not in cache:
                result = general_search.search_keywords(
                    index, terms, question="", limit=MAX_RANK,
                    per_document=50, extractor="adr0074-frozen-trace")
                cache[key] = _ranked_roots(
                    index, ((hit.doc_id, hit.node) for hit in result.hits),
                    limit=MAX_RANK)
            ranked = cache[key]
        except Exception as exc:
            ranked, error = [], f"{type(exc).__name__}: {exc}"
        out.append({"variant": variant, **_rank_record(
            index, ranked, gold, available=not error, error=error),
                    "wall_ms": round((time.perf_counter() - started) * 1000, 3)})
    return out


def _assertion_matrix(index, variants: dict, gold: tuple[str, object], cache: dict) -> list[dict]:
    from lawrag.core.rag import assertionfirst, conceptfirst

    out, assertion_index, setup_error = [], None, ""
    try:
        assertion_index = assertionfirst.current(conceptfirst.load_registry())
    except Exception as exc:
        setup_error = f"{type(exc).__name__}: {exc}"
    for variant in variants["phrases"]:
        query = variant["query"]
        key = ("assertion", query)
        started = time.perf_counter()
        error = setup_error
        try:
            if assertion_index is not None and key not in cache:
                cache[key] = _ranked_roots(
                    index, (hit.coordinate for hit in assertion_index.search(index, query)),
                    limit=MAX_RANK)
            ranked = cache.get(key, [])
        except Exception as exc:
            ranked, error = [], f"{type(exc).__name__}: {exc}"
        out.append({"variant": variant, **_rank_record(
            index, ranked, gold, available=not error, error=error),
                    "wall_ms": round((time.perf_counter() - started) * 1000, 3)})
    return out


def _vector_matrix(index, variants: dict, gold: tuple[str, object], cache: dict) -> list[dict]:
    from lawrag.core.rag import vector

    out, vector_index, setup_error = [], None, ""
    try:
        vector_index = vector.current()
        if vector_index is None:
            setup_error = "vector index unavailable"
    except Exception as exc:
        setup_error = f"{type(exc).__name__}: {exc}"
    for variant in variants["phrases"]:
        query = variant["query"]
        started = time.perf_counter()
        error = setup_error
        raw_ranked, product_ranked = [], []
        try:
            if vector_index is not None:
                raw_key, product_key = ("vector-raw", query), ("vector-product", query)
                if raw_key not in cache or product_key not in cache:
                    qvec = vector._query_vector(query)
                    if qvec is None:
                        raise RuntimeError("query embedding unavailable")
                    raw = vector_index.search(
                        qvec, topk=MAX_RANK, minimum=-1.0, doc_ids=index.scope)
                    product = [row for row in raw if row[2] >= vector.VECTOR_MIN]
                    cache[raw_key] = _ranked_roots(
                        index, ((d, n) for d, n, _score in raw), limit=MAX_RANK)
                    cache[product_key] = _ranked_roots(
                        index, ((d, n) for d, n, _score in product), limit=MAX_RANK)
                raw_ranked, product_ranked = cache[raw_key], cache[product_key]
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        out.append({
            "variant": variant,
            "product_threshold": _rank_record(
                index, product_ranked, gold, available=not error, error=error),
            "unthresholded": _rank_record(
                index, raw_ranked, gold, available=not error, error=error),
            "wall_ms": round((time.perf_counter() - started) * 1000, 3),
        })
    return out


def _relation_bfs(index, seeds: Iterable[tuple[str, object]], *, policy: bool) -> dict:
    from lawrag.core.rag import relation_navigation, relations

    normalized = _ranked_roots(index, seeds)
    visited, frontier = set(normalized), list(normalized)
    discovered, depth_by_coordinate, kinds_by_coordinate = [], {}, {}
    truncated, error = False, ""
    try:
        for depth in range(1, RELATION_DEPTH + 1):
            next_frontier = []
            if policy:
                hops, _meta = relation_navigation.neighbors(
                    index, frontier, direction="both", cap=RELATION_VISITED_CAP,
                    exclude=visited)
                stream = [(hop.target, hop.graph_kind) for hop in hops]
            else:
                stream = []
                for coordinate in frontier:
                    outgoing, incoming = relations.incident(index, *coordinate)
                    stream.extend((((edge.dst_doc, edge.dst_node), edge.kind)
                                   for edge in outgoing))
                    stream.extend((((edge.src_doc, edge.src_node), edge.kind)
                                   for edge in incoming))
            for target, kind in stream:
                root = _article_root(index, target)
                if root is None or root in visited:
                    continue
                visited.add(root)
                discovered.append(root)
                depth_by_coordinate[root] = depth
                kinds_by_coordinate[root] = kind
                next_frontier.append(root)
                if len(visited) >= RELATION_VISITED_CAP:
                    truncated = True
                    break
            frontier = next_frontier
            if truncated or not frontier:
                break
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {
        "seed_count": len(normalized), "visited_count": len(visited),
        "discovered": discovered, "depth_by_coordinate": depth_by_coordinate,
        "kinds_by_coordinate": kinds_by_coordinate,
        "truncated": truncated, "error": error,
    }


def _relation_record(index, state: dict, gold: tuple[str, object]) -> dict:
    discovered = state["discovered"]
    return {
        "available": not state["error"], "seed_count": state["seed_count"],
        "visited_count": state["visited_count"],
        "article_rank": rank_coordinate(discovered, gold),
        "depth": state["depth_by_coordinate"].get(gold),
        "arriving_relation": state["kinds_by_coordinate"].get(gold),
        "document_rank": rank_document(discovered, gold[0]),
        "document_family_rank": rank_document_family(index, discovered, gold[0]),
        "truncated": state["truncated"], "error": state["error"],
    }


def _min_rank(matrix: dict) -> int | None:
    ranks = []
    for channel in ("exact", "keyword", "assertion"):
        ranks.extend(row.get("article_rank") for row in matrix.get(channel, ()))
    for row in matrix.get("vector", ()):
        ranks.append((row.get("product_threshold") or {}).get("article_rank"))
        ranks.append((row.get("unthresholded") or {}).get("article_rank"))
    return min((rank for rank in ranks if rank is not None), default=None)


def classify_reachability(matrix: dict) -> str:
    best = _min_rank(matrix)
    relation = matrix.get("relations") or {}
    policy_depth = (relation.get("selected_seed_policy") or {}).get("depth")
    observed_depth = (relation.get("observed_seed_raw") or {}).get("depth")
    document_ranks = []
    for channel in ("exact", "keyword", "assertion"):
        document_ranks.extend(row.get("document_rank") for row in matrix.get(channel, ()))
    for row in matrix.get("vector", ()):
        document_ranks.extend([
            (row.get("product_threshold") or {}).get("document_rank"),
            (row.get("unthresholded") or {}).get("document_rank")])
    best_document = min((rank for rank in document_ranks if rank is not None), default=None)
    if best is not None and best <= 8:
        return "direct-top8"
    if best is not None and best <= 20:
        return "direct-top20-cap"
    if best is not None and best <= 50:
        return "direct-rank-21-50"
    if best is not None and best <= MAX_RANK:
        return "direct-rank-51-500"
    if policy_depth is not None or observed_depth is not None:
        return "relation-only"
    if best_document is not None:
        return "document-reachable-article-miss"
    return "unreachable-current-indexes"


def _best(matrix: dict) -> dict:
    by_channel = {}
    for channel in ("exact", "keyword", "assertion"):
        ranks = [row.get("article_rank") for row in matrix.get(channel, ())]
        by_channel[channel] = min((x for x in ranks if x is not None), default=None)
    for key, field in (("vector_product", "product_threshold"),
                       ("vector_raw", "unthresholded")):
        ranks = [(row.get(field) or {}).get("article_rank")
                 for row in matrix.get("vector", ())]
        by_channel[key] = min((x for x in ranks if x is not None), default=None)
    relation = matrix.get("relations") or {}
    by_channel["relation_policy_depth"] = (
        relation.get("selected_seed_policy") or {}).get("depth")
    by_channel["relation_raw_depth"] = (
        relation.get("observed_seed_raw") or {}).get("depth")
    return by_channel


def _reduce_run(path: Path, *, arm: str) -> dict[str, dict]:
    blob = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for row in blob.get("rows") or ():
        selected = row.get("arms", {}).get(arm, {})
        out[row["case_id"]] = {
            "llm_calls": selected.get("llm_calls") or [],
            "retrieval_meta": selected.get("retrieval_meta") or {},
        }
    return out


def _missing_instances(frozen: dict, parent_run: dict) -> list[tuple[dict, dict]]:
    by_case = {row["case_id"]: row for row in parent_run["rows"]}
    out = []
    for case in frozen["cases"]:
        baseline = by_case[case["id"]]["arms"]["baseline"]
        for gold in baseline.get("gold_results") or ():
            if gold.get("scorable") and not gold.get("hit"):
                out.append((case, gold))
    ids = tuple(dict.fromkeys(case["id"] for case, _gold in out))
    if len(out) != EXPECTED_MISSING_GOLD or ids != EXPECTED_CASE_IDS:
        raise ValueError(f"baseline-miss set drift: gold={len(out)} ids={ids}")
    return out


def _validate_manifest(adr: Path, *, require_frozen: bool) -> dict:
    manifest_path = adr / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID}")
    if _sha(ADR0068_MANIFEST) != ADR0068_MANIFEST_SHA256:
        raise ValueError("ADR-0068 manifest hash drift")
    parent = ((manifest.get("lineage") or {}).get("parents") or [{}])[0]
    if (parent.get("manifest_sha256") != ADR0068_MANIFEST_SHA256
            or parent.get("experiment_id") != "ADR-0068-experiment-v1"):
        raise ValueError("ADR-0074 parent lineage mismatch")
    if {row.get("id") for row in manifest.get("design", {}).get("arms", ())} != set(ARMS):
        raise ValueError("ADR-0074 arm mismatch")
    if (manifest.get("llm_policy") or {}).get("llm_calls"):
        raise ValueError("ADR-0074 must declare zero LLM calls")
    if tuple(row.get("case_id") for row in manifest.get("questions") or ()) != EXPECTED_CASE_IDS:
        raise ValueError("ADR-0074 question set mismatch")
    if require_frozen:
        if not manifest.get("design", {}).get("criteria_frozen_before_run"):
            raise ValueError("criteria must be frozen before audit")
        run = next((x for x in manifest.get("runs") or () if x.get("id") == RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned or running")
        if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
            raise ValueError("runner SHA is not frozen")
    return manifest


def _summarize(rows: list[dict]) -> dict:
    classes: dict[str, int] = {}
    best_by_channel: dict[str, int] = {}
    ranks = []
    for row in rows:
        classes[row["classification"]] = classes.get(row["classification"], 0) + 1
        for channel, rank in row["best"].items():
            if rank is not None:
                best_by_channel[channel] = best_by_channel.get(channel, 0) + 1
        direct = _min_rank(row["matrix"])
        if direct is not None:
            ranks.append(direct)
    at_k = {str(k): sum((_min_rank(row["matrix"]) or MAX_RANK + 1) <= k
                         for row in rows) for k in (8, 20, 50, 200, 500)}
    relation_any = sum(
        row["best"].get("relation_policy_depth") is not None
        or row["best"].get("relation_raw_depth") is not None for row in rows)
    errors = sum(
        bool(item.get("error"))
        for row in rows
        for channel in ("exact", "keyword", "assertion")
        for item in row["matrix"].get(channel, ()))
    errors += sum(
        bool((item.get(field) or {}).get("error"))
        for row in rows for item in row["matrix"].get("vector", ())
        for field in ("product_threshold", "unthresholded"))
    errors += sum(
        bool(item.get("error")) for row in rows
        for item in (row["matrix"].get("relations") or {}).values())
    criteria = {
        "all_19_missing_gold_instances_audited": len(rows) == EXPECTED_MISSING_GOLD,
        "all_channels_recorded": all(
            all(key in row["matrix"] for key in
                ("exact", "keyword", "assertion", "vector", "relations"))
            for row in rows),
        "all_instances_classified": len(classes) > 0 and sum(classes.values()) == len(rows),
        "gold_hidden_from_query_builder": True,
        "llm_calls_zero": True,
        "channel_errors_zero": errors == 0,
    }
    return {
        "missing_gold_instances": len(rows),
        "cases": len({row["case_id"] for row in rows}),
        "classification_counts": classes,
        "direct_reachable_at_k": at_k,
        "reachable_by_channel": best_by_channel,
        "relation_reachable": relation_any,
        "best_direct_rank_p50": statistics.median(ranks) if ranks else None,
        "channel_error_count": errors,
        "criteria": criteria,
        "target_pass": bool(rows) and all(criteria.values()),
    }


def _save(path: Path, rows: list[dict], corpus: int, trace67_sha: str) -> None:
    artifact = {
        "schema_version": "missing-gold-reachability-audit-v1",
        "adr_id": ADR_ID, "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lineage": {
            "frozen_path": str(base.PARENT_FROZEN.relative_to(ROOT)),
            "frozen_sha256": base.PARENT_FROZEN_SHA256,
            "baseline_path": str(base.PARENT_RUN.relative_to(ROOT)),
            "baseline_sha256": base.PARENT_RUN_SHA256,
            "adr0068_run_path": str(ADR0068_RUN.relative_to(ROOT)),
            "adr0068_run_sha256": ADR0068_RUN_SHA256,
            "adr0067_run_path": str(ADR0067_RUN.relative_to(ROOT)),
            "adr0067_run_sha256": trace67_sha,
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "contract": {
            "gold_hidden_from_query_builder": True,
            "gold_use": "post-retrieval rank matching and sample selection only",
            "query_sources": ["question", "ADR-0064 frozen terms",
                              "ADR-0067 trace", "ADR-0068 trace"],
            "max_direct_rank": MAX_RANK,
            "relation_depth": RELATION_DEPTH,
            "relation_visited_cap": RELATION_VISITED_CAP,
            "llm_calls": 0, "main_wiring": "unchanged",
        },
        "corpus_article_roots": corpus,
        "summary": _summarize(rows), "rows": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _question_markdown(row: dict) -> str:
    return f"""# ADR-0074 {row['case_id']} / 누락 정답 {row['gold_ordinal']}

## 질문

{row['question']}

## 감사 계약

- gold는 아래 순위 대조와 표본 선택에만 사용했다.
- query builder 입력에는 질문, frozen terms, ADR-0067/0068 기존 trace만 전달했다.
- 제품 LLM 호출: 0회
- 메인 배선 변경: 없음

## 채점 전용 gold

```json
{json.dumps(row['gold'], ensure_ascii=False, indent=2)}
```

## gold 비공개 질의 변형

```json
{json.dumps(row['query_variants'], ensure_ascii=False, indent=2)}
```

## 채널별 최선 결과

```json
{json.dumps({'classification': row['classification'], 'best': row['best'],
             'relations': row['matrix']['relations']},
            ensure_ascii=False, indent=2)}
```

전체 variant별 rank는 `artifacts/run-001.json`의 같은 instance에 보존한다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    out = args.out or adr / "artifacts/run-001.json"
    out = out if out.is_absolute() else ROOT / out

    if _sha(ADR0068_RUN) != ADR0068_RUN_SHA256:
        raise ValueError("ADR-0068 run artifact hash drift")
    frozen, parent_run, _manifest = base._load_parent()
    misses = _missing_instances(frozen, parent_run)
    _validate_manifest(adr, require_frozen=not args.validate_only)

    from lawrag.core.rag import index as index_mod
    index = index_mod.current().scoped(None)
    corpus = base._article_roots(index)
    if args.validate_only:
        print(json.dumps({
            "valid": True, "cases": len(EXPECTED_CASE_IDS),
            "missing_gold_instances": len(misses),
            "corpus_article_roots": corpus, "llm_calls": 0,
            "gold_hidden_from_query_builder": True,
        }, ensure_ascii=False, indent=2))
        return 0

    trace67_sha = _sha(ADR0067_RUN)
    trace68 = _reduce_run(ADR0068_RUN, arm="recall-first-union")
    trace67 = _reduce_run(ADR0067_RUN, arm="proof-boundary-feedback")
    baseline_by_case = {row["case_id"]: row for row in parent_run["rows"]}
    cache: dict = {}
    relation_cache: dict = {}
    rows = []
    for pos, (case, gold_row) in enumerate(misses, 1):
        case_id = case["id"]
        baseline = baseline_by_case[case_id]["arms"]["baseline"]
        frozen_terms = base._terms(baseline.get("retrieval_meta") or {})
        variants = build_query_variants(
            case["question"], frozen_terms, trace68[case_id], trace67[case_id])
        gold = _article_root(index, (str(gold_row["doc_id"]), gold_row["node"]))
        if gold is None:
            raise ValueError(f"gold coordinate missing from index: {case_id}")

        selected = [(str(row["doc_id"]), row["node"])
                    for row in baseline.get("selected") or ()]
        observed = [(str(row["doc_id"]), row["node"])
                    for row in baseline.get("internal_pool") or ()]
        # ADR-0064 baseline의 internal_pool이 비어 있는 구버전도 전체 trace로 복원한다.
        if not observed:
            terms = base._terms(baseline.get("retrieval_meta") or {})
            initial = base._initial_branches(index, baseline, terms)
            observed = [row.coordinate for row in
                        base._observed_branches(index, baseline, initial, terms)]
        relation_key = (case_id, tuple(_ranked_roots(index, selected)),
                        tuple(_ranked_roots(index, observed)))
        if relation_key not in relation_cache:
            relation_cache[relation_key] = {
                "selected_seed_policy": _relation_bfs(index, selected, policy=True),
                "selected_seed_raw": _relation_bfs(index, selected, policy=False),
                "observed_seed_policy": _relation_bfs(index, observed, policy=True),
                "observed_seed_raw": _relation_bfs(index, observed, policy=False),
            }
        relation_states = relation_cache[relation_key]
        matrix = {
            "exact": _exact_matrix(index, variants, gold, cache),
            "keyword": _keyword_matrix(index, variants, gold, cache),
            "assertion": _assertion_matrix(index, variants, gold, cache),
            "vector": _vector_matrix(index, variants, gold, cache),
            "relations": {name: _relation_record(index, state, gold)
                          for name, state in relation_states.items()},
        }
        same_case_count = sum(old["case_id"] == case_id for old in rows) + 1
        row = {
            "instance": pos, "case_id": case_id,
            "gold_ordinal": same_case_count, "suite": case["suite"],
            "question": case["question"],
            "gold": {key: gold_row.get(key) for key in
                     ("doc_id", "node", "doc", "path", "corpus_status")},
            "query_variants": variants,
            "query_input_sha256": _json_sha({
                "question": case["question"], "frozen_terms": list(frozen_terms),
                "adr0068_trace": trace68[case_id], "adr0067_trace": trace67[case_id]}),
            "matrix": matrix, "best": _best(matrix),
        }
        row["classification"] = classify_reachability(matrix)
        rows.append(row)
        _save(out, rows, corpus, trace67_sha)
        print(f"[{pos:02d}/{EXPECTED_MISSING_GOLD}] {case_id} gold={gold} "
              f"class={row['classification']} best={row['best']}", flush=True)

    # 질문 파일은 case당 하나이며, 복수 gold는 한 파일에 함께 요약한다.
    for number, case_id in enumerate(EXPECTED_CASE_IDS, 1):
        case_rows = [row for row in rows if row["case_id"] == case_id]
        text = "\n\n---\n\n".join(_question_markdown(row) for row in case_rows)
        (adr / "실험" / f"질문-{number:03d}-{case_id}.md").write_text(
            text + "\n", encoding="utf-8")
    _save(out, rows, corpus, trace67_sha)
    print(json.dumps(_summarize(rows), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
