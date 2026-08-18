"""금융위 회신사례(better.fsc.go.kr) 순수 파싱 — 실측 응답 픽스처 대상."""
import json
from pathlib import Path

from lawrag.sources.fsc import DETAIL, case_text, parse_detail, parse_list

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "law_crawler" / "fsc"


def test_parse_list_keeps_only_interpretation_kinds():
    payload = json.loads((FIX / "list_page1.json").read_text("utf-8"))
    total, rows = parse_list(payload)
    assert total >= 12067                  # 2026-08-14 실측 전량
    assert rows, "채택 유형이 한 건도 없다"
    for r in rows:
        assert r["kind"] in DETAIL         # 현장건의 과제는 여기 못 들어온다
        assert r["idx"] and r["title"]


def test_parse_detail_three_parts():
    case = parse_detail((FIX / "lawreq_detail_4477.html").read_text("utf-8"))
    assert case["replied"] == "2026-08-06"
    assert case["dept"] == "은행과"
    assert "건축자금" in case["issue"]
    assert case["answer"].startswith("토지매입자금은")
    assert "은행업감독규정" in case["reason"]
    # 정리 규칙 — 태그·엔티티가 남으면 안 된다
    for k in ("issue", "answer", "reason"):
        assert "<" not in case[k] and "&nbsp;" not in case[k]


def test_case_text_carries_title_and_parts():
    case = parse_detail((FIX / "lawreq_detail_4477.html").read_text("utf-8"))
    text = case_text(case, "제목표시")
    assert text.startswith("제목표시")
    assert "은행업감독규정" in text
