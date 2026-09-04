from lawrag.core.rag import grounded_witness, relations, termexplore
from lawrag.core.rag.index import Index


LAW_TEXT = "금융회사는 준법감시인을 두어야 한다."
DECREE_TEXT = "준법감시인은 다른 업무를 겸직할 수 없다."


def _index():
    def doc(text):
        return {
            "nodes": [{
                "id": 1, "parent": None, "level": 1,
                "surface": "제1조", "title": "원칙", "span": [0, 1],
            }],
            "blocks": [{"idx": 0, "node": 1, "text": text, "kind": "text"}],
        }

    return Index.from_docs([
        ("law", {"name": "시험법", "kind": "law"}, doc(LAW_TEXT)),
        ("decree", {"name": "시험법 시행령", "kind": "law"}, doc(DECREE_TEXT)),
    ])


def _candidates(index):
    return {
        "C1": termexplore._branch(index, "law", 1, (), origin="test"),
        "C2": termexplore._branch(index, "decree", 1, (), origin="test"),
    }


def _span(text, quote):
    start = text.index(quote)
    return {"start": start, "end": start + len(quote)}


def _relation():
    return relations.SectionRelation(
        "DELEGATES_TO", "law", 1, "decree", 1,
        {"status": "resolved", "provenance": ["test:official"]},
    )


def _install_relation(monkeypatch, edge):
    def incident(_index, doc_id, node):
        if (doc_id, node) == ("law", 1):
            return (edge,), ()
        if (doc_id, node) == ("decree", 1):
            return (), (edge,)
        return (), ()

    monkeypatch.setattr(grounded_witness.relations, "incident", incident)


def test_exact_quote와_실제_companion_edge가_모두_있어야_complete(monkeypatch):
    index = _index()
    candidates = _candidates(index)
    edge = _relation()
    _install_relation(monkeypatch, edge)
    menu = grounded_witness.build_closed_edge_menu(index, candidates)
    forward = next(row for row in menu.values()
                   if row.from_candidate_id == "C1" and row.to_candidate_id == "C2")
    rule_quote = "준법감시인을 두어야 한다"
    companion_quote = "다른 업무를 겸직할 수 없다"

    result = grounded_witness.validate_witness(
        index, candidates, ["rule", "companion"], {
            "witnesses": [
                {
                    "facet": "rule", "candidate_id": "C1",
                    "quote": rule_quote,
                    "source_span": _span(candidates["C1"].body, rule_quote),
                },
                {
                    "facet": "companion", "candidate_id": "C2",
                    "quote": companion_quote,
                    "source_span": _span(candidates["C2"].body, companion_quote),
                    "source_candidate_id": "C1", "edge_id": forward.edge_id,
                },
            ],
        }, closed_edges=menu, companion_facets=["companion"])

    assert result["status"] == "complete"
    assert result["covered_facets"] == ["rule", "companion"]
    assert result["span_covered_facets"] == ["rule", "companion"]
    assert result["missing_facets"] == []
    assert result["errors"] == []


def test_유효한_witness가_일부만_있으면_partial():
    index = _index()
    candidates = _candidates(index)
    quote = "준법감시인을 두어야 한다"

    result = grounded_witness.validate_witness(
        index, candidates, ["rule", "exception"], {
            "witnesses": [{
                "facet": "rule", "candidate_id": "C1", "quote": quote,
                "source_span": _span(candidates["C1"].body, quote),
            }],
        })

    assert result["status"] == "partial"
    assert result["covered_facets"] == ["rule"]
    assert result["missing_facets"] == ["exception"]
    assert result["errors"] == []


def test_closed_menu_밖의_candidate_id는_invalid():
    index = _index()
    result = grounded_witness.validate_witness(
        index, _candidates(index), ["rule"], {
            "witnesses": [{
                "facet": "rule", "candidate_id": "C999",
                "quote": "준법감시인", "source_span": [4, 10],
            }],
        })

    assert result["status"] == "invalid"
    assert result["covered_facets"] == []
    assert result["missing_facets"] == ["rule"]
    assert {row["code"] for row in result["errors"]} == {
        "candidate_id_not_in_closed_menu"}


