from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
REVISION = (Path(__import__("lawrag").__file__).resolve().parent / "research/candidates/adr_0149/proviso-runtime-data/"
            "revisions/rev-002/snapshot/lawrag/core/domain_graph/requirements.py")
RUN = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0149-proviso-span-relationship-runtime-data/artifacts/run-002.json"


def _requirements():
    spec = importlib.util.spec_from_file_location("adr0149_test_requirements", REVISION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_proviso_is_one_span_with_effect_not_two_cues():
    module = _requirements()
    text = "주식을 6개월 보유한다. 다만, 벤처금융이 취득한 경우는 제외한다."
    rows = module.extract_provisos(
        text, doc_id="doc", node=3, article=1, block=7)
    assert len(rows) == 1
    assert rows[0].cue == "다만,"
    assert rows[0].body == "벤처금융이 취득한 경우는 제외한다."
    assert rows[0].effect_kind == "EXCEPTION_TO"
    assert rows[0].parent_text == "주식을 6개월 보유한다."


def test_unverified_cross_predicate_equivalence_stays_unknown():
    module = _requirements()
    slot = module.ConditionSlot(
        "method", "non_offering_or_sale_method", evidence_ids=("E1",))
    evidence = module.SlotEvidence(
        "E1", "제3자배정으로 취득", predicates=("third_party_allotment",))
    result = module.validate_condition_slots((slot,), (evidence,))
    assert result[0].value == "unknown"
    assert result[0].reason == "no_exact_evidence_or_verified_bridge"


def test_full_corpus_relation_contract_and_cm_route():
    run = json.loads(RUN.read_text("utf-8"))
    validation = run["candidate"]["validation"]
    assert run["candidate"]["section_relation_key_loss"] == 0
    assert validation["invalid_span_count"] == 0
    assert validation["missing_physical_count"] == 0
    assert validation["missing_legal_effect_count"] == 0
    assert validation["dangling_target_count"] == 0
    assert run["cm003"]["direct_detail_routed"] is True
    assert run["cm003"]["unsupported_method_equivalence_blocked"] is True


def test_frozen_out_of_corpus_holdout_is_reported_not_hidden():
    run = json.loads(RUN.read_text("utf-8"))
    assert run["criteria"]["holdout_packages"] == 1
    assert sum(row["has_proviso_package"] for row in run["structural_holdout"]) == 1
