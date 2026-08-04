"""데이터 모델 — 파싱 결과와 태깅 결과.

## 파이프라인

    P1 파싱   파일 → ParsedDocument(blocks[])                  [도클링, LLM 없음]
    P2 태깅   blocks + tag_schema → TaggedDocument(sections[])  [LLM]
    P3 1단계  두 TaggedDocument → SectionPair[]                 [코드 축소 + LLM 판정]
    P4 2단계  SectionPair → ElementComparison[]                 [코드 비교, 서술만 LLM]

## 왜 P1 이 "섹션"이 아니라 "블록"을 내는가

도클링을 dataset 실물에 돌려 본 결과:

| 문서 | section_header 인식 | table 인식 |
|---|---|---|
| 유안타 계약서 | 33개 조항 중 **6개** | **0개** (별지1 세부내역서를 놓침) |
| 하나은행 ISA | 78개 | 2개 |

유안타 계약서는 조항 제목이 본문과 시각적으로 완전히 동일하다(10pt, 같은 폰트, 같은 들여쓰기).
원본에 계층 정보가 없으므로 어떤 레이아웃 모델도 조항 경계를 그어 줄 수 없다.

그래서 섹션 경계를 파서에 기대지 않는다.
**섹션 = 같은 메인 태그가 붙은 연속 블록들** 로 정의하고, 그 판단은 P2 태깅이 한다.
태깅은 제목이 아니라 본문 내용을 보므로, 제목이 없어도(또는 같아도) 구분해 낸다.
별도 세그멘테이션 단계가 사라져 파이프라인이 오히려 단순해진다.

## 2계층 (사용자 선언)

    tag_schema.sections[]            메인 요소 — 각 섹션이 무엇에 관한 것인가   → 1단계 대상
    tag_schema.sections[].elements[] 세부 요소 — 그 안의 개별 용어와 값         → 2단계 대상
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Optional


def to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


# ===========================================================================
# P1 — 파싱 결과
# ===========================================================================

@dataclass
class Provenance:
    """이 내용이 원본 어디서 왔는지. 모든 판정에 출처가 붙어야 사람이 검증할 수 있다."""
    page: Optional[int] = None
    doc_ref: str = ""            # 도클링 self_ref — 원본 블록으로 되돌아가는 열쇠
    bbox: Optional[list] = None  # [x0, top, x1, bottom]

    def label(self) -> str:
        return f"p.{self.page}" if self.page else "-"


@dataclass
class DocBlock:
    """파서가 낸 블록 하나. 아직 의미(태그)는 붙지 않았다."""
    block_id: str
    order: int = 0                       # 읽기 순서
    kind: str = "text"                   # text | list_item | section_header | table | caption
    text: str = ""
    table: Optional[list[list[str]]] = None
    provenance: Provenance = field(default_factory=Provenance)
    source: str = ""                     # docling | pdfplumber(보완) — 어느 파서가 냈는지

    def content(self, table_limit: int = 3000) -> str:
        if self.kind == "table" and self.table:
            return "\n".join(" | ".join(c for c in row) for row in self.table)[:table_limit]
        return self.text


@dataclass
class DocMeta:
    """문서 메타. 예전에는 정규식 6종으로 뽑아 9종 중 4종(44%)만 성공했다.
    이제 LLM 이 문서 앞부분을 읽고 채우며, 못 찾으면 정직하게 None 을 남긴다."""
    title: Optional[str] = None
    issuer: Optional[str] = None
    version_date: Optional[str] = None       # "YYYY-MM-DD"
    product_type: Optional[str] = None
    confidence: float = 0.0
    evidence: str = ""


@dataclass
class ParsedDocument:
    doc_id: str
    doc_role: str                        # contract | product_statement | change_table
    source_path: str = ""
    source_format: str = ""              # pdf | docx | md | txt
    parser: str = ""                     # "docling 2.117.0 (ocr=off, tables=on)"
    content_hash: str = ""               # 스냅샷 캐시 키
    meta: DocMeta = field(default_factory=DocMeta)
    blocks: list[DocBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def block(self, block_id: str) -> Optional[DocBlock]:
        return next((b for b in self.blocks if b.block_id == block_id), None)

    def digest(self, preview: int = 160) -> list[dict]:
        """태깅에 넘길 블록 요약. 전문을 그대로 넣지 않기 위한 것."""
        from .textkit import truncate
        return [{
            "block_id": b.block_id,
            "kind": b.kind,
            "page": b.provenance.page,
            "text": truncate(b.content(), preview),
        } for b in self.blocks]


# ===========================================================================
# P2 — 태깅 결과
# ===========================================================================

@dataclass
class ElementValue:
    """LLM 이 구조화해 준 값.

    코드는 이 dict 만 보고 비교한다. 문자열을 다시 파싱하지 않는다 —
    그 파싱을 정규식으로 하다가 금액 오탐 80%가 났던 자리다.
    """
    value_type: str = "text"
    raw: str = ""                        # 문서에 쓰인 표현 그대로 (사람이 검증할 근거)
    data: dict = field(default_factory=dict)


@dataclass
class TaggedElement:
    element_id: str                      # tag_schema sections[].elements[].id
    display: str = ""
    value: ElementValue = field(default_factory=ElementValue)
    status: str = "found"                # found | not_found | ambiguous
    confidence: float = 0.0
    note: str = ""
    provenance: Provenance = field(default_factory=Provenance)


# 같은 큰 요소(태그)라도 문서 안에서 하는 역할이 다르다.
#   provision   관련 조항 — "최초 신탁금액은 [별지1]에 기재된 금액으로 한다" (규정이지 값이 아님)
#   value       실제 값   — 별지1 세부내역서의 "신탁금액 | 금 100,000,000원정"
#   explanation 설명 서술 — 설명서의 "가입금액은 1억원이며…"
# 값 비교는 value/explanation 에서만 하고, provision 은 근거로 붙인다.
# 이 구분이 없으면 계약서 조항의 "별지1 참조"와 설명서의 "1억원"을 비교하게 되어
# 영원히 uncertain 이 난다(실측에서 6건 발생).
ROLE_VALUE, ROLE_PROVISION, ROLE_EXPLANATION = "value", "provision", "explanation"
VALUE_BEARING = (ROLE_VALUE, ROLE_EXPLANATION)
ROLE_PRIORITY = {ROLE_VALUE: 3, ROLE_EXPLANATION: 2, ROLE_PROVISION: 1}


@dataclass
class TaggedSection:
    """같은 메인 태그가 붙은 연속 블록 묶음 = 하나의 섹션."""
    section_id: str
    tag: Optional[str] = None            # tag_schema sections[].id  (= 큰 요소)
    role: str = ROLE_VALUE               # value | provision | explanation
    title: str = ""                      # 문서에 실제로 쓰인 제목(있으면)
    block_ids: list[str] = field(default_factory=list)
    tag_confidence: float = 0.0
    rationale: str = ""
    terms: list[str] = field(default_factory=list)   # 이 섹션에 등장한 용어(용어집 정규형)
    elements: list[TaggedElement] = field(default_factory=list)
    provenance: Provenance = field(default_factory=Provenance)

    def element(self, element_id: str) -> Optional[TaggedElement]:
        return next((e for e in self.elements if e.element_id == element_id), None)


@dataclass
class TaggedDocument:
    doc_id: str
    doc_role: str
    schema_version: str = ""
    backend: str = ""
    sections: list[TaggedSection] = field(default_factory=list)
    # 선언에 없지만 문서에 있던 것 — 버리지 않고 사용자에게 스키마 추가를 제안한다
    suggestions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def section(self, section_id: str) -> Optional[TaggedSection]:
        return next((s for s in self.sections if s.section_id == section_id), None)

    def by_tag(self, tag: str) -> list[TaggedSection]:
        return [s for s in self.sections if s.tag == tag]

    def tags(self) -> set[str]:
        return {s.tag for s in self.sections if s.tag}


# ===========================================================================
# P3 — 1단계: 섹션 대응 ("실제로 동일한 부분인가")
# ===========================================================================

@dataclass
class SectionPair:
    pair_id: str
    tag: Optional[str] = None
    contract_sections: list[str] = field(default_factory=list)   # 1:N 가능
    statement_sections: list[str] = field(default_factory=list)
    method: str = "tag"                  # tag | llm_semantic
    confidence: float = 0.0
    evidence: str = ""
    shared_terms: list[str] = field(default_factory=list)
    flag: str = "ok"                     # ok | uncertain | contract_only | statement_only


# ===========================================================================
# P4 — 2단계: 요소 비교 ("실제로 값이 일치하는가")
# ===========================================================================

@dataclass
class ElementComparison:
    pair_id: str
    tag: str = ""
    element_id: str = ""
    display: str = ""
    value_type: str = ""
    contract_raw: str = ""
    statement_raw: str = ""
    verdict: str = "uncertain"           # match | mismatch | uncertain | missing_side
    method: str = ""                     # typed_compare | mapping_table | llm_semantic | missing
    reason: str = ""
    confidence: float = 0.0
    is_key: bool = False                 # tag_schema 에서 key=true 인 요소
    evidence: dict = field(default_factory=dict)


# ===========================================================================
# 완결성 / 리포트
# ===========================================================================

@dataclass
class CompletenessResult:
    tag: str
    display: str = ""
    present: bool = False
    required: bool = True
    verdict: str = "missing"             # ok | missing | not_applicable
    location: str = "-"
    reason: str = ""


@dataclass
class Finding:
    type: str                            # mismatch | missing | uncertain | unpaired | suggestion
    tag: str = ""
    display: str = ""
    severity: str = "med"                # high | med | low
    detail: dict = field(default_factory=dict)


@dataclass
class Report:
    summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    authority: str = "contract"
    documents: dict = field(default_factory=dict)
    backend: str = ""
    schema_version: str = ""
    pairs: list[SectionPair] = field(default_factory=list)
    comparisons: list[ElementComparison] = field(default_factory=list)
    completeness: list[CompletenessResult] = field(default_factory=list)
    suggestions: list[dict] = field(default_factory=list)
