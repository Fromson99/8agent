"""T0. pydantic 스키마 — 인스턴스 계층 (SPEC §4, 정본 `trust_contract_chunks_sample.json`).

이 계층에는 **도메인 지식이 없다.** "무엇이 어디에 있다"만 담는다(§C1).
값의 유효성(신탁금액>0 등)은 여기가 아니라 온톨로지가 판정한다(validate.py).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    page: int
    bbox: Optional[list[float]] = None


class Item(BaseModel):
    """호 리스트의 한 항목 (§4 items)."""
    level: str = "호"
    no: str
    text: str


class Option(BaseModel):
    """체크박스 그리드의 한 옵션 (§4 options)."""
    no: int
    label: str
    checked: bool = False


class Chunk(BaseModel):
    chunk_id: str
    role: str
    level: str
    article: Optional[str] = None
    article_title: Optional[str] = None
    clause: Optional[str] = None
    topic: str
    heading_path: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    cross_ref_explicit: Optional[str] = None
    provenance: Provenance
    text: str

    # 선택 구조 (§4)
    items: Optional[list[Item]] = None
    options: Optional[list[Option]] = None
    table_options: Optional[list[str]] = None
    structure: Optional[str] = None
    value_template: Optional[str] = None

    # 파이프라인 내부용 — 출력에서는 제외한다(정본 스키마에 없음)
    char_count: Optional[int] = Field(default=None, exclude=True)
    block_ids: list[str] = Field(default_factory=list, exclude=True)

    def dump(self) -> dict[str, Any]:
        """정본과 같은 모양으로 — None 필드는 빼고, 키 순서를 맞춘다."""
        order = ["chunk_id", "role", "level", "article", "article_title", "clause",
                 "topic", "heading_path", "refs", "cross_ref_explicit", "provenance",
                 "structure", "value_template", "text", "items", "options", "table_options"]
        raw = self.model_dump(exclude_none=True)
        return {k: raw[k] for k in order if k in raw}


class ChunkDocument(BaseModel):
    document: str
    schema_version: str = "facet-v1"
    source_pdf: Optional[str] = None
    chunks: list[Chunk] = Field(default_factory=list)

    def dump(self) -> dict[str, Any]:
        out: dict[str, Any] = {"document": self.document,
                               "schema_version": self.schema_version}
        if self.source_pdf:
            out["source_pdf"] = self.source_pdf
        out["chunks"] = [c.dump() for c in self.chunks]
        return out

    def by_role(self, role: str) -> list[Chunk]:
        return [c for c in self.chunks if c.role == role]

    def articles(self) -> list[str]:
        seen, out = set(), []
        for c in self.chunks:
            if c.article and c.article not in seen:
                seen.add(c.article)
                out.append(c.article)
        return out


# ===========================================================================
# Part B — Fact / 리포트 (§B9)
# ===========================================================================

class Source(BaseModel):
    doc: str
    page: Optional[int] = None
    bbox: Optional[list[float]] = None


class Fact(BaseModel):
    """양쪽 문서를 같은 모양으로 투영한 것 (§B3-1). 비교는 이 표에서만 일어난다."""
    field_name: str
    topic: Optional[str] = None
    value_type: str
    value: Any = None          # 타입별 정규형 (comparators 가 소비)
    raw: str = ""              # 문서에 쓰인 표현 그대로
    source: Optional[Source] = None
    note: str = ""


VERDICTS = ("MATCH", "VALUE_MISMATCH", "MISSING_IN_SUMMARY", "UNMAPPED", "NEEDS_REVIEW")


class ReconcileRow(BaseModel):
    field_name: str
    topic: Optional[str] = None
    value_type: str
    contract_value: Optional[str] = None
    contract_source: Optional[Source] = None
    summary_value: Optional[str] = None
    summary_source: Optional[Source] = None
    verdict: str
    note: str = ""


class ReconcileReport(BaseModel):
    contract: str
    summary: str
    generated_at: str
    rows: list[ReconcileRow] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    violations: list[dict] = Field(default_factory=list)
    firings: dict = Field(default_factory=dict)      # T20 제약별 발화 통계 (§C12.4)

    def recount(self) -> "ReconcileReport":
        key = {"MATCH": "match", "VALUE_MISMATCH": "value_mismatch",
               "MISSING_IN_SUMMARY": "missing", "UNMAPPED": "unmapped",
               "NEEDS_REVIEW": "needs_review"}
        s = {v: 0 for v in key.values()}
        for r in self.rows:
            s[key[r.verdict]] = s.get(key[r.verdict], 0) + 1
        self.stats = {"total": len(self.rows), **s}
        return self
