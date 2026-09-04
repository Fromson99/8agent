#!/usr/bin/env python3
"""ADR-0075: relation-only/unreachable gold까지의 최단 tool 경로를 감사한다."""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _key, _relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from scripts import rag_missing_gold_reachability_audit as previous
from scripts import rag_proof_guided_span_golden_61 as base


ADR_ID = "ADR-0075"
RUN_ID = "run-002"
ARMS = ("baseline", "multiplex-shortest-path")
TARGET_CLASSES = frozenset({"relation-only", "unreachable-current-indexes"})
EXPECTED_INSTANCES = 10
EXPECTED_CASE_IDS = (
    "cm-039", "cm-040", "cm-041", "cm-042",
    "cm-043", "cm-044", "cm-046", "cm-048",
)
TOOL_TOPK = 20
GLOBAL_SOURCE_BUDGET = 12
GLOBAL_INITIAL_SEED_BUDGET = 6
DOCUMENT_BUDGET = 32
MAX_RELATION_NODES = 50_000

PARENT_ADR = ROOT / "docs/adr/ADR-0074-missing-gold-reachability-audit"
PARENT_RUN = PARENT_ADR / "artifacts/run-001.json"
PARENT_MANIFEST = PARENT_ADR / "실험/manifest.json"
PARENT_RUN_SHA256 = "cb135c27b1e68d5a6ed4399fef27ccfffda0abbec723c8b7b2cbe71b75f1af77"
PARENT_MANIFEST_SHA256 = "5cb8fd12a8316faa0b23eae79536a91abb66a146f776165c73fb698b3cdb8c33"

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")
_GENERIC = frozenset({
    "업무", "문맥", "관련", "여부", "어떻게", "어느", "기관", "결정",
    "사항", "있는가", "하는가", "이상", "내용", "제정", "규정", "회사",
    "제1장", "제2장", "제3장", "제4장", "제1절", "제2절", "제3절",
})


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _root(index, coordinate: tuple[str, object]) -> tuple[str, object] | None:
    return previous._article_root(index, coordinate)


def _roots(index, values: Iterable[tuple[str, object]]) -> list[tuple[str, object]]:
    return previous._ranked_roots(index, values)


def _relation_adjacency(index) -> dict[tuple[str, object], list[tuple[tuple[str, object], dict]]]:
    from lawrag.core.rag import relations

    adjacency: dict[tuple[str, object], list[tuple[tuple[str, object], dict]]] = {}
    for edge in relations.build(index).sections:
        left = _root(index, (edge.src_doc, edge.src_node))
        right = _root(index, (edge.dst_doc, edge.dst_node))
        if left is None or right is None or left == right:
            continue
        surface = str(edge.props.get("surface") or edge.props.get("link")
                      or edge.props.get("term") or edge.label)
        adjacency.setdefault(left, []).append((right, {
            "operator": "RELATION", "relation": edge.kind,
            "direction": "out", "surface": surface,
        }))
        adjacency.setdefault(right, []).append((left, {
            "operator": "RELATION", "relation": edge.kind,
            "direction": "in", "surface": surface,
        }))
    for source, rows in adjacency.items():
        rows.sort(key=lambda row: (row[1]["relation"], row[1]["direction"],
                                   row[0][0], str(row[0][1])))
    return adjacency


def _structure_adjacency(index) -> dict[tuple[str, object], list[tuple[tuple[str, object], dict]]]:
    from lawrag.core.rag import legal_coordinates

    adjacency: dict[tuple[str, object], list[tuple[tuple[str, object], dict]]] = {}
    for doc_id, view in index.docs.items():
        articles = []
        for node in view.nodes:
            node_id = node.get("id")
            if (node.get("family") == "kr_article"
                    and legal_coordinates.article_root(view, node_id) == node_id):
                articles.append((doc_id, node_id))
        for left, right in zip(articles, articles[1:]):
            adjacency.setdefault(left, []).append((right, {
                "operator": "ADJACENT_ARTICLE", "direction": "next",
                "surface": "다음 조문",
            }))
            adjacency.setdefault(right, []).append((left, {
                "operator": "ADJACENT_ARTICLE", "direction": "previous",
                "surface": "이전 조문",
            }))
    return adjacency