def test_candidate_span은_있어도_quote_span이_틀리면_witness가_아니다():
    index = _index()
    quote = "준법감시인을 두어야 한다"
    actual = _span(_candidates(index)["C1"].body, quote)
    wrong = {"start": actual["start"] - 1, "end": actual["end"] - 1}

    result = grounded_witness.validate_witness(
        index, _candidates(index), ["rule"], {
            "witnesses": [{
                "facet": "rule", "candidate_id": "C1", "quote": quote,
                "source_span": wrong,
            }],
        })

    assert result["status"] == "invalid"
    assert result["span_covered_facets"] == ["rule"]
    assert result["covered_facets"] == []
    assert result["span_only_facets"] == ["rule"]
    assert result["missing_facets"] == ["rule"]
    assert result["errors"][0]["code"] == "quote_not_exact_source_span"


def test_구조표시문은_Branch에_있어도_원문_quote로_인정하지_않는다():
    index = _index()
    candidates = _candidates(index)
    synthetic = "▸ 제1조 원칙"

    result = grounded_witness.validate_witness(
        index, candidates, ["rule"], {
            "witnesses": [{
                "facet": "rule", "candidate_id": "C1", "quote": synthetic,
                "source_span": _span(candidates["C1"].body, synthetic),
            }],
        })

    assert result["status"] == "invalid"
    assert result["span_covered_facets"] == ["rule"]
    assert result["covered_facets"] == []
    assert result["errors"][0]["code"] == "quote_not_in_source_blocks"


def test_closed_edge처럼_보여도_Index에_연결이_없으면_invalid(monkeypatch):
    index = _index()
    candidates = _candidates(index)
    edge = _relation()
    edge_id = grounded_witness.stable_edge_id(edge, "out")
    fake_closed = grounded_witness.ClosedEdge(
        edge_id=edge_id,
        from_candidate_id="C1", to_candidate_id="C2",
        kind=edge.kind, direction="out",
        src_doc_id="law", src_node=1,
        dst_doc_id="decree", dst_node=1,
    )
    monkeypatch.setattr(
        grounded_witness.relations, "incident", lambda *_args: ((), ()))
    quote = "다른 업무를 겸직할 수 없다"

    result = grounded_witness.validate_witness(
        index, candidates, ["companion"], {
            "witnesses": [{
                "facet": "companion", "candidate_id": "C2",
                "quote": quote,
                "source_span": _span(candidates["C2"].body, quote),
                "source_candidate_id": "C1", "edge_id": edge_id,
            }],
        }, closed_edges={edge_id: fake_closed},
        companion_facets=["companion"])

    assert result["status"] == "invalid"
    assert result["span_covered_facets"] == ["companion"]
    assert result["covered_facets"] == []
    assert result["missing_facets"] == ["companion"]
    assert {row["code"] for row in result["errors"]} == {"edge_not_in_index"}


def test_가짜_stable_edge_id는_closed_menu에_있어도_invalid(monkeypatch):
    index = _index()
    candidates = _candidates(index)
    edge = _relation()
    _install_relation(monkeypatch, edge)
    fake = grounded_witness.ClosedEdge(
        edge_id="E1", from_candidate_id="C1", to_candidate_id="C2",
        kind=edge.kind, direction="out",
        src_doc_id="law", src_node=1,
        dst_doc_id="decree", dst_node=1,
    )
    quote = "다른 업무를 겸직할 수 없다"

    result = grounded_witness.validate_witness(
        index, candidates, ["companion"], {
            "witnesses": [{
                "facet": "companion", "candidate_id": "C2",
                "quote": quote,
                "source_span": _span(candidates["C2"].body, quote),
                "source_candidate_id": "C1", "edge_id": "E1",
            }],
        }, closed_edges={"E1": fake}, companion_facets=["companion"])

    assert result["status"] == "invalid"
    assert result["errors"][0]["code"] == "edge_id_not_stable"
