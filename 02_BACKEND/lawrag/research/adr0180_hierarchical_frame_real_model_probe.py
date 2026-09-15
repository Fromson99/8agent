"""Frozen, write-isolated real-model probe for ADR-0180."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from lawrag.core.llm import LLM
from lawrag.core.rag import frames
from lawrag.core.rag.index import DocView
from lawrag.platform.active_data import active_structure_path


MODEL = "claude-haiku-4-5-20251001"
CASES = (
    ("subitem", "7c2875fa7de1718f", 130),
    ("proviso", "00f033fddcef6be2", 2),
    ("longest", "51b4c50081ea6bb3", 1041),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _packed(value: str) -> str:
    return "".join(str(value or "").split())


def run(workspace: Path) -> dict:
    llm = LLM(model=MODEL)
    structure_root = active_structure_path(workspace)
    started = time.perf_counter()
    case_rows = []
    grounded = total_fields = valid_nodes = total_frames = 0
    child_observed = proviso_observed = True
    all_ok = True

    for case_id, doc_id, article_id in CASES:
        root = structure_root / doc_id
        meta_path, result_path = root / "meta.json", root / "result.json"
        view = DocView.build(doc_id, json.loads(meta_path.read_text("utf-8")),
                             json.loads(result_path.read_text("utf-8")))
        article = view.by_id[article_id]
        units = frames._units(view, article)
        chunks = frames._chunks(units)
        texts: dict[int, str] = {}
        for unit in units:
            texts[unit["id"]] = "\n".join(
                part for part in (texts.get(unit["id"], ""), unit["text"]) if part
            )
        log_start = len(llm.log)
        extracted, observation = frames.extract_jo(llm, view, article)
        exchanges = llm.log[log_start:]
        rows = []
        for frame in extracted:
            node = frame.get("node")
            node_text = texts.get(node, "")
            node_valid = node in texts
            valid_nodes += int(node_valid)
            field_checks = {}
            for field in ("actor", "act", "target", "object"):
                value = frame.get(field) or ""
                if not value:
                    continue
                total_fields += 1
                exact = _packed(value) in _packed(node_text)
                grounded += int(exact)
                field_checks[field] = exact
            rows.append({**frame, "coordinate": view.path(node),
                         "family": (view.by_id.get(node) or {}).get("family"),
                         "surface_grounding": field_checks})
        total_frames += len(rows)
        if case_id == "subitem":
            child_observed = any(
                row.get("family") in {"dot_number:1", "hangul_dot", "hangul_jamo", "paren_number:right"}
                for row in rows
            )
        if case_id == "proviso":
            proviso_observed = any(
                row.get("proviso") and "다만" in texts.get(row.get("node"), "") for row in rows
            )
        ok = not observation.get("error") and len(exchanges) <= len(chunks) + 1
        all_ok = all_ok and ok
        case_rows.append({
            "case_id": case_id,
            "doc_id": doc_id,
            "article_id": article_id,
            "document": view.name,
            "coordinate": view.path(article_id),
            "input_hashes": {"meta": _sha(meta_path), "result": _sha(result_path)},
            "unit_count": len(units),
            "chunk_count": len(chunks),
            "observation": observation,
            "frames": rows,
            "exchanges": [
                {**exchange.dump(), "parsed": exchange.parsed} for exchange in exchanges
            ],
            "result": "pass" if ok else "fail",
        })

    calls = len(llm.log)
    grounding_rate = grounded / total_fields if total_fields else 0.0
    models = sorted({exchange.model for exchange in llm.log})
    result = (
        all_ok
        and len(case_rows) == 3
        and valid_nodes == total_frames
        and grounding_rate >= 0.90
        and child_observed
        and proviso_observed
        and calls <= 8
        and models == [MODEL]
    )
    return {
        "schema_version": "hierarchical-frame-real-model-probe-v1",
        "model": MODEL,
        "cases": case_rows,
        "summary": {
            "cases_passed": sum(row["result"] == "pass" for row in case_rows),
            "cases_total": len(case_rows),
            "frames": total_frames,
            "valid_node_rate": valid_nodes / total_frames if total_frames else 0.0,
            "grounded_fields": grounded,
            "nonempty_fields": total_fields,
            "surface_grounding_rate": grounding_rate,
            "child_coordinate_observed": child_observed,
            "proviso_observed": proviso_observed,
            "models": models,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            **llm.totals(),
        },
        "external_calls": {"llm": calls, "embedding": 0, "network": calls},
        "operational_frame_writes": 0,
        "canonical_or_main_changes": 0,
        "result": "pass" if result else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root.resolve())
    output = args.output if args.output.is_absolute() else args.root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True, indent=2))
    print(result["result"])
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
