"""거래소 KRX 법무포털(rule.krx.co.kr) 어댑터.

실측 모델 (docs/site_survey.md §3 + 별표 흐름 추가 실측):
- 세션: GET /out/index.do → JSESSIONID + 페이지 내 _csrf (Spring Security)
- 목록: POST /out/regulation/getTreeNode.do (X-CSRF-TOKEN) — JSON 트리
  0 → [정관, 업무규정] → 업무규정 → 11개 분류 → 분류별 문서(text, bookid)
- 본문: regulationMain.do 선행 → regulationView.do(bookid) → 조문 전체 HTML
  (개정 이력·조문별 시행일 포함) + JS 의 STATEHISTORYID(판 ID)
- 문서 파일: downloadRuleFile.do(bookid, statehistoryid, filecd) → JSON fileMap
  filecd 실측: JUN=전문 / GAE=개정문 / SIN=신구조문 / REA=개정이유 / ENG=영문
- 별표·별지서식: regulationList.do(mtype=byul) 를 세션에 먼저 열어야
  regulationListData.do(gbnid=BYUL|BYULSEO) 가 JSON 을 준다 (안 열면 500).
  응답 행: TITLE(규정명)·PCFILENAME·SERVERFILE — 전 규정 공용 목록이라 TITLE 로 거른다.
- 다운로드: POST /Download.do (Serverfile, Pcfilename, folder=ATTACH, _csrf)
  ⚠ 실측: 토큰은 1회용이다. /login/getData.do 가 주는 신선 토큰으로만 열리고,
  재사용·페이지 토큰이면 200 + 88B alert 페이지가 온다. KrxClient 가 Download.do
  요청마다 신선 토큰을 받아 주입한다 (파이프라인의 fetch_ref 는 그대로 둔다).
"""
from __future__ import annotations

import json
import re
from typing import Iterable

import requests

from .base import DocumentRef, Target
from .common import FetchError, HttpClient, make_session

BASE = "https://rule.krx.co.kr"

# 별표 목록의 gbnid 분류 — 목록 페이지 JS 의 노드 매핑 (BYULCH 등은 트리에 없지만
# 코드가 알고 있는 분류라 시도하고, 500 이면 그 분류가 없는 것으로 취급한다)
BYUL_CATEGORIES = {
    "BYUL": "별표",
    "BYULSEO": "별지서식",
    "BYULCH": "별첨",
    "BYULBU": "부록",
    "BYULJI": "별지",
}

_CSRF_JS_RE = re.compile(r'name:"_csrf",\s*value:"([0-9a-f-]{36})"')
_CSRF_META_RE = re.compile(r'content="([0-9a-f-]{36})"')
_SHID_RE = re.compile(r'name:"STATEHISTORYID",\s*value:"(\d+)"')


def _norm(label: str) -> str:
    return re.sub(r"\s+", "", label)


# ---------------------------------------------------------------- 순수 파싱 (픽스처 테스트 대상)

def parse_csrf(html: str) -> str | None:
    m = _CSRF_JS_RE.search(html) or _CSRF_META_RE.search(html)
    return m.group(1) if m else None


def parse_statehistoryid(html: str) -> str | None:
    m = _SHID_RE.search(html)
    return m.group(1) if m else None


def parse_doc_nodes(nodes: list[dict]) -> dict[str, dict]:
    """트리 노드 목록 → {정규화 규정명: 노드} (catcd=doc 만)"""
    return {_norm(n["text"]): n for n in nodes if n.get("catcd") == "doc"}


def filter_byul_rows(rows: list[dict], label: str) -> list[dict]:
    """별표 목록 행에서 규정명이 정확히 일치하는 행만 (부분일치 금지 —
    '유가증권시장 상장규정'이 '… 시행세칙' 행을 끌어오면 안 된다)"""
    return [r for r in rows if _norm(r.get("TITLE", "")) == _norm(label)]


def is_alert_page(body: bytes) -> bool:
    """Download.do 의 88B '잘못된 접근' 응답 — 200 으로 위장한 실패."""
    return body.lstrip()[:8].startswith(b"<script>")


# ---------------------------------------------------------------- 클라이언트

