"""hwpx → md — 실제 수집 파일 픽스처 대상 (네트워크 없음)."""
from pathlib import Path

from lawrag.core import hwpx_md

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "law_crawler" / "lawgo"


def test_is_hwpx():
    assert hwpx_md.is_hwpx(FIX / "annex_byul16.hwpx")
    assert not hwpx_md.is_hwpx(FIX / "law_search_capital_markets.xml")


def test_hwpx_to_md_text_and_table():
    md = hwpx_md.hwpx_to_md(FIX / "annex_byul16.hwpx")
    assert "배당주식의 권리가격 산정" in md
    # 표가 md 표로 살아 있다 — 수식 셀과 구분행
    assert "| 배당주식의 권리가격 = (배당신주의 최초 상장일의 종가)" in md
    assert "|---|" in md
    # 셀 안 줄바꿈은 <br> 로 (md 셀엔 개행 불가)
    assert "<br>" in md
