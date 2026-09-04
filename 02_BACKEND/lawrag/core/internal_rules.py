"""내규(회사 규정·지침·세칙) 인제스트 — 유도(DP) 경로 위의 **문서군 프로파일** 한 장.

외규는 law.go.kr 태그(lawxml)나 조문 HTML(rulehtml)이 계층을 찍어 주지만, 내규는
docx 본문에 `제1조`·`①`·`1.`·`가.` 만 있는 문서다. 그래서 내규는 **유도 경로**
(`core/structure/pipeline.py` S0~S6)로 간다 — Word 제목 스타일을 통짜로 믿는
`docxstyle` 은 쓰지 않는다. 실측(2026-08, 예시 세칙 v2): docxstyle 은 장·조까지만
28마디, 유도는 장·조·항·호 73마디이고, 스타일을 전부 지운 판·굵게만 친 판·
`제 1 조 (목적)`+`(1)` 표기 판이 전부 같은 73마디로 나왔다. 유도 경로는 스타일에
기대지 않는다.

## 이 파일이 담는 것 — 코드가 아니라 문서군에 대한 입력

    PROFILE      유도 경로에 넣는 힌트(§7). 어휘·레벨 규칙이 아니라 "내규라는
                 문서군은 이렇게 생겼다"는 사람의 지식이다.
    header_meta  머리(문서명·제정·개정 일자)를 meta 로. 법령은 manifest 가
                 enforce·revised 를 주지만 docx 는 그런 게 없어서 본문 머리에서 뽑는다.
    ingest_internal_rule   업로드 API·CLI 가 같이 쓰는 문 하나 (ingest_lawxml_bytes 와
                 같은 자리).

## PROFILE 이 왜 partial_order 뿐인가

`ladder_hint`(층 통째 지정)는 문서마다 다른 계열(항을 `①` 로 쓰는 세칙과 `(1)` 로
쓰는 지침, 절이 있는 기준과 없는 지침)을 한 사다리로 못 덮는다 — 힌트에 없는 계열이
발화하면 층을 못 받는다. `partial_order` 는 확실한 쌍만 못박고 나머지는 문서가
유도한다. 여기 적은 쌍은 한국 규정 문서의 관례라 어느 내규에서든 참이다:

    장 > 절 > 조

**부칙·별표는 일부러 안 적는다.** `부칙 > 조` 를 못박으면 조가 L1 이 되는데, 장이
없는 내규(조만 있는 지침·세칙이 흔하다)는 첫 조를 열 L0 가 없어 DP 가 조 계열의
층을 풀고, 그 뒤 제2조가 제1조 안으로 들어가는 트리가 나왔다(실측 2026-08 변형 B·C).
부칙은 본문 계층과 축이 다른 문제(SPEC §10 미해결)라 사다리로 못박을 것이 아니다 —
사다리 밖(하나짜리·문맥판정)에 두면 DP 가 부칙을 최상위에, 그 아래 조·항을 맞게
앉힌다(변형 A·B·C 전부). 하나짜리 계열은 감점도 받지 않는다(ladder.singletons).

## 머리 meta

    kind      "internal" — 외규(law·admrul)와 가르는 축. RAG 스코프가 이걸 본다.
    enacted   제정 일자 YYYYMMDD
    revised   마지막 개정 일자 (없으면 제정)
    enforce   시행 일자 (`시행 …` 표기가 없으면 revised)
    history   머리에 적힌 그대로 — ["제정 2024. 1. 2.", "개정 2026. 7. 1."] (grounding)
    status    "현행" | "구판" — 신구 대비의 두 판을 한 스토어에 두려면 이 표식이 있어야
              기본 스코프가 현행만 본다
    series    문서군 키(판이 달라도 같은 값) — 신구 대비가 짝을 찾는 열쇠

머리는 **첫 구조 마커 앞**의 문단이다. `제정 2024. 1. 2.` · `(제정 2025. 3. 1.)` ·
`개정 2026년 7월 1일` · `시행 2026. 7. 1.` 을 받는다. 본문 속 `<개정 2026. 7. 1.>`
꼬리표는 머리가 아니므로 세지 않는다 — 그건 조문 단위 개정 표식이고 신구 대비의
재료다.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

# 문서군 프로파일 — 유도 경로 힌트. 확실한 쌍만.
PROFILE: dict = {
    "partial_order": [
        ("kr_장", "kr_절"), ("kr_장", "kr_article"), ("kr_절", "kr_article"),
    ],
}

FOLDER = "내규"
KIND = "internal"

# 머리 판독 ---------------------------------------------------------------

_MARKER = re.compile(r"^\s*(제\s*\d+\s*(장|절|조)|부\s*칙|[\[〔]\s*(별표|별지|서식)|[①-⑳])")
_DATE = (r"(\d{4})\s*[.년]\s*(\d{1,2})\s*[.월]\s*(\d{1,2})\s*[.일]?")
_EVENT = re.compile(
    r"(제정|전부개정|일부개정|개정|시행)\s*[:：]?\s*" + _DATE)
_MAX_HEAD = 15          # 머리로 볼 문단 수 상한 — 그 안에 첫 마커가 없으면 머리가 없는 문서다
_NOTICE = re.compile(r"^\s*[※*]")   # "※ 본 문서는 …" 류 안내문은 제목이 아니다


def _yyyymmdd(m: re.Match, base: int = 2) -> str:
    y, mo, d = m.group(base), m.group(base + 1), m.group(base + 2)
    return f"{int(y):04d}{int(mo):02d}{int(d):02d}"


def docx_paragraphs(raw: bytes) -> list[str]:
    """docx 의 문단 텍스트(빈 줄 제외). 머리 판독에만 쓴다 — 구조화는 유도 경로가
    docling 으로 따로 읽는다."""
    from docx import Document
    doc = Document(io.BytesIO(raw))
    return [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]


def header_meta(paragraphs: list[str]) -> dict:
    """머리 문단 → meta 조각. 첫 구조 마커 앞까지만 본다."""
    head: list[str] = []
    for p in paragraphs[:_MAX_HEAD]:
        if _MARKER.match(p):
            break
        head.append(p)
    meta: dict = {"kind": KIND}
    history: list[str] = []
    enacted = revised = enforce = ""
    title = ""
    for p in head:
        events = list(_EVENT.finditer(p))
        for m in events:
            history.append(" ".join(m.group(0).split()))
            when = _yyyymmdd(m)
            if m.group(1) == "제정":
                enacted = enacted or when
            elif m.group(1) == "시행":
                enforce = when
            else:
                revised = max(revised, when)
        if not title and not events and not _NOTICE.match(p) and len(p) <= 60:
            title = p.strip("[]〔〕 ")
    if title:
        meta["title"] = title
    if history:
        meta["history"] = history
    if enacted:
        meta["enacted"] = enacted
    revised = revised or enacted
    if revised:
        meta["revised"] = revised
    if enforce or revised:
        meta["enforce"] = enforce or revised
    return meta


def split_series(name: str) -> tuple[str, str]:
    """`위험관리기준시행세칙_v2_2026` → (series, version). 꼬리가 없으면 version 은 ''."""
    m = re.search(r"[_\s-]+v(\d+)(?:[_\s-]+(\d{4}))?\s*$", name, re.I)
    if not m:
        return name.strip(), ""
    return name[:m.start()].strip(), f"v{m.group(1)}"


# 인제스트 문 ---------------------------------------------------------------

def ingest_internal_rule(raw: bytes, filename: str, *, store: Path,
                         name: str = "", folder: str = FOLDER,
                         status: str = "현행", series: str = "",
                         version: str = "", extra_meta: Optional[dict] = None) -> dict:
    """내규 한 건을 유도 경로로 구조 스토어에 넣는다. 반환은 core.ingest.ingest 와 같다."""
    from lawrag.core.ingest import ingest

    name = name or Path(filename).stem
    auto_series, auto_version = split_series(name)
    meta = {"status": status,
            "series": series or auto_series,
            "version": version or auto_version}
    if filename.lower().endswith(".docx"):
        try:
            meta.update(header_meta(docx_paragraphs(raw)))
        except Exception:
            meta["kind"] = KIND       # 머리를 못 읽어도 축은 찍는다
    else:
        meta["kind"] = KIND
    meta.update(extra_meta or {})
    return ingest(raw, filename, store=store, name=name, folder=folder,
                  engine="", hints=dict(PROFILE), extra_meta=meta)
