"""회복의 도메인 단 — 창고를 아는 지식이 범용 사다리보다 먼저 선다.

지키는 것 넷:
  (1) 법령판 두 단(쟁점 재회수·명칭 확장)이 등록부에 있다 — 전부 결정론.
  (2) 명칭 확장 — 약칭만 아는 질문이 정식 명칭 문서의 좌표에 닿는다.
  (3) 쟁점 재회수 — 카드의 조문질의(probe)로 재검색한다. 조문 후보는 안 쓴다.
  (4) run() 통합 — 도메인 단이 찾으면 범용 사다리는 돌지 않고(LLM 없이도),
      스위치를 끄면 도메인 단 자체가 서지 않는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import recover, recover_domains, switches      # noqa: E402
from lawrag.core.rag.index import Index                             # noqa: E402


def _law_doc():
    return ("L1", {"name": "자본시장과 금융투자업에 관한 법률.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제12조",
         "title": "인가", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제12조(인가) 투자매매업 인가를 받아야 한다.",
         "kind": "text"},
    ]})


def _aliases(tmp_path, monkeypatch) -> None:
    p = tmp_path / "aliases.json"
    p.write_text(json.dumps({"자본시장법": "자본시장과 금융투자업에 관한 법률"},
                            ensure_ascii=False), "utf-8")
    monkeypatch.setenv("RAG_ALIASES", str(p))


def _wiki(tmp_path, monkeypatch) -> None:
    w = tmp_path / "wiki"
    (w / "쟁점").mkdir(parents=True)
    (w / "쟁점" / "실권주-인수.md").write_text(
        "# 실권주 인수\n\n"
        "> 트리거: 실권주 · 유상증자\n"
        "> 조문 후보: 투자매매업 인가\n\n"     # 색인값(조 제목)과 일치 — 사다리 ①이 무는 모양
        "본문.\n", "utf-8")
    (w / "index.md").write_text(
        "# 인덱스\n\n| Article | Summary | Updated |\n|---|---|---|\n"
        "| [실권주 인수](쟁점/실권주-인수.md) | 실권주 | 2026-08-14 |\n", "utf-8")
    monkeypatch.setenv("WIKI_STORE", str(tmp_path))


def test_법령판_세_단이_등록돼_있다():
    names = [r.name for r in recover_domains.rungs("law")]
    assert names == ["쟁점 재회수", "명칭 확장", "법 스코프 깔때기"]


def test_법_스코프_깔때기는_법령명이_있을_때만_그_법_안에서_돈다(tmp_path, monkeypatch):
    """어휘 격차의 우회로 — 벡터가 못 잇는 조문을 장→조 읽고 고르기로 닿는다.
    법령명이 없으면 침묵(범용 사다리의 몫), LLM 이 없으면 침묵."""
    _aliases(tmp_path, monkeypatch)
    idx = Index.from_docs([_law_doc()])
    # 이름 부르기 — 정식·축약·약칭 세 갈래
    assert recover_domains.laws_named(idx, "자본시장법상 인가는?") == ["L1"]
    assert recover_domains.laws_named(idx, "자본시장과 금융투자업에 관한 법률의 인가") == ["L1"]
    assert recover_domains.laws_named(idx, "아무 법 이름 없는 질문") == []
    # 법령명 없음 → 문서 선택 콜 1회 (빈손이면 침묵) — 벡터가 아니라 구조로 내려간다
    class _NoPick:
        log = []
        def structured(self, kind, *a, **k):
            assert kind == "rag.recover.pickdocs"
            return {"picks": [], "reason": "확신 없음"}
    coords, meta = recover_domains.law_scoped_funnel(_NoPick(), idx, "법 이름 없는 질문")
    assert coords == [] and "문서 선택도 빈손" in meta["note"]
    # LLM 없음 → 침묵
    coords, meta = recover_domains.law_scoped_funnel(None, idx, "자본시장법상 인가는?")
    assert coords == [] and "LLM 없음" in meta["note"]


def test_명칭_확장이_약칭을_정식_명칭으로_잇는다(tmp_path, monkeypatch):
    _aliases(tmp_path, monkeypatch)
    idx = Index.from_docs([_law_doc()])
    coords, meta = recover_domains.law_alias_expand(None, idx, "자본시장법상 인가 요건은?")
    assert coords and coords[0]["doc_id"] == "L1" and coords[0]["via"] == "명칭 확장"
    assert "자본시장법→자본시장과 금융투자업에 관한 법률" in meta["note"]
    # 정식 명칭이 이미 질문에 있으면 확장하지 않는다
    coords2, meta2 = recover_domains.law_alias_expand(
        None, idx, "자본시장과 금융투자업에 관한 법률의 인가 요건은?")
    assert coords2 == [] and meta2["note"] == "약칭 없음"


class _ProbeLLM:
    """쟁점 분해 LLM 대역 — 카드를 고르고 조문 문체 재작성(probe)을 낸다."""
    log = []

    def structured(self, kind, system, user, schema, **kw):
        return {"cards": [{"slug": "쟁점/실권주-인수", "why": "실권주",
                           "조문질의": "투자매매업 인가"}]}   # 색인값(조 제목)과 일치


def test_쟁점_재회수는_조문질의로만_찾는다_조문_후보는_안_쓴다(tmp_path, monkeypatch):
    """카드의 소임은 문체 번역(probe → 검색)이지 좌표 연결이 아니다 (2026-08-18).
    트리거 판은 재작성이 없으니 침묵하고, LLM 판(issue_spot_pre)이 probe 를 내면
    그 문장으로 검색한다 — 카드 메타의 조문 후보는 어느 쪽에서도 안 읽는다."""
    _wiki(tmp_path, monkeypatch)
    engine = tmp_path / "engine.json"
    monkeypatch.setenv("RAG_ENGINE_RULES", str(engine))
    switches._cache.update(mtime=None, ovr={})
    idx = Index.from_docs([_law_doc()])
    q = "유상증자에서 실권주가 생기면 어떻게 되나요?"
    # 트리거 판 — 카드는 서지만 probe 가 없다 → 조문 후보로 대신 찾지 않는다
    coords, meta = recover_domains.law_issue_respot(None, idx, q)
    assert coords == [] and "조문질의 없음" in meta["note"]
    # LLM 판 — probe 로 검색해 좌표를 찾는다
    engine.write_text(json.dumps({"switches": {"issue_spot_pre": True}}), "utf-8")
    switches._cache.update(mtime=None, ovr={})
    coords, meta = recover_domains.law_issue_respot(_ProbeLLM(), idx, q)
    assert coords and coords[0]["doc_id"] == "L1"
    assert coords[0]["via"] == "쟁점 재회수"
    assert meta["cards"] == ["쟁점/실권주-인수"]


def test_run_통합_도메인_단이_먼저_서고_스위치로_꺼진다(tmp_path, monkeypatch):
    _aliases(tmp_path, monkeypatch)
    monkeypatch.setenv("WIKI_STORE", str(tmp_path / "빈위키"))
    engine = tmp_path / "engine.json"
    monkeypatch.setenv("RAG_ENGINE_RULES", str(engine))
    switches._cache.update(mtime=None, ovr={})
    idx = Index.from_docs([_law_doc()])
    rec = recover.run(None, idx, "자본시장법상 인가 요건은?")     # llm 없이도
    assert rec.rungs_fired == ["명칭 확장"] and rec.coords
    assert rec.trail[0]["stage"] == "쟁점 재회수"                 # 순서: 쟁점 → 명칭
    assert rec.trail[1]["stage"] == "명칭 확장"
    # 스위치 off — 도메인 단이 서지 않고 범용 사다리(원문 단)로 간다
    engine.write_text(json.dumps({"switches": {"domain_recover": False}}),
                      "utf-8")
    switches._cache.update(mtime=None, ovr={})
    rec2 = recover.run(None, idx, "자본시장법상 인가 요건은?")
    assert all(t["stage"] not in ("쟁점 재회수", "명칭 확장") for t in rec2.trail)