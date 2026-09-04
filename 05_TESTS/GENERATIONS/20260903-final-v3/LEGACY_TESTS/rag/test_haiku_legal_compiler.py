from lawrag.core.rag.experiments import haiku_legal_compiler as compiler


def _row(evidence_id, document, path, text):
    return {
        "id": evidence_id, "document": document, "path": path,
        "role": "exact-structural", "original_text": text,
    }


def test_clause_cards_keep_primary_structure_and_promote_exception_block():
    evidence = [
        _row("E1", "A규정", "제26조 원칙",
             "제26조 원칙\n제3호의 경우 의무보유하여야 한다."),
        _row("E2", "A규정 시행세칙", "제23조 예외",
             "제23조 예외\n규정 제26조제1항제3호 단서에서 정하는 경우란 다음과 같다.\n"
             "2. 전문투자자가 취득한 경우"),
        _row("E3", "다른 규정", "제9조 무관", "제9조\n별도 절차를 정한다."),
    ]
    cards = compiler.build_clause_cards(
        "전문투자자가 취득하면 제3호인가?", evidence, max_cards=12)
    assert {"E1:L1", "E1:L2"}.issubset({row["quote_id"] for row in cards})
    assert any(row["evidence_id"] == "E2"
               and row["deterministic_role"] in {
                   "exception", "delegation_or_reference"}
               for row in cards)
    assert any(row["evidence_id"] == "E2" and "전문투자자" in row["text"]
               for row in cards)


def test_inventory_separates_ancestor_history_and_document_version():
    row = _row(
        "E1", "상법",
        "제1관 주식과 주권 <신설 2001.7.24> ▸ 제341조의4 자기주식",
        "제341조의4 회사는 1년 이내에 소각하여야 한다.")
    row.update({"document_revision": "20260306",
                "document_enforcement": "20260306"})
    inventory = compiler.evidence_inventory([row])
    assert "2001.7.24" not in inventory[0]["path"]
    assert inventory[0]["ancestor_heading_history"] == ["<신설 2001.7.24>"]
    assert inventory[0]["document_revision"] == "20260306"


def test_validation_rejects_nonexistent_quote_ids():
    inventory = [{"evidence_id": "E1"}]
    cards = [{"quote_id": "E1:L1"}]
    compiled = {
        "rules": [{
            "rule_id": "R1", "evidence_ids": ["E1"],
            "quote_ids": ["E9:L9"],
        }],
        "application": {
            "matched_rules": ["R1"], "support_quote_ids": ["E9:L9"],
        },
    }
    result = compiler.validate_compilation(compiled, inventory, cards)
    assert not result["valid"]
    assert "R1:invalid_quote" in result["errors"]


def test_all_compiler_model_calls_are_haiku():
    assert compiler.HAIKU_MODEL == "claude-haiku-4-5-20251001"


def test_three_tier_policy_allows_candidate_support_but_strict_rejects_it():
    inventory = [{
        "evidence_id": "E2",
        "typed_connection": {
            "conclusion_eligible": False,
            "support_eligible": True,
        },
    }]
    cards = [{
        "quote_id": "E2:L1",
        "conclusion_eligible": False,
        "support_eligible": True,
    }]
    compiled = {
        "rules": [{
            "rule_id": "R1", "role": "governing",
            "evidence_ids": ["E2"], "quote_ids": ["E2:L1"],
        }],
        "application": {
            "status": "supported", "matched_rules": ["R1"],
            "support_quote_ids": ["E2:L1"],
        },
    }
    strict = compiler.validate_compilation(compiled, inventory, cards)
    tiered = compiler.validate_compilation(
        compiled, inventory, cards, evidence_policy="three-tier")
    assert not strict["valid"]
    assert tiered["valid"]


def test_render_gate_preserves_fallback_when_compiler_has_unresolved_issue():
    fallback = "기존 답"
    bundle = {
        "validation": {"valid": True, "errors": []},
        "compiled": {
            "application": {
                "status": "supported", "unresolved": ["수식 범위 불명확"],
                "support_quote_ids": ["E1:L1"],
            },
            "rules": [], "conflicts": [],
        },
        "cards": [{"quote_id": "E1:L1"}], "inventory": [],
    }
    result = compiler.render_compilation(None, "질문", bundle, fallback)
    assert result["answer"] == fallback
    assert result["guard"] == "unresolved_or_conflicted"


class _RenderLLM:
    def structured(self, *_args, **_kwargs):
        return {"answerable": True, "answer": "예, 확정적으로 적용됩니다.",
                "support_quote_ids": ["E1:L1"]}


def test_render_gate_preserves_existing_interpretive_qualification():
    fallback = "문언상 적용되는 것으로 해석됩니다. 다만 유권해석이 필요합니다."
    bundle = {
        "validation": {"valid": True, "errors": []},
        "compiled": {
            "application": {"status": "supported", "unresolved": [],
                            "support_quote_ids": ["E1:L1"]},
            "rules": [{"quote_ids": ["E1:L1"]}], "conflicts": [],
        },
        "cards": [{"quote_id": "E1:L1"}], "inventory": [],
    }
    result = compiler.render_compilation(_RenderLLM(), "질문", bundle, fallback)
    assert result["answer"] == fallback
    assert result["guard"] == "preserve_interpretive_qualification"
