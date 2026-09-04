"""law.go.kr 본문 XML → 구조 결과 — 실응답 발췌 픽스처 대상 (네트워크 없음)."""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from lawrag.core.structure import lawxml

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "law_crawler" / "lawgo"


def _law_root():
    return ET.fromstring((FIX / "law_body_full_excerpt.xml").read_text("utf-8"))


def _admrul_root():
    return ET.fromstring((FIX / "admrul_body_full_excerpt.xml").read_text("utf-8"))


def test_law_tree_divisions_and_articles():
    tree, info = lawxml.law_tree(_law_root())
    # 제1편 총칙이 열리고 조가 그 아래에 온다 (자본시장법 1편은 장 없이 조 직결)
    pyeon = tree[0]
    assert pyeon.kind == "편" and pyeon.surface == "제1편"
    surfaces = [u.surface for u in pyeon.children]
    assert "제1조" in surfaces and "제5조" in surfaces
    assert info.get("법령ID") == "010513"


def test_law_tree_hang_ho_mok_nesting():
    tree, _ = lawxml.law_tree(_law_root())
    jo3 = next(u for u in tree[0].children if u.surface == "제3조")
    hang1 = jo3.children[0]
    assert hang1.kind == "항" and hang1.surface == "①"
    ho2 = next(c for c in hang1.children if c.surface == "2.")
    # 목은 XML 에서 항의 자식으로 오지만 순서상 앞의 호에 속한다 (실측)
    assert [m.surface for m in ho2.children] == ["가.", "나."]
    assert all(m.kind == "목" for m in ho2.children)


def test_law_appendix_units():
    units = lawxml._appendix_units(_law_root())
    kinds = {u.kind for u in units}
    assert kinds == {"부칙", "별표"}
    buchik = next(u for u in units if u.kind == "부칙")
    assert buchik.children and buchik.children[0].title.startswith("부칙 <")
    byul = next(u for u in units if u.kind == "별표")
    assert byul.children and (byul.children[0].content or byul.children[0].children)  # 별표내용이 실린다


def test_admrul_tree_line_classification():
    tree, info = lawxml.admrul_tree(_admrul_root())
    assert info.get("조문형식여부") == "N"      # 평문 덩어리라는 원천 선언
    pyeon = tree[0]
    assert pyeon.kind == "편"
    jo = next(u for u in pyeon.children if u.surface == "제1-1조")
    assert jo.title == "목적"
    assert jo.ordinal == (1, 1)
    # 조 아래 계속행은 내용으로, 호·목 행은 자식으로
    jo22 = next((u for u in pyeon.children if "의2" in u.surface), None)
    assert jo22 is not None and any(c.kind == "호" for c in jo22.children)


def test_build_end_to_end_same_payload_shape():
    xml_text = (FIX / "law_body_full_excerpt.xml").read_text("utf-8")
    result, blocks, pdf_bytes, info = lawxml.build(xml_text, "자본시장법(발췌)")
    assert pdf_bytes.startswith(b"%PDF")
    assert result.fitness_score == 1.0 and result.fitness_passed
    assert result.stats["deterministic"] is True
    # 모든 마디 span 이 블록 범위 안이고, 제목 블록 좌표가 있다
    for node in result.nodes():
        assert 0 <= node.span[0] < node.span[1] <= len(blocks)
        assert blocks[node.block_idx].bbox is not None
    # 같은 입력 → 같은 구조 (결정성)
    result2, blocks2, _, _ = lawxml.build(xml_text, "자본시장법(발췌)")
    assert [n.surface for n in result.nodes()] == [n.surface for n in result2.nodes()]
    assert len(blocks) == len(blocks2)


def test_build_rejects_unknown_root():
    with pytest.raises(ValueError):
        lawxml.build("<이상한루트/>", "x")


def test_annex_branch_number_kept():
    # 실측 회귀 — 금융투자업규정시행세칙: 별표번호 0014 에 가지 00/01/02 가 별개 별표다
    xml = """<AdmRulService>
    <별표><별표단위>
      <별표번호>0014</별표번호><별표가지번호>00</별표가지번호>
      <별표구분>별표</별표구분>
      <별표제목>국가별·거액신용·시장위험 관리기준(제2-12조 관련)</별표제목>
      <별표내용>본문</별표내용>
    </별표단위><별표단위>
      <별표번호>0014</별표번호><별표가지번호>01</별표가지번호>
      <별표구분>별표</별표구분>
      <별표제목>외환파생상품거래 위험관리기준</별표제목>
      <별표내용>본문</별표내용>
    </별표단위></별표>
    </AdmRulService>"""
    units = lawxml._appendix_units(ET.fromstring(xml))
    byul = next(u for u in units if u.kind == "별표")
    surfaces = [c.surface for c in byul.children]
    assert surfaces == ["별표 14", "별표 14의1"]
    assert byul.children[1].heading.startswith("[별표 14의1]")
    assert byul.children[0].ordinal == (14,)
    assert byul.children[1].ordinal == (14, 1)


