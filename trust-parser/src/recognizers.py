"""§7. 구조 인식 어댑터 — 원문을 먹어 fact 를 만든다.

## 인식 ≠ 제약

여기 있는 패턴은 **추출 구현**이지 도메인 규칙이 아니다.
"무엇이 참이어야 하는가"는 전부 온톨로지(§C)에 있고, 이 모듈은
그 선언을 **이 PDF 포맷에서 어떻게 알아보는가**만 담당한다.

    판별 기준(§7): 이미 추출된 fact 에 대고 검사할 수 있으면 제약(→ 온톨로지),
                   원문을 먹어 fact 를 만들면 인식(→ 여기).

## 어떤 recognizer 를 쓸지는 온톨로지가 고른다

    structure.조.recognizer: korean_article   ← 선언
    REGISTRY["korean_article"]                ← 구현

그래서 새 문서 종류가 다른 표기를 쓰면(예: 조가 아니라 `제N관`),
같은 스타일이 이미 등록돼 있으면 온톨로지 한 줄만 바꾸면 된다.
없으면 여기에 어댑터를 하나 추가한다 — 제약이 아니라 인식이므로 코드가 맞는 자리다.

## 정규식은 구현 수단일 뿐이다

이 문서군에서 정규식이 견고한 이유는 실측으로 확인됐다.
dataset 9종(3,460줄) 전수조사: 조 헤더 `^제N조(제목)` 352건 매칭에 **오탐 1건(0.3%)**,
항 번호 424건, 호 번호 262건(9/9 문서), 별지 마커 33건.
반면 값 파싱(금액·기간·기준일)에 정규식을 쓰면 오탐 80%·커버리지 44%로 무너진다.
그래서 **구조 인식만 정규식으로 하고, 값 해석은 comparators/fact 레이어로 넘긴다.**
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Optional

# 원문자 ①~⑳ (U+2460~U+2473)
CIRCLED = "".join(chr(c) for c in range(0x2460, 0x2474))


@dataclass
class Marker:
    """인식된 구조 마커 하나."""
    kind: str                      # 조 | 항 | 호 | 별지
    no: str                        # "15" | "①" | "1" | "1"
    title: str = ""                # 조 제목
    inline_text: str = ""          # 마커 뒤에 이어지는 본문
    span: tuple[int, int] = (0, 0)  # 원문 내 위치


# ===========================================================================
# 어댑터 구현
# ===========================================================================

_RE_ARTICLE = re.compile(r"^제\s*(\d+)\s*조\s*[(（]\s*([^)）]{1,40})\s*[)）]")
_RE_ARTICLE_NO_TITLE = re.compile(r"^제\s*(\d+)\s*조(?![의])\s")
# 줄 첫머리의 조항 **인용** — 제목이 아니다. 실측 오탐 1건이 전부 이 형태였다.
_RE_ARTICLE_CITATION = re.compile(
    r"^제\s*\d+\s*조(?:\s*제?\s*\d+\s*항)?\s*"
    r"(?:에서|에\s*따라|에\s*의하|에\s*정한|의\s*규정|및|또는|,|과|와|·)")


def korean_article(line: str) -> Optional[Marker]:
    """`제15조(중도해지)` — 조 마커. 온톨로지: 조 = 번호 + 제목."""
    s = line.strip()
    if not s or _RE_ARTICLE_CITATION.match(s):
        return None
    m = _RE_ARTICLE.match(s)
    if m:
        return Marker("조", m.group(1), m.group(2).strip(), s[m.end():].strip(), (0, m.end()))
    m = _RE_ARTICLE_NO_TITLE.match(s)
    if m:
        return Marker("조", m.group(1), "", s[m.end():].strip(), (0, m.end()))
    return None


def circled_clause(line: str) -> Optional[Marker]:
    """`① …` — 항 마커. 온톨로지: 조 contains 항."""
    s = line.strip()
    if s and s[0] in CIRCLED:
        return Marker("항", s[0], "", s[1:].strip(), (0, 1))
    return None


_RE_ITEM = re.compile(r"^(\d{1,2})\.\s+")


def numbered_item(line: str) -> Optional[Marker]:
    """`1. …` — 호 마커. 온톨로지: 항 contains 호."""
    s = line.strip()
    m = _RE_ITEM.match(s)
    if m:
        return Marker("호", m.group(1), "", s[m.end():].strip(), (0, m.end()))
    return None


_RE_APPENDIX = re.compile(r"[\[<（(]?\s*별지\s*(\d+)\s*[\]>）)]?")


def appendix_marker(line: str) -> Optional[Marker]:
    """`[별지1]` — 별지 파트 진입 마커."""
    m = _RE_APPENDIX.search(line or "")
    if m:
        return Marker("별지", m.group(1), "", "", m.span())
    return None


REGISTRY: dict[str, Callable[[str], Optional[Marker]]] = {
    "korean_article": korean_article,
    "circled_clause": circled_clause,
    "numbered_item": numbered_item,
    "appendix_marker": appendix_marker,
}


def get(name: Optional[str]) -> Optional[Callable[[str], Optional[Marker]]]:
    return REGISTRY.get(name) if name else None


# ===========================================================================
# ref 멘션 인식 (§7) — 제약("존재하는 대상으로 해소")은 온톨로지에 있고 여기선 멘션만 찾는다
# ===========================================================================

_RE_REF_ARTICLE_CLAUSE = re.compile(r"제\s*(\d+)\s*조\s*제\s*(\d+)\s*항")
_RE_REF_ARTICLE = re.compile(r"제\s*(\d+)\s*조")
_RE_REF_CLAUSE = re.compile(r"제\s*(\d+)\s*항")
_RE_REF_APPENDIX = re.compile(r"[\[<（(]?\s*별지\s*(\d+)\s*[\]>）)]?")
_RE_REF_EACH_ITEM = re.compile(r"각\s*호")


def find_refs(text: str) -> list[str]:
    """본문에서 참조 멘션을 찾아 정규화한다. 등장 순서를 유지하고 중복은 제거."""
    if not text:
        return []
    out: list[str] = []

    def add(v: str) -> None:
        if v not in out:
            out.append(v)

    # 조+항 결합형을 먼저 소비해 "제2조 제3항" 이 조/항으로 쪼개지지 않게 한다
    consumed = text
    for m in _RE_REF_ARTICLE_CLAUSE.finditer(text):
        add(f"제{m.group(1)}조")
        consumed = consumed.replace(m.group(0), " ")
    for m in _RE_REF_ARTICLE.finditer(consumed):
        add(f"제{m.group(1)}조")
    for m in _RE_REF_APPENDIX.finditer(text):
        add(f"별지{m.group(1)}")
    if _RE_REF_EACH_ITEM.search(text):
        add("각호")
    return out


def has_bare_clause_ref(text: str) -> bool:
    """`제1항` 처럼 조 없이 항만 가리키는 참조가 있는가 — 같은 조를 뜻한다."""
    if not text:
        return False
    stripped = _RE_REF_ARTICLE_CLAUSE.sub(" ", text)
    return bool(_RE_REF_CLAUSE.search(stripped))


_RE_CONTRACT_ARTICLE_CELL = re.compile(r"계약서\s*제\s*(\d+)\s*조")


def contract_article_cell(cell: str) -> Optional[str]:
    """별지 표 우측의 `계약서제N조` 셀 → `제N조`. 제약("필드 ↔ 조 대응")은 온톨로지에 있다."""
    m = _RE_CONTRACT_ARTICLE_CELL.search(cell or "")
    return f"제{m.group(1)}조" if m else None


# ===========================================================================
# 체크박스 인식 (§7 엣지 케이스)
# ===========================================================================

_RE_OPTION = re.compile(r"(\d{1,2})\.\s*([^\[\]\n]{1,60}?)(?=\s*(?:\[|\d{1,2}\.|$))")
CHECK_MARKS = "√✓✔☑▣■X"
EMPTY_BOX = "[ ]"


def checkbox_options(text: str) -> list[dict]:
    """`[ ] 1. 채무증권  [ ] 2. 지분증권 …` → [{no, label, checked}].

    빈 템플릿이면 전부 checked:false (§7).
    체결본의 √ 마크 검출은 텍스트만으로는 불안정하다 — 실측에서 도클링이
    √ 를 라벨과 분리해 표 끝에 몰아넣었다. 좌표 기반 판정은 v2(§10).
    """
    if not text:
        return []
    out: list[dict] = []
    for m in _RE_OPTION.finditer(text):
        label = m.group(2).strip(" .·")
        if not label or label in ("[", "]"):
            continue
        out.append({"no": int(m.group(1)), "label": label, "checked": False})
    # 번호 중복 제거 (표가 여러 열로 쪼개져 같은 항목이 반복될 수 있다)
    seen, uniq = set(), []
    for o in out:
        if o["no"] not in seen:
            seen.add(o["no"])
            uniq.append(o)
    return sorted(uniq, key=lambda o: o["no"])


def mark_checked(options: list[dict], checked_labels: set[str]) -> list[dict]:
    """좌표·부가 정보로 확인된 체크 항목을 반영한다."""
    for o in options:
        if o["label"] in checked_labels:
            o["checked"] = True
    return options


# ===========================================================================
# 보조
# ===========================================================================

def normalize_ws(s: str) -> str:
    return " ".join((s or "").split())


def count_tokens(text: str) -> int:
    """토큰 근사 — 한글은 문자 단위에 가깝고 영문/숫자는 어절 단위에 가깝다.

    HybridChunker 의 토크나이저를 쓰지 못하는 환경에서도 §9-6 을 잴 수 있게 하는 근사치다.
    """
    if not text:
        return 0
    n = 0
    for ch in text:
        if unicodedata.category(ch)[0] in ("L", "N"):
            n += 1 if "가" <= ch <= "힣" else 0.4
    return int(n) + 1
