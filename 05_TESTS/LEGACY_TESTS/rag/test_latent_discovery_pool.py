from __future__ import annotations

import os
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
for _key, _relative in (
    ("STRUCTURE_STORE", "01_DATA/structure"),
    ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
    ("GLOSSARY_STORE", "01_DATA/glossary.json"),
    ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ("RAG_DELEGATION_STORE", "01_DATA/delegation.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from lawrag.core.rag import index as index_mod
from lawrag.core.rag import latent_discovery_pool as discovery
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger


class FakeLLM:
    model = discovery.MODEL

    def structured(self, kind, system, user, schema, **_kwargs):
        assert kind == "rag.legalclosure.latent_seed_lattice"
        assert "정답 법령명" in system
        assert user.startswith("[질문]\n")
        assert schema["additionalProperties"] is False
        return {
            "factual_slots": ["회사에서 규정 준수를 살피는 사람", "상환 부담을 낮추는 업무"],
            "operation_hypotheses": ["준법감시", "채무조정", "제29조", "가상의 법률"],
            "exact_surfaces": ["겸직 제한", "준법감시"],
            "keyword_queries": ["준법 감시", "채무 부담 조정"],
            "vector_queries": ["내부 통제 담당자의 다른 업무 수행 제한"],
        }


def test_semantic_plan_keeps_multiple_operations_and_rejects_authority_coordinates():
    plan = discovery.semantic_plan(FakeLLM(), "사실관계 질문?")
    assert plan.mode == "semantic-seed-lattice"
    assert plan.operation_hypotheses == ("준법감시", "채무조정")
    assert "제29조" in plan.rejected
    assert "가상의 법률" in plan.rejected
    assert len(plan.operation_hypotheses) <= 6
    assert len(plan.vector_queries) <= 4


def test_simple_capture_records_every_stage_and_pool_cap_discard_receipts():
    index = index_mod.current().scoped(None)
    first = ("3521c3aaa5a735fd", 175)
    second = ("eae25aa6e8a83c58", 82)
    capture, final = discovery.record_simple_capture(
        index,
        "case-test",
        "baseline",
        {"exact": [first, first], "keyword": [second], "vector": [], "assertion": []},
        [],
        prefix="b",
    )
    ledger.validate_capture(capture)
    assert [stage["stage_id"] for stage in capture["stages"]] == [
        "b00-source", "b10-exact", "b20-keyword", "b30-vector",
        "b40-assertion", "b50-union", "b60-canonicalize",
        "b70-relation-closure", "b80-pool-cap", "b90-present",
    ]
    assert final == [first, second]
    assert capture["stages"][1]["occurrence_counts"]["canonical_collapsed_after"] == 1
    graded = ledger.grade_capture(capture, [first, second])
    assert graded["computed_post_selection"] is True
    assert graded["gold_visible_to_product"] is False
    assert graded["stages"][-1]["gold_after"] == 2


def test_residual_capture_is_append_only_before_the_explicit_pool_cap():
    index = index_mod.current().scoped(None)
    coordinates = [
        ("3521c3aaa5a735fd", 175),
        ("eae25aa6e8a83c58", 82),
        ("ada543ab1a11ae54", 274),
        ("f67493d630cab3e6", 183),
    ]
    capture, final = discovery.record_residual_capture(
        index,
        "case-test",
        {"exact": coordinates[:1], "keyword": [], "vector": [], "assertion": []},
        coordinates[1:2],
        coordinates[2:3],
        coordinates[3:4],
        [],
        [],
    )
    ledger.validate_capture(capture)
    counts = [stage["after_count"] for stage in capture["stages"]]
    residual_counts = counts[6:12]
    assert residual_counts == sorted(residual_counts)
    assert final == coordinates
    assert all(
        not stage["discarded"]
        for stage in capture["stages"]
        if stage["stage_id"] != "r130-pool-cap"
    )