def merge_adjacency(*graphs: dict) -> dict:
    out: dict = {}
    for graph in graphs:
        for source, rows in graph.items():
            out.setdefault(source, []).extend(rows)
    return out


def shortest_tree(adjacency: dict, seeds: Iterable[tuple[str, object]],
                  *, cap: int = MAX_RELATION_NODES) -> tuple[dict, dict, list]:
    normalized = list(dict.fromkeys(seeds))
    distance = {seed: 0 for seed in normalized}
    predecessor: dict = {}
    order = list(normalized)
    queue = deque(normalized)
    while queue and len(distance) < cap:
        source = queue.popleft()
        for target, edge in adjacency.get(source, ()):
            if target in distance:
                continue
            distance[target] = distance[source] + 1
            predecessor[target] = (source, edge)
            order.append(target)
            queue.append(target)
            if len(distance) >= cap:
                break
    return distance, predecessor, order


def reconstruct(predecessor: dict, target: tuple[str, object]) -> list[dict] | None:
    if target not in predecessor:
        return []
    rows = []
    current = target
    while current in predecessor:
        source, edge = predecessor[current]
        rows.append({"source": source, "target": current, **edge})
        current = source
    rows.reverse()
    return rows


def _path_from_source(predecessor: dict, source: tuple[str, object]) -> list[dict]:
    return reconstruct(predecessor, source) or []


def _reverse_relation_path(adjacency: dict, start: tuple[str, object],
                           gold: tuple[str, object]) -> list[dict] | None:
    distance, predecessor, _order = shortest_tree(adjacency, [start])
    if gold not in distance:
        return None
    return reconstruct(predecessor, gold)


def _public_coordinate(index, coordinate: tuple[str, object]) -> dict:
    doc_id, node = coordinate
    view = index.docs.get(doc_id)
    return {
        "doc_id": doc_id, "node": node,
        "doc": view.name if view else "",
        "path": view.path(node) if view else "",
    }


def _public_path(index, rows: list[dict] | None) -> list[dict] | None:
    if rows is None:
        return None
    return [{
        **{key: value for key, value in row.items()
           if key not in {"source", "target"}},
        "source": _public_coordinate(index, row["source"]),
        "target": _public_coordinate(index, row["target"]),
    } for row in rows]


def _path_surfaces(rows: list[dict]) -> list[str]:
    return list(dict.fromkeys(
        str(row.get("surface") or row.get("relation") or "").strip()
        for row in rows if str(row.get("surface") or row.get("relation") or "").strip()))


def build_dynamic_query(index, question: str, coordinate: tuple[str, object],
                        path: list[dict]) -> dict:
    """gold를 받지 않고 현재 좌표와 누적 간선만으로 다음 tool query를 만든다."""
    from lawrag.core.rag import exploration

    doc_id, node = coordinate
    view = index.docs[doc_id]
    heading = view.path(node) or view.name
    body = exploration.subtree_text(view, node, cap=700)
    question_tokens = [token for token in _TOKEN.findall(question)
                       if len(token) >= 2 and token not in _GENERIC]
    context_tokens = [token for token in _TOKEN.findall(heading)
                      if len(token) >= 2 and token not in _GENERIC
                      and not re.fullmatch(r"제?\d+(?:조|장|절|관)?", token)]
    relation_tokens = [token for value in _path_surfaces(path)
                       for token in _TOKEN.findall(value)
                       if len(token) >= 2 and token not in _GENERIC]
    terms = previous._dedupe_strings(
        [*question_tokens, *relation_tokens, *context_tokens], limit=10)
    phrase = "\n".join(filter(None, [
        question.strip(), f"현재 탐색 좌표: {heading}",
        f"지금까지 확인한 관계: {' / '.join(_path_surfaces(path)[-5:])}",
        f"현재 조문: {body[:500]}",
    ]))
    return {"terms": terms, "phrase": phrase, "source": _public_coordinate(index, coordinate)}


