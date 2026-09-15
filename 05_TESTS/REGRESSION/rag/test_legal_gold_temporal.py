import json
from pathlib import Path

from lawrag.platform import active_runtime_paths, active_structure_path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
STRUCTURE = active_structure_path(ROOT, target="local")


def test_fsc_answer_time_and_current_coordinates_are_explicit_and_grounded():
    suite = json.loads((ROOT / "01_DATA/review/fsc_hard_retrieval_v2.json").read_text("utf-8"))
    assert suite["schema_version"] == 2 and suite["version"] == 2
    assert suite["temporal_contract"]["no_silent_rebinding"] is True
    assert sum(len(c["answer_time_articles"]) for c in suite["cases"]) == 15
    assert sum(len(c["current_articles"]) for c in suite["cases"]) == 15
    for case in suite["cases"]:
        assert case["answer_as_of"] == case["published"].replace("-", "")
        assert case["expected_articles"] == case["current_articles"]
        for field in ("answer_time_articles", "current_articles"):
            for row in case[field]:
                result = json.loads((STRUCTURE / row["doc_id"]
                                     / "result.json").read_text("utf-8"))
                node = next(n for n in result["nodes"] if str(n["id"]) == row["node"])
                assert node["coordinate_scope"] == "body"
                assert node["coordinate_key"] == row["coordinate_key"]


def test_cm_audited_citation_gaps_have_explicit_roles():
    suite = json.loads((ROOT / "01_DATA/review/cm_core_e2e_v2.json").read_text("utf-8"))
    reviewed = {"cm-005", "cm-006", "cm-009", "cm-013", "cm-015", "cm-016",
                "cm-018", "cm-025", "cm-027", "cm-028", "cm-029", "cm-030",
                "cm-042", "cm-043", "cm-045", "cm-046", "cm-047", "cm-049",
                "cm-050"}
    cases = {case["id"]: case for case in suite["cases"]}
    assert reviewed <= set(cases)
    assert sum(len(c["expected_articles"]) for c in suite["cases"]) == 75
    assert sum(len(c["required_companions"]) for c in suite["cases"]) == 22
    assert sum(len(c["auxiliary_evidence"]) for c in suite["cases"]) == 2
    assert all(cases[cid]["material"] == "complete" for cid in reviewed)


def test_active_release_consumers_share_one_runtime_generation():
    runtime_root = ROOT / "01_DATA/ACTIVE/local/RUNTIMES"
    paths = active_runtime_paths(ROOT, target="local")
    generations = {path.relative_to(runtime_root).parts[0] for path in paths.values()}
    assert len(generations) == 1
    assert all(path.exists() for path in paths.values())


def test_semantic_seed_v2_is_rebound_to_current_source_coordinates():
    suite = json.loads(
        (ROOT / "01_DATA/review/semantic_operation_seed_v2.json").read_text("utf-8"))
    assert suite["schema_version"] == 2 and suite["version"] == 2
    assert suite["authority_contract"]["no_stale_source_copy"] is True
    assert sum(len(case["expected_articles"]) for case in suite["cases"]) == 14
    cm_048 = next(case for case in suite["cases"]
                  if case["provenance"]["source_case_id"] == "cm-048")
    assert cm_048["expected_articles"] == [{
        "law": "상법",
        "article": "제416조",
        "doc_id": "7bbe815ff43b6635",
        "document_revision": "20250722",
        "document_enforcement": "20260723",
        "node": "1686",
        "corpus_status": "present",
        "evidence_role": "decisive",
        "authority_as_of": "20260827",
        "coordinate_scope": "body",
        "coordinate_key": "body:제416조",
    }]
