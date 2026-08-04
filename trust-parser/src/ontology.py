"""T14. 온톨로지 로더 — 제약 계층의 단일 출처 (SPEC §C6, §C8).

이 모듈은 YAML 온톨로지를 읽어 검증된 모델로 만든다.
파이프라인의 다른 모듈은 도메인 지식을 여기서만 가져온다 — 코드에 상수로 박지 않는다(§C8 완료기준 1).

인식 vs 제약 (§7)
    온톨로지는 "무엇이 참이어야 하는가"를 선언한다.
    "이 PDF 에서 어떻게 알아보는가"는 recognizers.py 가 구현한다.
    다만 **어떤 recognizer 를 쓸지는 온톨로지가 고른다**(`structure.*.recognizer`).
    구현은 코드, 선택은 선언 — 이 경계가 §C8 완료기준 2("파일만 바꿔 다른 문서 종류")를 성립시킨다.
"""

from __future__ import annotations

from datetime import date as _date
from pathlib import Path
from typing import Any, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, model_validator


class EnumClass(BaseModel):
    kind: Literal["enum"]
    values: list[str]
    note: Optional[str] = None


class StructureNode(BaseModel):
    """구조 모델의 한 요소. '조는 번호와 제목을 갖고 항을 포함한다' 같은 서술."""
    has: list[str] = Field(default_factory=list)
    contains: Optional[str] = None
    ordinal: bool = False
    field_links_to: Optional[str] = None
    recognizer: Optional[str] = None
    # 청킹 선언 (§C6). 코드가 아니라 여기서 정한다.
    #   primary        이 단위가 기본 청크
    #   split_if_long  부모가 매우 길 때만 이 단위로 분할
    #   inline         부모 청크의 items[] 로 담는다
    #   per_field      필드/표 단위
    chunk: Optional[str] = None
    chunk_boundary: Optional[str] = None      # hard = 절대 넘지 않음


class PartSpec(BaseModel):
    role: str
    default: bool = False
    starts_at: Optional[str] = None
    appendix_no: Optional[int] = None


class PropertySpec(BaseModel):
    type: str
    range: list[str] = Field(default_factory=list)
    formula: Optional[str] = None
    applies_to_role: list[str] = Field(default_factory=list)
    recognizer: Optional[str] = None
    note: Optional[str] = None


class Provenance(BaseModel):
    """제약의 출처 (§C12.3) — 감사 대응과 폐기 판단의 근거."""
    origin: Optional[str] = None
    approved_by: Optional[str] = None
    # YAML 이 날짜 리터럴을 date 로 파싱하므로 둘 다 받는다
    date: Optional[Union[str, _date]] = None


class FieldSpec(BaseModel):
    """별지1 필드 = Part B 검증 대상 (§B4).

    source_of_truth·equals·aliases 가 교차문서 공리이며,
    reconcile.py 는 이것을 읽어서 동작한다(하드코딩 금지).
    """
    value_type: str
    constraints: list[str] = Field(default_factory=list)
    article: Optional[str] = None
    source_of_truth: Optional[str] = None
    equals: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    derived: Optional[str] = None
    note: Optional[str] = None
    cq: list[str] = Field(default_factory=list)          # 근거 competency question (§C12.2)
    provenance: Optional[Provenance] = None              # 제약의 출처 (§C12.3)


class Axiom(BaseModel):
    id: str
    source: Optional[str] = None
    quote: Optional[str] = None
    rule: str
    kind: str = "constraint"
    approved: bool = False
    note: Optional[str] = None


