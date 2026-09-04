"""T4. LLM 형식 유도기 — 문서 종류당 **한 번**만 (SPEC §2.3).

LLM 에게 주는 것
    1. 샘플 문서의 파싱 결과 (요소 리스트, docling 의 type 판단 포함)
    2. 용어집 — **출현 위치를 미리 문자열 매칭으로 표시해서** 전달한다.
       LLM 이 용어를 새로 찾게 하지 않고, 표시된 출현을 *해석*하게 한다.

LLM 의 임무
    · 반복 마커 → 정규표현식 생성. 여러 샘플에서 공통으로 성립하는 패턴만 채택.
    · 용어형 마커 → section 경계 지정. **정규표현식을 만들지 않는다**
      (비반복 문자열에 패턴을 억지로 씌우면 취약해진다 — §0 핵심원칙 2).
    · section 계층 조립.
    · 미등록 section 용어 후보 역제안 (근거: 위치·반복 여부·heading 신호).

LLM 이 없어도 컴파일할 수 있다 — `draft_without_llm()` 이 규칙만으로 초안을 만든다.
정확도는 낮지만 오프라인·비용 제약 환경의 대비책이고, 어차피 사람이 확정한다(§2.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from lawrag.core import term_marker
from lawrag.core.format_model import Format, RegexMarker, TermMarker
from lawrag.core.glossary import Glossary
from lawrag.core.parse_adapter import ParseResult

MAX_ELEMENTS_PER_SAMPLE = 220          # 프롬프트 폭주 방지 — 앞부분이 구조를 담는다

SYSTEM = """당신은 한국어 문서의 **구조 형식(format)** 을 유도하는 도구다.
출력은 런타임이 LLM 없이 결정론으로 실행할 형식 파일이 된다. 한 번만 만들고 계속 쓴다.

## 두 종류의 마커 — 인식 방법은 마커의 성질이 정한다

1. **반복 마커 → regex_markers**
   번호가 바뀌며 되풀이되는 것만. 예: `제1조/제2조/…`, `①②③`, `1. 2. 3.`, `[별지1]`.
   - 여러 샘플에서 **공통으로** 성립하는 패턴만 채택한다(한 샘플의 우연을 배제).
   - 파이썬 정규표현식. 줄 **처음**에 앵커(`^`)를 건다.
   - 번호·제목을 캡처 그룹으로 잡고 groups 에 이름을 준다(예: ["no","title"]).

2. **용어형 마커 → term_markers**
   반복하지 않는 제목 문자열. 예: "신탁계약 세부내역", "세부 운용지시".
   - **절대 정규표현식을 만들지 마라.** 용어 문자열 매칭으로 충분하며,
     비반복 문자열에 패턴을 씌우면 취약해진다.
   - 제공된 용어집의 section 용어 중, 입력에서 `section_candidate: true` 로 표시된 것만.

## level 과 계층
level 은 0 이 가장 바깥(대구역: 별지/본문), 숫자가 클수록 안쪽(조 → 항 → 호).
regex_markers 의 parent 는 자기 바로 위 마커의 id.
term_markers 의 under 는 그 용어가 유효한 상위 구역의 이름(모르면 생략).

## 미등록 후보
용어집에 없는데 구역 경계로 보이고, 정규표현식으로 보기 애매한 문자열을 후보로 낸다.
각 후보에 근거(위치·반복 여부·heading 신호)를 붙인다. 확실하지 않으면 넣지 마라.

