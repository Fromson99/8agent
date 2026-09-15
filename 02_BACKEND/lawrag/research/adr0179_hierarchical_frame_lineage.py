"""Zero-call corpus and fake-LLM validation for ADR-0179 rev-001."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from lawrag.core.rag.index import DocView
from lawrag.platform.active_data import active_structure_path


WORKSPACE = Path(__file__).resolve().parents[3]
CANDIDATE = (
    WORKSPACE
    / "02_BACKEND/lawrag/research/candidates/adr_0179/clause-unit-frame-contract"
    / "revisions/rev-001/snapshot/02_BACKEND/lawrag/core/rag/frames.py"
)


def _load_candidate():
    spec = importlib.util.spec_from_file_location("adr0179_candidate_frames", CANDIDATE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load candidate: {CANDIDATE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _nested_view() -> tuple[DocView, dict]:
    nodes = [
        {"id": 1, "parent": None, "family": "kr_article", "surface": "제1조", "level": 0, "span": [0, 5]},
        {"id": 2, "parent": 1, "family": "circled", "surface": "①", "level": 1, "span": [1, 5]},
        {"id": 3, "parent": 2, "family": "dot_number:1", "surface": "1.", "level": 2, "span": [2, 4]},
        {"id": 4, "parent": 3, "family": "hangul_jamo", "surface": "가.", "level": 3, "span": [3, 4]},
    ]
    blocks = [
        {"idx": 0, "text": "article"},
        {"idx": 1, "text": "paragraph"},
        {"idx": 2, "text": "item"},
        {"idx": 3, "text": "subitem"},
        {"idx": 4, "text": "paragraph tail"},
    ]
    return DocView.build("probe", {"name": "probe"}, {"nodes": nodes, "blocks": blocks}, apply_structure_fixes=False), nodes[0]


class _FakeLLM:
    log: list = []

    def structured(self, *_args, **_kwargs):
        def row(node: int) -> dict:
            return {"node": node, "actor": "actor", "act": "act", "target": "",
                    "object": "object", "mode": "의무", "function": "기타",
                    "proviso": False}
        return {"frames": [row(4), row(999)]}


def main() -> int:
    frames = _load_candidate()
    view, article = _nested_view()
    units = frames._units(view, article)
    assert [row["id"] for row in units] == [1, 2, 3, 4, 2]
    assert [block for row in units for block in row["blocks"]] == [0, 1, 2, 3, 4]
    split = frames._chunks(units, cap=8)
    assert len(split) > 1
    assert "".join(row["text"] for chunk in split for row in chunk) == "".join(row["text"] for row in units)
    extracted, meta = frames.extract_jo(_FakeLLM(), view, article)
    assert [row["node"] for row in extracted] == [4]
    assert meta["dropped"] == 1

    corpus = active_structure_path(WORKSPACE)
    documents = articles = chunks = units_total = loss = invalid = 0
    for directory in sorted(path for path in corpus.iterdir() if path.is_dir()):
        meta_path, result_path = directory / "meta.json", directory / "result.json"
        if not meta_path.is_file() or not result_path.is_file():
            continue
        try:
            real = DocView.build(directory.name, json.loads(meta_path.read_text("utf-8")),
                                 json.loads(result_path.read_text("utf-8")))
        except Exception:
            continue
        documents += 1
        for jo in frames._mainbody_jos(real):
            articles += 1
            rows = frames._units(real, jo)
            packed = frames._chunks(rows)
            units_total += len(rows)
            chunks += len(packed)
            source = "\n".join(
                ((real.block_by_idx.get(block_id) or {}).get("text") or "").strip()
                for block_id in range(jo["span"][0], max(jo["span"][1], jo["span"][0] + 1))
                if ((real.block_by_idx.get(block_id) or {}).get("text") or "").strip()
            )
            rebuilt = "\n".join(row["text"] for row in rows)
            loss += source != rebuilt
            invalid += sum(not frames._is_descendant(real, row["id"], jo["id"]) for row in rows)

    result = {
        "schema_version": "hierarchical-frame-lineage-probe-v1",
        "documents": documents,
        "articles": articles,
        "clause_units": units_total,
        "chunks": chunks,
        "extra_calls_over_article_baseline": chunks - articles,
        "block_reconstruction_failures": loss,
        "invalid_descendant_units": invalid,
        "nested_probe_unit_ids": [row["id"] for row in units],
        "fake_llm_accepted_nodes": [row["node"] for row in extracted],
        "fake_llm_dropped_invalid_nodes": meta["dropped"],
        "external_calls": {"llm": 0, "embedding": 0, "network": 0},
        "operational_writes": 0,
        "result": "pass" if loss == invalid == 0 else "fail",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
