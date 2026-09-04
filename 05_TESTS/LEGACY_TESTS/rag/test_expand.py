"""타입 간선 확장 — 결정론 바닥과 LLM 항해 (lawrag/core/rag/expand.py).

여기서 지키는 것 넷:
  (1) 역방향 배제 — 착지 조문을 배제하는 조항이 **무조건** 실린다. 간선
      방향이 반대라 기존 확장(expand_refs)은 원리상 못 데려오는 간선이다.
  (2) 위임 — delegation.json 의 좌표를 타고 대상 조문이 동반된다. 착지가
      항이라도 조로 올라가 걷는다.
  (3) 준용(순방향 바닥) — rel=준용 간선은 빈자리 경쟁 없이 실린다.
  (4) 항해 — LLM 은 본문이 아니라 간선 카드만 보고 고르고, 걸음은
      kind="항해" 경위로 남는다. LLM 이 없으면 항해는 없다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import delegation, expand                # noqa: E402
from lawrag.core.rag.answer import Section                    # noqa: E402
from lawrag.core.rag.index import Index                       # noqa: E402


def _doc():
    return ("d1", {"name": "규정.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1장",
         "title": "총칙", "page": 1, "span": [0, 5]},
        {"id": 4, "parent": 1, "level": 2, "surface": "제4조",
         "title": "설정", "page": 1, "span": [1, 2]},
        {"id": 9, "parent": 4, "level": 3, "surface": "①",
         "title": "", "page": 1, "span": [1, 2]},
        {"id": 5, "parent": 1, "level": 2, "surface": "제4조의2",
         "title": "특례", "page": 2, "span": [2, 3]},
        {"id": 6, "parent": 1, "level": 2, "surface": "제6조",
         "title": "절차", "page": 2, "span": [3, 4]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제1장 총칙", "kind": "text"},
        {"idx": 1, "page": 1, "text": "제4조(설정) ① 신탁은 계약으로 설정한다.",
         "kind": "text"},
        {"idx": 2, "page": 2, "text": "제4조의2(특례) 제4조에도 불구하고 특례를 "
         "둘 수 있다.", "kind": "text"},
        {"idx": 3, "page": 2, "text": "제6조(절차) 절차는 「세부기준」 제2조를 "
         "준용한다. 제4조를 참고한다.", "kind": "text"},
    ]})


def _d2():
    return ("d2", {"name": "세부기준.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제2조",
         "title": "세부 절차", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제9조",
         "title": "고시 기준", "page": 1, "span": [1, 2]},
        {"id": 3, "parent": None, "level": 1, "surface": "제3조",
         "title": "수임 조문", "page": 1, "span": [2, 3]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제2조(세부 절차) 절차의 세부는 이와 같다.",
         "kind": "text"},
        {"idx": 1, "page": 1, "text": "제9조(고시 기준) 기준은 이와 같다.",
         "kind": "text"},
        {"idx": 2, "page": 1, "text": '제3조(수임 조문) 「규정」 제4조에서 '
         '"특례기준"이란 다음 각 호를 말한다.', "kind": "text"},
    ]})


def _land(idx, doc_id, node) -> list[Section]:
    v = idx.docs[doc_id]
    return [Section(n=1, doc_id=doc_id, doc=v.name, node=node,
                    path=v.path(node), page=1, kind="벡터", matched="시험",
                    text=v.section_text(v.by_id[node]))]


def test_역방향_배제가_무조건_동반된다():
    idx = Index.from_docs([_doc()])
    out = expand.expand_floor(idx, _land(idx, "d1", 4))      # 제4조 착지
    got = {(s.doc_id, s.node): s for s in out}
    ex = got.get(("d1", 5))
    assert ex is not None and ex.kind == "배제"               # 제4조의2 가 실린다
    assert "배제" in ex.matched


def test_착지가_항이라도_조의_배제를_찾는다():
    idx = Index.from_docs([_doc()])
    out = expand.expand_floor(idx, _land(idx, "d1", 9))      # 제4조 ① 착지
    assert ("d1", 5) in {(s.doc_id, s.node) for s in out}


def test_위임이_delegation_좌표를_탄다(tmp_path, monkeypatch):
    p = tmp_path / "delegation.json"
    p.write_text(json.dumps({"edges": [
        {"kind": "위임행정규칙",
         "src": {"doc_id": "d1", "node": 4, "name": "규정", "jo": "제4조"},
         "dst": {"doc_id": "d2", "node": 2, "name": "세부기준", "jo": "제9조"},
         "link": "금융위원회가 정하여 고시하는"},
        {"kind": "인용법령",                                   # 위임 계열 아님 — 안 탄다
         "src": {"doc_id": "d1", "node": 4},
         "dst": {"doc_id": "d2", "node": 1}, "link": ""},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("RAG_DELEGATION_STORE", str(p))
    delegation._cache.update(mtime=None, out={})
    idx = Index.from_docs([_doc(), _d2()])
    out = expand.expand_floor(idx, _land(idx, "d1", 9))      # 항 착지 → 조로 올라감
    got = {(s.doc_id, s.node): s for s in out}
    w = got.get(("d2", 2))
    assert w is not None and w.kind == "위임"
    assert "금융위원회가 정하여 고시하는" in w.matched
    assert ("d2", 1) not in got                               # 인용법령은 바닥이 아니다


def test_준용이_바닥으로_실린다():
    idx = Index.from_docs([_doc(), _d2()])
    out = expand.expand_floor(idx, _land(idx, "d1", 6))      # 제6조 착지
    got = {(s.doc_id, s.node): s for s in out}
    jun = got.get(("d2", 1))                                  # 「세부기준」 제2조
    assert jun is not None and jun.kind == "준용"
    # 같은 블록의 단순 참조(제4조)는 바닥이 아니다 — expand_refs 몫
    assert ("d1", 4) not in got


def test_역방향_수임이_동반된다():
    """"제4조에서 '…'이란"을 쓴 하위 문서 조문 — 시행령→규정 체인의 좌표."""
    idx = Index.from_docs([_doc(), _d2()])
    out = expand.expand_floor(idx, _land(idx, "d1", 4))      # 제4조 착지
    got = {(s.doc_id, s.node): s for s in out}
    su = got.get(("d2", 3))
    assert su is not None and su.kind == "수임"
    assert "위임을 받은 조문" in su.matched


class StubLLM:
    def __init__(self, picks):
        self.picks, self.calls = picks, []

    def structured(self, kind, system, user, schema, **kw):
        self.calls.append({"kind": kind, "user": user})
        return {"picks": self.picks, "done": True, "reason": "시험"}


def test_항해는_카드에서_고르고_경위가_남는다():
    idx = Index.from_docs([_doc(), _d2()])
    land = _land(idx, "d1", 6)                                # 제6조 — 인용 간선 보유
    llm = StubLLM(picks=[0])
    out, nav = expand.navigate(llm, idx, "절차가 뭐냐", land)
    assert nav["hops"] == 1 and len(nav["picked"]) == 1
    added = [s for s in out if s.kind == "항해"]
    assert len(added) == 1 and added[0].ref_src is not None
    assert "간선 카드" in llm.calls[0]["user"]                 # 본문이 아니라 카드를 봤다
    out2, nav2 = expand.navigate(None, idx, "질문", land)     # LLM 없으면 그대로
    assert out2 == land and nav2["hops"] == 0
