"""국가법령정보센터 OPEN API(law.go.kr/DRF) 어댑터 — 법령·행정규칙.

실측 모델 (2026-08-10 확인):
- 검색: GET /DRF/lawSearch.do?OC=<oc>&target=law|admrul&type=XML&query=<명칭>
  law 는 <law> 행(법령일련번호=MST·시행일자·공포일자·현행연혁코드),
  admrul 은 <admrul> 행(행정규칙일련번호·발령일자·현행연혁구분)
- 본문: GET /DRF/lawService.do?OC=<oc>&target=law&MST=<mst>&type=XML
  (admrul 은 ID=<행정규칙일련번호>) — 조문 전체 + <별표단위> 블록
- 별표·서식: 본문 XML 의 <별표단위>/<별표서식파일링크> → /LSW/flDownload.do?flSeq=
  HWP 원문만 받는다 (PDF·이미지 링크는 같은 내용의 파생본)
- 행정규칙 <첨부파일> 블록도 flDownload 링크 — 그대로 수집
- OC 는 등록 이메일 ID. 기본값 test 는 API 문서의 예시 키로 동작이 확인되지만,
  운영 수집은 open.law.go.kr 에서 발급받아 LAW_OC 환경변수로 넣을 것.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import date

import requests

from .base import DocumentRef, Target
from .common import HttpClient, make_session

BASE = "https://www.law.go.kr"
_FLSEQ_RE = re.compile(r"flSeq=(\d+)")


def _norm(label: str) -> str:
    return re.sub(r"\s+", "", label)


def _fl_url(link: str) -> str | None:
    m = _FLSEQ_RE.search(link or "")
    return f"{BASE}/LSW/flDownload.do?flSeq={m.group(1)}" if m else None


# ---------------------------------------------------------------- 순수 파싱 (픽스처 테스트 대상)

def parse_search(xml_text: str, kind: str) -> list[dict[str, str]]:
    """검색 응답 → 행 목록. kind: 'law' | 'admrul'"""
    root = ET.fromstring(xml_text)
    rows: list[dict[str, str]] = []
    if kind == "law":
        for el in root.iter("law"):
            rows.append({
                "name": el.findtext("법령명한글", "").strip(),
                "serial": el.findtext("법령일련번호", "").strip(),      # MST
                "doc_id": el.findtext("법령ID", "").strip(),
                "promulgated": el.findtext("공포일자", "").strip(),
                "promul_no": el.findtext("공포번호", "").strip(),
                "rev_kind": el.findtext("제개정구분명", "").strip(),
                "enforce": el.findtext("시행일자", "").strip(),
                "dept": el.findtext("소관부처명", "").strip(),
                "current": el.findtext("현행연혁코드", "").strip(),
            })
    else:
        for el in root.iter("admrul"):
            rows.append({
                "name": el.findtext("행정규칙명", "").strip(),
                "serial": el.findtext("행정규칙일련번호", "").strip(),
                "doc_id": el.findtext("행정규칙ID", "").strip(),
                "promulgated": el.findtext("발령일자", "").strip(),
                "promul_no": el.findtext("발령번호", "").strip(),
                "rev_kind": el.findtext("제개정구분명", "").strip(),
                "enforce": el.findtext("시행일자", "").strip(),
                "dept": el.findtext("소관부처명", "").strip(),
                "current": el.findtext("현행연혁구분", "").strip(),
            })
    return rows


def parse_body_meta(xml_text: str, kind: str = "law") -> dict[str, str]:
    """본문 응답의 기본정보를 검색 행과 같은 메타 모양으로 읽는다.

    법령 검색 API는 같은 이름의 시행 예정·현행 가지가 함께 나타날 수 있다.
    재현 실험이 특정 MST/ID를 고정한 경우에는 검색 행의 메타가 아니라 실제로
    받은 본문 머리말이 정본이어야 한다.
    """
    root = ET.fromstring(xml_text)
    if kind == "law":
        return {
            "name": root.findtext(".//법령명_한글", "").strip(),
            "doc_id": root.findtext(".//법령ID", "").strip(),
            "promulgated": root.findtext(".//공포일자", "").strip(),
            "promul_no": root.findtext(".//공포번호", "").strip(),
            "rev_kind": root.findtext(".//제개정구분", "").strip(),
            "enforce": root.findtext(".//시행일자", "").strip(),
            "dept": (root.findtext(".//소관부처", "").strip()
                     or root.findtext(".//소관부처명", "").strip()),
        }
    return {
        "name": root.findtext(".//행정규칙명", "").strip(),
        "doc_id": root.findtext(".//행정규칙ID", "").strip(),
        "promulgated": root.findtext(".//발령일자", "").strip(),
        "promul_no": root.findtext(".//발령번호", "").strip(),
        "rev_kind": root.findtext(".//제개정구분", "").strip(),
        "enforce": root.findtext(".//시행일자", "").strip(),
        "dept": (root.findtext(".//소관부처", "").strip()
                 or root.findtext(".//소관부처명", "").strip()),
    }


def parse_annexes(xml_text: str) -> list[dict[str, str]]:
    """본문 XML → 별표·서식 HWP 링크 목록 [{title, url}] (+ 행정규칙 첨부파일)"""
    root = ET.fromstring(xml_text)
    out: list[dict[str, str]] = []
    for el in root.iter("별표단위"):
        url = _fl_url(el.findtext("별표서식파일링크", ""))
        if not url:
            continue
        gubun = el.findtext("별표구분", "별표").strip() or "별표"
        no = (el.findtext("별표번호", "").lstrip("0") or "0").strip()
        branch = el.findtext("별표가지번호", "").lstrip("0").strip()
        title = el.findtext("별표제목", "").strip()
        label = f"[{gubun} {no}{'의' + branch if branch else ''}] {title}"
        out.append({"title": label, "url": url})
    for el in root.iter("첨부파일"):
        url = _fl_url(el.findtext("첨부파일링크", ""))
        if not url:
            continue
        out.append({"title": el.findtext("첨부파일명", "첨부파일").strip() or "첨부파일",
                    "url": url})
    return out


# ---------------------------------------------------------------- 어댑터

class LawGoAdapter:
    source_id = "law"

    def __init__(self, client: HttpClient, oc: str | None = None) -> None:
        self.client = client
        self.oc = oc or os.environ.get("LAW_OC", "test")
        self._meta: dict[str, dict[str, str]] = {}

    def session(self) -> requests.Session:
        return self.client.session

    def expand_targets(self, target: Target) -> list[Target]:
        return [target]

    def discover(self, target: Target) -> list[DocumentRef]:
        kind = target.hints.get("kind", "law")
        pinned = str(target.hints.get("serial") or "").strip()
        requested_as_of = str(target.hints.get("as_of") or "").replace("-", "")
        if pinned:
            row = {"serial": pinned}
        else:
            resp = self.client.get(
                f"{BASE}/DRF/lawSearch.do",
                params={"OC": self.oc, "target": kind, "type": "XML",
                        "query": target.label, "display": "50"},
            )
            try:
                rows = parse_search(resp.text, kind)
            except ET.ParseError as e:
                raise RuntimeError(f"{target.label}: 검색 응답이 XML 이 아님 (OC 거부?): {e}")
            matches = [r for r in rows
                       if _norm(r["name"]) == _norm(target.label)
                       and r["current"] == "현행"]
            if not matches:
                raise RuntimeError(
                    f"{target.label}: 현행 항목을 찾지 못함 "
                    f"(검색 {len(rows)}건: {[r['name'] for r in rows][:5]})")
            row = sorted(matches, key=lambda r: (
                r.get("doc_id", ""), r.get("enforce", ""), r.get("serial", "")))[0]

        if kind == "law" and not pinned:
            body_url = (f"{BASE}/DRF/lawService.do?OC={self.oc}&target=eflaw"
                        f"&ID={row['doc_id']}&type=XML")
            authority_mode = "effective-current"
        elif kind == "law" and requested_as_of:
            body_url = (f"{BASE}/DRF/lawService.do?OC={self.oc}&target=eflaw"
                        f"&MST={row['serial']}&efYd={requested_as_of}&type=XML")
            authority_mode = "effective-date"
        elif kind == "law":
            body_url = (f"{BASE}/DRF/lawService.do?OC={self.oc}&target=law"
                        f"&MST={row['serial']}&type=XML")
            authority_mode = "pinned-revision"
        else:
            body_url = (f"{BASE}/DRF/lawService.do?OC={self.oc}&target=admrul"
                        f"&ID={row['serial']}&type=XML")
            authority_mode = "official-current"

        refs: list[DocumentRef] = [
            DocumentRef(
                title=f"{target.label} 본문",
                url=body_url, role="body", version_hint=row["serial"], file_ext=".xml",
            ),
        ]

        body = self.client.get(body_url)
        try:
            annexes = parse_annexes(body.text)
            row.update({k: v for k, v in parse_body_meta(body.text, kind).items() if v})
        except ET.ParseError as e:
            raise RuntimeError(f"{target.label}: 본문 응답이 XML 이 아님: {e}")
        for annex in annexes:
            refs.append(DocumentRef(
                title=annex["title"], url=annex["url"], role="attachment",
                version_hint=row["serial"], file_ext=".hwp", subdir="별표서식",
            ))

        self._meta[target.key] = {
            "seq": row["serial"], "kind": kind,
            "revised": row["promulgated"], "rev_kind": row["rev_kind"],
            "enforce": row["enforce"], "dept": row["dept"],
            "promul_no": row["promul_no"], "law_id": row.get("doc_id", ""),
            "authority_mode": authority_mode,
            "authority_as_of": (requested_as_of
                                  if requested_as_of not in ("", "current")
                                  else date.today().strftime("%Y%m%d")),
        }
        return refs

    def metadata(self, target: Target) -> dict[str, str]:
        return self._meta.get(target.key, {})


def build(logger) -> LawGoAdapter:
    return LawGoAdapter(HttpClient(make_session(), logger))
