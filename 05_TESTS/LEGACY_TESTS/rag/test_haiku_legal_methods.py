from lawrag.core.rag.experiments import haiku_legal_methods as methods


def test_authority_kind_separates_formal_rule_and_guidance():
    assert methods.authority_kind("자본시장과 금융투자업에 관한 법률") == "statute"
    assert methods.authority_kind("자본시장법 시행령") == "enforcement_decree"
    assert methods.authority_kind("코스닥시장 상장규정 시행세칙") == "detailed_rule"
    assert methods.authority_kind("기업실사 체크리스트 작성 가이드") == (
        "guidance_or_model_rule")


def test_operator_ledger_marks_legal_operators_without_inventing_rules():
    evidence = [{
        "id": "E1", "document": "법", "path": "제1조",
        "original_text": "원칙 문장\n다만 각각 100분의 10 이내로 하여야 한다.",
    }]
    ledger = methods.operator_ledger(evidence)
    assert ledger["authority_inventory"][0]["id"] == "E1"
    assert ledger["operator_cues"] == [{
        "evidence_id": "E1", "excerpt": "다만 각각 100분의 10 이내로 하여야 한다."
    }]


def test_all_experiment_methods_are_haiku_only():
    assert methods.HAIKU_MODEL == "claude-haiku-4-5-20251001"
    assert set(methods.RUNNERS) == set(methods.METHODS)


def test_wiki_background_is_explicitly_non_evidentiary():
    _, block = methods.wiki_background(
        "단서가 적용되는가?", [{
            "id": "E1", "document": "상법", "path": "제1조",
            "role": "", "original_text": "다만 예외로 한다.",
        }])
    assert "증거가 아님" in block
    assert "회수 원문 E번호" in block


def test_provenance_path_separates_ancestor_history_from_article():
    path, ancestors = methods.provenance_path(
        "제4장 주식회사 ▸ 제1관 주식과 주권 <신설 2001.7.24> ▸ "
        "제341조의4 자기주식의 소각의무 등")
    assert "2001.7.24" not in path
    assert ancestors == ["<신설 2001.7.24>"]
    own_path, own_ancestors = methods.provenance_path(
        "제6장 기업성장집합투자증권 ▸ 제85조의2 정의[신설 2026.3.4]")
    assert "[신설 2026.3.4]" in own_path
    assert own_ancestors == []


def test_focus_evidence_keeps_explicit_article_and_reverse_exception():
    rows = [{
        "id": "E1", "document": "A법", "path": "제26조 원칙",
        "role": "exact-structural", "original_text": "원칙을 정한다.",
    }] + [{
        "id": f"E{i}", "document": "다른 규정", "path": f"제{i}조 무관",
        "role": "keyword-bm25", "original_text": "무관한 본문",
    } for i in range(2, 7)] + [{
        "id": "E7", "document": "A법", "path": "제30조 예외",
        "role": "supplemental-closure",
        "original_text": "제26조에도 불구하고 적용하지 아니한다.",
    }]
    focused = methods.focus_evidence("A법 제26조의 적용은?", rows)
    assert "E1" in {row["id"] for row in focused}
    assert "E7" in {row["id"] for row in focused}
    assert len(focused) <= 7


def test_rescue_gate_only_opens_for_explicit_abstention():
    assert methods.is_abstaining_answer("회수된 자료에는 직접 규정이 없습니다.")
    assert methods.is_abstaining_answer("이 자료만으로 판단할 수 없습니다.")
    assert not methods.is_abstaining_answer("다만 예외는 적용되지 않습니다.")