추측하지 마라. 입력에서 실제로 관찰된 것만 낸다."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "regex_markers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "pattern": {"type": "string"},
                    "level": {"type": "integer"},
                    "groups": {"type": "array", "items": {"type": "string"}},
                    "parent": {"type": ["string", "null"]},
                    "label": {"type": ["string", "null"]},
                    "max_tail": {"type": ["integer", "null"],
                                 "description": "마커 뒤에 허용하는 글자 수. 같은 문자열이 본문 속 참조로도 나타나는 마커에만 (예: [별지N] → 20). 아니면 null."},
                    "require_heading": {"type": ["boolean", "null"],
                                        "description": "이 마커를 제목(heading) 요소에서만 인정. 같은 번호 패턴이 구역 제목이자 본문 열거 번호로도 쓰이는 문서에만 (예: 준칙의 `N.`). 아니면 null."},
                    "evidence": {"type": "string"},
                },
                "required": ["id", "pattern", "level", "groups", "parent", "label", "max_tail", "require_heading", "evidence"],
                "additionalProperties": False,
            },
        },
        "term_markers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "level": {"type": "integer"},
                    "under": {"type": ["string", "null"]},
                    "evidence": {"type": "string"},
                },
                "required": ["term", "level", "under", "evidence"],
                "additionalProperties": False,
            },
        },
        "hierarchy": {"type": "array", "items": {"type": "string"}},
        "default_section": {"type": "string"},
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "reason": {"type": "string"},
                    "repeated": {"type": "boolean"},
                    "heading_signal": {"type": "boolean"},
                    "suggest": {"type": "string", "enum": ["section", "fact", "ignore"]},
                },
                "required": ["text", "reason", "repeated", "heading_signal", "suggest"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["regex_markers", "term_markers", "hierarchy", "default_section",
                 "candidates", "notes"],
    "additionalProperties": False,
}


@dataclass
class Candidate:
    text: str
    reason: str
    repeated: bool = False
    heading_signal: bool = False
    suggest: str = "section"