class KrxClient(HttpClient):
    """Download.do 요청마다 신선 CSRF 토큰(1회용)을 받아 주입하는 HttpClient."""

    def __init__(self, session: requests.Session, logger, **kw) -> None:
        super().__init__(session, logger, **kw)
        self.page_csrf: str = ""

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        # ref 에 박제된 _csrf 는 요청 시점에 항상 살아있는 토큰으로 바꾼다
        # (Download.do 는 1회용 신선 토큰, 그 외는 현재 페이지 토큰 — 실측 §3)
        if kwargs.get("data") is not None and "_csrf" in kwargs["data"]:
            data = dict(kwargs["data"])
            if url.endswith("/Download.do"):
                data["_csrf"] = self._fresh_token()
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("Referer", f"{BASE}/out/regulation/regulationView.do")
                kwargs["headers"] = headers
            else:
                data["_csrf"] = self.page_csrf
            kwargs["data"] = data
        resp = super().request(method, url, **kwargs)
        if not url.endswith("/Download.do"):
            new = parse_csrf(resp.text) if b"csrf" in resp.content[:65536] else None
            if new:
                self.page_csrf = new
        return resp

    def _fresh_token(self) -> str:
        resp = super().request(
            "POST", f"{BASE}/login/getData.do",
            headers={"X-CSRF-TOKEN": self.page_csrf},
            data={"_csrf": self.page_csrf},
        )
        try:
            return resp.json()["data"]["_csrf"]
        except (ValueError, KeyError, TypeError) as e:
            raise FetchError(f"신선 토큰 획득 실패: {resp.status_code} {resp.text[:120]!r}") from e


# ---------------------------------------------------------------- 어댑터

