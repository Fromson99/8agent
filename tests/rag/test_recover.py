"""회복 루프 — 사다리 순서·첫 성공 멈춤·fail-closed 검증을 시험한다.

LLM 은 스텁이다. 시험하는 것은 판단이 아니라 **계약**이다: 어느 단이 언제
돌고, 신뢰 문턱 미만이 정말 전량 폐기되고, 결과에 via 가 남는가.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import recover                        # noqa: E402
from lawrag.core.rag.answer import sections_from_coords    # noqa: E402
from lawrag.core.rag.index import Index                    # noqa: E402
from tests.rag.test_graph import _docs              # noqa: E402


def _risk_doc():
    """제목은 있는데 본문에 그 말이 없는 문서 — 원문 단은 빗나가고 수색대만 잡는다."""
    return ("d3", {"name": "RISK.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "1.",
         "title": "위험등급", "page": 1, "span": [0, 1]}],
        "blocks": [{"idx": 0, "page": 1,
                    "text": "1등급부터 5등급까지 구분한다", "kind": "text"}]})


def _index(extra=None):
    return Index.from_docs(_docs() + (extra or []))


class StubLLM:
    model = "stub"

    def __init__(self, by_kind=None):
        self.by_kind = {k: list(v) for k, v in (by_kind or {}).items()}
        self.calls = []

    def structured(self, kind, system, user, schema, **kw):
        self.calls.append(kind)
        q = self.by_kind.get(kind)
        return q.pop(0) if q else None

    def totals(self):
        return {"calls": len(self.calls)}


# ---------------------------------------------------------------- 단별
def test_의미해석이_잡으면_거기서_멈춘다():
    llm = StubLLM({"rag.recover.sense": [{
        "route": "use_terms", "reason": "의미 연결",
        "selected": [{"id": 0, "confidence": 0.9, "reason": "같은 제도"}],
        "explore_branches": []}]})
    rec = recover.run(llm, _index(), "고객에게 상품을 알릴 의무")
    assert rec.rungs_fired == ["의미해석"]
    assert rec.coords and all(c["via"] == "의미해석" for c in rec.coords)
    assert llm.calls == ["rag.recover.sense"]           # 아래 단은 돌지 않았다


def test_의미해석_신뢰_문턱_미만은_버려진다():
    llm = StubLLM({"rag.recover.sense": [{
        "route": "use_terms", "reason": "",
        "selected": [{"id": 0, "confidence": 0.3, "reason": "약함"}],
        "explore_branches": []}]})
    rec = recover.run(llm, _index(), "존재하지않는말")
    assert "의미해석" not in rec.rungs_fired


def test_깔때기는_계층을_내려가며_고른다():
    llm = StubLLM({
        "rag.recover.sense": [{"route": "deep_explore", "reason": "",
                               "selected": [], "explore_branches": [
                                   {"doc_id": "d1", "reason": "규정 문서"}]}],
        "rag.recover.nav": [{"picks": ["d1:1"], "done": False, "reason": ""}],
        "rag.recover.judge": [{"keep": ["d1:2"], "confidence": 0.8,
                               "enough": True, "reason": "조문이 있다"}],
    })
    rec = recover.run(llm, _index(), "설명 의무 조문")
    assert rec.rungs_fired == ["깔때기"]
    assert rec.coords[0]["doc_id"] == "d1" and rec.coords[0]["node"] == 2
    assert rec.meta["funnel"]["steps"] == 1


def test_깔때기_신뢰_문턱_미만은_전량_폐기():
    llm = StubLLM({
        "rag.recover.nav": [{"picks": ["d1:1"], "done": True, "reason": ""}],
        "rag.recover.judge": [{"keep": ["d1:2"], "confidence": 0.4,
                               "enough": True, "reason": "약함"}],
    })
    # 원문 단이 잡도록 질의에 본문 토큰을 둔다 — 깔때기 폐기 후 사다리가 계속 내려간다
    rec = recover.run(llm, _index(), "설명의무 이행")
    assert "깔때기" not in rec.rungs_fired
    assert rec.rungs_fired == ["원문"]                  # 다음 단이 잡았다


def test_원문_단은_LLM_없이_돈다():
    rec = recover.run(None, _index(), "설명의무 이행 지침")
    assert rec.rungs_fired == ["원문"]
    assert all(c["via"] == "원문" for c in rec.coords)


def test_수색대는_제목_용어로_잡고_검증을_통과해야_남는다():
    llm = StubLLM({"rag.recover.verify": [
        {"keep": ["b0"], "confidence": 0.8, "reason": "관련"}]})
    # '위험등급' 은 제목에만 있다 — 원문 단은 빗나가고 수색대의 걷기가 잡는다
    rec = recover.run(llm, _index([_risk_doc()]), "위험등급")
    assert rec.rungs_fired == ["수색대"]
    assert rec.coords[0]["doc_id"] == "d3" and rec.coords[0]["via"] == "수색대"


def test_수색대_검증_fail_closed():
    llm = StubLLM({"rag.recover.verify": [
        {"keep": ["b0"], "confidence": 0.3, "reason": "약함"}]})
    rec = recover.run(llm, _index([_risk_doc()]), "위험등급")
    assert "수색대" not in rec.rungs_fired
    assert rec.coords == []                             # 문턱 미만 → 전량 폐기


def test_둘러보기는_고를_게_없으면_정직하게_되묻는다():
    llm = StubLLM({"rag.recover.orient": [{"pick": [], "ask_user": ""}]})
    rec = recover.run(llm, _index(), "완전히 무관한 이야기")
    assert rec.coords == []
    assert "가진 자료" in rec.ask_user                  # 보유 문서를 들어 되묻는다


def test_사다리_기록이_남는다(tmp_path, monkeypatch):
    # 도메인 단이 실제 위키·사전을 물지 않게 빈 경로로 격리한다
    monkeypatch.setenv("WIKI_STORE", str(tmp_path / "빈위키"))
    monkeypatch.setenv("RAG_ALIASES", str(tmp_path / "없음.json"))
    rec = recover.run(None, _index(), "존재하지않는말")
    stages = [t["stage"] for t in rec.trail]
    assert stages == ["쟁점 재회수", "명칭 확장",          # ⓪ 도메인 단 (법령판)
                      "의미해석", "깔때기", "원문", "수색대", "둘러보기"]


# ---------------------------------------------------------------- 좌표 → 구역
def test_좌표가_구역이_되고_via_가_남는다():
    idx = _index()
    secs = sections_from_coords(idx, [
        {"doc_id": "d1", "node": 2, "via": "의미해석", "why": "용어 연결"}])
    assert secs[0].kind == "탐색(의미해석)"
    assert secs[0].path.endswith("설명의무")
    assert secs[0].n == 1
