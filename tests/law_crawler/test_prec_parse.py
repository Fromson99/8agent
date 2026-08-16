"""판례(prec) 순수 파싱 + 평문 인용 경계 — 실측 응답 픽스처 대상."""
from pathlib import Path

from sources.cite import plain_mentions
from sources.prec import case_text, parse_case, parse_search

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "law_crawler" / "prec"


def test_parse_search():
    total, rows = parse_search((FIX / "prec_search_capital.xml").read_text())
    assert total >= 120                    # '자본시장과 금융투자업' 사건명 실측
    first = rows[0]
    assert first["serial"] and first["case_no"]
    assert first["court"] == "대법원"


def test_parse_case_official_digest():
    case = parse_case((FIX / "prec_case_622119.xml").read_text())
    assert case["case_no"] == "2025도21859"
    assert case["decided"] == "20260520"
    assert "시세조종" in case["issues"]
    assert "자본시장과 금융투자업에 관한 법률" in case["ref_articles"]
    assert case["body"], "전문이 비었다"
    # 관련 판정 대상엔 전문이 없어야 한다 — 방론 소음 차단
    assert case["body"][:40] not in case_text(case)


def test_plain_mentions_boundary():
    names = ["상법", "자본시장과 금융투자업에 관한 법률"]
    # 앞이 한글이면 꼬리 일치 — 거른다
    assert plain_mentions("국가배상법 제2조와 기상법 제14조", names) == []
    # 문장 시작·공백·구두점 뒤는 진짜 인용
    assert plain_mentions("상법 제388조에 따라", names) == ["상법"]
    assert plain_mentions("구 자본시장과금융투자업에관한법률 제176조",
                          names) == ["자본시장과 금융투자업에 관한 법률"]


def test_plain_mentions_on_real_case():
    case = parse_case((FIX / "prec_case_622119.xml").read_text())
    laws = plain_mentions(case_text(case),
                          ["자본시장과 금융투자업에 관한 법률", "상법",
                           "외국환거래법"])
    assert "자본시장과 금융투자업에 관한 법률" in laws
