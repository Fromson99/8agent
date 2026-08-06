"""형식(format) 파일 스키마 — 컴파일 국면의 산출물 (SPEC §2.4).

형식은 **stochastic 을 가둬 둔 상자**다. LLM 은 이 파일을 만들 때 한 번만 관여하고,
런타임은 이 파일만 읽어 결정론으로 돈다(§0 핵심원칙 1).

두 종류의 마커가 있고, 인식 방법은 **마커의 성질이 정한다**(§0 핵심원칙 2).
    regex_markers — 번호가 바뀌며 반복되는 마커 (제N조, ①, N., [별지N])
    term_markers  — 반복하지 않는 제목 문자열 ("신탁계약 세부내역")
비반복 문자열에 정규표현식을 억지로 씌우지 않는다. 취약해질 뿐이다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class RegexMarker(BaseModel):
    """반복 마커 — 번호가 바뀌며 되풀이되므로 패턴으로 잡는다."""
    id: str
    pattern: str
    level: int
    groups: list[str] = Field(default_factory=list)   # 캡처 그룹의 의미 이름
    parent: Optional[str] = None
    label: Optional[str] = None            # 표시용 형식 (예: "제{no}조({title})")
    # 마커 뒤에 남는 글자 수 상한. 같은 문자열이 **경계**로도 **본문 속 참조**로도
    # 나타나는 마커에 건다 — `[별지1]` 은 제목 줄이지만
    # `[별지1]신탁계약 세부내역의 위탁자와 …` 는 문장이다(§1.3 의 mention 구별을
    # 반복 마커에 적용한 것). 길이만으로 가르는 게 아니라 "이 줄이 마커뿐인가"를 본다.
    max_tail: Optional[int] = None
    # 이 마커를 **제목(heading) 요소에서만** 인정한다. 같은 번호 패턴이 구역 제목이자
    # 본문 열거 번호이기도 한 문서에 건다 — 표준투자권유준칙의 `N.` 은 목차 항목
    # ("11. 고령투자자에 대한 …")이면서 확인서 문항·법령 인용 목록의 번호이기도 하고,
    # 패턴만으로는 둘이 갈리지 않는다(실측: 적중 103건 중 47건만 제목).
    # 용어형 마커가 이미 레이아웃 신호로 mention 을 가르는 것(§1.3)을 반복 마커로 넓힌 것이며,
    # heading 은 어디까지나 힌트이므로(§2.2) **켠 마커에만** 적용된다.
    require_heading: Optional[bool] = None

    def compiled(self) -> re.Pattern:
        return re.compile(self.pattern)

    def match(self, line: str) -> Optional[dict[str, str]]:
        """적중하면 {그룹이름: 값} + `_matched`, 아니면 None."""
        s = line.strip()
        m = self.compiled().match(s)
        if not m:
            return None
        if self.max_tail is not None and len(s[m.end():].strip()) > self.max_tail:
            return None                    # 경계가 아니라 문장 속 참조다
        out: dict[str, str] = {}
        for i, name in enumerate(self.groups, start=1):
            if i <= (m.re.groups or 0):
                out[name] = (m.group(i) or "").strip()
        out["_matched"] = m.group(0)
        out["_end"] = str(m.end())
        return out

    def key_of(self, captured: dict[str, str]) -> str:
        """section_id 에 쓸 짧은 라벨. 예: 조 + no=2 → '제2조'."""
        if self.label:
            try:
                return self.label.format(**captured)
            except (KeyError, IndexError):
                pass
        no = captured.get("no")
        return f"{self.id}{no}" if no else (captured.get("_matched") or self.id)


class TermMarker(BaseModel):
    """용어형 마커 — 용어집의 section 용어가 제목 위치에 나타난 곳."""
    term: str
    level: int
    under: Optional[str] = None            # 어느 상위 구역 아래에서만 유효한가


class Format(BaseModel):
    doc_type: str
    format_version: int = 1
    compiled_from: list[str] = Field(default_factory=list)
    regex_markers: list[RegexMarker] = Field(default_factory=list)
    term_markers: list[TermMarker] = Field(default_factory=list)
    hierarchy: list[str] = Field(default_factory=list)
    default_section: str = "본문"          # 어떤 마커도 지나기 전 구역의 이름
    confidence: Literal["high", "medium", "low"] = "high"
    notes: list[str] = Field(default_factory=list)

    # --- 무결성 ------------------------------------------------------------
    @model_validator(mode="after")
    def _check(self) -> "Format":
        problems: list[str] = []
        ids = [m.id for m in self.regex_markers]
        for m in self.regex_markers:
            try:
                re.compile(m.pattern)
            except re.error as exc:
                problems.append(f"regex_markers.{m.id} 패턴이 잘못됐습니다: {exc}")
            if m.parent and m.parent not in ids:
                problems.append(f"regex_markers.{m.id}.parent '{m.parent}' 가 정의되지 않았습니다")
        if len(ids) != len(set(ids)):
            problems.append("regex_markers.id 가 중복됩니다")
        terms = [t.term for t in self.term_markers]
        if len(terms) != len(set(terms)):
            problems.append("term_markers.term 이 중복됩니다")
        if not self.regex_markers and not self.term_markers:
            problems.append("마커가 하나도 없습니다 — 형식이 아무것도 자르지 못합니다")
        if problems:
            raise ValueError("형식 파일 오류:\n  - " + "\n  - ".join(problems))
        return self

    # --- 조회 --------------------------------------------------------------
    def marker(self, marker_id: str) -> Optional[RegexMarker]:
        return next((m for m in self.regex_markers if m.id == marker_id), None)

    def by_level(self) -> list[RegexMarker]:
        """레벨 오름차순 — 얕은 마커를 먼저 걸어 본다."""
        return sorted(self.regex_markers, key=lambda m: m.level)

    def term_marker(self, term: str) -> Optional[TermMarker]:
        return next((t for t in self.term_markers if t.term == term), None)

    def section_terms(self) -> set[str]:
        return {t.term for t in self.term_markers}

    def max_level(self) -> int:
        levels = [m.level for m in self.regex_markers] + [t.level for t in self.term_markers]
        return max(levels) if levels else 0

    def validate_against_glossary(self, glossary) -> list[str]:
        """term_markers 가 용어집의 section 용어를 가리키는지 — 컴파일 확정 전 검사."""
        problems = []
        for t in self.term_markers:
            term = glossary.terms.get(t.term)
            if term is None:
                problems.append(f"term_markers 의 '{t.term}' 이 용어집에 없습니다")
            elif not term.is_section:
                problems.append(f"'{t.term}' 은 용어집에서 section 용어가 아닙니다 (kind={term.kind})")
        return problems

    def dump(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


def load(path: str | Path) -> Format:
    return Format.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def save(fmt: Format, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fmt.dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
