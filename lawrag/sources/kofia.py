"""금투협 법규정보시스템(law.kofia.or.kr) 어댑터.

실측 모델 (docs/site_survey.md §1):
- 규정 트리 lawCurrentPartTree.do 의 gotoLawList(...) 인자에서 seq/lawType/hseq 를 얻는다
- 본문은 lawFullScreenContent.do (조문 HTML) + download.do?gubun=101 (전문 HWP)
- 별표는 조문 HTML 의 [별표/서식 파일] 섹션 → gubun=102
- 신구조문대비표는 개정 건 상세(revisionView.do)의 gubun=105 버튼 — 개정 건마다
  있을 수도 없을 수도 있어 최근 판부터 역탐색한다
- 시행일 필드는 사이트에 없다. 개정일(revisionInfo.do)을 기록하고 해시로 개정을 감지한다
"""
from __future__ import annotations

import re
from typing import Iterable

import requests

from .base import DocumentRef, Target
from .common import HttpClient, make_session

BASE = "https://law.kofia.or.kr"

# 존재하지 않는 경로가 307 → /common/error.html (200) 로 위장하는 사이트다
ERROR_MARKERS = ("페이지를 찾을 수 없습니다", "/common/error.html", "에러페이지")

_TREE_ENTRY_RE = re.compile(
    r"gotoLawList\('(?P<seq>\d+)',\s*'(?P<folder>\d)',\s*'(?P<label>[^']*)'"
    r"(?:,\s*'[^']*'){6},\s*'(?P<law_type>[^']*)',\s*'(?P<hseq>[^']*)'"
)
_PART_ROW_RE = re.compile(
    r'href="/service/law/lawView\.do\?seq=(?P<seq>\d+)&(?:amp;)?historySeq=(?P<hseq>\d+)'
    r'[^"]*"[^>]*>\s*(?P<label>[^<]+?)\s*<'
)
_CONTENT_HSEQ_RE = re.compile(
    r'lawFullScreenContent\.do\?seq=(\d+)&(?:amp;)?historySeq=(\d+)'
)
_ATTACH_RE = re.compile(
    r'href="(?P<url>/download\.do\?gubun=102&(?:amp;)?seq=\d+)"[^>]*>\s*(?P<title>[^<]+?)\s*</a>'
)
_REV_ROW_RE = re.compile(
    r'href="/service/revision/revisionView\.do\?historySeq=(?P<hseq>\d+)"[^>]*>'
    r'\s*(?P<label>[^<]+?)\s*</a>'
)
_REV_BUTTON_RE = re.compile(
    r'href="(?P<url>/download\.do\?gubun=(?P<gubun>10[145])&(?:amp;)?seq=\d+)"[^>]*'
    r'title="(?P<title>[^"]*)"'
)
_REV_INFO_ROW_RE = re.compile(r"<th[^>]*>\s*([^<]+?)\s*</th>\s*<td[^>]*>(.*?)</td>", re.S)
_PAGE_LINK_RE = re.compile(r"goPage\('(\d+)'\)")


def _norm(label: str) -> str:
    """규정명 비교 키 — 공백 차이(옛 표기 '증권인수업무등에관한규정')를 무시한다."""
    return re.sub(r"\s+", "", label)


def _clean_url(url: str) -> str:
    return BASE + url.replace("&amp;", "&")


# ---------------------------------------------------------------- 순수 파싱 (픽스처 테스트 대상)

def parse_tree(html: str) -> dict[str, dict[str, str]]:
    """트리 HTML → {정규화 규정명: {seq, folder, law_type, hseq, label}}"""
    out: dict[str, dict[str, str]] = {}
    for m in _TREE_ENTRY_RE.finditer(html):
        d = m.groupdict()
        out[_norm(d["label"])] = d
    return out


def parse_part_list(html: str) -> list[dict[str, str]]:
    """분류 목록 페이지 → [{seq, hseq, label}] (문서 순서 유지, 중복 제거)"""
    seen: dict[str, dict[str, str]] = {}
    for m in _PART_ROW_RE.finditer(html):
        d = m.groupdict()
        d["label"] = re.sub(r"\s+", " ", d["label"]).strip()
        seen.setdefault(d["seq"], d)
    return list(seen.values())


def parse_part_list_pages(html: str) -> int:
    pages = [int(p) for p in _PAGE_LINK_RE.findall(html)]
    return max(pages) if pages else 1


def parse_view_hseq(html: str) -> str | None:
    m = _CONTENT_HSEQ_RE.search(html)
    return m.group(2) if m else None


def parse_content_attachments(html: str) -> list[dict[str, str]]:
    return [
        {"url": _clean_url(m.group("url")), "title": re.sub(r"\s+", " ", m.group("title")).strip()}
        for m in _ATTACH_RE.finditer(html)
    ]


def parse_revision_rows(html: str) -> list[dict[str, str]]:
    return [{"hseq": m.group("hseq"), "label": re.sub(r"\s+", " ", m.group("label")).strip()}
            for m in _REV_ROW_RE.finditer(html)]


def parse_revision_buttons(html: str) -> dict[str, dict[str, str]]:
    """revisionView HTML → {gubun: {url, title}} — 101 전문 / 104 개정문 / 105 신구대비표"""
    out: dict[str, dict[str, str]] = {}
    for m in _REV_BUTTON_RE.finditer(html):
        out.setdefault(m.group("gubun"), {"url": _clean_url(m.group("url")), "title": m.group("title")})
    return out


