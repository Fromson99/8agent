import json

from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL
from scripts.rag_haiku_source_relations_consensus import (
    audit_artifacts,
    normalize_surface,
    relation_fingerprint,
    revalidate_candidate,
    sentinel_results,
)


def _inventory():
    return [{
        "evidence_id": "E1", "document": "A 법", "path": "제8조",
        "document_revision": "2025-01-01", "document_enforcement": "2025-02-01",
        "document_current": True,
    }]


def _actor(value="회사의 대표자"):
    return {
        "relation_id": "R1", "relation_type": "GOVERNS_ACTOR",
        "source_id": "E1", "target_id": "", "target_value": value,
        "defined_term": "", "quote_ids": ["E1:L1"],
        "evidence_statement": "주체", "confidence": "high",
        "proof_quotes": [{"quote_id": "E1:L1", "evidence_id": "E1",
                          "kind": "source", "text": "회사의 대표자는 문서를 제출한다."}],
        "validation_errors": [],
    }


def test_normalized_fingerprint_only_folds_surface_formatting():
    left = relation_fingerprint(_actor("회사의 대표자"), _inventory(), normalized=True)
    right = relation_fingerprint(_actor("회사 의 대표자"), _inventory(), normalized=True)
    exact_left = relation_fingerprint(_actor("회사의 대표자"), _inventory())
    exact_right = relation_fingerprint(_actor("회사 의 대표자"), _inventory())
    assert left == right
    assert exact_left != exact_right
    assert normalize_surface("Ａ 법") == "a법"


def test_revalidation_uses_embedded_exact_proof_quote():
    result = revalidate_candidate(_actor(), _inventory())
    assert result["published_count"] == 1
    broken = _actor("감사인")
    assert revalidate_candidate(broken, _inventory())["rejected_count"] == 1


def test_known_sentinels_are_case_and_path_scoped():
    rows = [{
        "case_no": "cm-036", "relation_type": "GOVERNS_ACTOR",
        "source_path": "제8조", "target_path": "", "target_value": "회사의 대표자",
    }]
    assert sentinel_results(rows) == {
        "cm009_no_false_exception_16_to_13": True,
        "cm036_internal_control_actor_created": True,
        "cm045_no_fake_current_version_relation": True,
    }


def test_false_exception_and_fake_version_fail_sentinels():
    rows = [
        {"case_no": "cm-009", "relation_type": "EXCEPTION_TO",
         "source_path": "제16조", "target_path": "제13조", "target_value": ""},
        {"case_no": "cm-045", "relation_type": "CURRENT_VERSION_OF",
         "source_path": "제1조", "target_path": "제1조", "target_value": ""},
    ]
    result = sentinel_results(rows)
    assert not result["cm009_no_false_exception_16_to_13"]
    assert not result["cm036_internal_control_actor_created"]
    assert not result["cm045_no_fake_current_version_relation"]


def test_artifact_audit_requires_same_input_hash_and_haiku_rows(tmp_path):
    row = {
        "case_no": "cm-036", "model": HAIKU_MODEL,
        "product_input_sha256": "abc", "inventory": _inventory(),
        "published": [_actor()], "rejected": [],
    }
    contract = {
        "all_models": HAIKU_MODEL, "question_in_product_input": False,
        "gold_in_product_input": False, "reference_answer_in_product_input": False,
    }
    paths = []
    for name in ("pass1.json", "pass2.json"):
        path = tmp_path / name
        path.write_text(json.dumps({"contract": contract, "rows": [row]}), "utf-8")
        paths.append(path)
    result = audit_artifacts(paths, threshold=2)
    assert result["all_contract_checks_pass"]
    assert result["exact"]["policies"]["consensus_2_of_2"]["unique_relations"] == 1

    broken = json.loads(paths[1].read_text("utf-8"))
    broken["rows"][0]["product_input_sha256"] = "different"
    paths[1].write_text(json.dumps(broken), "utf-8")
    assert not audit_artifacts(paths, threshold=2)["all_contract_checks_pass"]
