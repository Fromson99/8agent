"""위키 맥락 라우팅 — 코드 결정론 (문서명 강신호·질의 낱말 약신호·무신호 빈손)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import switches, wikictx                       # noqa: E402


def _wiki(tmp_path: Path) -> Path:
    w = tmp_path / "wiki"
    (w / "해석원칙").mkdir(parents=True)
    (w / "법령갈래").mkdir()
    (w / "쟁점").mkdir()
    (w / "해석원칙" / "준용의-방향.md").write_text(
        "# 준용의 방향\n\n준용은 문언 범위 그대로 따라간다. "
        "「자본시장과 금융투자업에 관한 법률」 제160조가 그 예다.\n", "utf-8")
    (w / "법령갈래" / "개인정보-경계.md").write_text(
        "# 개인정보 경계\n\n「개인정보 보호법」 동의 체계.\n" + "가" * 5000, "utf-8")
    (w / "쟁점" / "실권주-인수.md").write_text(
        "# 실권주 인수\n\n"
        "> 트리거: 실권주 · 유상증자 · 제3자 배정\n"
        "> 판단 축: 투자매매업자 인수 계약이 있는가\n"
        "> 조문 후보: 「자본시장과 금융투자업에 관한 법률」 제165조의6 · "
        "「상법」 제418조\n\n"
        "실권주는 이사회 결의만으로 못 넘긴다.\n", "utf-8")
    (w / "index.md").write_text(
        "# 인덱스\n\n"
        "| Article | Summary | Updated |\n|---|---|---|\n"
        "| [준용의 방향](해석원칙/준용의-방향.md) | 준용 해석 | 2026-08-13 |\n"
        "| [개인정보 경계](법령갈래/개인정보-경계.md) | 동의 체계 | 2026-08-13 |\n"
        "| [실권주 인수](쟁점/실권주-인수.md) | 실권주 쟁점 | 2026-08-14 |\n",
        "utf-8")
    return tmp_path


def test_문서명이_강신호다(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    picks = wikictx.pick("보고서 기재사항은?",
                         {"자본시장과 금융투자업에 관한 법률"})
    assert [p["slug"] for p in picks] == ["해석원칙/준용의-방향"]
    assert "자본시장과 금융투자업에 관한 법률" in picks[0]["why"]


def test_질의_낱말은_제목·요약에만_약신호(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    picks = wikictx.pick("준용 조항은 어디까지 가나", set())
    assert picks and picks[0]["slug"] == "해석원칙/준용의-방향"


def test_무신호면_빈손(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    assert wikictx.pick("오늘 날씨", set()) == []


def test_긴_아티클은_잘리고_표시된다(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    picks = wikictx.pick("동의", {"개인정보 보호법"})
    assert picks[0]["slug"] == "법령갈래/개인정보-경계"
    assert len(picks[0]["text"]) <= wikictx.ARTICLE_MAX_CHARS + 20
    assert picks[0]["text"].endswith("…(잘림 — 전문은 위키)")


def test_블록은_배경_표제를_단다(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    picks = wikictx.pick("준용", set())
    blk = wikictx.block(picks)
    assert blk.startswith("\n\n[해석 맥락 — 지식 위키]\n")
    assert "《준용의 방향》" in blk
    assert wikictx.block([]) == ""


def test_위키_스위치가_등록부에_있다():
    assert any(r["key"] == "wiki_context" for r in switches.REGISTRY)


def test_쟁점_트리거가_카드를_깨운다(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    spots = wikictx.spot("유상증자에서 실권주가 생기면 제3자에게 줄 수 있나?")
    assert [s["slug"] for s in spots] == ["쟁점/실권주-인수"]
    assert "실권주" in spots[0]["why"]
    assert spots[0]["provisions"] == [
        "「자본시장과 금융투자업에 관한 법률」 제165조의6", "「상법」 제418조"]
    assert spots[0]["axis"] == "투자매매업자 인수 계약이 있는가"


def test_쟁점_무매칭이면_빈손(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    assert wikictx.spot("오늘 날씨 어때") == []


def test_조문_후보가_질의를_넓힌다(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    q = "실권주 처리 절차는?"
    spots = wikictx.spot(q)
    qx = wikictx.expand_query(q, spots)
    assert qx.startswith(q)
    assert "제165조의6" in qx and "「상법」 제418조" in qx
    # 질문에 이미 있는 후보는 더하지 않는다
    q2 = "실권주와 「상법」 제418조의 관계는?"
    qx2 = wikictx.expand_query(q2, wikictx.spot(q2))
    assert qx2.count("제418조") == 1


def test_pick은_쟁점_카드를_건너뛴다(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    picks = wikictx.pick("실권주 인수 쟁점", set())
    assert all(not p["slug"].startswith("쟁점/") for p in picks)


def test_쟁점_스위치가_등록부에_있다():
    assert any(r["key"] == "issue_spot" for r in switches.REGISTRY)
    llm_row = next(r for r in switches.REGISTRY if r["key"] == "issue_spot_llm")
    assert llm_row["기본"] is False               # 지연을 얹는 실험 규칙 — 기본 꺼짐


class _FakeLLM:
    def __init__(self, out):
        self.out = out
        self.calls = []

    def structured(self, kind, system, user, schema, **kw):
        self.calls.append({"kind": kind, "user": user})
        return self.out


def test_spot_llm은_컨텍스트를_보고_고른_카드를_쓴다(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    llm = _FakeLLM({"cards": [{"slug": "쟁점/실권주-인수", "why": "실권주 배정 쟁점"}]})
    secs = [SimpleNamespace(n=1, doc="자본시장법", path="제165조의6",
                            text="주권상장법인은 신주를 배정하는 경우 …")]
    spots = wikictx.spot_llm(llm, "신주 배정이 무산되면 어떻게 되나요?", secs)
    assert [s["slug"] for s in spots] == ["쟁점/실권주-인수"]
    assert spots[0]["via"] == "llm" and spots[0]["why"] == ["실권주 배정 쟁점"]
    assert spots[0]["provisions"]                  # 조문 후보는 카드 메타에서 온다
    assert llm.calls[0]["kind"] == "rag.issue_spot"
    assert "실권주 인수" in llm.calls[0]["user"]   # 메뉴에 카드가 실렸다
    assert "[회수된 조문 컨텍스트]" in llm.calls[0]["user"]   # 사안 전체를 본다
    assert "제165조의6" in llm.calls[0]["user"]


def test_spot_llm의_빈_판단은_빈손이고_모른_slug는_버린다(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    assert wikictx.spot_llm(_FakeLLM({"cards": []}), "실권주 문제") == []
    spots = wikictx.spot_llm(_FakeLLM({"cards": [{"slug": "쟁점/없는-카드",
                                                  "why": "환각"}]}), "실권주 문제")
    assert spots == []                             # 메뉴가 정본 — 환각 slug 무시


def test_spot_llm은_판정_불가면_None(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    q = "유상증자에서 실권주가 생기면?"
    for llm in (None, _FakeLLM(None)):             # 무LLM · 콜 실패
        assert wikictx.spot_llm(llm, q) is None    # 폴백은 호출자(라우터) 몫
