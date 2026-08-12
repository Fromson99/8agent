"""T1. 용어집 로더 — 사용자가 시스템에 주는 최우선 입력 (SPEC §1).

용어는 **이원(二元)** 이다.
    section 용어 — 문서의 구역 경계가 될 수 있는 용어. 문단/구역 레벨.
    fact 용어   — 값이 붙는 내용 용어. 문장 레벨.
한 용어가 양쪽 모두일 수 있다("신탁계약 세부내역": 별지1의 제목이면서 본문 문장 속 mention).

이 모듈은 도메인을 모른다. 어떤 용어가 있는지는 `glossary/{doc_type}.glossary.yaml` 이 정하고,
여기서는 그 파일을 읽어 **검증된 모델**로 만들고 매칭에 쓸 색인을 제공할 뿐이다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

from core.normalize import normalize_text

# §1.2 — fact 용어에만 붙는다. 기본값 text.
VALUE_TYPES = ("number", "date", "date_range", "percent",
               "range_tiers", "option_set", "account_no", "text")

Kind = Literal["section", "fact"]


def normalize(surface: str) -> str:
    """매칭용 정규화 — 공백·괄호·구분자를 지우고 대소문자를 통일한다.

    "신탁 금액", "신탁금액(원)", "신탁금액" 이 모두 같은 키가 되게 한다(§B5-1 계승).
    조사는 지우지 않는다 — 지우면 서로 다른 용어가 충돌한다.
    구현은 `core.normalize.normalize_text` 하나다 — 같은 정규화가 두 벌이면
    한쪽만 고쳐져 매칭과 값 비교가 서로 다른 키를 쓰게 된다.
    """
    return normalize_text(surface)


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
        """후보 승격(§2.4) — 용어집은 살아있는 파일이다.

        **사본으로 먼저 검증한다.** 넣고 나서 검증하면 실패해도 `self.terms` 에
        오염된 항목이 남고, 호출자가 예외를 잡고 저장하면 무효 용어집이 디스크에
        쓰인다 — 실제로 그 순서였다.
        """
        candidate = Term(kind=list(kind), value_type=value_type,
                         aliases=list(aliases or []))
        data = self.model_dump()
        data["terms"][name] = candidate.model_dump()
        Glossary.model_validate(data)                   # 실패하면 여기서 멈춘다
        self.terms[name] = candidate

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


# 전역 용어집 — 화면(api/routers/glossary.py)이 관리하는 JSON 이 정본이다.
# 유형별 용어집을 route 에 매달지 않는 방향이라, route 에 용어집이 없으면 이쪽을 쓴다.
GLOBAL_STORE = Path(
    os.environ.get("GLOSSARY_STORE",
                   Path(os.environ.get("STRUCTURE_STORE",
                                       Path(__file__).resolve().parent.parent
                                       / "out" / "structure" / "viewer")).parent
                   / "glossary.json"))


def load_global(doc_type: str = "*", path: str | Path | None = None) -> Glossary:
    """전역 용어집(JSON) → `Glossary`.

    화면의 용어집은 **출현 네트워크**(어느 문서 어느 마디에 나왔나)이고 여기서
    필요한 것은 **판정에 쓸 이름과 표면형**뿐이다. 그래서 옮기는 것은 셋:
      - `term`      용어 이름
      - `surfaces`  다른 표기 → aliases
      - `status`    `tombstone`(버린 것)은 싣지 않는다

    kind 는 `section` 으로 둔다 — 전역 용어는 "이 이름이 구역 제목이면 구역을 연다"
    까지만 말한다. 값이 붙는 fact 용어는 태스크(체크리스트)의 일이라 여기서 정하지 않는다.
    doc_type 이 route 와 어긋나면 적재가 거부되므로 호출자가 자기 유형을 넘긴다.
    """
    p = Path(path or GLOBAL_STORE)
    if not p.exists():
        return Glossary(version=1, doc_type=doc_type, terms={})
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Glossary(version=1, doc_type=doc_type, terms={})

    terms: dict[str, Term] = {}
    for item in raw.get("terms", []):
        name = str(item.get("term") or "").strip()
        if not name or item.get("status") == "tombstone":
            continue
        aliases = [s for s in (item.get("surfaces") or []) if s and s != name]
        terms[name] = Term(kind=["section"], aliases=sorted(set(aliases)))
    return Glossary(version=1, doc_type=doc_type, terms=terms)


def save(g: Glossary, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(g.dump_yaml(), encoding="utf-8")
    return p
