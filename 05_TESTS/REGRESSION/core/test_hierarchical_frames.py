from __future__ import annotations

from lawrag.core.rag import frames
from lawrag.core.rag.index import DocView


def _view():
    nodes = [
        {"id": 1, "parent": None, "family": "kr_article", "surface": "제1조", "level": 0, "span": [0, 5]},
        {"id": 2, "parent": 1, "family": "circled", "surface": "①", "level": 1, "span": [1, 5]},
        {"id": 3, "parent": 2, "family": "dot_number:1", "surface": "1.", "level": 2, "span": [2, 4]},
        {"id": 4, "parent": 3, "family": "hangul_jamo", "surface": "가.", "level": 3, "span": [3, 4]},
    ]
    blocks = [
        {"idx": 0, "text": "article"},
        {"idx": 1, "text": "paragraph"},
        {"idx": 2, "text": "item"},
        {"idx": 3, "text": "subitem"},
        {"idx": 4, "text": "paragraph tail"},
    ]
    return (
        DocView.build("probe", {"name": "probe"}, {"nodes": nodes, "blocks": blocks},
                      apply_structure_fixes=False),
        nodes[0],
    )


def test_units_preserve_deepest_coordinates_and_source_order():
    view, article = _view()
    units = frames._units(view, article)
    assert [row["id"] for row in units] == [1, 2, 3, 4, 2]
    assert [block for row in units for block in row["blocks"]] == [0, 1, 2, 3, 4]


def test_chunks_preserve_all_text_without_tail_truncation():
    view, article = _view()
    units = frames._units(view, article)
    chunks = frames._chunks(units, cap=8)
    assert len(chunks) > 1
    assert "".join(row["text"] for chunk in chunks for row in chunk) == "".join(
        row["text"] for row in units
    )


def test_extract_accepts_subitem_and_rejects_invented_node():
    class FakeLLM:
        log = []

        def structured(self, *_args, **_kwargs):
            def row(node):
                return {"node": node, "actor": "actor", "act": "act", "target": "",
                        "object": "object", "mode": "의무", "function": "기타",
                        "proviso": False}
            return {"frames": [row(4), row(999)]}

    view, article = _view()
    extracted, meta = frames.extract_jo(FakeLLM(), view, article)
    assert [row["node"] for row in extracted] == [4]
    assert meta["dropped"] == 1
