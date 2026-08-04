"""T8. Fact 추출 레이어 — 계약서·요약서 **양쪽 공용** (SPEC §B10 T8).

두 문서를 직접 비교하지 않는다(§B3-1). 각각 `{field → 타입값 + 출처}` 로 투영한 뒤
그 표에서만 대조한다. 문서 레이아웃이 비교에 개입하지 못하게 하는 장치다.

value_type 은 온톨로지 `fields.*.value_type` 에서 온다 — 여기 하드코딩하지 않는다.
"""
from __future__ import annotations

from typing import Any, Optional

import comparators as cmp
from ontology import Ontology
from schema import Chunk, ChunkDocument, Fact, Source


def _value_of(value_type: str, raw: Any) -> Any:
    parser = cmp.PARSERS.get(value_type)
    return parser(raw) if parser else raw


def from_contract(doc: ChunkDocument, onto: Ontology) -> list[Fact]:
    """검증 대상 = role 이 source_of_truth 인 청크 전체 (§B4).

    별도 필드 목록을 손으로 만들지 않는다. 온톨로지의 fields 선언과
    청크의 heading_path/field 라벨을 맞춰 앵커로 삼는다.
    """
    sot_roles = {s.source_of_truth for s in onto.fields.values() if s.source_of_truth}
    facts: list[Fact] = []
    seen: set[str] = set()

    for name, spec in onto.fields.items():
        if spec.derived:
            continue                       # 파생 필드는 계약서에 직접 없다
        hit = _find_chunk(doc, name, spec.source_of_truth or "", sot_roles)
        if hit is None:
            continue
        raw = _raw_value(hit, name)
        facts.append(Fact(
            field_name=name, topic=hit.topic, value_type=spec.value_type,
            value=_value_of(spec.value_type, raw if spec.value_type != "option_set"
                            else (hit.options or raw)),
            raw=str(raw),
            source=Source(doc="contract", page=hit.provenance.page,
                          bbox=hit.provenance.bbox)))
        seen.add(name)

    # 선언됐지만 문서에서 못 찾은 필드도 남긴다 — 조용한 스킵 금지(§B11-1)
    for name, spec in onto.fields.items():
        if name in seen or spec.derived:
            continue
        facts.append(Fact(field_name=name, value_type=spec.value_type,
                          value=None, raw="", source=None,
                          note="계약서에서 해당 필드를 찾지 못했습니다"))
    return facts


def _find_chunk(doc: ChunkDocument, name: str, sot_role: str,
                sot_roles: set[str]) -> Optional[Chunk]:
    norm = cmp.normalize_text(name)
    best = None
    for c in doc.chunks:
        if sot_role and c.role != sot_role:
            continue
        if not sot_role and c.role not in sot_roles:
            continue
        leaf = c.heading_path[-1] if c.heading_path else ""
        if cmp.normalize_text(leaf) == norm:
            return c
        if best is None and norm and norm in cmp.normalize_text(c.text):
            best = c
    return best


def _raw_value(c: Chunk, field_name: str) -> Any:
    """청크에서 값 부분만 꺼낸다. 라벨(필드명)은 뺀다."""
    if c.options:
        return c.options
    if c.table_options:
        return "\n".join(c.table_options)
    text = c.text or ""
    if ":" in text:
        head, _, tail = text.partition(":")
        if cmp.normalize_text(head) == cmp.normalize_text(field_name):
            return tail.strip()
    return text


def from_summary(records: list[dict], onto: Ontology) -> list[Fact]:
    """요약서 파서(T9)가 낸 {label, value, page} 목록 → Fact.

    value_type 은 매핑 성공 후에 온톨로지에서 가져오므로, 여기서는 raw 만 담는다.
    """
    out: list[Fact] = []
    for r in records:
        out.append(Fact(
            field_name=r.get("label", ""), value_type="text",
            value=None, raw=str(r.get("value", "")),
            source=Source(doc="summary", page=r.get("page"), bbox=r.get("bbox"))))
    return out


def retype(fact: Fact, value_type: str) -> Fact:
    """매핑이 끝나 value_type 이 정해진 뒤 값을 다시 파싱한다."""
    fact.value_type = value_type
    fact.value = _value_of(value_type, fact.raw)
    return fact
