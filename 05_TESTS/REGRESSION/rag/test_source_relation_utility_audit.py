from scripts import rag_source_relation_utility_audit as audit


def _retrieval(question="코스닥시장에서 회사가 신고해야 하는가?"):
    selected = [
        {"doc": "A법", "path": "제1조 원칙"},
        {"doc": "B법", "path": "제2조 절차"},
        {"doc": "C법", "path": "제3조 기타"},
    ]
    return {
        "case_no": "cm-test", "question": question,
        "variants": {audit.VARIANT: {
            "selected": selected,
            "gold": [{"law": "A법", "article": "제1조", "selected": True}],
        }},
    }


def _relations(relation_type="GOVERNS_ACTOR", target_value="회사", target_id=""):
    inventory = [
        {"evidence_id": "E1", "document": "A법", "path": "제1조 원칙"},
        {"evidence_id": "E2", "document": "B법", "path": "제2조 절차"},
        {"evidence_id": "E3", "document": "C법", "path": "제3조 기타"},
    ]
    return {
        "case_no": "cm-test", "inventory": inventory,
        "published": [{
            "relation_type": relation_type, "source_id": "E1",
            "target_id": target_id, "target_value": target_value,
            "defined_term": "",
        }],
    }


def test_gold_matching_is_exact_on_normalized_law_and_article():
    assert audit.is_gold_node(
        {"document": "A 법", "path": "제1편 ▸ 제1조 원칙"},
        [{"law": "A법", "article": "제1조"}],
    )
    assert not audit.is_gold_node(
        {"document": "A법", "path": "제10조 원칙"},
        [{"law": "A법", "article": "제1조"}],
    )


def test_actor_alignment_uses_question_but_not_gold():
    inventory = {row["evidence_id"]: row for row in _relations()["inventory"]}
    relation = _relations()["published"][0]
    assert audit.relation_query_aligned(relation, "회사가 신고해야 하나?", inventory)
    assert not audit.relation_query_aligned(relation, "감사인이 신고해야 하나?", inventory)


def test_market_conflict_prune_is_fail_open_without_explicit_market():
    relation_row = _relations("APPLIES_TO_MARKET", "KOSPI")
    no_market = audit.audit_case(relation_row, _retrieval("신고해야 하는가?"))
    assert no_market["conflicting_market_nodes"] == 0
    explicit = audit.audit_case(relation_row, _retrieval())
    assert explicit["conflicting_market_nodes"] == 1
    assert explicit["conflicting_market_gold_nodes"] == 1


def test_article_relation_creates_structural_edge_and_incident_nodes():
    row = audit.audit_case(
        _relations("IMPLEMENTS", target_id="E2"),
        _retrieval("제2조에 따른 절차인가?"),
    )
    assert row["relation_incident_nodes"] == 2
    assert row["structural_edges"][0]["touches_gold"] is True
    assert row["structural_edges"][0]["gold_to_non_gold"] is True


def test_unannotated_nodes_are_only_evaluation_predictions():
    row = audit.audit_case(_relations(), _retrieval())
    assert row["unannotated_nodes"] == 2
    assert row["unannotated_distractors"] == 2
    assert row["simulated_pruning"]["keep_relation_incident_only"] == {
        "kept": 1, "gold_kept": 1,
    }


def test_duplicate_published_relations_do_not_multiply_utility_score():
    relation_row = _relations()
    relation_row["published"].append(dict(relation_row["published"][0]))
    row = audit.audit_case(relation_row, _retrieval())
    assert row["published_relations_raw"] == 2
    assert row["published_relations"] == 1
    assert row["relation_incident_nodes"] == 1
