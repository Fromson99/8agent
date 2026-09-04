"""KRX 어댑터 순수 파싱 — Phase 1·별표 실측 픽스처 대상 (네트워크 없음)."""
import json
from pathlib import Path

from lawrag.sources.krx import (
    filter_byul_rows,
    is_alert_page,
    parse_csrf,
    parse_doc_nodes,
    parse_statehistoryid,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "law_crawler" / "krx"


def test_parse_statehistoryid_from_view():
    html = (FIX / "rule_regulation_view_book210233498.html").read_text()
    assert parse_statehistoryid(html) == "210234678"


def test_parse_csrf_from_view():
    html = (FIX / "rule_regulation_view_book210233498.html").read_text()
    token = parse_csrf(html)
    assert token and len(token) == 36


def test_parse_doc_nodes_tree_walk():
    walk = json.loads((FIX / "rule_get_tree_node_walk.json").read_text())
    docs = parse_doc_nodes(walk["lv2"])
    assert "유가증권시장상장규정" in docs
    assert docs["유가증권시장상장규정"]["bookid"] == 210233498
    assert "유가증권시장상장규정시행세칙" in docs
    # 폴더 노드는 들어오면 안 된다
    assert all(n.get("catcd") == "doc" for n in docs.values())


def test_filter_byul_rows_exact_title_only():
    data = json.loads((FIX / "rule_byul_list_data_p1.json").read_text())
    rows = data["result"]
    mine = filter_byul_rows(rows, "KRX금시장 운영규정 시행세칙")
    assert mine and all(r["TITLE"] == "KRX금시장 운영규정 시행세칙" for r in mine)
    # 부분일치 금지 — 상위 규정명으로 시행세칙 행이 딸려오면 안 된다
    assert filter_byul_rows(rows, "KRX금시장 운영규정") == []


def test_is_alert_page():
    # Download.do 의 88B '잘못된 접근' 응답 머리 (실측 프리픽스)
    assert is_alert_page(b'<script>alert("\xec\x9e\x98\xeb\xaa\xbb...")</script>')
    assert not is_alert_page(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
