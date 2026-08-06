"""T1. 용어집 로더 — 사용자가 시스템에 주는 최우선 입력 (SPEC §1).

용어는 **이원(二元)** 이다.
    section 용어 — 문서의 구역 경계가 될 수 있는 용어. 문단/구역 레벨.
    fact 용어   — 값이 붙는 내용 용어. 문장 레벨.
한 용어가 양쪽 모두일 수 있다("신탁계약 세부내역": 별지1의 제목이면서 본문 문장 속 mention).

이 모듈은 도메인을 모른다. 어떤 용어가 있는지는 `glossary/{doc_type}.glossary.yaml` 이 정하고,
여기서는 그 파일을 읽어 **검증된 모델**로 만들고 매칭에 쓸 색인을 제공할 뿐이다.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Iterable, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

# §1.2 — fact 용어에만 붙는다. 기본값 text.
VALUE_TYPES = ("number", "date", "date_range", "percent",
               "range_tiers", "option_set", "account_no", "text")

Kind = Literal["section", "fact"]


def normalize(surface: str) -> str:
    """매칭용 정규화 — 공백·괄호·구분자를 지우고 대소문자를 통일한다.

    "신탁 금액", "신탁금액(원)", "신탁금액" 이 모두 같은 키가 되게 한다(§B5-1 계승).
    조사는 지우지 않는다 — 지우면 서로 다른 용어가 충돌한다.
    """
    out = []
    for ch in unicodedata.normalize("NFKC", surface or ""):
        if unicodedata.category(ch)[0] in ("L", "N"):
            out.append(ch)
    return "".join(out).casefold()


class Term(BaseModel):
    """용어집의 한 항목."""
    kind: list[Kind]
    value_type: str = "text"
    aliases: list[str] = Field(default_factory=list)
    note: Optional[str] = None

    @property
    def is_section(self) -> bool:
        return "section" in self.kind

    @property
    def is_fact(self) -> bool:
        return "fact" in self.kind


class Glossary(BaseModel):
    version: int
    doc_type: str
    terms: dict[str, Term] = Field(default_factory=dict)

    # --- 무결성 검사 ------------------------------------------------------
    @model_validator(mode="after")
    def _check(self) -> "Glossary":
        problems: list[str] = []
        for name, t in self.terms.items():
            if not t.kind:
                problems.append(f"terms.{name}.kind 가 비어 있습니다 (section/fact 중 하나 이상)")
            if t.value_type not in VALUE_TYPES:
                problems.append(
                    f"terms.{name}.value_type '{t.value_type}' 은 허용되지 않습니다 "
                    f"({', '.join(VALUE_TYPES)})")
            # value_type 은 fact 용어에만 의미가 있다 — section 전용에 붙어 있으면 오해를 낳는다
            if not t.is_fact and t.value_type != "text":
                problems.append(
                    f"terms.{name} 은 fact 용어가 아닌데 value_type '{t.value_type}' 이 있습니다")
        # 표면형 충돌 — 두 용어가 같은 정규형으로 접히면 매칭이 갈린다
        seen: dict[str, str] = {}
        for name, t in self.terms.items():
            for surface in [name, *t.aliases]:
                key = normalize(surface)
                if not key:
                    problems.append(f"terms.{name} 의 표면형 '{surface}' 이 비어 있습니다")
                    continue
                if key in seen and seen[key] != name:
                    problems.append(
                        f"표면형 '{surface}' 이 '{seen[key]}' 와 '{name}' 양쪽에 걸립니다")
                seen[key] = name
        if problems:
            raise ValueError("용어집 오류:\n  - " + "\n  - ".join(problems))
        return self

    # --- 조회 -------------------------------------------------------------
    def section_terms(self) -> list[str]:
        return [n for n, t in self.terms.items() if t.is_section]

    def fact_terms(self) -> list[str]:
        return [n for n, t in self.terms.items() if t.is_fact]

    def surface_index(self) -> dict[str, str]:
        """정규화된 표면형 → 정규 용어명. 이름 자신과 aliases 를 모두 담는다."""
        idx: dict[str, str] = {}
        for name, t in self.terms.items():
            idx.setdefault(normalize(name), name)
            for a in t.aliases:
                idx.setdefault(normalize(a), name)
        return idx

    def lookup(self, surface: str) -> Optional[str]:
        """표면형 하나를 정규 용어명으로. 못 찾으면 None."""
        return self.surface_index().get(normalize(surface))

    def value_type(self, term: str) -> str:
        t = self.terms.get(term)
        return t.value_type if t else "text"

    def surfaces_of(self, term: str) -> list[str]:
        t = self.terms.get(term)
        return [term, *(t.aliases if t else [])]

    def add_term(self, name: str, kind: Iterable[str], value_type: str = "text",
                 aliases: Optional[list[str]] = None) -> None:
        """후보 승격(§2.4) — 용어집은 살아있는 파일이다."""
        self.terms[name] = Term(kind=list(kind), value_type=value_type,
                                aliases=list(aliases or []))
        Glossary.model_validate(self.model_dump())      # 추가 후에도 무결성 유지

    def dump_yaml(self) -> str:
        data = {
            "version": self.version,
            "doc_type": self.doc_type,
            "terms": {n: t.model_dump(exclude_none=True, exclude_defaults=False)
                      for n, t in self.terms.items()},
        }
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def load(path: str | Path) -> Glossary:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Glossary.model_validate(data)


def save(g: Glossary, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(g.dump_yaml(), encoding="utf-8")
    return p