class ToolSearch:
    def __init__(self, index):
        from lawrag.core.rag import assertionfirst, conceptfirst, vector

        self.index = index
        self.cache: dict = {}
        self.assertions = assertionfirst.current(conceptfirst.load_registry())
        self.vector = vector.current()

    def _article_scope(self, doc_ids: frozenset[str]) -> frozenset[tuple[str, object]]:
        return frozenset(
            (doc_id, node.get("id")) for doc_id in doc_ids
            if doc_id in self.index.docs for node in self.index.docs[doc_id].nodes
            if node.get("family") == "kr_article")

    def search(self, query: dict, *, doc_ids: frozenset[str] | None) -> dict[str, list]:
        from lawrag.core.rag import assertionfirst, general_search, termexplore, vector

        scope_key = tuple(sorted(doc_ids)) if doc_ids is not None else None
        key = (tuple(query["terms"]), query["phrase"], scope_key)
        if key in self.cache:
            return self.cache[key]
        scoped = self.index.scoped(set(doc_ids)) if doc_ids is not None else self.index
        out: dict[str, list] = {}
        exact = termexplore.search_all(scoped, tuple(query["terms"]))
        out["exact"] = _roots(self.index, (hit.coordinate for hit in exact))[:TOOL_TOPK]
        keyword = general_search.search_keywords(
            scoped, query["terms"], question="", limit=TOOL_TOPK,
            per_document=TOOL_TOPK, extractor="adr0075-dynamic-path")
        out["keyword"] = _roots(
            self.index, ((hit.doc_id, hit.node) for hit in keyword.hits))[:TOOL_TOPK]
        scope = self._article_scope(doc_ids) if doc_ids is not None else None
        assertions = self.assertions.search(self.index, query["phrase"], scope=scope)
        out["assertion"] = _roots(
            self.index, (hit.coordinate for hit in assertions))[:TOOL_TOPK]
        if self.vector is None:
            out["vector"] = []
        else:
            qvec = vector._query_vector(query["phrase"])
            effective_docs = doc_ids if doc_ids is not None else self.index.scope
            raw = (self.vector.search(
                qvec, topk=TOOL_TOPK, minimum=vector.VECTOR_MIN,
                doc_ids=effective_docs) if qvec is not None else [])
            out["vector"] = _roots(
                self.index, ((doc, node) for doc, node, _score in raw))[:TOOL_TOPK]
        self.cache[key] = out
        return out


def _tool_edge(operator: str, channel: str, source: tuple[str, object],
               target: tuple[str, object], query: dict, rank: int) -> dict:
    return {
        "source": source, "target": target, "operator": operator,
        "channel": channel, "rank": rank,
        "query_terms": list(query["terms"]), "query": query["phrase"],
        "surface": f"{channel} rank {rank}",
    }


def _better(candidate: list[dict] | None, current: list[dict] | None) -> list[dict] | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    candidate_key = (len(candidate),
                     sum(row.get("operator", "").endswith("SEARCH") for row in candidate),
                     json.dumps(candidate, ensure_ascii=False, default=str))
    current_key = (len(current),
                   sum(row.get("operator", "").endswith("SEARCH") for row in current),
                   json.dumps(current, ensure_ascii=False, default=str))
    return candidate if candidate_key < current_key else current


def _source_states(index, order: list, distance: dict, predecessor: dict) -> list[tuple]:
    initial = [coordinate for coordinate in order if distance.get(coordinate) == 0]
    selected = [(coordinate, [])
                for coordinate in initial[:GLOBAL_INITIAL_SEED_BUDGET]]
    seen_docs = {coordinate[0] for coordinate, _path in selected}
    for coordinate in order:
        if distance.get(coordinate) == 0:
            continue
        doc_id = coordinate[0]
        if doc_id not in seen_docs:
            selected.append((coordinate, _path_from_source(predecessor, coordinate)))
            seen_docs.add(doc_id)
        if len(selected) >= GLOBAL_SOURCE_BUDGET:
            break
    return selected


