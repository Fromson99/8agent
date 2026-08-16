"""법령해석례(expc) 순수 파싱·질의 계획 — 실측 응답 픽스처 대상 (네트워크 없음)."""
from pathlib import Path

from sources.expc import case_text, cited_laws, parse_case, parse_search, plan_queries

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "law_crawler" / "expc"


def test_parse_search():
    total, rows = parse_search((FIX / "expc_search_capital.xml").read_text())
    assert total == 8                       # '자본시장' 안건명 부분일치 실측값
    assert len(rows) == 3                   # display=3 요청분
    first = rows[0]
    assert first["serial"] == "311905"
    assert first["case_no"] == "09-0242"
    assert first["ans_org"] == "법제처"
    assert "자본시장과 금융투자업에 관한 법률" in first["label"]


def test_parse_case():
    case = parse_case((FIX / "expc_case_314484.xml").read_text())
    assert case["serial"] == "314484"
    assert case["case_no"] == "14-0342"
    assert case["decided"] == "20140707"
    assert case["req_org"] == "금융위원회"
    # 몸통 3단이 모두 차 있어야 한다 — 질의요지·회답·이유
    assert "반기보고서" in case["issue"]
    assert case["answer"].strip().startswith("「자본시장과 금융투자업에 관한 법률」")
    assert "제159조제1항" in case["reason"]


def test_plan_queries_drops_superstrings():
    names = ["상법", "상법 시행령", "외국환거래법",
             "자본시장과 금융투자업에 관한 법률",
             "자본시장과 금융투자업에 관한 법률 시행령"]
    # 다른 명칭을 부분문자열로 품는 명칭은 질의에서 빠진다
    assert plan_queries(names) == ["상법", "외국환거래법",
                                   "자본시장과 금융투자업에 관한 법률"]


def test_cited_laws_exact_bracket_match():
    case = parse_case((FIX / "expc_case_314484.xml").read_text())
    names = ["자본시장과 금융투자업에 관한 법률",
             "자본시장과 금융투자업에 관한 법률 시행령",
             "상법", "증권의 발행 및 공시 등에 관한 규정"]
    laws = cited_laws(case_text(case), names)
    assert "자본시장과 금융투자업에 관한 법률" in laws
    # '상법' 이 다른 법령명 속 부분문자열로는 걸리지 않아야 한다
    assert "상법" not in laws


def test_cited_laws_needs_closing_bracket():
    text = "「군인 재해보상법」 부칙과 「기상법」 제14조"
    assert cited_laws(text, ["상법"]) == []          # '…보상법'·'기상법' 오탐 차단
    assert cited_laws("「상법」 제388조", ["상법"]) == ["상법"]


def test_cited_laws_ignores_spacing():
    # 붙여쓰기 표기 실재 — 「개인정보보호법」 (15-0641 실측)
    assert cited_laws("「개인정보보호법」 제21조", ["개인정보 보호법"]) \
        == ["개인정보 보호법"]
