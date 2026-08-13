"""조문 HTML 결정적 이관 — KRX 마크업 규약 (core/structure/rulehtml.py).

여기서 지키는 것 다섯:
  (1) 편·장·절 문단(p.pyun/jang/jeol)과 조 블록(div.Mjo)이 문서 순서대로
      계층이 된다 — 절이 나오면 뒤 조는 절 아래로.
  (2) 조 안의 ①·1.·가. 행이 항·호·목으로 갈린다 (lawxml 행 머리 분류 재사용).
  (3) 부칙 제목 문단 + 직후 본문 블록이 부칙 컨테이너로 묶인다.
  (4) 결정적 이관 규약 공유 — fitness 1.0/hot, applied.source=rulehtml.
  (5) 모르는 site 는 명시적으로 거부한다 — 조용히 아는 척하지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.structure import rulehtml  # noqa: E402

HTML = """<html><body><form></form>
<div class="innerbody" id="innerbody" style="height:310">
  <p class="pyun"><a name="a1">제1편&nbsp;총칙</a></p>
  <p class="jang"><a name="a2">제1장&nbsp;통칙</a></p>
  <div id="206000124"><img class="histIcon" alt="인쇄"/>
    <div class="Mjo" id="jo"><a name="bon1"><strong>제1조(목적)</strong></a>이
      규정은 상장 심사에 필요한 사항을 정함을 목적으로 한다. <br/></div><br/></div>
  <div id="206000125">
    <div class="Mjo" id="jo"><a name="bon2"><strong>제2조(정의)</strong></a>① 이
      규정에서 사용하는 용어의 뜻은 다음과 같다.
      <span class="jotag2">&lt;개정 2014. 6. 18.&gt;</span> <br/>
      <div id="ho">1. "상장"이란 증권을 매매할 수 있게 하는 것을 말한다. <br/>
      가. 세부 목이다. <br/></div>
      <div id="hang">② 제1항 외의 용어는 세칙으로 정한다. <br/></div></div></div>
  <p class="jeol"><a name="a3">제1절&nbsp;신규상장</a></p>
  <div><div class="Mjo" id="jo"><a name="bon3"><strong>제3조의2(특례)</strong></a>특례
    본문이다. <br/></div></div>
  <p class="buchik_title"><a name="a4">부칙 &lt;제7호, 2005. 1. 21.&gt;</a></p>
  <div id="jo">① (시행일) 이 규정은 설립일부터 시행한다. <br/>
    <div id="hang">② (폐지) 종전 규정은 폐지한다. <br/></div></div>
</div>
<script>var ignored = "제99조(가짜)";</script>
</body></html>"""


def _kinds(us):
    return [(u.kind, u.surface) for u in us]


def test_편장절과_조가_문서_순서로_계층이_된다():
    tree = rulehtml.krx_tree(HTML)
    assert _kinds(tree) == [("편", "제1편"), ("부칙", "부칙")]
    pyun = tree[0]
    assert pyun.title == "제1편 총칙"                      # &nbsp; 정규화
    (jang,) = pyun.children
    assert _kinds(jang.children) == [("조", "제1조"), ("조", "제2조"), ("절", "제1절")]
    jeol = jang.children[-1]
    assert _kinds(jeol.children) == [("조", "제3조의2")]   # 절 뒤 조는 절 아래


def test_조_안의_행머리가_항호목으로_갈린다():
    tree = rulehtml.krx_tree(HTML)
    jo2 = tree[0].children[0].children[1]
    assert jo2.title == "정의"
    h1, h2 = jo2.children
    assert (h1.kind, h1.surface) == ("항", "①")
    (ho,) = h1.children
    assert (ho.kind, ho.surface) == ("호", "1.")
    (mok,) = ho.children
    assert (mok.kind, mok.surface) == ("목", "가.")
    assert (h2.kind, h2.surface) == ("항", "②")


def test_부칙이_제목과_본문으로_묶인다():
    tree = rulehtml.krx_tree(HTML)
    buchik = tree[-1]
    (u,) = buchik.children
    assert u.title == "부칙 <제7호, 2005. 1. 21.>"
    assert [c.surface for c in u.children] == ["①", "②"]


def test_결정적_이관_규약을_공유한다():
    result, blocks, pdf = rulehtml.build(HTML, "상장규정 시험", site="krx")
    assert result.fitness_score == 1.0 and result.tier == "hot"
    assert result.applied["source"] == "rulehtml"
    assert result.stats["source"] == "krx 조문 HTML"
    assert result.stats["units"]["조"] == 4                # 본문 3 + 부칙 1
    assert blocks and pdf[:4] == b"%PDF"
    assert "제99조" not in " ".join(b.text for b in blocks)  # script 무시


def test_모르는_site는_거부한다():
    with pytest.raises(ValueError, match="site"):
        rulehtml.build(HTML, "문서", site="dart")


KOFIA_HTML = """<html><body><div id="lawcontent">
<div class="lawname" align="center"><center>표준시험준칙</center></div>
<div class="PT"><div class="part" align="center"> Ⅰ. 총 칙 </div></div>
<a id="000001"></a><div class="JO" id="1">
  <div class="article">&nbsp;1. 목 적 &nbsp;</div>
  <div class="hang"><table><tr><td>1) </td><td><span>이 준칙은 투자권유의
    기준을 정한다.</span></td></tr></table></div>
  <div class="ho"><table><tr><td>(1) </td><td><span>첫째 호다.</span></td></tr></table></div>
  <div class="mok"><table><tr><td>가. </td><td><span>세부 목이다.</span></td></tr></table></div>
  <div class="dann"><table><tr><td>- </td><td><span>단서 내용이다.</span></td></tr></table></div>
