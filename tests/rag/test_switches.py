"""엔진 규칙 스위치 — 자동 규칙은 전부 사용자가 켜고 끈다 (core/rag/switches.py).

여기서 지키는 것 넷:
  (1) 기본값은 전부 켜짐 — 파일 없음 = 오늘의 시스템. 켜짐은 파일에 안 적는다.
  (2) 본문우선 — 한 문서 안 본문·부칙 번호 중복이면 본문 조로 확정(via 본문우선).
      끄면 보류로 남는다.
  (3) 선언 확정도 스위치를 따른다 — 끄면 그 참조가 보류로 내려간다.
  (4) 동반 규칙(배제)도 스위치를 따른다 — 끄면 회수에서 빠진다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.rag import expand, refs, switches            # noqa: E402
from core.rag.answer import Section                    # noqa: E402
from core.rag.index import Index                       # noqa: E402


def _use_engine(monkeypatch, tmp_path, off=()):
    p = tmp_path / "engine.json"
    if off:
        p.write_text(json.dumps({"switches": {k: False for k in off}},
                                ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("RAG_ENGINE_RULES", str(p))
    switches._cache.update(mtime=None, off=frozenset())
    return p


def test_기본은_전부_켜짐이고_끈_것만_파일에_남는다(monkeypatch, tmp_path):
    p = _use_engine(monkeypatch, tmp_path)
    assert all(s["on"] for s in switches.snapshot())
    switches.set_switch("presume", False)
    assert not switches.is_on("presume") and switches.is_on("declare")
    switches.set_switch("presume", True)          # 기본값 복귀 — 파일에서 사라진다
    assert json.loads(p.read_text())["switches"] == {}
    try:
        switches.set_switch("없는키", False)
        assert False, "모르는 스위치는 거부해야 한다"
    except ValueError:
        pass


def _dup_docs():
    """본문 제2조 + 부칙 제2조를 가진 대상 — 번호 중복의 무대."""
    target = ("T1", {"name": "타깃규정.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제2조",
         "title": "본문 조", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "부칙",
         "title": "", "page": 2, "span": [1, 3]},
        {"id": 3, "parent": 2, "level": 2, "surface": "제2조",
         "title": "경과조치", "page": 2, "span": [2, 3]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제2조(본문 조) 기준은 이와 같다.", "kind": "text"},
        {"idx": 1, "page": 2, "text": "부칙", "kind": "text"},
        {"idx": 2, "page": 2, "text": "제2조(경과조치) 종전 규정에 따른다.", "kind": "text"},
    ]})
    caller = ("c1", {"name": "부르는규정.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "목적", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제1조(목적) 「타깃규정」 제2조에 따라 정한다.",
         "kind": "text"},
    ]})
    return caller, target


def test_본문우선이_부칙_중복을_가른다(monkeypatch, tmp_path):
    _use_engine(monkeypatch, tmp_path)
    idx = Index.from_docs([*_dup_docs()])
    edges, pending = idx.cross_refs()
    e = next(x for x in edges if x["src_doc"] == "c1")
    assert (x := e)["dst_doc"] == "T1" and e["dst"] == 1     # 본문 조
    assert e["via"] == "본문우선"


def test_본문우선을_끄면_보류로_남는다(monkeypatch, tmp_path):
    _use_engine(monkeypatch, tmp_path, off=("mainbody",))
    idx = Index.from_docs([*_dup_docs()])
    edges, pending = idx.cross_refs()
    assert not any(e for e in edges if e["src_doc"] == "c1")
    assert any(p for p in pending if p["src_doc"] == "c1")


def _decl_docs():
    caller = ("c1", {"name": "갑감독규정.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "목적", "page": 1, "span": [0, 2]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": '제1조(목적) 「모범금융법」(이하 "법"이라 '
         '한다)에서 위임된 사항을 정한다.', "kind": "text"},
        {"idx": 1, "page": 1, "text": "법 제10조에 따라 기준을 정한다.", "kind": "text"},
    ]})
    law = ("L1", {"name": "모범금융법.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제10조",
         "title": "위임", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제10조(위임) 기준은 고시로 정한다.", "kind": "text"}]})
    law2 = ("L2", {"name": "다른금융법.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제10조",
         "title": "딴 조", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제10조(딴 조) 무관하다.", "kind": "text"}]})
    return caller, law, law2


def test_선언_확정을_끄면_보류로_내려간다(monkeypatch, tmp_path):
    _use_engine(monkeypatch, tmp_path, off=("declare", "presume", "mainbody"))
    idx = Index.from_docs([*_decl_docs()])
    edges, pending = idx.cross_refs()
    assert not any(e for e in edges if e.get("via") == "선언")
    assert any(p["hint"] == "법" for p in pending)
    # 켜면 확정된다
    switches.set_switch("declare", True)
    idx2 = Index.from_docs([*_decl_docs()])
    edges2, _ = idx2.cross_refs()
    assert any(e.get("via") == "선언" for e in edges2)


def test_배제_동반을_끄면_회수에서_빠진다(monkeypatch, tmp_path):
    _use_engine(monkeypatch, tmp_path, off=("floor_exclusion",))
    doc = ("d1", {"name": "규정.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제4조",
         "title": "설정", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제5조",
         "title": "특례", "page": 1, "span": [1, 2]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제4조(설정) 계약으로 설정한다.", "kind": "text"},
        {"idx": 1, "page": 1, "text": "제5조(특례) 제4조에도 불구하고 특례를 둔다.",
         "kind": "text"},
    ]})
    idx = Index.from_docs([doc])
    v = idx.docs["d1"]
    land = [Section(n=1, doc_id="d1", doc=v.name, node=1, path=v.path(1),
                    page=1, kind="벡터", matched="시험", text="")]
    out = expand.expand_floor(idx, land)
    assert not any(s.kind == "배제" for s in out)
    switches.set_switch("floor_exclusion", True)
    out2 = expand.expand_floor(idx, land)
    assert any(s.kind == "배제" for s in out2)
