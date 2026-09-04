"""OQL — 패턴 검증·걷기 실행·마일스톤의 계약을 시험한다. LLM 없음."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import oql                            # noqa: E402
from lawrag.core.rag.graph import Graph                    # noqa: E402
from lawrag.core.rag.index import Index                    # noqa: E402
from tests.rag.test_graph import _docs              # noqa: E402


def _graph():
    return Graph.from_index(Index.from_docs(_docs()))


# ---------------------------------------------------------------- 카탈로그
def test_기본_카탈로그가_검증을_통과한다():
    pats = oql.load()
    assert {p["id"] for p in pats} >= {"sec_by_term", "bridge_by_term",
                                       "neighbors_of_sec", "terms_of_sec"}


def _base():
    return {"id": "x", "world": "doc", "limit": 10,
            "parameters": [{"name": "tag", "type": "string", "required": True}],
            "traversal": {"seed": {"labels": ["Term"],
                                   "match": {"key_prop": "key", "param": "tag"}},
                          "steps": [{"rel": "MENTIONS", "direction": "out",
                                     "target_label": "Section", "alias": "sec"}]},
            "return": [{"expr": "sec.doc", "as": "doc"}]}


def test_검증_limit_필수_상한():
    p = _base(); p.pop("limit")
    with pytest.raises(ValueError, match="limit"):
        oql.validate(p)
    p = _base(); p["limit"] = 9999
    with pytest.raises(ValueError, match="limit"):
        oql.validate(p)


def test_검증_선언_안_된_파라미터_거부():
    p = _base(); p["traversal"]["seed"]["match"]["param"] = "ghost"
    with pytest.raises(ValueError, match="parameters"):
        oql.validate(p)


def test_검증_return_식_화이트리스트():
    p = _base(); p["return"] = [{"expr": "sec.doc; DROP", "as": "doc"}]
    with pytest.raises(ValueError, match="화이트리스트"):
        oql.validate(p)


def test_검증_마일스톤은_return_의_as_만():
    p = _base(); p["milestones"] = {"by": "ghost"}
    with pytest.raises(ValueError, match="milestones"):
        oql.validate(p)


# ---------------------------------------------------------------- 걷기
def _pat(pid):
    return next(p for p in oql.load() if p["id"] == pid)


def test_용어에서_구역으로_걷는다():
    res = oql.execute(_graph(), _pat("sec_by_term"), {"tag": "설명의무"})
    assert res["count"] >= 2                            # d1 제19조 + d2 지침
    docs = {r["doc"] for r in res["rows"]}
    assert docs == {"KSB.pdf", "GUIDE.pdf"}
    r = res["rows"][0]
    assert r["doc_id"] and r["node"] is not None and r["path"]   # 좌표가 늘 붙는다


def test_브리지_걷기는_다른_문서로_간다():
    res = oql.execute(_graph(), _pat("bridge_by_term"), {"tag": "설명의무"})
    assert res["count"] >= 1
    # 시드 구역과 같은 문서는 계층이 담당 — 브리지 결과에는 늘 상대 문서가 있다
    assert {"KSB.pdf", "GUIDE.pdf"} >= {r["doc"] for r in res["rows"]}


def test_구역_시드로_이웃을_걷는다():
    res = oql.execute(_graph(), _pat("neighbors_of_sec"), {"sec": "d1:2"})
    assert [r["node"] for r in res["rows"]] == [3]      # 형제는 제21조 하나


def test_필수_파라미터_누락은_예외():
    with pytest.raises(ValueError, match="누락"):
        oql.execute(_graph(), _pat("sec_by_term"), {})


def test_limit_이_결과를_자른다():
    p = dict(_pat("sec_by_term")); p["limit"] = 1
    res = oql.execute(_graph(), p, {"tag": "설명의무"})
    assert res["count"] == 1


# ---------------------------------------------------------------- 마일스톤
def test_마일스톤_버킷과_누적_컷():
    rows = [{"doc": "A", "page": 1, "preview": "가"},
            {"doc": "A", "page": 2, "preview": "나"},
            {"doc": "B", "page": 9, "preview": "다"}]
    pat = {"milestones": {"by": "doc", "order": "page", "preview": "preview",
                          "cutoff": True}}
    by, ms, cutoff = oql.build_milestones(pat, rows)
    assert by == "doc" and cutoff
    assert [m["key"] for m in ms] == ["A", "B"]         # order=page 순
    assert ms[0]["count"] == 2 and ms[0]["preview"] == "가"
    assert len(oql.filter_by_depth(rows, by, ms, 1)) == 2    # 1 = 첫 버킷까지 누적
    assert oql.filter_by_depth(rows, by, ms, "ALL") == rows
    assert oql.filter_by_depth(rows, by, ms, "NONE") == []
    assert len(oql.filter_by_depth(rows, by, ms, ["B"])) == 1


def test_렌더는_빈_키에도_죽지_않는다():
    pat = {"id": "x", "doc_type": "시험", "render": "- {doc} ({ghost})"}
    out = oql.render_block(pat, [{"doc": "A"}])
    assert "### 시험" in out and "- A ()" in out
    assert oql.render_block(pat, []) is None
