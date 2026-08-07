"""KOFIA 파싱 — Phase 1 에서 저장한 실제 응답을 픽스처로 쓴다. 네트워크 없음."""
from __future__ import annotations

from pathlib import Path

from sources import kofia

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "law_crawler" / "kofia"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_tree_resolves_target_regulations():
    tree = kofia.parse_tree(_read("law_current_part_tree.html"))
    entry = tree[kofia._norm("표준투자권유준칙")]
    assert entry["seq"] == "149"
    assert entry["hseq"] == "1787"
    assert entry["law_type"] == "1"
    assert tree[kofia._norm("증권 인수업무 등에 관한 규정")]["seq"] == "140"
    assert tree[kofia._norm("대표주관업무 등 모범기준")]["seq"] == "153"


def test_tree_marks_folder_nodes():
    tree = kofia.parse_tree(_read("law_current_part_tree.html"))
    assert tree[kofia._norm("모범규준")]["folder"] == "1"
    assert tree[kofia._norm("모범규준")]["seq"] == "3"


def test_part_list_members_and_paging():
    html = _read("part_list_seq3_p1.html")
    rows = kofia.parse_part_list(html)
    labels = [r["label"] for r in rows]
    assert "표준투자권유준칙" in labels
    assert "대표주관업무 등 모범기준" in labels
    assert len(rows) == 10                      # 페이지당 10건 (실측)
    assert kofia.parse_part_list_pages(html) >= 6


def test_view_page_resolves_current_history_seq():
    assert kofia.parse_view_hseq(_read("law_view_seq149.html")) == "1787"


def test_content_lists_attachment_files():
    atts = kofia.parse_content_attachments(_read("law_content_seq149_hseq1787.html"))
    assert len(atts) == 12                      # 표준투자권유준칙 별표 12건 (실측)
    assert atts[0]["title"] == "1. 0000_[참고 1].hwp"
    assert atts[0]["url"] == "https://law.kofia.or.kr/download.do?gubun=102&seq=27611"


def test_revision_view_with_comparison_table():
    buttons = kofia.parse_revision_buttons(_read("revision_view_hseq1785.html"))
    assert "105" in buttons                     # 신구대비표
    assert buttons["105"]["url"].endswith("gubun=105&seq=1781")
    assert "101" in buttons


def test_revision_view_without_comparison_table():
    buttons = kofia.parse_revision_buttons(_read("revision_view_hseq1782.html"))
    assert "105" not in buttons                 # 이 개정 건에는 신구대비표가 없다 (실측)
    assert buttons["101"]["url"].endswith("gubun=101&seq=1782")
    assert buttons["104"]["url"].endswith("gubun=104&seq=1778")


def test_revision_info_fields():
    info = kofia.parse_revision_info(_read("revision_info_hseq1787.html"))
    assert info["개정일"] == "2026-04-09"
    assert info["규정명"] == "표준투자권유준칙"
    assert info["제개정구분"] == "개정"


def test_revision_rows_ordered_latest_first():
    rows = kofia.parse_revision_rows(_read("revision_list_p1.html"))
    assert rows[0]["hseq"] == "1802"
    assert len(rows) == 10


def test_error_page_detection():
    assert kofia.is_error_page("<title>페이지를 찾을 수 없습니다...</title>")
    assert not kofia.is_error_page(_read("law_content_seq149_hseq1787.html"))
