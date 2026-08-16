"""국가법령정보센터 OPEN API — 법령해석례(expc) 파싱·질의 계획.

법령해석례는 법제처 정부유권해석 사례다. 규정 문서(법령·행정규칙)와 달리
"명칭 → 문서 파일"이 아니라 "질의 → 사례 집합"이라 Target/DocumentRef
계약(base.py)에 맞지 않는다 — 그래서 어댑터가 아니라 이 모듈 + collect_expc.py
쌍이고, HTTP·저장·manifest 는 collect.py 와 같은 공통 기반(common.py)을 쓴다.

실측 모델 (2026-08-13 확인):
- 목록: GET /DRF/lawSearch.do?OC=<oc>&target=expc&type=XML&query=<키워드>
  기본 section=itmNm(안건명 부분일치)·display 최대 100·page 순회, totalCnt 제공.
  search=2(bdyText)는 형태소 OR 매칭이라 못 쓴다 — "자본시장과 금융투자업에
  관한 법률"이 8,028건(첫 행이 군인 퇴직급여금 안건)으로 쏟아진다.
- 본문: GET /DRF/lawService.do?OC=<oc>&target=expc&ID=<일련번호>&type=XML
  <ExpcService> 아래 안건명·안건번호·해석일자·해석기관·질의기관·질의요지·회답·이유.
- 관련법령 필드는 응답에 없다. 안건명·본문의 「법령명」 낫표 인용 완전일치로
  잇는다. 부분일치 오탐이 실재해서다 — '상법' 질의가 '군인 재해보상법' 안건을
  끌고 온다(안건명 부분일치가 '…보상법'의 '상법'을 문다).
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

from .common import HttpClient

BASE = "https://www.law.go.kr"
PAGE_SIZE = 100          # display 최대 실측값
MAX_PAGES = 50           # 폭주 방지 — 질의 하나가 5,000건이면 질의가 틀린 것이다


# ---------------------------------------------------------------- 순수 파싱 (픽스처 테스트 대상)

def parse_search(xml_text: str) -> tuple[int, list[dict[str, str]]]:
    """목록 응답 → (totalCnt, 행 목록)."""
    root = ET.fromstring(xml_text)
    total = int(root.findtext("totalCnt", "0") or 0)
    rows: list[dict[str, str]] = []
    for el in root.iter("expc"):
        rows.append({
            "serial": el.findtext("법령해석례일련번호", "").strip(),
            "label": (el.findtext("안건명", "") or "").strip(),
            "case_no": el.findtext("안건번호", "").strip(),
            "req_org": el.findtext("질의기관명", "").strip(),
            "ans_org": el.findtext("회신기관명", "").strip(),
            "replied": el.findtext("회신일자", "").strip(),
        })
    return total, rows


def parse_case(xml_text: str) -> dict[str, str]:
    """본문 응답(<ExpcService>) → 사례 한 건. 질의요지·회답·이유가 몸통이다."""
    root = ET.fromstring(xml_text)
    return {
        "serial": root.findtext("법령해석례일련번호", "").strip(),
        "label": (root.findtext("안건명", "") or "").strip(),
        "case_no": root.findtext("안건번호", "").strip(),
        "decided": root.findtext("해석일자", "").strip(),      # YYYYMMDD
        "ans_org": root.findtext("해석기관명", "").strip(),
        "req_org": root.findtext("질의기관명", "").strip(),
        "registered": root.findtext("등록일시", "").strip(),
        "issue": (root.findtext("질의요지", "") or "").strip(),
        "answer": (root.findtext("회답", "") or "").strip(),
        "reason": (root.findtext("이유", "") or "").strip(),
    }


def case_text(case: dict[str, str]) -> str:
    """인용 판정 대상 전문 — 안건명과 세 몸통을 잇는다."""
    return "\n".join((case.get("label", ""), case.get("issue", ""),
                      case.get("answer", ""), case.get("reason", "")))


def plan_queries(names: list[str]) -> list[str]:
    """안건명 부분일치 검색의 최소 질의 집합.

    '상법 시행령'은 '상법' 질의 결과에 부분일치로 이미 들어 있다 — 다른 명칭을
    부분문자열로 품는 명칭은 질의에서 뺀다. 명칭 자체를 줄이지는 않는다
    (문서별 상수 금지 — 코퍼스 명칭 그대로가 질의다).
    """
    uniq = sorted(set(n.strip() for n in names if n.strip()))
    return [n for n in uniq
            if not any(other != n and other in n for other in uniq)]


def cited_laws(text: str, names: list[str]) -> list[str]:
    """전문에서 「명칭」 낫표 인용 완전일치로 걸리는 코퍼스 명칭들.

    닫는 낫표까지 맞춰야 한다 — 「X 시행령」 인용은 「X」와 다르다.
    법령명 속 공백은 표기 편차(붙여쓰기)가 실재해서 공백 무시로 비교한다.
    """
    packed = re.sub(r"\s+", "", text)
    out = []
    for name in names:
        needle = "「" + re.sub(r"\s+", "", name) + "」"
        if needle in packed:
            out.append(name)
    return sorted(set(out))


# ---------------------------------------------------------------- API 호출

class ExpcClient:
    """목록 페이지 순회 + 본문 획득. 요청 규율은 HttpClient 소유."""

    def __init__(self, client: HttpClient, oc: str | None = None) -> None:
        self.client = client
        self.oc = oc or os.environ.get("LAW_OC", "test")

    def search_all(self, query: str) -> tuple[int, list[dict[str, str]]]:
        total, rows, page = 0, [], 1
        while page <= MAX_PAGES:
            resp = self.client.get(
                f"{BASE}/DRF/lawSearch.do",
                params={"OC": self.oc, "target": "expc", "type": "XML",
                        "query": query, "display": str(PAGE_SIZE), "page": str(page)},
            )
            try:
                total, batch = parse_search(resp.text)
            except ET.ParseError as e:
                raise RuntimeError(f"{query}: 목록 응답이 XML 이 아님 (OC 거부?): {e}")
            rows.extend(batch)
            if len(rows) >= total or not batch:
                break
            page += 1
        return total, rows

    def case_url(self, serial: str) -> str:
        return (f"{BASE}/DRF/lawService.do?OC={self.oc}&target=expc"
                f"&ID={serial}&type=XML")

    def fetch_case(self, serial: str) -> str:
        resp = self.client.get(self.case_url(serial))
        text = resp.text
        try:
            ET.fromstring(text)
        except ET.ParseError as e:
            raise RuntimeError(f"해석례 {serial}: 본문 응답이 XML 이 아님: {e}")
        return text
