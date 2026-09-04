"""마디 성격 태그와 동반 두 종 — 정의·제재 (lawrag/core/rag/tags.py, expand.py).

여기서 지키는 것 다섯:
  (1) 다중 태그 — 한 마디가 정의·단서·정량을 **동시에** 가질 수 있다
      (실물: 증권발행공시규정 제1-2조 ⑦). enum 하나로 뭉개지 않는다.
  (2) 제목 없는 정의 조 — 자본시장법 제3~8조의2처럼 제목에 '정의'가 없어도
      본문 선언('이 법에서 "X"란')이 정의 조를 잡는다.
  (3) 관할 — 정의 조가 여럿일 때(금융투자업규정 11개) 최근접 스코프 +
      문서 대표만 동반하고, 착지가 정의 조 자신이면 침묵한다.
  (4) 제재 동반 — 착지가 의무·금지 조문일 때만, 벌칙 조의 역간선
      ("제N조를 위반한 자는…")을 싣는다. rel 이 아니라 출발점의 성격이 가른다.
  (5) 정량은 원문 표기 그대로 — "100분의 25"를 "25%"로 바꿔 적지 않는다
      (grounding). 기준(base)은 문면에 붙었을 때만 담는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import expand, switches, tags            # noqa: E402
from lawrag.core.rag.answer import Section                    # noqa: E402
from lawrag.core.rag.index import Index                       # noqa: E402


def _doc():
    """은행법 축소판 — 정의 조 둘(제목 판·선언 판), 의무+단서+정량 조, 벌칙 조."""
    return ("d1", {"name": "은행법(시험)", "enforce": "20260101"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1장",
         "title": "총칙", "page": 1, "span": [0, 5]},
        {"id": 2, "parent": 1, "level": 2, "surface": "제1조",
         "title": "목적", "page": 1, "span": [1, 2]},
        {"id": 3, "parent": 1, "level": 2, "surface": "제2조",
         "title": "정의", "page": 1, "span": [2, 5]},
        {"id": 4, "parent": None, "level": 1, "surface": "제2장",
         "title": "업무", "page": 2, "span": [5, 8]},
        {"id": 5, "parent": 4, "level": 2, "surface": "제5조",
         "title": "건전성 유지", "page": 2, "span": [6, 7]},
        {"id": 6, "parent": 4, "level": 2, "surface": "제6조",
         "title": "전문투자자", "page": 2, "span": [7, 8]},
        {"id": 7, "parent": None, "level": 1, "surface": "제3장",
         "title": "벌칙", "page": 3, "span": [8, 10]},
        {"id": 8, "parent": 7, "level": 2, "surface": "제10조",
         "title": "벌칙", "page": 3, "span": [9, 10]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제1장 총칙", "kind": "text"},
        {"idx": 1, "page": 1, "text": "제1조(목적) 이 법은 은행의 건전한 운영을 "
         "목적으로 한다.", "kind": "text"},
        {"idx": 2, "page": 1, "text": "제2조(정의) 이 법에서 사용하는 용어의 뜻은 "
         "다음과 같다.", "kind": "text"},
        {"idx": 3, "page": 1, "text": "1. \"은행\"이란 예금을 받아 자금을 대출하는 "
         "자를 말한다.", "kind": "text"},
        {"idx": 4, "page": 1, "text": "2. \"자기자본\"이란 자본금과 적립금의 합계를 "
         "말한다.", "kind": "text"},
        {"idx": 5, "page": 2, "text": "제2장 업무", "kind": "text"},
        {"idx": 6, "page": 2, "text": "제5조(건전성 유지) ① 은행은 자기자본의 "
         "100분의 25 이내에서 신용공여를 하여야 한다. 다만, 국채는 그러하지 "
         "아니하다.", "kind": "text"},
        {"idx": 7, "page": 2, "text": "제6조(전문투자자) 이 법에서 \"전문투자자\"란 "
         "위험을 감수할 능력이 있는 자를 말한다.", "kind": "text"},
        {"idx": 8, "page": 3, "text": "제3장 벌칙", "kind": "text"},
        {"idx": 9, "page": 3, "text": "제10조(벌칙) 제5조를 위반한 자는 1년 이하의 "
         "징역 또는 1천만원 이하의 벌금에 처한다.", "kind": "text"},
    ]})


def _use_engine(monkeypatch, tmp_path, off=()):
    p = tmp_path / "engine.json"
    if off:
        p.write_text(json.dumps({"switches": {k: False for k in off}},
                                ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("RAG_ENGINE_RULES", str(p))
    switches._cache.update(mtime=None, ovr={})
    return p


def _landed(idx, node=5):
    v = idx.docs["d1"]
    n = v.by_id[node]
    return Section(n=1, doc_id="d1", doc=v.name, node=node,
                   path=v.path(node), page=n.get("page"),
                   kind="벡터", matched="코사인 0.70",
                   text=v.section_text(n))


def test_한_마디가_여러_성격을_동시에_가진다():
    idx = Index.from_docs([_doc()])
    v = idx.docs["d1"]
    marks = tags.node_marks(v, 5)                       # 제5조
    assert "의무" in marks and "단서" in marks and "정량" in marks
    assert tags.node_marks(v, 8) and "벌칙" in tags.node_marks(v, 8)


def test_제목_없는_정의_조를_본문_선언이_잡는다():
    idx = Index.from_docs([_doc()])
    v = idx.docs["d1"]
    # 제2조(제목 '정의') + 제6조(제목엔 없음 — '이 법에서 "X"란' 선언)
    assert tags.definition_jos(v) == [3, 6]


def test_관할은_최근접과_대표_그리고_자기_자신엔_침묵():
    idx = Index.from_docs([_doc()])
    v = idx.docs["d1"]
    # 착지 제5조(제2장): 같은 장의 제6조(최근접) + 문서 첫 정의 조 제2조(대표)
    assert tags.governing_definitions(v, 5) == [6, 3]
    # 착지가 정의 조 자신(제2조의 호)이면 빈손
    assert tags.governing_definitions(v, 3) == []


def test_정량은_원문_표기_그대로_기준은_문면에_붙었을_때만():
    idx = Index.from_docs([_doc()])
    v = idx.docs["d1"]
    rows = tags.quant_rules(v, 5)
    assert {"종류": "비율", "표기": "100분의 25", "기준": "자기자본"} in rows
    # 벌칙 조 — 기간·금액이 기준 없이 잡힌다
    kinds = {r["종류"] for r in tags.quant_rules(v, 8)}
    assert "기간" in kinds and "금액" in kinds


def test_정의_동반은_쓰인_정의어의_호만_없으면_관할_조로(monkeypatch, tmp_path):
    """제5조 본문에 '은행'·'자기자본'(제2조)은 쓰였고 '전문투자자'(제6조)는 안 쓰였다 —
    쓰인 정의만 온다(정의 조 통째보다 좁다). 쓰인 정의어가 하나도 없으면 관할 정의 조."""
    _use_engine(monkeypatch, tmp_path)
    idx = Index.from_docs([_doc()])
    out = expand.expand_floor(idx, [_landed(idx)])
    defs = [s for s in out if s.kind == "정의"]
    assert {s.node for s in defs} == {3}
    assert any("은행" in s.matched or "자기자본" in s.matched for s in defs)
    # 정의어가 하나도 안 쓰인 착지(제10조 벌칙 — 은행·자기자본·전문투자자 없음)
    # → 관할 정의 조로 폴백 (제3장엔 최근접이 없어 문서 대표 제2조만)
    out2 = expand.expand_floor(idx, [_landed(idx, node=8)])
    assert {s.node for s in out2 if s.kind == "정의"} == {3}
    # 끄면 침묵
    _use_engine(monkeypatch, tmp_path, off=("floor_definition",))
    out = expand.expand_floor(idx, [_landed(idx)])
    assert not [s for s in out if s.kind == "정의"]


def test_제재_동반은_의무_조문에서만_벌칙_역간선을_탄다(monkeypatch, tmp_path):
    _use_engine(monkeypatch, tmp_path)
    idx = Index.from_docs([_doc()])
    # 착지 제5조(의무) — 제10조가 "제5조를 위반한"으로 겨눈다 → 제재 동반
    out = expand.expand_floor(idx, [_landed(idx, node=5)])
    sanc = [s for s in out if s.kind == "제재"]
    assert [s.node for s in sanc] == [8]
    assert sanc[0].ref_src["node"] == 5                 # 경위 — 어디서 왔나
    # 착지 제1조(의무 아님) — 같은 문서지만 제재는 침묵
    out = expand.expand_floor(idx, [_landed(idx, node=2)])
    assert not [s for s in out if s.kind == "제재"]
    # 끄면 침묵
    _use_engine(monkeypatch, tmp_path, off=("floor_sanction",))
    out = expand.expand_floor(idx, [_landed(idx, node=5)])
    assert not [s for s in out if s.kind == "제재"]


def test_편조_체계의_정의_조도_잡힌다():
    """규정류 제3-6조 — 조 표면형을 좁게 잡으면 조용히 빠진다 (LEGAL_DOMAIN §2)."""
    doc = ("d2", {"name": "규정(시험)"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제3편",
         "title": "영업", "page": 1, "span": [0, 2]},
        {"id": 2, "parent": 1, "level": 2, "surface": "제3-6조",
         "title": "용어의 정의", "page": 1, "span": [1, 2]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제3편 영업", "kind": "text"},
        {"idx": 1, "page": 1, "text": "제3-6조(용어의 정의) 이 편에서 \"운용\"이란 "
         "재산을 관리하는 것을 말한다.", "kind": "text"},
    ]})
    idx = Index.from_docs([doc])
    assert tags.definition_jos(idx.docs["d2"]) == [2]