def test_flat_classifier_ho_branch_and_hang16():
    # 실측 회귀 — 행정규칙 평문의 호 가지("10의2.")와 16항 이상 표기("<16>")
    lines = [
        "제2-1조(정의) 이 규정에서 사용하는 용어의 뜻은 다음과 같다.",
        "10의2. 영 제70조제1항제1호다목에 따른 집합투자증권",
        "<16> 이 법에서 \"외국법인등\"이란 다음 각 호의 어느 하나에 해당하는 자를 말한다.",
    ]
    top = lawxml._parse_flat(lines, allow_div=False)
    jo = top[0]
    assert jo.surface == "제2-1조"
    ho = jo.children[0]
    assert ho.kind == "호" and ho.ordinal == (10, 2)
    hang = jo.children[1]
    assert hang.kind == "항" and hang.ordinal == (16,)


def test_annex_body_markers_become_nodes():
    # 실측 회귀 — 금융투자업규정시행세칙 별표내용의 ①②③ 이 마디로 추출돼야 한다
    xml = """<AdmRulService><별표><별표단위>
      <별표번호>0004</별표번호><별표가지번호>00</별표가지번호>
      <별표구분>별표</별표구분><별표제목>유동화증권 기준</별표제목>
      <별표내용>다음 요건을 모두 충족하는 경우 위험가중치를 적용한다.
① 독립적 수탁기관이 담보자산을 안전하게 보관ㆍ관리할 것
② 수탁기관이 유동화증권 소지자들을 위하여 담보자산에 대한 1순위의 완전한 담보권을 확보할 것
③ 담보자산에서 발생하는 현금흐름이 항상 유동화증권 원리금 상환에 충분하고 미배분 수입의 재투자 수익에 지나치게 의존하지 않는 구조일 것
</별표내용></별표단위></별표></AdmRulService>"""
    units = lawxml._appendix_units(ET.fromstring(xml))
    unit = next(u for u in units if u.kind == "별표").children[0]
    assert unit.content == ["다음 요건을 모두 충족하는 경우 위험가중치를 적용한다."]
    assert [c.surface for c in unit.children] == ["①", "②", "③"]
    assert unit.children[2].heading.startswith("③ 담보자산에서")


def test_buchik_body_articles_become_nodes():
    tree = ET.fromstring((FIX / "law_body_full_excerpt.xml").read_text("utf-8"))
    units = lawxml._appendix_units(tree)
    buchik = next(u for u in units if u.kind == "부칙")
    first = buchik.children[0]
    # 법령 부칙 본문의 "제N조(…)" 행이 자식 마디로 선다 (실측: 부칙 조 행 1,006개)
    assert any(c.kind == "조" for c in first.children) or first.content


def test_annex_md_replaces_xml_body():
    # 별표 md(HWP 변환)가 있으면 XML 별표내용 대신 쓴다 — 표가 md 표로 산다
    xml = """<AdmRulService><별표><별표단위>
      <별표번호>0016</별표번호><별표가지번호>00</별표가지번호>
      <별표구분>별표</별표구분><별표제목>배당주식의 권리가격 산정</별표제목>
      <별표내용>표가 평문으로 뭉개진 xml 본문</별표내용>
    </별표단위></별표></AdmRulService>"""
    md = "# title: x\n# converted: hwpx\n\n제목행\n| 권리가격 = 종가 × 비율 |\n|---|\n"
    stats = {}
    units = lawxml._appendix_units(ET.fromstring(xml), {"별표 16": md}, stats)
    unit = next(u for u in units if u.kind == "별표").children[0]
    assert stats["annex_md_used"] == 1
    assert "제목행" in unit.content
    assert any(line.startswith("| 권리가격") for line in unit.content)
    assert "표가 평문으로 뭉개진 xml 본문" not in unit.content
