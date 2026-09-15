from lawrag.research.experiments import governing_anchor_selector as selector


def _row(evidence_id, document, path, role, text, connection_role="parallel_search_context"):
    return {
        "id": evidence_id,
        "document": document,
        "path": path,
        "role": role,
        "original_text": text,
        "typed_connection": {
            "connection_role": connection_role,
            "evidence_tier": "B_candidate_support",
            "direct_relations": [],
        },
    }


def test_scope_channel_prefers_explicit_market_and_article():
    question = "코스닥시장 상장규정 제13조의 의무는?"
    kospi = _row("E1", "유가증권시장 상장규정", "제13조 상장주선인의 의무",
                 "exact-structural", "의무인수하여야 한다.")
    kosdaq = _row("E2", "코스닥시장 상장규정", "제13조 상장주선인의 의무",
                  "assertion-tree", "의무인수하여야 한다.")
    first = selector.governing_anchor_panel(question, [kospi, kosdaq], max_candidates=1)
    assert first[0]["evidence_id"] == "E2"
    assert "kosdaq_scope_match" in first[0]["reasons"]


def test_issue_channel_keeps_formula_provision_even_when_title_differs():
    question = "괴리율은 어떻게 산정하는가?"
    landing = _row("E1", "A규정", "제26조 의무보유", "exact-structural",
                   "의무보유하여야 한다.", "seed_governing_candidate")
    formula = _row("E2", "B규정", "제5조 공모가격 결정", "exact-structural",
                   "제5호의 괴리율은 공모가격을 기준으로 산정한다.")
    panel = selector.governing_anchor_panel(
        question, [landing, formula], max_candidates=2)
    selected = {row["evidence_id"]: row for row in panel}
    assert selected["E2"]["issue_terms"] == ["괴리율", "산정"]
    assert "issue" in selected["E2"]["selected_by"]


def test_issue_terms_strip_common_korean_particles():
    assert selector.issue_terms("괴리율은 어떻게 산정하는가?") == {"괴리율", "산정"}