class KrxAdapter:
    source_id = "krx"

    def __init__(self, client: KrxClient) -> None:
        self.client = client
        self._booted = False
        self._docs: dict[str, dict] | None = None
        self._byul: list[dict] | None = None
        self._meta: dict[str, dict[str, str]] = {}

    def session(self) -> requests.Session:
        return self.client.session

    def expand_targets(self, target: Target) -> list[Target]:
        return [target]

    # -- discover ----------------------------------------------------------

    def discover(self, target: Target) -> list[DocumentRef]:
        self._boot()
        node = self._doc_lookup(target.label)
        bookid = str(node["bookid"])

        view = self._post_html(
            f"{BASE}/out/regulation/regulationView.do",
            {"bookid": bookid, "noformyn": node.get("noformyn") or "N", "gbnid": "0",
             "mtype": "htree", "searchForm": "", "Menucd": "BYLAW"},
        )
        shid = parse_statehistoryid(view)
        if not shid:
            raise RuntimeError(f"{target.label}: STATEHISTORYID 해석 실패 (bookid={bookid})")

        refs: list[DocumentRef] = [
            DocumentRef(
                title=f"{target.label} 조문",
                url=f"{BASE}/out/regulation/regulationView.do",
                role="body", version_hint=shid, file_ext=".html", method="POST",
                data={"bookid": bookid, "noformyn": node.get("noformyn") or "N",
                      "gbnid": "0", "mtype": "htree", "searchForm": "",
                      "Menucd": "BYLAW", "_csrf": ""},
            ),
        ]

        # 문서 파일: 전문 / 개정문 / 신구조문 — fileMap 이 없으면 그 파일이 없는 판이다
        for filecd, (title, role, subdir) in {
            "JUN": (f"{target.label} 전문", "body", ""),
            "GAE": (f"{target.label} 개정문", "attachment", ""),
            "SIN": (f"{target.label} 신구조문대비표", "comparison_table", "신구조문대비표"),
        }.items():
            file_map = self._rule_file(bookid, shid, filecd)
            if not file_map:
                continue
            refs.append(self._download_ref(
                title=title, role=role, subdir=subdir, version_hint=shid,
                serverfile=file_map["SERVERFILE"], pcfilename=file_map["PCFILENAME"],
            ))

        # 별표·별지서식 — 전 규정 공용 목록에서 이 규정 행만
        for row in filter_byul_rows(self._byul_rows(), target.label):
            refs.append(self._download_ref(
                title=row.get("PCFILENAME") or row["SERVERFILE"],
                role="attachment", subdir=BYUL_CATEGORIES.get(row["_gbnid"], "별표"),
                version_hint=str(row.get("STATEHISTORYID") or shid),
                serverfile=row["SERVERFILE"], pcfilename=row.get("PCFILENAME") or "",
            ))

        self._meta[target.key] = {
            "seq": bookid, "history_seq": shid,
            "revised": str(node.get("promuldt") or ""),
            "rev_kind": str(node.get("revcd") or ""),
            "enforce": str(node.get("startdt") or ""),
            "dept": str(node.get("dept") or ""),
        }
        return refs

    def metadata(self, target: Target) -> dict[str, str]:
        return self._meta.get(target.key, {})

    # -- 내부 --------------------------------------------------------------

    def _boot(self) -> None:
        if self._booted:
            return
        resp = self.client.get(f"{BASE}/out/index.do")
        csrf = parse_csrf(resp.text)
        if not csrf:
            raise RuntimeError("index.do 에서 CSRF 토큰을 찾지 못함")
        self.client.page_csrf = csrf
        self._post_html(
            f"{BASE}/out/regulation/regulationMain.do",
            {"Menucd": "BYLAW", "index": "law_rule", "gbn": "out"},
        )
        self._booted = True

    def _post_html(self, url: str, data: dict[str, str]) -> str:
        """페이지 POST — 응답에 새 토큰이 있으면 갱신, 토큰 거부면 1회 재시도."""
        for attempt in (0, 1):
            resp = self.client.post(url, data={**data, "_csrf": self.client.page_csrf})
            new = parse_csrf(resp.text)
            if resp.status_code == 200 and len(resp.content) > 4096:
                if new:
                    self.client.page_csrf = new
                return resp.text
            if new:
                self.client.page_csrf = new  # 오류 페이지가 새 토큰을 들고 온다 — 재시도
        raise FetchError(f"페이지 POST 실패: {url} ({resp.status_code}, {len(resp.content)}B)")

    def _post_json(self, url: str, data: dict[str, str]):
        # Referer 없으면 regulationListData.do 가 500 을 준다 (실측 — 격리 실험)
        resp = self.client.post(
            url, data=data,
            headers={"X-CSRF-TOKEN": self.client.page_csrf,
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": f"{BASE}/out/regulation/regulationList.do"},
        )
        try:
            return resp.json()
        except ValueError:
            new = parse_csrf(resp.text)
            if new:
                self.client.page_csrf = new
            return None

    def _rule_file(self, bookid: str, shid: str, filecd: str) -> dict | None:
        j = self._post_json(
            f"{BASE}/web/regulation/downloadRuleFile.do",
            {"bookid": bookid, "statehistoryid": shid, "filecd": filecd},
        )
        return (j or {}).get("fileMap")

    def _download_ref(self, title: str, role: str, subdir: str, version_hint: str,
                      serverfile: str, pcfilename: str) -> DocumentRef:
        # _csrf 는 자리표시자 — KrxClient 가 요청 직전에 신선 토큰으로 바꾼다
        return DocumentRef(
            title=title, url=f"{BASE}/Download.do", role=role,  # type: ignore[arg-type]
            version_hint=version_hint, file_ext=".hwp", subdir=subdir, method="POST",
            data={"Serverfile": serverfile, "Pcfilename": pcfilename,
                  "folder": "ATTACH", "_csrf": ""},
        )

    def _doc_lookup(self, label: str) -> dict:
        if self._docs is None:
            docs: dict[str, dict] = {}
            root = self._tree_nodes("0")
            for lv1 in root:
                if "업무규정" not in lv1.get("text", "") and "정관" not in lv1.get("text", ""):
                    continue
                for cat in self._tree_nodes(str(lv1["id"])):
                    if cat.get("catcd") == "doc":
                        docs.update(parse_doc_nodes([cat]))
                        continue
                    docs.update(parse_doc_nodes(self._tree_nodes(str(cat["id"]))))
            self._docs = docs
        entry = self._docs.get(_norm(label))
        if not entry:
            raise RuntimeError(f"KRX 트리에서 규정을 찾지 못함: {label}")
        return entry

    def _tree_nodes(self, node: str) -> list[dict]:
        j = self._post_json(
            f"{BASE}/out/regulation/getTreeNode.do",
            {"node": node, "statecd": "현행", "mtype": "htree", "Menucd": "BYLAW",
             "webgbn": "OUT", "gbnid": "0", "gbn2": "out"},
        )
        if not isinstance(j, list):
            raise FetchError(f"트리 조회 실패 (node={node})")
        return j

    def _byul_rows(self) -> list[dict]:
        if self._byul is not None:
            return self._byul
        # 목록 페이지를 세션에 열어야 데이터 API 가 응답한다 (실측 — 안 열면 500)
        self._post_html(
            f"{BASE}/out/regulation/regulationList.do",
            {"Menucd": "BYLAW", "mtype": "byul", "gbnid": "BYUL", "smType": "byul",
             "index": "law_rule", "gbn": "out"},
        )
        rows: list[dict] = []
        for gbnid in BYUL_CATEGORIES:
            start, total = 0, None
            while total is None or start < total:
                j = self._post_json(
                    f"{BASE}/web/regulation/regulationListData.do",
                    {"start": str(start), "limit": "100", "mtype": "byul",
                     "Menucd": "BYLAW", "stit": "규정", "gbnid": gbnid, "gbn2": "out"},
                )
                if not isinstance(j, dict) or "result" not in j:
                    break  # 이 분류가 없는 것 (BYULCH 등) — 500 은 _post_json 이 None 으로
                total = int(j.get("total") or 0)
                for row in j["result"]:
                    row["_gbnid"] = gbnid
                    rows.append(row)
                start += 100
        self._byul = rows
        return rows


def build(logger) -> KrxAdapter:
    return KrxAdapter(KrxClient(make_session(), logger))
