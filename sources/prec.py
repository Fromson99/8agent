"""국가법령정보센터 OPEN API — 판례(prec).

법령해석례(expc)와 같은 API 가족이다. 실측 모델 (2026-08-14 확인):
- 목록: GET /DRF/lawSearch.do?target=prec — 기본 section=evtNm(사건명
  부분일치). 사건명은 붙여쓰기("자본시장과금융투자업에관한법률위반")지만
  서버가 공백을 무시하고 맞춰 준다 (질의 "자본시장과 금융투자업" 126건 실측).
- 본문: GET /DRF/lawService.do?target=prec&ID=<판례정보일련번호> —
  <PrecService>: 사건명·사건번호·선고일자·법원명·사건종류명·판결유형·
  판시사항·판결요지·참조조문·참조판례·판례내용(전문, 수십~수백 KB).
- 판례는 낫표 인용 관례가 없다 — 관련 법령 판정은 앞 경계 평문 판정
  (sources/cite.plain_mentions)으로 한다. '국가배상법' 속 '상법'은 경계
  규칙이 거른다.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from .common import HttpClient

BASE = "https://www.law.go.kr"
PAGE_SIZE = 100
MAX_PAGES = 50


def parse_search(xml_text: str) -> tuple[int, list[dict[str, str]]]:
    root = ET.fromstring(xml_text)
    total = int(root.findtext("totalCnt", "0") or 0)
    rows = []
    for el in root.iter("prec"):
        rows.append({
            "serial": el.findtext("판례일련번호", "").strip(),
            "label": (el.findtext("사건명", "") or "").strip(),
            "case_no": el.findtext("사건번호", "").strip(),
            "decided": el.findtext("선고일자", "").strip(),
            "court": el.findtext("법원명", "").strip(),
            "kind": el.findtext("사건종류명", "").strip(),
        })
    return total, rows


def parse_case(xml_text: str) -> dict[str, str]:
    root = ET.fromstring(xml_text)
    g = lambda tag: (root.findtext(tag, "") or "").replace("<br/>", "\n").strip()
    return {
        "serial": g("판례정보일련번호"), "label": g("사건명"),
        "case_no": g("사건번호"), "decided": g("선고일자"),
        "court": g("법원명"), "kind": g("사건종류명"),
        "judgment": g("판결유형"),
        "issues": g("판시사항"), "summary": g("판결요지"),
        "ref_articles": g("참조조문"), "ref_cases": g("참조판례"),
        "body": g("판례내용"),
    }


def case_text(case: dict[str, str]) -> str:
    """관련 법령 판정 대상 — 요지·참조조문까지. 전문(판례내용)은 안 본다:
    방론에 스친 법령까지 관련로 묶으면 연결이 소음이 된다."""
    return "\n".join((case.get("label", ""), case.get("issues", ""),
                      case.get("summary", ""), case.get("ref_articles", "")))


class PrecClient:
    def __init__(self, client: HttpClient, oc: str | None = None) -> None:
        self.client = client
        self.oc = oc or os.environ.get("LAW_OC", "test")

    def search_all(self, query: str) -> tuple[int, list[dict[str, str]]]:
        total, rows, page = 0, [], 1
        while page <= MAX_PAGES:
            resp = self.client.get(
                f"{BASE}/DRF/lawSearch.do",
                params={"OC": self.oc, "target": "prec", "type": "XML",
                        "query": query, "display": str(PAGE_SIZE),
                        "page": str(page)})
            try:
                total, batch = parse_search(resp.text)
            except ET.ParseError as e:
                raise RuntimeError(f"{query}: 목록 응답이 XML 이 아님 (OC 거부?): {e}")
            rows.extend(batch)
            if len(rows) >= total or not batch:
                break
            page += 1
        return total, rows

    def fetch_case(self, serial: str) -> str:
        resp = self.client.get(
            f"{BASE}/DRF/lawService.do",
            params={"OC": self.oc, "target": "prec", "ID": serial,
                    "type": "XML"})
        text = resp.text
        try:
            ET.fromstring(text)
        except ET.ParseError as e:
            raise RuntimeError(f"판례 {serial}: 본문 응답이 XML 이 아님: {e}")
        return text