class Ontology(BaseModel):
    version: int
    doc_type: str
    source_document: Optional[str] = None
    competency_questions: dict[str, str] = Field(default_factory=dict)
    classes: dict[str, EnumClass] = Field(default_factory=dict)
    structure: dict[str, StructureNode] = Field(default_factory=dict)
    parts: list[PartSpec] = Field(default_factory=list)
    properties: dict[str, PropertySpec] = Field(default_factory=dict)
    fields: dict[str, FieldSpec] = Field(default_factory=dict)
    shapes: list[str] = Field(default_factory=list)
    axioms_from_text: list[Axiom] = Field(default_factory=list)

    # --- 무결성 검사 ------------------------------------------------------
    @model_validator(mode="after")
    def _check(self) -> "Ontology":
        problems: list[str] = []

        roles = set(self.enum("role"))
        for p in self.parts:
            if p.role not in roles:
                problems.append(f"parts 의 role '{p.role}' 이 classes.role 에 없습니다")
        if not any(p.default for p in self.parts):
            problems.append("parts 에 default:true 인 파트가 없습니다")

        for name, spec in self.fields.items():
            if spec.source_of_truth and spec.source_of_truth not in roles:
                problems.append(f"fields.{name}.source_of_truth '{spec.source_of_truth}' 가 role 이 아닙니다")
            # §C12.2 — 근거 CQ 가 선언 목록에 있어야 한다. 쓰이지 않는 제약은 만들지 않는다.
            for q in spec.cq:
                if self.competency_questions and q not in self.competency_questions:
                    problems.append(f"fields.{name}.cq '{q}' 가 competency_questions 에 없습니다")
            # 파생식은 로드 시점에 검사한다 — 오타가 런타임까지 살아남으면
            # 계산이 조용히 엉뚱한 값을 내고, 그건 대사 리포트에서 구분되지 않는다.
            if spec.derived:
                import derive
                problems += [f"fields.{name}.derived — {p}"
                             for p in derive.check(spec.derived, self.fields)]

        for name, node in self.structure.items():
            if node.contains and node.contains not in self.structure:
                problems.append(f"structure.{name}.contains '{node.contains}' 가 정의되지 않았습니다")
            if node.field_links_to and node.field_links_to not in self.structure:
                problems.append(f"structure.{name}.field_links_to '{node.field_links_to}' 가 정의되지 않았습니다")

        if problems:
            raise ValueError("온톨로지 무결성 오류:\n  - " + "\n  - ".join(problems))
        return self

    # --- 조회 도우미 ------------------------------------------------------
    def enum(self, name: str) -> list[str]:
        c = self.classes.get(name)
        return list(c.values) if c else []

    def default_role(self) -> str:
        return next(p.role for p in self.parts if p.default)

    def appendix_parts(self) -> list[PartSpec]:
        return [p for p in self.parts if p.starts_at]

    def recognizer_for(self, node: str) -> Optional[str]:
        n = self.structure.get(node)
        return n.recognizer if n else None

    def chunk_mode(self, node: str) -> Optional[str]:
        """이 구조 단위를 어떻게 청킹할지 — 온톨로지 선언을 읽는다 (§C6, T4)."""
        n = self.structure.get(node)
        return n.chunk if n else None

    def nodes_with_chunk(self, mode: str) -> list[str]:
        return [k for k, v in self.structure.items() if v.chunk == mode]

    def hard_boundary_nodes(self) -> list[str]:
        return [k for k, v in self.structure.items() if v.chunk_boundary == "hard"]

    def containment_chain(self, root: str = "조") -> list[str]:
        """조 → 항 → 호 처럼 중첩 순서를 펼친다."""
        chain, cur, seen = [], root, set()
        while cur and cur in self.structure and cur not in seen:
            chain.append(cur)
            seen.add(cur)
            cur = self.structure[cur].contains
        return chain

    def topic_formula(self) -> str:
        p = self.properties.get("topic")
        return (p.formula if p and p.formula else "{article_title}({article})")

    def refs_range(self) -> list[str]:
        p = self.properties.get("refs")
        return list(p.range) if p else []

    def alias_index(self) -> dict[str, str]:
        """요약서 표면명 → 별지1 정규 필드명. Part B 매핑이 쓴다(§B5-3)."""
        idx: dict[str, str] = {}
        for canonical, spec in self.fields.items():
            idx.setdefault(_norm(canonical), canonical)
            for a in spec.aliases:
                idx.setdefault(_norm(a), canonical)
        return idx

    def field_of_article(self, article: str) -> list[str]:
        return [n for n, s in self.fields.items() if s.article == article]

    def approved_axioms(self) -> list[Axiom]:
        return [a for a in self.axioms_from_text if a.approved]


def _norm(name: str) -> str:
    """필드명 정규화 (§B5-1) — 공백·괄호·조사 제거. 매핑 전용."""
    out = []
    skip = set(" \t　()（）[]{}·:：,，.。/-_")
    for ch in (name or ""):
        if ch not in skip:
            out.append(ch)
    return "".join(out).casefold()


def load(path: str | Path) -> Ontology:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Ontology.model_validate(data)


def default_path(root: Path | None = None) -> Path:
    root = root or Path(__file__).resolve().parent.parent
    return root / "ontology" / "trust_contract.ontology.yaml"
