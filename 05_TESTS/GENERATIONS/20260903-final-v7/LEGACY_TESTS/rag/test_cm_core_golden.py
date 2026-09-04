import json
from collections import Counter

from lawrag.core.rag import evaluation
from lawrag.api.routers import golden as golden_api
from scripts import cm_core_golden


def _suite():
    return json.loads(cm_core_golden.DEFAULT_SUITE.read_text(encoding="utf-8"))


def test_cm_core_is_51_answered_actual_work_cases():
    suite = _suite()
    cases = suite["cases"]

    assert suite["role"] == "final_rag_release_core"
    assert suite["frozen"] is True
    assert {k: suite["counts"][k] for k in (
        "source_questions", "source_answers", "scorable_cases", "excluded_questions")} == {
        "source_questions": 52,
        "source_answers": 51,
        "scorable_cases": 51,
        "excluded_questions": 1,
    }
    assert suite["counts"]["decisive_article_instances"] == 75
    assert suite["counts"]["required_companion_instances"] == 22
    assert len(cases) == 51
    assert [case["id"] for case in cases] == [f"cm-{i:03d}" for i in range(1, 52)]
    assert all(case["reference_answer_kind"] == "actual_work_answer" for case in cases)
    assert all(case["reference_answer"] for case in cases)
    assert suite["excluded_questions"][0]["source_question_no"] == 1


def test_cm_core_round_trips_docx_and_tracks_corpus_gaps():
    report = cm_core_golden.validate(cm_core_golden.DEFAULT_SUITE)

    assert report["valid"] is True
    assert report["errors"] == []
    assert report["current_material"] == {"complete": 51}
    assert report["turn_contract"] == {
        "mode": "single_turn", "standalone_cases": 51,
        "additional_cases": 31,
    }


def test_cm_core_single_turn_input_is_deterministic_and_has_raw_ablation():
    suite = _suite()
    assert suite["turn_contract"]["mode"] == "single_turn"
    for case in suite["cases"]:
        assert case["question"] == (
            case["source_question"] + f"\n(업무 문맥: {case['topic']})")


def test_cm_core_has_business_slices_and_decisive_articles():
    suite = _suite()
    cases = suite["cases"]
    material = Counter(case["material"] for case in cases)

    assert material == {"complete": 51}
    assert sum(len(case["expected_articles"]) for case in cases) == 75
    assert sum(len(case["required_companions"]) for case in cases) == 22
    assert all(a["evidence_role"] == "decisive"
               for case in cases for a in case["expected_articles"])
    assert len({case["axes"]["business_domain"] for case in cases}) >= 10
    assert set(suite["axis_order"]) <= set(cases[0]["axes"])


def test_cm_core_is_exposed_as_frozen_read_only_ui_payload():
    payload = golden_api.cm_cases()
    detail = golden_api.cm_case("cm-001")

    assert payload["frozen"] is True
    assert payload["role"] == "final_rag_release_core"
    assert payload["summary"]["cases"] == 51
    assert payload["summary"]["expected_articles"] == 75
    assert payload["summary"]["required_companions"] == 22
    assert payload["summary"]["business_domains"] >= 10
    assert payload["validation"]["valid"] is True
    assert len(payload["cases"]) == 51
    assert detail["case"]["reference_answer_kind"] == "actual_work_answer"
    assert detail["case"]["expected_articles"]


def test_manifest_preserves_field_reference_and_actual_system_answer(tmp_path):
    source = tmp_path / "cm.raw.json"
    source.write_text("{}", encoding="utf-8")
    row = {
        "case_no": "cm-001", "question": "현업 질문", "source_question": "원문 질문",
        "reference_answer": "당시 현업 답변", "reference_answer_kind": "actual_work_answer",
        "answer": "현재 시스템 답변", "direction": "긍정", "m_gold": "",
        "m_n": 1, "m_ret": 1, "m_basis": 1, "basis_n": 1,
        "want_arts_list": ["법 제1조"], "semantic_correct": True,
        "semantic_reason": "일치", "semantic_grade": {"correct": True},
        "material": "complete", "mode": "B", "text_kind": "직접질문",
        "axes": {"business_domain": "IPO", "material": "complete"},
        "runtime": {"final_contexts": 1},
    }
    suite = {"name": "cm", "axis_order": ["business_domain", "material"]}

    manifest = evaluation.build_review_manifest(
        source_path=source, source_rows=[row], labels={}, source_flow="ask",
        source_suite=suite)
    result = manifest["results"][0]

    assert result["question"] == "현업 질문"
    assert result["source_question"] == "원문 질문"
    assert result["reference_answer"] == "당시 현업 답변"
    assert result["system_answer"] == "현재 시스템 답변"
    assert result["semantic_grade"] == {"correct": True}
    assert manifest["suite"]["axis_order"] == ["business_domain", "material"]
