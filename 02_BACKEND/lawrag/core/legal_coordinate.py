"""문서 구조 라벨과 자유문 질문이 공유하는 법률 좌표 문법.

이 모듈은 코퍼스나 RAG에 의존하지 않는다. 문서 인제스트가 만든 라벨과 질문·본문의
참조 표면형을 같은 :class:`LegalCoordinate`로 정규화하는 일만 맡는다. 실제 문서에서
좌표가 존재하고 유일한지는 호출부가 구조 트리로 검증한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional


UNITS = "편장절관"
MOK_LETTERS = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허고노도로모보소오조초코토포호구누두루무부"

# 질문·본문은 문장 중간을 훑고, 문서 라벨은 같은 문법을 문자열 시작에서 읽는다.
ARTICLE_PATTERN = re.compile(
    r"제\s*(\d{1,4})(?:\s*-\s*(\d{1,4}))?\s*조(?:의\s*(\d{1,3}))?"
)
DIVISION_PATTERN = re.compile(rf"제\s*(\d{{1,3}})\s*([{UNITS}])")
ANNEX_PATTERN = re.compile(r"(별표|별지)\s*(?:제\s*)?(\d{1,3})(?:\s*호)?")

TAIL_PATTERNS = (
    ("항", re.compile(r"\s*제\s*(\d{1,3})\s*항")),
    ("호", re.compile(r"\s*제\s*(\d{1,3})\s*호")),
    ("목", re.compile(rf"\s*([{MOK_LETTERS}]|\d{{1,2}})\s*목(?!적)")),
    ("항", re.compile(r"\s?([①-⑳㉑-㉟㊱-㊿])")),
    ("항", re.compile(r"\s?<\s*(\d{1,3})\s*>")),
    (None, re.compile(r"\s?\(\s*(\d{1,2})\s*\)")),
)
CONTINUATION_PATTERN = re.compile(
    r"\s*(?:(?:단서|본문|전단|후단)\s*)?(?:[ㆍ·,、]|및|또는|부터|와|과)\s*"
)

LABEL_ARTICLE_PATTERN = re.compile("^" + ARTICLE_PATTERN.pattern)
LABEL_DIVISION_PATTERN = re.compile("^" + DIVISION_PATTERN.pattern)
LABEL_ANNEX_PATTERN = re.compile(r"^(별표|별지)\s*(?:제\s*)?(\d{1,3})")
LABEL_CLAUSE_PATTERN = re.compile(r"^제\s*(\d{1,3})\s*항")
LABEL_ANGLE_CLAUSE_PATTERN = re.compile(r"^<\s*(\d{1,3})\s*>")
LABEL_HO_PATTERN = re.compile(r"^제\s*(\d{1,3})\s*호")
LABEL_ENUM_PATTERN = re.compile(r"^\(?(\d{1,3})[.)](?!\d)")
LABEL_MOK_PATTERN = re.compile(rf"^([{MOK_LETTERS}])\s*[.)]")
CIRCLED_ORDINALS = {
    **{chr(0x2460 + i): i + 1 for i in range(20)},
    **{chr(0x3251 + i): i + 21 for i in range(15)},
    **{chr(0x32B1 + i): i + 36 for i in range(15)},
}


def ordinal(token: str) -> int:
    """공식 숫자·원문자·한글 목 표면형을 동일한 서수로 접는다."""
    if token in CIRCLED_ORDINALS:
        return CIRCLED_ORDINALS[token]
    if token in MOK_LETTERS:
        return MOK_LETTERS.index(token) + 1
    return int(token)


@dataclass(frozen=True)
class LegalCoordinate:
    """문서 종류와 무관한 법률 구조 좌표.

    ``dash``는 행정규정의 ``제2-4조``를, ``sub``는 가지조문 ``제2조의4``를
    나타낸다. 공개 ``key``는 기존 refs tuple 계약과 동일하다.
    """

    unit: str
    n: int
    sub: Optional[int] = None
    dash: Optional[int] = None
    chain: tuple[tuple[Optional[str], int], ...] = ()
    # 가지 호처럼 하강 단위 자체에 ``의N``이 붙는 원천 구조를 보존한다. 기존
    # refs 계약의 pair chain은 그대로 두고, 필요한 자리만 병렬 sub를 가진다.
    chain_subs: tuple[Optional[int], ...] = ()

    def key(self) -> tuple:
        branch = (("dash", self.dash, self.sub)
                  if self.unit == "조" and self.dash is not None else self.sub)
        return (self.unit, self.n, branch)

    def replace_chain(self, chain: tuple[tuple[Optional[str], int], ...]
                      ) -> "LegalCoordinate":
        return replace(self, chain=chain, chain_subs=())

    def append_part(self, part: "LegalCoordinate") -> "LegalCoordinate":
        """조문 좌표 뒤에 실제 자식 항·호·목 좌표를 붙인다."""
        if self.unit != "조" or part.unit not in {"항", "호", "목", "세목", "세세목", "세세세목"}:
            raise ValueError(f"조문 하강 좌표가 아닙니다: {self!r} + {part!r}")
        subs = list(self.chain_subs or (None,) * len(self.chain))
        subs.append(part.sub)
        return replace(
            self,
            chain=self.chain + ((part.unit, part.n),),
            chain_subs=tuple(subs) if any(value is not None for value in subs) else (),
        )

    def canonical_surface(self) -> str:
        """원천의 공백·원문자 표기를 제거한 저장·대조용 공식 표면형."""
        if self.unit == "조":
            text = f"제{self.n}"
            if self.dash is not None:
                text += f"-{self.dash}"
            text += "조"
            if self.sub is not None:
                text += f"의{self.sub}"
            subs = self.chain_subs or (None,) * len(self.chain)
            for (unit, number), sub in zip(self.chain, subs):
                if unit == "세목":
                    text += f"{number})"
                elif unit == "세세목":
                    text += f"({number})"
                elif unit == "세세세목":
                    text += f"({MOK_LETTERS[number - 1]})"
                elif unit is None:
                    text += f"({number})"
                elif unit == "목" and 0 < number <= len(MOK_LETTERS):
                    text += f"{MOK_LETTERS[number - 1]}목"
                else:
                    text += f"제{number}{unit}"
                if sub is not None:
                    text += f"의{sub}"
            return text
        if self.unit in UNITS or self.unit in {"항", "호"}:
            text = f"제{self.n}{self.unit}"
        elif self.unit == "목" and 0 < self.n <= len(MOK_LETTERS):
            text = f"{MOK_LETTERS[self.n - 1]}목"
        elif self.unit in {"별표", "별지"}:
            text = f"{self.unit} {self.n}"
        else:
            text = f"{self.unit or ''}{self.n}"
        if self.sub is not None:
            text += f"의{self.sub}"
        return text

    def as_dict(self) -> dict:
        """result.json에 저장할 안정적인 JSON 표현."""
        subs = self.chain_subs or (None,) * len(self.chain)
        return {
            "unit": self.unit,
            "n": self.n,
            "sub": self.sub,
            "dash": self.dash,
            "chain": [
                {"unit": unit, "n": number, "sub": sub}
                for (unit, number), sub in zip(self.chain, subs)
            ],
            "surface": self.canonical_surface(),
        }


@dataclass(frozen=True)
class CoordinateOccurrence:
    """질문·본문에서 발견한 좌표와 그 정확한 표면 구간."""

    coordinate: LegalCoordinate
    surface: str
    start: int
    end: int


def read_tail(text: str, pos: int) -> tuple[tuple, int]:
    """조문 뒤의 항·호·목 사슬을 실재하는 표면형만큼 읽는다."""
    chain: list[tuple[Optional[str], int]] = []
    while True:
        for unit, pattern in TAIL_PATTERNS:
            match = pattern.match(text, pos)
            if match:
                chain.append((unit, ordinal(match.group(1))))
                pos = match.end()
                break
        else:
            return tuple(chain), pos


def parse_label(label: str) -> Optional[LegalCoordinate]:
    """인제스트된 문서 노드 라벨을 공통 좌표로 바꾼다."""
    text = (label or "").strip()
    if not text:
        return None
    if text[0] in CIRCLED_ORDINALS:
        return LegalCoordinate("항", CIRCLED_ORDINALS[text[0]])
    match = LABEL_ARTICLE_PATTERN.match(text)
    if match:
        return LegalCoordinate(
            "조", int(match.group(1)),
            sub=int(match.group(3)) if match.group(3) else None,
            dash=int(match.group(2)) if match.group(2) else None,
        )
    match = LABEL_DIVISION_PATTERN.match(text)
    if match:
        return LegalCoordinate(match.group(2), int(match.group(1)))
    match = LABEL_ANNEX_PATTERN.match(text)
    if match:
        return LegalCoordinate(match.group(1), int(match.group(2)))
    match = LABEL_CLAUSE_PATTERN.match(text) or LABEL_ANGLE_CLAUSE_PATTERN.match(text)
    if match:
        return LegalCoordinate("항", int(match.group(1)))
    match = LABEL_HO_PATTERN.match(text) or LABEL_ENUM_PATTERN.match(text)
    if match:
        return LegalCoordinate("호", int(match.group(1)))
    match = LABEL_MOK_PATTERN.match(text)
    if match:
        return LegalCoordinate("목", ordinal(match.group(1)))
    return None


def find_coordinates(text: str) -> list[CoordinateOccurrence]:
    """질문·본문의 명시 좌표를 공통 좌표로 찾는다.

    ``제19조제1항ㆍ제3항``처럼 조를 생략한 연속 항·호·목은 앞 조의 좌표를
    상속한다. 문서명 해석과 외부참조 관계 판정은 이 모듈의 책임이 아니다.
    """
    source = text or ""
    found: list[CoordinateOccurrence] = []
    for match in ARTICLE_PATTERN.finditer(source):
        chain, end = read_tail(source, match.end())
        base = LegalCoordinate(
            "조", int(match.group(1)),
            sub=int(match.group(3)) if match.group(3) else None,
            dash=int(match.group(2)) if match.group(2) else None,
            chain=chain,
        )
        found.append(CoordinateOccurrence(
            base, source[match.start():end], match.start(), end))

        pos = end
        while True:
            connector = CONTINUATION_PATTERN.match(source, pos)
            if not connector or ARTICLE_PATTERN.match(source, connector.end()):
                break
            token = None
            for unit, pattern in TAIL_PATTERNS[:3]:
                tail_match = pattern.match(source, connector.end())
                if tail_match:
                    token = (unit, ordinal(tail_match.group(1)), tail_match.end())
                    break
            if token is None:
                break
            unit, number, tail_end = token
            more, tail_end = read_tail(source, tail_end)
            cut = next((i for i, (existing, _) in enumerate(chain)
                        if existing == unit), len(chain))
            continued = chain[:cut] + ((unit, number),) + more
            coordinate = base.replace_chain(continued)
            found.append(CoordinateOccurrence(
                coordinate, source[connector.end():tail_end],
                connector.end(), tail_end))
            pos = tail_end

    for match in DIVISION_PATTERN.finditer(source):
        coordinate = LegalCoordinate(match.group(2), int(match.group(1)))
        found.append(CoordinateOccurrence(
            coordinate, match.group(0), match.start(), match.end()))
    for match in ANNEX_PATTERN.finditer(source):
        coordinate = LegalCoordinate(match.group(1), int(match.group(2)))
        found.append(CoordinateOccurrence(
            coordinate, match.group(0), match.start(), match.end()))
    return sorted(found, key=lambda row: row.start)