</div>
<div class="CT"><div class="chapter" align="center">Ⅳ-1. 투자자정보</div></div>
<div class="JO" id="2">
  <div class="article">제5조(정보파악)</div>
  <div class="hang"><table><tr><td>① </td><td><span>원문자 항이다.</span></td></tr></table></div>
</div>
<div class="addenda">부 칙 (2008. 12. 30)</div>
<div class="JO" id="3">
  <div class="article">제1조(시행일)</div>
  <div class="hang"><table><tr><td>1) </td><td><span>이 준칙은 즉시 시행한다.</span></td></tr></table></div>
</div>
</div></body></html>"""


def test_kofia_클래스가_곧_계층이_된다():
    tree = rulehtml.kofia_tree(KOFIA_HTML)
    assert _kinds(tree) == [("편", "Ⅰ."), ("부칙", "부칙")]
    pyun = tree[0]
    jo1, jang = pyun.children
    assert (jo1.kind, jo1.surface, jo1.title) == ("조", "1.", "목 적")
    assert jo1.ordinal == (1,)
    h = jo1.children[0]
    assert (h.kind, h.surface, h.ordinal) == ("항", "1)", (1,))
    (ho,) = h.children
    assert (ho.kind, ho.surface) == ("호", "(1)")
    (mok,) = ho.children
    assert (mok.kind, mok.surface) == ("목", "가.")
    assert any("단서" in c for c in mok.content)          # dann 은 내용으로


def test_kofia_장과_원문자_항과_제N조_표기():
    tree = rulehtml.kofia_tree(KOFIA_HTML)
    jang = tree[0].children[1]
    assert (jang.kind, jang.title) == ("장", "Ⅳ-1. 투자자정보")
    (jo5,) = jang.children
    assert (jo5.surface, jo5.title, jo5.ordinal) == ("제5조", "정보파악", (5,))
    assert jo5.children[0].ordinal == (1,)                # ① → 1


def test_kofia_부칙이_라벨_아래_조를_품는다():
    tree = rulehtml.kofia_tree(KOFIA_HTML)
    buchik = tree[-1]
    (label,) = buchik.children
    assert label.title == "부 칙 (2008. 12. 30)"
    (jo,) = label.children
    assert (jo.surface, jo.title) == ("제1조", "시행일")


def test_kofia_이관_규약():
    result, blocks, pdf = rulehtml.build(KOFIA_HTML, "표준시험준칙", site="kofia")
    assert result.fitness_score == 1.0
    assert result.stats["source"] == "kofia 조문 HTML"
    assert result.stats["units"]["조"] == 4 and pdf[:4] == b"%PDF"   # 본문 3 + 부칙 라벨 1