def parse_revision_info(html: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for th, td in _REV_INFO_ROW_RE.findall(html):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", td)).strip()
        info[th.strip()] = text
    return info


def is_error_page(text: str) -> bool:
    return any(marker in text for marker in ERROR_MARKERS)


# ---------------------------------------------------------------- 어댑터

class KofiaAdapter:
    source_id = "kofia"

    def __init__(self, client: HttpClient) -> None:
        self.client = client
        self._tree: dict[str, dict[str, str]] | None = None
        self._meta: dict[str, dict[str, str]] = {}

    def session(self) -> requests.Session:
        return self.client.session

    # -- 대상 전개 ---------------------------------------------------------

    def expand_targets(self, target: Target) -> list[Target]:
        folder_seq = target.hints.get("folder_seq")
        if not folder_seq:
            return [target]
        members: list[Target] = []
        page, last_page = 1, 1
        while page <= last_page:
            resp = self.client.post(
                f"{BASE}/service/law/lawPartCurrentList.do",
                data={"page": str(page), "selectedSeq": folder_seq},
            )
            last_page = max(last_page, parse_part_list_pages(resp.text))
            for row in parse_part_list(resp.text):
                members.append(
                    Target(
                        source_id=self.source_id,
                        key=row["label"],
                        label=row["label"],
                        hints={"seq": row["seq"], "hseq": row["hseq"]},
                    )
                )
            page += 1
        return members

    # -- discover ----------------------------------------------------------

    def discover(self, target: Target) -> list[DocumentRef]:
        seq = target.hints.get("seq")
        hseq = target.hints.get("hseq")
        if not seq:
            entry = self._tree_lookup(target.label)
            seq, hseq = entry["seq"], entry["hseq"] or None
            if entry["law_type"] != "1":
                raise RuntimeError(
                    f"{target.label}: lawType={entry['law_type']} (비정형/외부링크) — 수집 대상 아님"
                )
        if not hseq:
            view = self.client.get(
                f"{BASE}/service/law/lawView.do",
                params={"seq": seq, "historySeq": "0", "gubun": "cur", "tree": "part"},
            )
            hseq = parse_view_hseq(view.text)
            if not hseq:
                raise RuntimeError(f"{target.label}: 현행 historySeq 해석 실패 (seq={seq})")

        refs: list[DocumentRef] = [
            DocumentRef(
                title=f"{target.label} 전문",
                url=f"{BASE}/download.do?gubun=101&seq={hseq}",
                role="body", version_hint=hseq, file_ext=".hwp",
            ),
            DocumentRef(
                title=f"{target.label} 조문",
                url=f"{BASE}/service/law/lawFullScreenContent.do?seq={seq}&historySeq={hseq}",
                role="body", version_hint=hseq, file_ext=".html",
            ),
        ]

        content = self.client.get(
            f"{BASE}/service/law/lawFullScreenContent.do",
            params={"seq": seq, "historySeq": hseq},
        )
        if is_error_page(content.text):
            raise RuntimeError(f"{target.label}: 본문 조회가 에러페이지 (seq={seq}, hseq={hseq})")
        for att in parse_content_attachments(content.text):
            refs.append(
                DocumentRef(
                    title=att["title"], url=att["url"], role="attachment",
                    version_hint=hseq, file_ext=".hwp", subdir="별표서식",
                )
            )

        refs.extend(self._revision_refs(target.label, hseq))

        info = parse_revision_info(
            self.client.get(f"{BASE}/service/law/revisionInfo.do", params={"historySeq": hseq}).text
        )
        self._meta[target.key] = {
            "seq": seq, "history_seq": hseq,
            "revised": info.get("개정일", ""), "rev_kind": info.get("제개정구분", ""),
            "dept": info.get("담당부서", ""),
        }
        return refs

    def metadata(self, target: Target) -> dict[str, str]:
        return self._meta.get(target.key, {})

    # -- 내부 --------------------------------------------------------------

    def _tree_lookup(self, label: str) -> dict[str, str]:
        if self._tree is None:
            resp = self.client.get(f"{BASE}/service/law/lawCurrentPartTree.do")
            self._tree = parse_tree(resp.text)
        entry = self._tree.get(_norm(label))
        if not entry:
            raise RuntimeError(f"트리에서 규정을 찾지 못함: {label}")
        return entry

    def _revision_refs(self, label: str, current_hseq: str,
                       lookback: int = 5) -> Iterable[DocumentRef]:
        """개정 이력에서 개정문(최신 판)과 신구조문대비표(최신 발견 1건)를 찾는다."""
        resp = self.client.post(
            f"{BASE}/service/revision/revisionlist.do",
            data={"page": "1", "searchValue": label},
        )
        rows = [r for r in parse_revision_rows(resp.text) if _norm(r["label"]) == _norm(label)]
        if not rows and current_hseq:
            rows = [{"hseq": current_hseq, "label": label}]

        refs: list[DocumentRef] = []
        found_comparison = False
        for i, row in enumerate(rows[:lookback]):
            view = self.client.get(
                f"{BASE}/service/revision/revisionView.do", params={"historySeq": row["hseq"]}
            )
            buttons = parse_revision_buttons(view.text)
            if i == 0 and "104" in buttons:
                refs.append(
                    DocumentRef(
                        title=f"{label} 개정문", url=buttons["104"]["url"], role="attachment",
                        version_hint=row["hseq"], file_ext=".hwp",
                    )
                )
            if not found_comparison and "105" in buttons:
                refs.append(
                    DocumentRef(
                        title=f"{label} 신구조문대비표", url=buttons["105"]["url"],
                        role="comparison_table", version_hint=row["hseq"],
                        file_ext=".hwp", subdir="신구조문대비표",
                    )
                )
                found_comparison = True
            if found_comparison:
                break
        return refs


def build(logger) -> KofiaAdapter:
    return KofiaAdapter(HttpClient(make_session(), logger))