def audit_instance(index, searcher: ToolSearch, relation_graph: dict,
                   structure_graph: dict, question: str,
                   seeds: list[tuple[str, object]], gold: tuple[str, object]) -> dict:
    started = time.perf_counter()
    relation_distance, relation_pred, relation_order = shortest_tree(relation_graph, seeds)
    combined = merge_adjacency(relation_graph, structure_graph)
    combined_distance, combined_pred, _combined_order = shortest_tree(combined, seeds)

    pure_relation = (reconstruct(relation_pred, gold)
                     if gold in relation_distance else None)
    relation_structure = (reconstruct(combined_pred, gold)
                          if gold in combined_distance else None)
    best_tool: list[dict] | None = None
    tool_calls = []
    global_landings: list[tuple[tuple[str, object], list[dict]]] = []

    source_states = _source_states(index, relation_order, relation_distance, relation_pred)
    for source, source_path in source_states:
        query = build_dynamic_query(index, question, source, source_path)
        result = searcher.search(query, doc_ids=None)
        tool_calls.append({
            "scope": "global", "source": _public_coordinate(index, source),
            "source_distance": len(source_path), "query": query,
            "counts": {key: len(value) for key, value in result.items()},
        })
        for channel, coordinates in result.items():
            for rank, landing in enumerate(coordinates, 1):
                prefix = [*source_path, _tool_edge(
                    "GLOBAL_SEARCH", channel, source, landing, query, rank)]
                global_landings.append((landing, prefix))
                if landing == gold:
                    best_tool = _better(prefix, best_tool)
                    continue
                tail = _reverse_relation_path(relation_graph, landing, gold)
                if tail is not None:
                    best_tool = _better([*prefix, *tail], best_tool)

    # 최초 관계 도달 순서의 서로 다른 문서와 global jump 도착 문서를 document menu로 연다.
    document_entries: list[tuple[tuple[str, object], list[dict]]] = []
    seen_docs = set()
    for coordinate in relation_order:
        if coordinate[0] in seen_docs:
            continue
        seen_docs.add(coordinate[0])
        document_entries.append((coordinate, _path_from_source(relation_pred, coordinate)))
        if len(document_entries) >= DOCUMENT_BUDGET:
            break
    for landing, prefix in global_landings:
        if landing[0] in seen_docs:
            continue
        seen_docs.add(landing[0])
        document_entries.append((landing, prefix))
        if len(document_entries) >= DOCUMENT_BUDGET:
            break

    gold_document_menu_rank = None
    for menu_rank, (entry, prefix) in enumerate(document_entries, 1):
        query = build_dynamic_query(index, question, entry, prefix)
        result = searcher.search(query, doc_ids=frozenset({entry[0]}))
        tool_calls.append({
            "scope": "document", "menu_rank": menu_rank,
            "source": _public_coordinate(index, entry),
            "source_distance": len(prefix), "query": query,
            "counts": {key: len(value) for key, value in result.items()},
        })
        if entry[0] == gold[0] and gold_document_menu_rank is None:
            gold_document_menu_rank = menu_rank
        for channel, coordinates in result.items():
            for rank, landing in enumerate(coordinates, 1):
                edge = _tool_edge(
                    "DOCUMENT_SEARCH", channel, entry, landing, query, rank)
                candidate = [*prefix, edge]
                if landing == gold:
                    best_tool = _better(candidate, best_tool)
                    continue
                tail = _reverse_relation_path(relation_graph, landing, gold)
                if tail is not None:
                    best_tool = _better([*candidate, *tail], best_tool)

    paths = {
        "pure_relation": _public_path(index, pure_relation),
        "relation_plus_adjacency": _public_path(index, relation_structure),
        "bounded_tool_shortest": _public_path(index, best_tool),
    }
    return {
        "paths": paths,
        "distances": {key: len(value) if value is not None else None
                      for key, value in paths.items()},
        "gold_document_menu_rank": gold_document_menu_rank,
        "source_states": len(source_states),
        "document_menu_count": len(document_entries),
        "tool_calls": tool_calls,
        "wall_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def _target_rows() -> tuple[dict, list[dict]]:
    if _sha(PARENT_RUN) != PARENT_RUN_SHA256:
        raise ValueError("ADR-0074 run hash drift")
    blob = json.loads(PARENT_RUN.read_text(encoding="utf-8"))
    rows = [row for row in blob.get("rows") or ()
            if row.get("classification") in TARGET_CLASSES]
    ids = tuple(dict.fromkeys(row["case_id"] for row in rows))
    if len(rows) != EXPECTED_INSTANCES or ids != EXPECTED_CASE_IDS:
        raise ValueError(f"target drift: instances={len(rows)} ids={ids}")
    return blob, rows


def _validate_manifest(adr: Path, *, require_frozen: bool) -> dict:
    manifest = json.loads((adr / "실험/manifest.json").read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID}")
    if _sha(PARENT_MANIFEST) != PARENT_MANIFEST_SHA256:
        raise ValueError("ADR-0074 parent manifest hash drift")
    parent = ((manifest.get("lineage") or {}).get("parents") or [{}])[0]
    if (parent.get("experiment_id") != "ADR-0074-experiment-v1"
            or parent.get("arm_id") != "reachability-matrix"
            or parent.get("manifest_sha256") != PARENT_MANIFEST_SHA256):
        raise ValueError("ADR-0075 parent lineage mismatch")
    if (manifest.get("llm_policy") or {}).get("llm_calls"):
        raise ValueError("ADR-0075 must use zero LLM calls")
    if tuple(row.get("case_id") for row in manifest.get("questions") or ()) != EXPECTED_CASE_IDS:
        raise ValueError("ADR-0075 question set mismatch")
    if require_frozen:
        if not manifest.get("design", {}).get("criteria_frozen_before_run"):
            raise ValueError("criteria not frozen")
        run = next((row for row in manifest.get("runs") or ()
                    if row.get("id") == RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned/running")
        if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
            raise ValueError("runner SHA not frozen")
    return manifest


def _summary(rows: list[dict]) -> dict:
    relation = sum(row["audit"]["distances"]["pure_relation"] is not None for row in rows)
    structured = sum(row["audit"]["distances"]["relation_plus_adjacency"] is not None
                     for row in rows)
    tool = sum(row["audit"]["distances"]["bounded_tool_shortest"] is not None
               for row in rows)
    errors = sum(bool(row.get("error")) for row in rows)
    criteria = {
        "all_10_instances_audited": len(rows) == EXPECTED_INSTANCES,
        "relation_shortest_recorded": all(
            "pure_relation" in row["audit"]["paths"] for row in rows),
        "relation_plus_adjacency_reaches_10": structured == EXPECTED_INSTANCES,
        "bounded_tool_path_reaches_10": tool == EXPECTED_INSTANCES,
        "gold_hidden_from_query_builder": True,
        "llm_calls_zero": True,
        "runtime_errors_zero": errors == 0,
    }
    return {
        "instances": len(rows), "cases": len({row["case_id"] for row in rows}),
        "pure_relation_reachable": relation,
        "relation_plus_adjacency_reachable": structured,
        "bounded_tool_reachable": tool,
        "pure_relation_distances": [
            row["audit"]["distances"]["pure_relation"] for row in rows],
        "bounded_tool_distances": [
            row["audit"]["distances"]["bounded_tool_shortest"] for row in rows],
        "runtime_errors": errors, "criteria": criteria,
        "target_pass": bool(rows) and all(criteria.values()),
    }


def _save(path: Path, rows: list[dict]) -> None:
    blob = {
        "schema_version": "shortest-tool-path-audit-v1",
        "adr_id": ADR_ID, "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lineage": {
            "parent_run": str(PARENT_RUN.relative_to(ROOT)),
            "parent_run_sha256": PARENT_RUN_SHA256,
            "parent_manifest": str(PARENT_MANIFEST.relative_to(ROOT)),
            "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "contract": {
            "target_classes": sorted(TARGET_CLASSES),
            "operator_cost": 1, "tool_topk": TOOL_TOPK,
            "global_source_budget": GLOBAL_SOURCE_BUDGET,
            "global_initial_seed_budget": GLOBAL_INITIAL_SEED_BUDGET,
            "document_budget": DOCUMENT_BUDGET,
            "relation_node_cap": MAX_RELATION_NODES,
            "gold_hidden_from_query_builder": True,
            "llm_calls": 0, "main_wiring": "unchanged",
        },
        "summary": _summary(rows), "rows": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _question_markdown(case_rows: list[dict]) -> str:
    case_id = case_rows[0]["case_id"]
    return f"""# ADR-0075 {case_id}

## 1. 실행 메타

- run: `{RUN_ID}`
- arms: `baseline`, `multiplex-shortest-path`
- 제품·중간·judge LLM: 없음
- operator cost: 모두 1

## 2. 사용자 질문 원문

{case_rows[0]['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```json
{json.dumps([row['gold'] for row in case_rows], ensure_ascii=False, indent=2)}
```

## 4. 제품 입력을 구성한 원값

질문, frozen baseline selected 좌표, 현재 좌표의 heading/body, 누적 relation surface만
query builder에 전달했다. gold는 전달하지 않았다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

해당 없음. LLM 호출 0회다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
[]
```

## 7. 채점 호출과 반복 판정

각 경로 생성이 끝난 뒤 gold article root와 exact coordinate match했다.

## 8. 사례 최종 판정

```json
{json.dumps([{'gold': row['gold'], 'source_class': row['source_class'],
              'distances': row['audit']['distances'],
              'gold_document_menu_rank': row['audit']['gold_document_menu_rank']}
             for row in case_rows], ensure_ascii=False, indent=2)}
```

전체 좌표·operator·query·rank는 `artifacts/run-001.json`에 보존한다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    out = args.out or adr / f"artifacts/{RUN_ID}.json"
    out = out if out.is_absolute() else ROOT / out
    _parent, targets = _target_rows()
    _validate_manifest(adr, require_frozen=not args.validate_only)

    from lawrag.core.rag import index as index_mod
    index = index_mod.current().scoped(None)
    if args.validate_only:
        print(json.dumps({
            "valid": True, "instances": len(targets),
            "cases": len(EXPECTED_CASE_IDS),
            "corpus_article_roots": base._article_roots(index),
            "llm_calls": 0, "gold_hidden_from_query_builder": True,
        }, ensure_ascii=False, indent=2))
        return 0

    frozen, baseline_run, _manifest = base._load_parent()
    frozen_by_case = {case["id"]: case for case in frozen["cases"]}
    baseline_by_case = {row["case_id"]: row for row in baseline_run["rows"]}
    relation_graph = _relation_adjacency(index)
    structure_graph = _structure_adjacency(index)
    searcher = ToolSearch(index)
    rows = []
    for pos, target in enumerate(targets, 1):
        case_id = target["case_id"]
        case = frozen_by_case[case_id]
        baseline = baseline_by_case[case_id]["arms"]["baseline"]
        seeds = _roots(index, ((str(row["doc_id"]), row["node"])
                              for row in baseline.get("selected") or ()))
        gold = _root(index, (str(target["gold"]["doc_id"]), target["gold"]["node"]))
        if not seeds or gold is None:
            raise ValueError(f"invalid seed/gold: {case_id}")
        error = ""
        try:
            audit = audit_instance(
                index, searcher, relation_graph, structure_graph,
                case["question"], seeds, gold)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            audit = {"paths": {}, "distances": {}, "tool_calls": [],
                     "gold_document_menu_rank": None, "wall_ms": 0.0}
        row = {
            "instance": pos, "case_id": case_id,
            "gold_ordinal": target["gold_ordinal"],
            "question": case["question"],
            "source_class": target["classification"],
            "gold": {**target["gold"], **_public_coordinate(index, gold)},
            "initial_seeds": [_public_coordinate(index, seed) for seed in seeds],
            "audit": audit, "error": error,
        }
        rows.append(row)
        _save(out, rows)
        print(f"[{pos:02d}/{EXPECTED_INSTANCES}] {case_id} "
              f"source={row['source_class']} distances={audit.get('distances')} "
              f"doc_menu={audit.get('gold_document_menu_rank')} error={error or '-'}",
              flush=True)
    for number, case_id in enumerate(EXPECTED_CASE_IDS, 1):
        case_rows = [row for row in rows if row["case_id"] == case_id]
        (adr / "실험" / f"질문-{number:03d}-{case_id}.md").write_text(
            _question_markdown(case_rows), encoding="utf-8")
    _save(out, rows)
    print(json.dumps(_summary(rows), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
