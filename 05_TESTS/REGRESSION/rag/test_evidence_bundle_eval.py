from scripts.rag_evidence_bundle_eval import CASES, build_prompt, score


def _materials(case):
    return [
        {
            "id": spec.id,
            "document": spec.doc_id,
            "path": str(spec.node),
            "role": spec.role,
            "scope": spec.scope,
            "original_text": f"body:{spec.id}",
        }
        for spec in case.evidence
    ]


def test_raw_and_structured_mixed_use_the_same_evidence():
    case = CASES[0]
    materials = _materials(case)
    raw, raw_order = build_prompt(case, "raw_mixed", materials, seed=7)
    structured, structured_order = build_prompt(
        case, "structured_mixed", materials, seed=7)

    assert raw_order == structured_order
    assert set(raw_order) == {case.gold_id, case.negative_id}
    for row in materials:
        assert row["original_text"] in raw
        assert row["original_text"] in structured


def test_gold_variants_exclude_hard_negative():
    case = CASES[1]
    materials = _materials(case)

    for variant in ("raw_gold", "structured_gold"):
        prompt, order = build_prompt(case, variant, materials, seed=1)
        assert order == [case.gold_id]
        assert f"body:{case.gold_id}" in prompt
        assert f"body:{case.negative_id}" not in prompt


def test_cm032_score_requires_complete_exception_and_right_evidence():
    case = CASES[0]
    good = {
        "answer": ("원칙은 45일이고 연결재무제표 기준 보고서는 최초 사업연도와 "
                   "그 다음 사업연도에 60일이다."),
        "decisive_evidence_ids": ["G32"],
    }
    incomplete = {**good, "answer": "원칙은 45일이고 예외는 60일이다."}

    assert score(case, good)["passed"] is True
    assert score(case, incomplete)["passed"] is False


def test_cm036_score_rejects_invented_equivalence():
    case = CASES[1]
    good = {
        "answer": ("제8조 제3항은 상근이사를 지정하도록 하지만 등기임원과 같다고 "
                   "직접 규정한 근거는 없다. 상법상 별도의 법적 근거가 필요하다."),
        "decisive_evidence_ids": ["G36"],
    }
    bad = {
        "answer": "상근임원은 등기임원을 의미하므로 반드시 등기임원이어야 한다.",
        "decisive_evidence_ids": ["N36"],
    }

    assert score(case, good)["passed"] is True
    assert score(case, bad)["passed"] is False


def test_cm036_score_rejects_categorical_no_from_absent_text():
    case = CASES[1]
    too_strong = {
        "answer": ("아니다. 내부회계관리자는 등기임원일 필요가 없다. 제8조 제3항은 "
                   "상근이사를 규정하고 등기임원을 직접 명시하지 않는다."),
        "decisive_evidence_ids": ["G36"],
    }

    result = score(case, too_strong)
    assert result["passed"] is False
    assert result["checks"]["avoids_categorical_no"] is False
