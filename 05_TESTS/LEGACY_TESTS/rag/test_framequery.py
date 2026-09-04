"""프레임 렉시컬 진입 — 3-그램 포함도 매칭과 vecfirst 배선 (2026-08-20 실측에서).

배경: 벡터 채널이 낱말 겹침으로 이웃 조에 끌리는 미스(골든 t3-07: '성과보수' →
제98조의2 투자일임, 정답은 제71조 3호)가 있었고, 조문 프레임의 행위 어휘와
질의 슬롯을 포함도로 맞추면 정답 조가 1위로 회복됐다. 임베딩 판(FrameIndex)이
아니라 렉시컬 판(lex_hits)이 배선이다 — CPU 임베딩 2건/초로는 15만 텍스트를
못 굽는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import framequery, vecfirst                   # noqa: E402
from lawrag.core.rag.index import Index                            # noqa: E402


def _row(jo, act, actor="투자매매업자", mode="금지", function="제한", object_=""):
    return {"jo": jo, "node": jo, "actor": actor, "act": act, "target": "",
            "object": object_, "mode": mode, "function": function,
            "_g": {k: framequery._grams(v) for k, v in
                   (("act", act), ("object", object_), ("actor", actor), ("target", ""))}}


ROWS = [
    _row(600, "조사분석자료 작성을 담당하는 자에 대하여 대통령령으로 정하는 "
              "기업금융업무와 연동된 성과보수를 지급하는 행위", object_="성과보수"),
    _row(700, "성과보수를 받아서는 아니 된다", actor="투자자문업자", object_="성과보수"),
    _row(800, "성과보수를 산정한다", actor="집합투자업자", mode="기타", function="절차",
         object_="성과보수"),
]


def test_containment_beats_word_overlap():
    """질의 act 가 행 act 의 부분이면 포함도 1.0 — 긴 조문 문장이 벌점을 받지 않는다."""
    qf = {"actor": "투자매매업자", "act": "성과보수를 지급", "object": "성과보수",
          "mode": "금지", "function": "제한"}
    ranked = framequery.score_rows(qf, ROWS)
    assert ranked and ranked[0][1]["jo"] == 600, [(s, r["jo"]) for s, r in ranked]


def test_closed_slots_break_ties():
    """열린 칸이 비슷하면 mode·function 일치가 가른다 — '기타'는 중립."""
    qf = {"act": "성과보수", "object": "성과보수", "mode": "금지", "function": "제한"}
    ranked = framequery.score_rows(qf, ROWS)
    jos = [r["jo"] for _, r in ranked]
    assert jos.index(700) < jos.index(800), jos   # 금지·제한 일치가 기타·절차보다 앞


def test_floor_drops_noise():
    """포함도가 바닥(0.5) 아래면 후보조차 아니다."""
    qf = {"act": "단독으로 인수", "object": "주식", "mode": "금지", "function": "제한"}
    assert framequery.score_rows(qf, ROWS) == []


def _mini_index(tmp_path, monkeypatch):
    """문서 하나(제71조·제98조의2)와 프레임 파일이 있는 진짜 Index."""
    nodes = [
        {"id": 600, "parent": None, "level": 1, "surface": "제71조",
         "title": "불건전 영업행위의 금지", "page": 1, "span": [0, 1]},
        {"id": 700, "parent": None, "level": 1, "surface": "제98조의2",
         "title": "성과보수의 제한", "page": 1, "span": [1, 2]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "text": "성과보수를 지급하는 행위 금지", "kind": "text"},
        {"idx": 1, "page": 1, "text": "성과보수를 받아서는 아니 된다", "kind": "text"},
    ]
    idx = Index.from_docs([("d1", {"name": "자본시장법"},
                            {"nodes": nodes, "blocks": blocks})])
    fdir = tmp_path / "frames"
    fdir.mkdir()
    rows = [{k: v for k, v in r.items() if k != "_g"} for r in ROWS[:2]]
    (fdir / "d1.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    monkeypatch.setenv("RAG_FRAMES_DIR", str(fdir))
    framequery._lex_cache.update(sig=None, rows=None)   # 환경이 바뀌었다
    return idx


class _FakeLLM:
    """1콜(열린 슬롯)은 구어 조각을, 2콜(메뉴)은 성과보수 지급 메뉴 항목을 고른다
    — 실전 하이쿠의 관측된 행동(열린 생성은 구어를 벗어나지 못한다)을 흉내낸다."""
    log: list = []

    def structured(self, kind, system, user, schema, **kw):
        base = {"actor": "투자매매업자", "target": "", "object": "성과보수",
                "mode": "금지", "function": "제한"}
        if "[행위 어휘 메뉴]" in user:
            picks = [int(l.split(".")[0]) for l in user.splitlines()  # 닫힌 선택 — 번호로
                     if l[:1].isdigit() and "성과보수를 지급" in l][:3]
            return {"frames": [{**base, "picks": picks}]}
        return {"frames": [{**base, "act": "성과보수를 지급"}]}   # 열린 생성 — 조문 어휘 미달


def test_lex_hits_returns_jo_coordinates(tmp_path, monkeypatch):
    idx = _mini_index(tmp_path, monkeypatch)
    hits, meta = framequery.lex_hits(idx, _FakeLLM(), "성과급 줘도 되나?")
    assert hits and hits[0]["doc_id"] == "d1" and hits[0]["node"] == 600, hits
    assert meta["frames"], "질의 슬롯이 관측에 남아야 한다"


def test_lex_hits_without_llm_is_empty():
    hits, meta = framequery.lex_hits(None, None, "질문")
    assert hits == [] and meta["hits"] == []


def test_vecfirst_gets_frame_entry(tmp_path, monkeypatch):
    """배선 — 프레임 좌표가 진입 구역(kind=프레임)으로 선다. 벡터 미스여도 온다."""
    idx = _mini_index(tmp_path, monkeypatch)
    monkeypatch.setattr(vecfirst.vector_mod, "search", lambda *a, **k: [])
    sections, meta = vecfirst.retrieve(idx, "성과급 줘도 되나?", llm=_FakeLLM())
    frame = [s for s in sections if s.kind == "프레임"]
    assert frame and frame[0].node == 600, [(s.kind, s.node) for s in sections]
    assert meta["frame_hits"], meta


def test_vecfirst_frame_entry_respects_switch(tmp_path, monkeypatch):
    from lawrag.core.rag import switches
    idx = _mini_index(tmp_path, monkeypatch)
    monkeypatch.setenv("STRUCTURE_STORE", str(tmp_path / "store"))
    switches.set_switch("frame_entry", False)
    try:
        monkeypatch.setattr(vecfirst.vector_mod, "search", lambda *a, **k: [])
        sections, meta = vecfirst.retrieve(idx, "성과급 줘도 되나?", llm=_FakeLLM())
        assert not [s for s in sections if s.kind == "프레임"]
    finally:
        switches.set_switch("frame_entry", True)
