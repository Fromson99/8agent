"""law.go.kr OPEN API 어댑터 순수 파싱 — 실측 응답 픽스처 대상 (네트워크 없음)."""
from pathlib import Path

from sources.lawgo import parse_annexes, parse_search

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "law_crawler" / "lawgo"


def test_parse_search_law():
    rows = parse_search((FIX / "law_search_capital_markets.xml").read_text(), "law")
    by_name = {r["name"]: r for r in rows}
    law = by_name["자본시장과 금융투자업에 관한 법률"]
    assert law["serial"] == "283193"
    assert law["current"] == "현행"
    assert law["enforce"] == "20260804"
    assert law["dept"] == "금융위원회"
    assert "자본시장과 금융투자업에 관한 법률 시행령" in by_name


def test_parse_search_admrul():
    rows = parse_search((FIX / "admrul_search_ftbr.xml").read_text(), "admrul")
    by_name = {r["name"]: r for r in rows}
    rule = by_name["금융투자업규정"]
    assert rule["serial"] == "2100000282072"
    assert rule["dept"] == "금융위원회"
    sechik = by_name["금융투자업규정시행세칙"]
    assert sechik["dept"] == "금융감독원"
    assert sechik["current"] == "현행"


def test_parse_annexes_decree():
    annexes = parse_annexes((FIX / "law_body_decree_excerpt.xml").read_text())
    assert len(annexes) == 2
    first = annexes[0]
    assert first["title"].startswith("[별표 1]")
    assert "인가업무 단위" in first["title"]
    assert first["url"].startswith("https://www.law.go.kr/LSW/flDownload.do?flSeq=")
    # HWP 링크만 — PDF·이미지 파생본이 섞이면 안 된다 (별표단위당 1건)
    assert len({a["url"] for a in annexes}) == 2
