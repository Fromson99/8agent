from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from lawrag.platform import active_structure_path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
STRUCTURE = active_structure_path(ROOT, target="local")
CANDIDATE = (
    Path(__import__("lawrag").__file__).resolve().parent / "research/candidates/adr_0155/terminal-aware-proviso-graph"
    "/revisions/rev-001/snapshot/lawrag/research/candidates/adr_0154"
    "/minimum-unit-proviso-graph/revisions/rev-002/snapshot/lawrag/research"
    "/candidates/adr_0150/proviso-schema-slot-gate/revisions/rev-002/snapshot"
    "/lawrag/core/domain_graph/requirements.py"
)


def load_candidate():
    spec = importlib.util.spec_from_file_location("test_adr0155_candidate", CANDIDATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_terminal_exclusion_cue_is_the_outcome():
    candidate = load_candidate()
    text = "의결권이 없는 주식은 제외한다. 뒤 문장이다."
    span = candidate.extract_provisos(
        text, doc_id="doc", node=3, article=1, block=7,
    )[0]
    condition, outcome = candidate.split_proviso_components(span, text)
    assert condition.text == "의결권이 없는 주식은"
    assert condition.end <= span.cue_start
    assert outcome.text == "제외한다"
    assert (outcome.start, outcome.end) == (span.cue_start, span.cue_end)
    assert candidate.classify_outcome(outcome.text) == "EXCLUDES_APPLICATION"


def test_forward_proviso_and_reverse_receiving_locator_remain_exact():
    candidate = load_candidate()
    documents = {}
    for doc_id in ("3521c3aaa5a735fd", "eae25aa6e8a83c58"):
        path = STRUCTURE / doc_id / "result.json"
        documents[doc_id] = json.loads(path.read_text("utf-8"))
    graph = candidate.build_minimum_unit_proviso_graph(documents)
    components = {row["component_id"]: row for row in graph["components"]}
    proviso = next(
        row for row in graph["provisos"]
        if row["source_locator"] == "제26조제1항제3호"
        and row["cue"].startswith("다만")
    )
    assert components[proviso["condition_id"]]["text"] == "세칙으로 정하는 경우는"
    assert components[proviso["outcome_id"]]["text"] == "제외한다."
    route = next(row for row in graph["routes"] if row["proviso_id"] == proviso["proviso_id"])
    assert (route["status"], route["target_doc_id"], route["target_node"]) == (
        "RESOLVED", "eae25aa6e8a83c58", 218,
    )
    assert len(route["member_unit_ids"]) == 8
