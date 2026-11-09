"""법제처(law.go.kr DRF) 본문 XML → 증분 공통 구조 (DocumentSnapshot).

입력 두 가지 (실측 2026-11-06, 보유 판본 대조):
- `<법령>` (target=law/eflaw): 조문단위마다 조문번호·조문가지번호·조문여부(전문/조문)·
  조문시행일자·조문변경여부·조문이동이전/이후 태그와 항·호·목 하위 태그가 있다.
- `<AdmRulService>` (target=admrul): 조문내용이 평문이다. 행 머리로 조를 가른다.
  `제26조 삭제<2025. 2. 5.>` 처럼 제목 없이 삭제 표시가 붙는 행이 실재한다.

문서 불변 ID는 이름이 아니라 법령ID·행정규칙ID다. 행정규칙ID는 발령마다 바뀌는
행정규칙일련번호와 달리 판본 간 같다 (전자금융감독규정 2026-7·2026-29 모두 21828,
외부감사 및 회계 등에 관한 규정 21840 확인).

파싱 규칙
- 조문 시작은 `제N조(제목)`, `제N조 삭제`, `제N조 <삭제…>`, 제목 없는 `제N조` 단독 행만.
  `제1조에 따른…`으로 시작하는 행은 본문 계속행이다.
- 장·절·관·편 제목은 조문 본문에 넣지 않는다.
- 첫 조문 앞의 문장은 `전문`으로 보존한다.
- 부칙은 공포번호별로 따로 둔다 (`부칙:21065`). 마지막 부칙이 이번 개정분이다.
- 별표는 `별표1`, `별표1의2`, `서식3`. 본문 XML의 별표내용을 행 단위 텍스트로 쓴다.
- 조문 0건이거나 키가 겹치면 거절한다.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .normalize import article_key, compare_hash, normalize_text, sha256_text, text_hash

PREAMBLE = "전문"
KIND_ARTICLE, KIND_PREAMBLE, KIND_ADDENDUM, KIND_ANNEX = "ARTICLE", "PREAMBLE", "ADDENDUM", "ANNEX"

_DIVISION = re.compile(r"^제\s*\d+\s*(?:편|장|절|관)(?:\s*의\s*\d+)?(?:\s|\[|$)")
_FLAT_ARTICLE = re.compile(
    r"^제\s*(\d+(?:-\d+)?)\s*조(?:\s*의\s*(\d+))?\s*"
    r"(?:\(([^)]*)\)|(?=삭제)|<\s*삭제|$)")
_DELETED = re.compile(r"^제\s*\d+(?:-\d+)?\s*조(?:\s*의\s*\d+)?\s*(?:\([^)]*\)\s*)?<?\s*삭제")


class ParseError(ValueError):
    """구조화 거절 — 조문 0건, 키 중복, XML 형식 오류."""


@dataclass(frozen=True)
class Article:
    key: str
    kind: str
    title: str
    text: str
    seq: int
    deleted: bool = False
    official_effective: str = ""      # 법령 XML 조문시행일자 (YYYYMMDD)
    official_changed: str = ""        # 조문변경여부 Y/N (참고값)
    official_moved: tuple[str, str] = ("", "")
    source_link: str = ""             # 별표서식 파일 링크
    attachment_sha256: str = ""       # 별표서식 HWP 등 첨부 파일 sha (수집기가 채움)

    @property
    def text_hash(self) -> str:
        return text_hash(self.text)

    @property
    def compare_hash(self) -> str:
        return compare_hash(self.text)


@dataclass(frozen=True)
class Addendum:
    key: str
    promulgated: str
    number: str
    text: str


@dataclass
class DocumentSnapshot:
    doc_cd: str                 # LAW:<법령ID> | ADMRUL:<행정규칙ID>
    source_kind: str            # LAW | ADMRUL
    official_id: str
    name: str
    promulgated: str            # 공포일자/발령일자 YYYYMMDD
    promulgation_no: str
    effective: str              # 시행일자 YYYYMMDD
    revision_kind: str
    source_sha256: str
    articles: list[Article]
    addenda: list[Addendum] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def last_addendum(self) -> Addendum | None:
        return self.addenda[-1] if self.addenda else None

    def content_articles(self) -> list[Article]:
        return [a for a in self.articles if a.kind != KIND_ADDENDUM and not a.deleted]


def _clean(text: str | None) -> str:
    return (text or "").strip()


def _date(text: str | None) -> str:
    digits = re.sub(r"\D", "", text or "")
    return digits if len(digits) == 8 else ""


def _info(root: ET.Element, tag: str) -> dict[str, str]:
    base = root.find(tag)
    if base is None:
        return {}
    return {el.tag: _clean(el.text) for el in base if el.text is not None and not len(el)}


_CONTENT_TAGS = {"조문내용", "항내용", "호내용", "목내용"}


def _law_article_text(jo: ET.Element) -> str:
    # 문서 순서로 모은다. 목이 호의 자식이 아니라 항의 형제로 오는 판본이 있다
    # (실측: 금융회사의 지배구조에 관한 법률 제21065호 제5조제1항제6호 가~다목).
    parts = [_clean(el.text) for el in jo.iter() if el.tag in _CONTENT_TAGS]
    return "\n".join(p for p in parts if p)


def _law_articles(root: ET.Element) -> list[Article]:
    articles: list[Article] = []
    preamble: list[str] = []
    for jo in root.iter("조문단위"):
        text = _clean(jo.findtext("조문내용"))
        if _clean(jo.findtext("조문여부")) == "전문":
            if _DIVISION.match(text):
                continue                          # 장·절 제목은 조문 본문에 넣지 않는다
            if not articles:
                preamble.append(text)
            elif text:                            # 조문 사이의 비구획 전문 행 — 앞 조문에 붙여 보존
                last = articles[-1]
                articles[-1] = Article(**{**last.__dict__, "text": last.text + "\n" + text})
            continue
        key = article_key(_clean(jo.findtext("조문번호")), _clean(jo.findtext("조문가지번호")))
        body = _law_article_text(jo)
        articles.append(Article(
            key=key, kind=KIND_ARTICLE, title=_clean(jo.findtext("조문제목")), text=body,
            seq=0, deleted=bool(_DELETED.match(text)),
            official_effective=_date(jo.findtext("조문시행일자")),
            official_changed=_clean(jo.findtext("조문변경여부")),
            official_moved=(_clean(jo.findtext("조문이동이전")), _clean(jo.findtext("조문이동이후"))),
        ))
    if any(preamble):
        articles.insert(0, Article(PREAMBLE, KIND_PREAMBLE, PREAMBLE,
                                   "\n".join(p for p in preamble if p), 0))
    return articles


def split_flat_articles(lines: list[str]) -> list[Article]:
    """평문 조문 → Article 목록 (행정규칙·부칙 공용)."""
    articles: list[Article] = []
    preamble: list[str] = []
    current: dict | None = None

    def close() -> None:
        if current is not None:
            articles.append(Article(
                key=current["key"], kind=KIND_ARTICLE, title=current["title"],
                text="\n".join(current["lines"]), seq=0, deleted=current["deleted"]))

    for raw in lines:
        line = _clean(raw)
        if not line:
            continue
        if _DIVISION.match(line) and len(line) <= 80:
            continue
        match = _FLAT_ARTICLE.match(line)
        if match:
            close()
            current = {"key": article_key(match.group(1), match.group(2)),
                       "title": _clean(match.group(3)), "lines": [line],
                       "deleted": bool(_DELETED.match(line))}
            continue
        if current is None:
            preamble.append(line)
        else:
            current["lines"].append(line)
    close()
    if preamble:
        articles.insert(0, Article(PREAMBLE, KIND_PREAMBLE, PREAMBLE, "\n".join(preamble), 0))
    return articles


def _addenda(root: ET.Element) -> list[Addendum]:
    block = root.find("부칙")
    if block is None:
        return []
    rows: list[tuple[str, str, str]] = []
    units = block.findall("부칙단위")
    if units:
        rows = [(_clean(u.findtext("부칙공포일자")), _clean(u.findtext("부칙공포번호")),
                 u.findtext("부칙내용") or "") for u in units]
    else:                               # 행정규칙: 단위 래퍼 없이 세 태그가 반복된다
        current = ["", "", ""]
        for el in block:
            if el.tag == "부칙공포일자":
                if any(current):
                    rows.append(tuple(current))
                current = [_clean(el.text), "", ""]
            elif el.tag == "부칙공포번호":
                current[1] = _clean(el.text)
            elif el.tag == "부칙내용":
                current[2] = el.text or ""
        if any(current):
            rows.append(tuple(current))
    out: list[Addendum] = []
    seen: dict[str, int] = {}
    for date, number, body in rows:
        base = f"부칙:{number or _date(date) or 'unknown'}"
        seen[base] = seen.get(base, 0) + 1
        key = base if seen[base] == 1 else f"{base}#{seen[base]}"
        lines = [_clean(x) for x in body.splitlines() if _clean(x)]
        out.append(Addendum(key, _date(date), number, "\n".join(lines)))
    return out


def _annexes(root: ET.Element) -> list[Article]:
    block = root.find("별표")
    if block is None:
        return []
    out: list[Article] = []
    for unit in block.findall("별표단위"):
        kind = _clean(unit.findtext("별표구분")) or "별표"
        number = _clean(unit.findtext("별표번호")).lstrip("0") or "0"
        branch = _clean(unit.findtext("별표가지번호")).lstrip("0")
        title = _clean(unit.findtext("별표제목"))
        # 번호 없는 [별표]는 번호 0000으로 온다 (실측: 금융회사의 지배구조에 관한 법률)
        key = kind + ("" if number == "0" and not branch else
                      f"{number}의{branch}" if branch else number)
        lines = [_clean(x) for x in (unit.findtext("별표내용") or "").splitlines() if _clean(x)]
        text = "\n".join([title, *lines]) if title else "\n".join(lines)
        link = _clean(unit.findtext("별표서식파일링크"))
        out.append(Article(key, KIND_ANNEX, title, text, 0, source_link=link))
    return out


def parse_lawgo_xml(raw: bytes, *, source_sha256: str | None = None) -> DocumentSnapshot:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ParseError(f"XML 형식 오류: {exc}") from exc
    digest = source_sha256 or hashlib.sha256(raw).hexdigest()
    if root.tag == "법령":
        info = _info(root, "기본정보")
        official = info.get("법령ID", "")
        articles = _law_articles(root)
        snapshot = DocumentSnapshot(
            doc_cd=f"LAW:{official}", source_kind="LAW", official_id=official,
            name=info.get("법령명_한글", ""), promulgated=_date(info.get("공포일자")),
            promulgation_no=info.get("공포번호", ""), effective=_date(info.get("시행일자")),
            revision_kind=info.get("제개정구분", ""), source_sha256=digest, articles=articles,
            meta={k: info.get(k, "") for k in ("법종구분", "소관부처", "법령명약칭")})
    elif root.tag == "AdmRulService":
        info = _info(root, "행정규칙기본정보")
        official = info.get("행정규칙ID", "")
        lines: list[str] = []
        for el in root.iter("조문내용"):
            lines.extend((el.text or "").splitlines())
        snapshot = DocumentSnapshot(
            doc_cd=f"ADMRUL:{official}", source_kind="ADMRUL", official_id=official,
            name=info.get("행정규칙명", ""), promulgated=_date(info.get("발령일자")),
            promulgation_no=info.get("발령번호", ""),
            effective=_date(info.get("시행일자")) or _date(info.get("발령일자")),
            revision_kind=info.get("제개정구분명", ""), source_sha256=digest,
            articles=split_flat_articles(lines),
            meta={k: info.get(k, "") for k in ("행정규칙종류", "행정규칙일련번호", "현행여부", "소관부처명")})
    else:
        raise ParseError(f"지원하지 않는 XML 루트: {root.tag}")
    if not official:
        raise ParseError("문서 불변 ID(법령ID/행정규칙ID)가 없음")
    snapshot.addenda = _addenda(root)
    body = [a for a in snapshot.articles if a.kind == KIND_ARTICLE]
    if not body:
        raise ParseError("조문 0건")
    tail = [Article(a.key, KIND_ADDENDUM, a.key, a.text, 0) for a in snapshot.addenda]
    merged = snapshot.articles + _annexes(root) + tail
    keys = [a.key for a in merged]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ParseError(f"조문 키 중복: {duplicates[:10]}")
    snapshot.articles = [Article(**{**a.__dict__, "seq": i}) for i, a in enumerate(merged, 1)]
    return snapshot


_FLSEQ = re.compile(r"flSeq=(\d+)")


def _flseq(link: str) -> str:
    match = _FLSEQ.search(link or "")
    return f"flSeq:{match.group(1)}" if match else ""


def manifest_attachments(item: dict) -> dict[str, str]:
    """collect.py manifest 항목의 첨부 → {flSeq:<번호> 또는 별표 키: sha256}."""
    out: dict[str, str] = {}
    for entry in item.get("attachments") or ():
        sha = entry.get("sha256")
        if not sha:
            continue
        if (key := _flseq(entry.get("url", ""))):
            out[key] = sha
        title = re.match(r"^\[(\S+)\s*(\d+)(?:의(\d+))?\]", entry.get("title", ""))
        if title:
            out.setdefault(title.group(1) + title.group(2) + (f"의{title.group(3)}" if title.group(3) else ""), sha)
    return out


def attach_files(snapshot: DocumentSnapshot, files: dict[str, str]) -> DocumentSnapshot:
    """별표 키 또는 첨부 링크(flSeq) → 첨부 파일 sha. 법령 XML 별표내용은 머리 한 줄뿐이라
    별표 내용 변경은 첨부 sha 로만 잡힌다. flSeq는 판본마다 바뀌므로 링크가 먼저다."""
    articles = []
    for a in snapshot.articles:
        sha = (files.get(_flseq(a.source_link)) if a.source_link else None) or files.get(a.key)
        articles.append(Article(**{**a.__dict__, "attachment_sha256": sha}) if sha and a.kind == KIND_ANNEX else a)
    snapshot.articles = articles
    return snapshot


def snapshot_fingerprint(snapshot: DocumentSnapshot) -> str:
    """조문 내용 전체의 해시 — XML 바이트가 바뀌어도 조문이 같으면 같다."""
    return sha256_text("\n".join(f"{a.key}\x1f{a.text_hash}\x1f{a.attachment_sha256}"
                                  for a in snapshot.articles))
