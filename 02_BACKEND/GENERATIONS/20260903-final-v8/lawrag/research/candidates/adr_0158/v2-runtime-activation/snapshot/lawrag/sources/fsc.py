"""금융규제·법령해석포털(better.fsc.go.kr) — 금융위 법령해석·비조치의견서 회신사례.

법제처 해석례(expc)의 금융 판이다 — 금융위 소관 법령·감독규정의 해석은
법제처가 아니라 이 포털에 쌓인다 (실측: 법제처 expc 에서 금소법·외감법·
전자금융 0건이던 공백이 여기서 채워진다. 전자금융감독규정 311건 등).

실측 모델 (2026-08-14 확인):
- 목록: POST /fsc_new/replyCase/selectReplyCaseTotalReplyList.do
  DataTables 프로토콜 — draw·start·length(100 동작)·searchCondition(title|all)·
  searchKeyword. 응답 {recordsTotal, data:[{dataIdx, pastreqType, title,
  replyRegDate}]}. 전량 12,067건(2026-08-14), 본문검색(all)이 서버에서 돈다.
- 상세: POST — 유형(gubun)마다 주소·키가 다르다 (목록 JS 실측):
    법령해석(1)        /fsc_new/replyCase/LawreqDetail.do   lawreqIdx
    비조치의견서(2)     /fsc_new/replyCase/OpinionDetail.do  opinionIdx
    과거회신(2014이전,4) /fsc_new/replyCase/PastReqDetail.do  pastreqIdx
  공통 폼: muNo=117&stNo=11&actCd=R. '현장건의 과제'(3)는 해석이 아니라 뺀다.
- 상세 HTML 은 <th>질의요지/회답/이유</th><td>…</td> 표 — expc 와 같은 3단.
"""
from __future__ import annotations

import html as html_mod
import re

from .common import HttpClient

BASE = "https://better.fsc.go.kr"
LIST_URL = f"{BASE}/fsc_new/replyCase/selectReplyCaseTotalReplyList.do"
PAGE_SIZE = 100
MAX_PAGES = 200          # 질의 하나 2만 건이면 질의가 틀린 것이다

# pastreqType → (gubun, 상세 주소, idx 키). 현장건의 과제는 없다 — 해석이 아니다.
DETAIL: dict[str, tuple[int, str, str]] = {
    "법령해석": (1, f"{BASE}/fsc_new/replyCase/LawreqDetail.do", "lawreqIdx"),
    "비조치의견서": (2, f"{BASE}/fsc_new/replyCase/OpinionDetail.do", "opinionIdx"),
    "법령해석(2014이전)": (4, f"{BASE}/fsc_new/replyCase/PastReqDetail.do", "pastreqIdx"),
    "비조치의견서(2014이전)": (4, f"{BASE}/fsc_new/replyCase/PastReqDetail.do", "pastreqIdx"),
}

_ROW_FIELD_RE = re.compile(r'<th[^>]*>\s*([^<]+?)\s*</th>\s*<td[^>]*>(.*?)</td>',
                           re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_list(payload: dict) -> tuple[int, list[dict]]:
    """목록 JSON → (전체 건수, 행 목록). 유형이 DETAIL 에 없는 행은 버린다."""
    rows = []
    for r in payload.get("data", []):
        kind = str(r.get("pastreqType", "")).strip()
        if kind not in DETAIL:
            continue
        rows.append({"idx": str(r.get("dataIdx", "")).strip(), "kind": kind,
                     "title": str(r.get("title", "")).strip(),
                     "replied": str(r.get("replyRegDate", "")).strip()})
    return int(payload.get("recordsTotal", 0) or 0), rows


def _clean(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = html_mod.unescape(text).replace("\xa0", " ")
    return "\n".join(" ".join(line.split())
                     for line in re.split(r"\s*(?:□|ㅇ|◦)\s*", text) if line.strip())


def parse_detail(html_text: str) -> dict[str, str]:
    """상세 HTML → 표 필드. 몸통은 질의요지·회답·이유 3단 (expc 와 같은 결)."""
    fields: dict[str, str] = {}
    for m in _ROW_FIELD_RE.finditer(html_text):
        label = m.group(1).strip()
        if label not in fields:              # 같은 라벨 중복(처리구분)은 첫 값
            fields[label] = _clean(m.group(2))
    return {"issue": fields.get("질의요지", ""), "answer": fields.get("회답", ""),
            "reason": fields.get("이유", ""), "dept": fields.get("소관부서", ""),
            "replied": fields.get("회신일", ""),
            "attachment": fields.get("첨부파일", "")}


def case_text(case: dict[str, str], title: str = "") -> str:
    return "\n".join((title, case.get("issue", ""), case.get("answer", ""),
                      case.get("reason", "")))


class FscClient:
    """목록 페이지 순회 + 상세 획득. 요청 규율은 HttpClient 소유."""

    def __init__(self, client: HttpClient) -> None:
        self.client = client
        self.client.session.headers.setdefault("Referer", BASE + "/fsc_new/")

    def search_all(self, query: str) -> tuple[int, list[dict]]:
        total, rows, start = 0, [], 0
        for _ in range(MAX_PAGES):
            resp = self.client.post(LIST_URL, data={
                "draw": "1", "start": str(start), "length": str(PAGE_SIZE),
                "searchCondition": "all", "searchKeyword": query})
            try:
                payload = resp.json()
            except ValueError as e:
                raise RuntimeError(f"{query}: 목록 응답이 JSON 이 아님: {e}")
            total = int(payload.get("recordsTotal", 0) or 0)
            got = payload.get("data", [])
            _, batch = parse_list(payload)
            rows.extend(batch)
            start += len(got)
            if not got or start >= total:
                break
        return total, rows

    def fetch_detail(self, kind: str, idx: str) -> str:
        gubun, url, key = DETAIL[kind]
        resp = self.client.post(url, data={"muNo": "117", "stNo": "11",
                                           key: idx, "actCd": "R"})
        return resp.text
