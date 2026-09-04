import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
SCRIPT = ROOT / "06_TOOLS/LEGACY_SCRIPTS/rag_schema_grounded_query_probe.py"


def _runner():
    spec = importlib.util.spec_from_file_location("schema_grounded_probe", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_public_inputs_are_physically_gold_free():
    runner = _runner()
    assert runner._verify_sources() == runner.EXPECTED

    cases, parent = runner._public_cases()

    assert len(cases) == 16
    assert all(set(case) == {
        "case_id", "number", "suite", "question", "baseline"
    } for case in cases)
    assert sum(len(case["baseline"]) for case in cases) <= 16 * runner.FINAL_CAP
    assert set(parent) == {"graph_generation", "graph_content_sha256"}

    public_lock = runner.SOURCES["public_input"].read_text(encoding="utf-8")
    assert '"gold_articles"' not in public_lock
    assert '"reference_answer"' not in public_lock


def test_parent_gold_headline_is_a_post_selection_read():
    runner = _runner()
    headline = runner._post_selection_parent_headline()
    assert headline["baseline_gold_hits"] == 15
    assert headline["baseline_gold_total"] == 29


def test_raw_seed_coordinates_ignore_concept_bindings_and_use_typed_seed_menus():
    runner = _runner()
    grounding = {
        "candidates": {"menu": [
            {"id": "concept-wrapper", "candidate_kind": "TIER1_CONCEPT",
             "coordinate": ["doc", 1], "coordinates": [["doc", 1]]},
            {"id": "assertion-wrapper", "candidate_kind": "TIER1_ASSERTION",
             "coordinate": ["doc", 2], "coordinates": [["doc", 2]]},
            {"id": "evidence-wrapper", "candidate_kind": "EVIDENCE_COORDINATE",
             "coordinate": ["doc", 3], "coordinates": [["doc", 3]]},
        ]},
        "binding": {"raw_output": {
            "concept_bindings": [{"candidate_id": "concept-wrapper"}],
            "assertion_selections": [{"candidate_id": "assertion-wrapper"}],
            "evidence_selections": [{"candidate_id": "evidence-wrapper"}],
        }},
    }

    assert runner._raw_selected_coordinates(grounding) == [
        ("doc", 2), ("doc", 3)
    ]


def test_provider_schema_avoids_known_unsupported_array_bounds():
    from lawrag.core.rag import query_grounding
    from lawrag.core.rag import legal_research_llm_selector as selector

    canonical = query_grounding.binding_schema([], [])
    schema = selector.project_outbound_schema(
        canonical,
        selector.onsite_qwen_profile(reduced_schema=True),
    )

    def walk(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    assert all("maxItems" not in node and "minItems" not in node
               for node in walk(schema))
    assert canonical["properties"]["concept_bindings"]["maxItems"] == 0


def test_pre_gold_gate_requires_exact_plan_then_bind_and_zero_retries():
    runner = _runner()
    calls = []
    rows = []
    for case_id in runner.CASE_IDS:
        case_calls = []
        for kind in ("rag.query_grounding.plan", "rag.query_grounding.bind"):
            call = {
                "kind": kind,
                "requested_model": runner.MODEL,
                "backend": "anthropic",
                "transport_max_retries": 0,
                "wrapper_error": "",
                "provider": {"model": runner.MODEL, "error": ""},
            }
            calls.append(call)
            case_calls.append(call)
        rows.append({
            "case_id": case_id,
            "arm_id": "schema-grounded-planner",
            "product_calls": case_calls,
            "product_error": "",
        })

    audit = runner._pre_gold_audit(
        rows, SimpleNamespace(audit=calls), runtime_sources_match=True,
    )
    assert audit["passed"] is True
    assert audit["logical_call_count"] == 32

    calls[-1]["transport_max_retries"] = 2
    failed = runner._pre_gold_audit(
        rows, SimpleNamespace(audit=calls), runtime_sources_match=True,
    )
    assert failed["passed"] is False
    assert failed["checks"]["transport_retries_disabled"] is False
