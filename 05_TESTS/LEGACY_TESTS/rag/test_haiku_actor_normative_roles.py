from lawrag.core.rag.experiments import haiku_actor_normative_roles as roles


def _relation(actor="회사의 대표자", text="회사의 대표자는 신고하여야 한다."):
    return {
        "relation_id": "R1", "relation_type": "GOVERNS_ACTOR",
        "source_id": "E1", "target_value": actor,
        "proof_quotes": [{"quote_id": "E1:L1", "evidence_id": "E1",
                          "kind": "source", "text": text}],
    }


def _candidate(**changes):
    value = {
        "relation_ref": "A1", "actor_surface": "회사의 대표자",
        "role": "OBLIGOR", "quote_id": "E1:L1",
        "modality_surface": "신고하여야 한다", "rationale": "신고 의무",
        "confidence": "high",
    }
    value.update(changes)
    return value


def test_input_contains_only_actor_relation_and_embedded_proof():
    menu, closed = roles.build_actor_role_input([_relation(), {
        "relation_type": "APPLIES_TO_MARKET", "target_value": "KOSDAQ"}])
    assert len(menu) == 1
    assert set(menu[0]) == {
        "relation_ref", "relation_type", "source_id", "actor_surface", "proof_quotes"}
    assert "question" not in str(menu).lower()
    assert closed["A1"] == menu[0]


def test_obligor_requires_exact_actor_and_modality_in_same_quote():
    menu, closed = roles.build_actor_role_input([_relation()])
    result = roles.validate_actor_roles({"roles": [_candidate()]}, closed)
    assert result["published_count"] == 1
    bad = _candidate(actor_surface="대표이사", modality_surface="신고 의무")
    result = roles.validate_actor_roles({"roles": [bad]}, closed)
    assert result["rejected_count"] == 1
    assert "actor_surface_not_exact" in result["rejected"][0]["validation_errors"]
    assert "modality_not_exact_in_quote" in result["rejected"][0]["validation_errors"]


def test_role_signal_must_be_compatible():
    _, closed = roles.build_actor_role_input([_relation()])
    candidate = _candidate(role="POWER_HOLDER")
    result = roles.validate_actor_roles({"roles": [candidate]}, closed)
    assert result["rejected_count"] == 1
    assert "modality_incompatible_with_role" in result["rejected"][0]["validation_errors"]


def test_power_holder_accepts_exact_discretion_surface():
    relation = _relation(text="거래소는 제출을 요구할 수 있다.", actor="거래소")
    _, closed = roles.build_actor_role_input([relation])
    candidate = _candidate(actor_surface="거래소", role="POWER_HOLDER",
                           modality_surface="요구할 수 있다")
    result = roles.validate_actor_roles({"roles": [candidate]}, closed)
    assert result["published_count"] == 1


def test_condition_actor_is_distinct_from_obligor():
    relation = _relation(text="법인이 신주를 발행함으로써 이익이 발생한다.", actor="법인")
    _, closed = roles.build_actor_role_input([relation])
    candidate = _candidate(actor_surface="법인", role="CONDITION_ACTOR",
                           modality_surface="신주를 발행함으로써")
    result = roles.validate_actor_roles({"roles": [candidate]}, closed)
    assert result["published_count"] == 1


def test_composition_requirement_is_not_actor_obligation():
    relation = _relation(
        text="감사위원회 위원 중 1명 이상은 회계 전문가이어야 한다.",
        actor="감사위원회")
    _, closed = roles.build_actor_role_input([relation])
    candidate = _candidate(
        actor_surface="감사위원회", role="OBLIGOR",
        modality_surface="위원 중 1명 이상은 회계 전문가이어야 한다")
    result = roles.validate_actor_roles({"roles": [candidate]}, closed)
    assert result["rejected_count"] == 1
    assert "status_requirement_mislabeled_as_obligor" in (
        result["rejected"][0]["validation_errors"])


def test_active_prohibited_subject_is_not_procedural_object():
    relation = _relation(
        text="의무보유 대상자는 주식등을 매각할 수 없다.", actor="의무보유 대상자")
    _, closed = roles.build_actor_role_input([relation])
    candidate = _candidate(
        actor_surface="의무보유 대상자", role="PROCEDURAL_OBJECT",
        modality_surface="주식등을 매각할 수 없다")
    result = roles.validate_actor_roles({"roles": [candidate]}, closed)
    assert result["rejected_count"] == 1
    assert "active_deontic_subject_mislabeled_as_object" in (
        result["rejected"][0]["validation_errors"])


def test_same_actor_as_subject_and_object_requires_uncertain():
    relation = _relation(
        text="평가심의위원회에 신청하면 평가심의위원회가 심의하여 제시한다.",
        actor="평가심의위원회")
    _, closed = roles.build_actor_role_input([relation])
    candidate = _candidate(
        actor_surface="평가심의위원회", role="PROCEDURAL_OBJECT",
        modality_surface="평가심의위원회에 신청")
    result = roles.validate_actor_roles({"roles": [candidate]}, closed)
    assert result["rejected_count"] == 1
    assert "actor_has_multiple_grammatical_roles" in (
        result["rejected"][0]["validation_errors"])


def test_missing_or_unresolved_are_explicit():
    _, closed = roles.build_actor_role_input([_relation()])
    missing = roles.validate_actor_roles({"roles": [], "unresolved_refs": []}, closed)
    assert missing["missing_refs"] == ["A1"]
    unresolved = roles.validate_actor_roles(
        {"roles": [], "unresolved_refs": ["A1"]}, closed)
    assert unresolved["missing_refs"] == []
    assert unresolved["coverage_count"] == 1


def test_compiler_model_is_haiku():
    assert roles.HAIKU_MODEL == "claude-haiku-4-5-20251001"
