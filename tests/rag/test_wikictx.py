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


def test_확장_질의는_조문질의만_붙이고_조문_후보는_안_붙인다(tmp_path, monkeypatch):
    """카드의 소임은 문체 번역이지 좌표 연결이 아니다 (2026-08-18 결정) —
    조문 후보는 컴파일 사례의 좌표라 사안이 다르면 다른 조를 가리킨다(18-0124)."""
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    q = "실권주 처리 절차는?"
    spots = wikictx.spot(q)                       # 트리거 판 — probe 없음
    assert spots and spots[0]["provisions"]       # 메타는 읽히지만
    assert wikictx.expand_query(q, spots) == q    # 질의에는 안 실린다
    # LLM 판이 probe 를 달면 그것만 붙는다
    spots[0]["probe"] = "실권주의 제3자 배정에 관한 투자매매업자의 인수"
    qx = wikictx.expand_query(q, spots)
    assert qx.startswith(q) and "[법률용어 질의]" in qx
    assert "제165조의6" not in qx and "제418조" not in qx


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


# ===========================================================================
# 방법 갈래 — 질의가 아니라 회수 결과의 성격(신호)이 깨운다
# ===========================================================================

class _Sec:
    """Section 축소판 — methods_for 는 kind·text 만 본다."""
    def __init__(self, kind="벡터", text=""):
        self.kind, self.text = kind, text


def _wiki_with_methods(tmp_path, monkeypatch):
    w = _wiki(tmp_path)
    (w / "wiki" / "방법").mkdir()
    (w / "wiki" / "방법" / "단서-읽기.md").write_text(
        "# 단서 읽기\n\n> 신호: 단서\n\n본문과 단서는 한 세트다.\n", "utf-8")
    (w / "wiki" / "방법" / "제재-연결.md").write_text(
        "# 제재 연결\n\n> 신호: 제재\n\n법정형은 그대로 인용한다.\n", "utf-8")
    idx = w / "wiki" / "index.md"
    idx.write_text(idx.read_text("utf-8")
                   + "| [단서 읽기](방법/단서-읽기.md) | 단서 | 2026-08-18 |\n"
                   + "| [제재 연결](방법/제재-연결.md) | 제재 | 2026-08-18 |\n",
                   "utf-8")
    monkeypatch.setenv("WIKI_STORE", str(w))
    wikictx._cache.update(key=None, rows=[])
    return w


def test_방법은_회수_성격이_깨운다(tmp_path, monkeypatch):
    _wiki_with_methods(tmp_path, monkeypatch)
    # 제재 동반 + 본문에 단서 — 두 신호가 각자의 방법을 깨운다
    secs = [_Sec(kind="벡터", text="① 은행은 하여야 한다. 다만, 예외가 있다."),
            _Sec(kind="제재", text="위반한 자는 벌금에 처한다.")]
    picks = wikictx.methods_for(secs)
    assert {p["slug"] for p in picks} == {"방법/단서-읽기", "방법/제재-연결"}
    # why 에 어느 신호가 물었는지 남는다 — 관측
    assert ["단서"] in [p["why"] for p in picks]


def test_방법은_무신호면_빈손(tmp_path, monkeypatch):
    _wiki_with_methods(tmp_path, monkeypatch)
    assert wikictx.methods_for([_Sec(kind="벡터", text="평범한 조문")]) == []


def test_방법은_일반_pick_경쟁에도_남는다(tmp_path, monkeypatch):
    """신호 메타는 추가 경로지 pick 박탈이 아니다 — 이중 경로, 중복은 합성이 걸러낸다."""
    _wiki_with_methods(tmp_path, monkeypatch)
    picks = wikictx.pick("단서 읽기가 뭐야", set())
    assert any(p["slug"] == "방법/단서-읽기" for p in picks)