@dataclass
class Induction:
    fmt: Optional[Format]
    candidates: list[Candidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = "llm"                        # llm | rules


# ---------------------------------------------------------------------------
# LLM 입력 만들기 — 용어 출현을 미리 표시해서 넘긴다 (§2.3-2)
# ---------------------------------------------------------------------------

def build_prompt(samples: list[tuple[str, ParseResult]], glossary: Glossary) -> str:
    lines: list[str] = [
        f"# 문서 종류: {glossary.doc_type}",
        "",
        "## 용어집 (section 용어만 term_markers 후보가 될 수 있다)",
    ]
    for name in glossary.section_terms():
        lines.append(f"  - [section] {name}")
    for name in glossary.fact_terms():
        t = glossary.terms[name]
        alias = f"  aliases={t.aliases}" if t.aliases else ""
        lines.append(f"  - [fact]    {name}  ({t.value_type}){alias}")

    for path, parsed in samples:
        marks = term_marker.mark(parsed.elements, glossary)
        by_elem: dict[int, list] = {}
        for m in marks:
            by_elem.setdefault(m.element_index, []).append(m)

        lines += ["", f"## 샘플: {Path(path).name}  (요소 {len(parsed.elements)}개)"]
        for e in parsed.elements[:MAX_ELEMENTS_PER_SAMPLE]:
            tag = "TABLE" if e.table else ("FIGURE" if e.is_picture else e.type)
            body = (e.table.text().splitlines()[0] if e.table
                    else (f"[캡션] {e.text}" if e.is_picture and e.text else e.text))[:110]
            marked = ""
            hits = by_elem.get(e.index, [])
            if hits:
                marked = "   ⟦용어: " + ", ".join(
                    f"{m.term}{'/section후보' if m.is_section_candidate else ''}"
                    for m in hits) + "⟧"
            lines.append(f"  [{e.index:3}] p{e.page} {tag:16} {body}{marked}")
        if len(parsed.elements) > MAX_ELEMENTS_PER_SAMPLE:
            lines.append(f"  … 외 {len(parsed.elements) - MAX_ELEMENTS_PER_SAMPLE}개 생략")
    return "\n".join(lines)


def induce(samples: list[tuple[str, ParseResult]], glossary: Glossary,
           llm, doc_type: Optional[str] = None) -> Induction:
    """LLM 으로 형식을 유도한다. 실패하면 규칙 기반 초안으로 떨어진다."""
    prompt = build_prompt(samples, glossary)
    data = llm.structured("format_induce", SYSTEM, prompt, SCHEMA, effort="high")
    if not data:
        out = draft_without_llm(samples, glossary, doc_type)
        out.warnings.append("LLM 유도에 실패해 규칙 기반 초안으로 대체했습니다")
        return out

    warnings: list[str] = []
    regex_markers = []
    for m in data.get("regex_markers", []):
        try:
            re.compile(m["pattern"])
        except re.error as exc:
            warnings.append(f"regex '{m.get('id')}' 패턴을 버렸습니다: {exc}")
            continue
        regex_markers.append(RegexMarker(
            id=m["id"], pattern=m["pattern"], level=int(m["level"]),
            groups=m.get("groups") or [], parent=m.get("parent") or None,
            label=m.get("label") or None, max_tail=m.get("max_tail"),
            require_heading=m.get("require_heading") or None))

    # 용어형 마커는 **용어집에 있는 section 용어만** 받는다 — LLM 이 지어낸 용어를 막는다
    section_terms = set(glossary.section_terms())
    term_markers = []
    for t in data.get("term_markers", []):
        if t["term"] not in section_terms:
            warnings.append(f"term_marker '{t['term']}' 은 용어집의 section 용어가 아니라 버렸습니다")
            continue
        term_markers.append(TermMarker(term=t["term"], level=int(t["level"]),
                                       under=t.get("under") or None))

    try:
        fmt = Format(
            doc_type=doc_type or glossary.doc_type,
            compiled_from=[Path(p).name for p, _ in samples],
            regex_markers=regex_markers, term_markers=term_markers,
            hierarchy=data.get("hierarchy") or [],
            default_section=data.get("default_section") or "본문",
            confidence="high" if len(samples) >= 3 else "low",
            notes=data.get("notes") or [])
    except ValueError as exc:
        out = draft_without_llm(samples, glossary, doc_type)
        out.warnings.append(f"LLM 형식이 무결성 검사를 통과하지 못했습니다: {exc}")
        return out

    candidates = [Candidate(text=c["text"], reason=c.get("reason", ""),
                            repeated=bool(c.get("repeated")),
                            heading_signal=bool(c.get("heading_signal")),
                            suggest=c.get("suggest", "section"))
                  for c in data.get("candidates", [])]
    return Induction(fmt=fmt, candidates=candidates,
                     notes=data.get("notes") or [], warnings=warnings, source="llm")


# ---------------------------------------------------------------------------
# LLM 없이 — 규칙만으로 초안 (대비책)
# ---------------------------------------------------------------------------

# 한국 계약서 계열에서 흔한 반복 마커. 초안일 뿐이며 사용자가 확정한다(§2.4).
KNOWN_PATTERNS = [
    # 별지 마커는 본문 속 참조로도 등장한다 — 꼬리 제약으로 가른다(§1.3)
    ("별지", r"^\[별지\s*(\d+)\]", 0, ["no"], None, "별지{no}", 20),
    ("조",   r"^제\s*(\d+)\s*조\s*[(（]\s*([^)）]{1,40})\s*[)）]", 1, ["no", "title"], None, "제{no}조", None),
    ("항",   r"^([①-⑳])", 2, ["no"], "조", "{no}", None),
    ("호",   r"^(\d{1,2})\.\s+", 3, ["no"], "항", "{no}", None),
]


def _collect_candidates(samples: list[tuple[str, ParseResult]], glossary: Glossary,
                        regex_markers: list[RegexMarker]) -> list[Candidate]:
    """미등록 section 용어 후보 (§2.3-4).

    **반복 마커가 이미 잡는 것은 후보가 아니다.** `제6조(대리인의 지정)` 은 조 마커가
    처리하므로 용어로 승격할 이유가 없다 — 후보는 "구역 경계로 보이는데 정규표현식으로
    보기 애매한 문자열"만이다. 이 필터가 없으면 후보 목록이 조 제목으로 뒤덮인다.
    """
    candidates: list[Candidate] = []
    for path, parsed in samples:
        for e in term_marker.unmatched_headings(parsed.elements, glossary):
            if any(m.match(e.text) for m in regex_markers):
                continue                              # 이미 반복 마커의 몫
            if any(c.text == e.text for c in candidates):
                continue
            candidates.append(Candidate(
                text=e.text, reason=f"{Path(path).name} p{e.page} 의 제목형 요소인데 용어집에 없음",
                repeated=False, heading_signal=True, suggest="section"))
    return candidates


def draft_without_llm(samples: list[tuple[str, ParseResult]], glossary: Glossary,
                      doc_type: Optional[str] = None) -> Induction:
    """알려진 반복 패턴을 실제로 적중시켜 본 뒤 살아남은 것만 채택한다."""
    warnings: list[str] = []
    # 마커별로 **어느 샘플에서** 적중했는지를 본다. 누적 개수로 세면 한 샘플에서
    # 여러 번 맞은 것이 "샘플마다 최소 1회" 를 통과해 버린다 — "여러 샘플에서
    # 공통으로 성립하는 패턴만 채택"(모듈 원칙)이 깨진다.
    hit_samples: dict[str, set[int]] = {}
    for si, (_path, parsed) in enumerate(samples):
        for e in parsed.elements:
            if not e.opens_structure:
                continue
            for mid, pattern, *_rest in KNOWN_PATTERNS:
                if re.match(pattern, e.text.strip()):
                    hit_samples.setdefault(mid, set()).add(si)

    adopted = {mid for mid, *_ in KNOWN_PATTERNS
               if len(hit_samples.get(mid, ())) == max(1, len(samples))}
    # parent 가 채택되지 않은 마커는 함께 버린다 — `항(parent=조)` 만 남으면
    # Format 무결성 검사가 ValueError 로 초안 경로를 통째로 세운다. 조 없이 항
    # 패턴만 맞았다는 것은 우연이므로, 계층을 지어내지 않고 버리는 쪽이 초안답다.
    deps = {mid: parent for mid, _p, _lv, _g, parent, *_ in KNOWN_PATTERNS}
    changed = True
    while changed:
        changed = False
        for mid in sorted(adopted):
            need = deps.get(mid)
            if need and need not in adopted:
                adopted.discard(mid)
                warnings.append(f"'{mid}' 마커는 상위 '{need}' 가 없어 버렸습니다")
                changed = True

    regex_markers = [
        RegexMarker(id=mid, pattern=pattern, level=level, groups=groups,
                    parent=parent, label=label, max_tail=max_tail)
        for mid, pattern, level, groups, parent, label, max_tail in KNOWN_PATTERNS
        if mid in adopted
    ]

    # section 용어가 제목 위치에 나타난 곳만 term_marker 로
    term_markers: list[TermMarker] = []
    for _path, parsed in samples:
        marks = term_marker.mark(parsed.elements, glossary)
        for m in marks:
            if not m.is_section_candidate:
                continue
            if any(t.term == m.term for t in term_markers):
                continue
            term_markers.append(TermMarker(term=m.term, level=1))

    candidates = _collect_candidates(samples, glossary, regex_markers)

    if not regex_markers and not term_markers:
        warnings.append("규칙만으로는 마커를 하나도 찾지 못했습니다 — LLM 유도가 필요합니다")
        return Induction(fmt=None, candidates=candidates, warnings=warnings, source="rules")

    fmt = Format(
        doc_type=doc_type or glossary.doc_type,
        compiled_from=[Path(p).name for p, _ in samples],
        regex_markers=regex_markers, term_markers=term_markers,
        hierarchy=["문서", "대구역", "조|용어section", "항", "호"],
        confidence="low",
        notes=["LLM 없이 규칙으로 만든 초안입니다 — 적용 결과를 반드시 확인하세요"])
    return Induction(fmt=fmt, candidates=candidates, warnings=warnings, source="rules")
