"""계층 사후 교정 — 사람이 옮긴 마디가 재해석을 견디고, 트리를 깨지 않는 계약.

    교정은 result.json 을 안 건드린다(겹쳐 읽는다) — 재해석해도 살아남는다
    부모를 옮기면 level 은 부모에서 다시 센다 — 자손까지 함께 따라온다
    고리를 만드는 이동은 무시한다 — 트리가 먼저다
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import structure_fixes                          # noqa: E402
from core.rag.index import Index                          # noqa: E402


def _nodes():
    """"라." 밑에 들어가야 할 "6)" 이 형제로 붙은 문서 — 실제 오파싱의 축소판."""
    return [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "", "page": 1, "span": [0, 4]},
        {"id": 2, "parent": 1, "level": 2, "surface": "라.",
         "title": "", "page": 1, "span": [1, 2]},
        {"id": 3, "parent": 1, "level": 2, "surface": "6)",
         "title": "", "page": 1, "span": [2, 3]},
        {"id": 4, "parent": 3, "level": 3, "surface": "가)",
         "title": "", "page": 1, "span": [3, 4]},
    ]


def _doc():
    return ("d1", {"name": "규정.pdf"}, {"nodes": _nodes(), "blocks": [
        {"idx": 0, "page": 1, "text": "제1조", "kind": "text"},
        {"idx": 1, "page": 1, "text": "라. 투자운용인력의 변경", "kind": "text"},
        {"idx": 2, "page": 1, "text": "6) 집합투자업자의 합병", "kind": "text"},
        {"idx": 3, "page": 1, "text": "가) 세부", "kind": "text"},
    ]})


def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("STRUCTURE_FIXES_STORE", str(tmp_path / "structure_fixes.json"))


def test_교정은_부모를_옮기고_자손_층이_따라온다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    structure_fixes.record("d1", 3, 2, {"parent": 1}, "들여쓰기")
    out = {n["id"]: n for n in structure_fixes.apply("d1", _nodes())}
    assert out[3]["parent"] == 2 and out[3]["level"] == 3    # 라. 밑으로
    assert out[4]["level"] == 4                              # 자손도 함께 내려간다
    assert out[3]["교정됨"] is True
    assert _nodes()[2]["parent"] == 1                        # 원본은 그대로


def test_교정은_색인의_경로에_그대로_보인다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    idx = Index.from_docs([_doc()])
    assert idx.docs["d1"].path(3) == "제1조 ▸ 6)"
    structure_fixes.record("d1", 3, 2, {"parent": 1})
    idx2 = Index.from_docs([_doc()])                         # 새 색인 = 교정 반영
    assert idx2.docs["d1"].path(3) == "제1조 ▸ 라. ▸ 6)"
    assert idx2.docs["d1"].path(4) == "제1조 ▸ 라. ▸ 6) ▸ 가)"


def test_고리를_만드는_이동은_무시된다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    structure_fixes.record("d1", 1, 4, {"parent": None})      # 조를 제 자손 밑으로
    out = {n["id"]: n for n in structure_fixes.apply("d1", _nodes())}
    assert out[1]["parent"] is None                           # 트리가 먼저다


def test_사라진_마디의_교정은_조용히_빠진다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    structure_fixes.record("d1", 999, 1, {})                  # 재해석으로 사라진 마디
    out = structure_fixes.apply("d1", _nodes())
    assert [n["parent"] for n in out] == [None, 1, 1, 3]


def test_교정_되돌리기(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    structure_fixes.record("d1", 3, 2, {"parent": 1})
    assert structure_fixes.remove("d1", 3) == 1
    out = {n["id"]: n for n in structure_fixes.apply("d1", _nodes())}
    assert out[3]["parent"] == 1 and out[3]["level"] == 2
