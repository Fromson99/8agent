"""T12. Reconciliation 엔진 — 별지1 기준 순회 (SPEC §B3-2, §B12).

방향성이 고정돼 있다: **계약서(별지1)가 정답**이고, 요약서가 그것을 담고 있는지 본다.
"요약서를 훑는다"가 아니라 "별지1 필드를 하나씩 돌며 요약서에 올바르게 있는지" 확인한다 —
그래야 정답에 있는 값을 빠뜨리지 않는다(§B11-1 조용한 스킵 금지).

판정은 코드 결정론이다(§B11-5). LLM 은 여기 관여하지 않는다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import comparators as cmp
import derive
import fact as fact_layer
import mapping as mapping_mod
import summary_parse
from ontology import Ontology
from schema import ChunkDocument, Fact, ReconcileReport, ReconcileRow


def _load_chunks(path: str | Path) -> ChunkDocument:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ChunkDocument.model_validate(data)


def run(contract_chunks: str | Path, summary_path: str | Path,
        onto: Ontology, aliases_yaml: Optional[Path] = None) -> ReconcileReport:
    doc = _load_chunks(contract_chunks)
    contract_facts = {f.field_name: f for f in fact_layer.from_contract(doc, onto)}

    records = summary_parse.parse(summary_path)
    summary_facts = fact_layer.from_summary(records, onto)
    mapper = mapping_mod.Mapper(onto, aliases_yaml)
    mapped = mapper.build(summary_facts)

    rows: list[ReconcileRow] = []

    # **별지1 필드를 기준으로 순회한다** — 요약서가 아니라 정답 문서가 기준이다
    for name, spec in onto.fields.items():
        c = contract_facts.get(name)
        s = mapped.get(name)

        # 파생 필드 — '동일'이 아니라 '계산상 일관'으로 본다(§B7 말미)
        if spec.derived:
            rows.append(_derived_row(name, spec, contract_facts, s, onto))
            continue

        if c is None or not c.raw:
            rows.append(ReconcileRow(
                field_name=name, topic=c.topic if c else None,
                value_type=spec.value_type, contract_value=None,
                contract_source=c.source if c else None,
                summary_value=s.raw if s else None,
                summary_source=s.source if s else None,
                verdict="NEEDS_REVIEW",
                note="계약서(별지1)에서 값을 찾지 못해 대조 기준이 없습니다"))
            continue

        if s is None:
            # 요약서에서 못 찾음 — 이름을 못 찾은 것(UNMAPPED)인지
            # 이름은 있는데 값이 없는 것(MISSING)인지 구분한다(§B8)
            verdict = "UNMAPPED" if not spec.aliases and not _label_seen(records, name) \
                else "MISSING_IN_SUMMARY"
            note = ("요약서에서 이름으로도 alias 로도 찾지 못했습니다 — aliases 보강 필요"
                    if verdict == "UNMAPPED" else "요약서에 해당 값이 없습니다")
            rows.append(ReconcileRow(
                field_name=name, topic=c.topic, value_type=spec.value_type,
                contract_value=c.raw, contract_source=c.source,
                summary_value=None, summary_source=None,
                verdict=verdict, note=note))
            continue

        fact_layer.retype(s, spec.value_type)
        # option_set 만 파싱된 값(체크 상태)을 넘긴다 — 나머지는 원문 그대로 비교기에 준다.
        contract_input = c.value if spec.value_type == "option_set" else c.raw
        res = cmp.compare(spec.value_type, contract_input, s.raw)
        rows.append(ReconcileRow(
            field_name=name, topic=c.topic, value_type=spec.value_type,
            contract_value=c.raw, contract_source=c.source,
            summary_value=s.raw, summary_source=s.source,
            verdict=res.verdict, note=res.note))

    report = ReconcileReport(
        contract=str(contract_chunks), summary=str(summary_path),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        rows=rows)
    report.firings = _count_firings(rows, onto)
    return report.recount()


def _count_firings(rows, onto) -> dict:
    """T20. 제약별 발화 통계 (§C12.4).

    두 종류의 죽은 제약을 걸러내기 위한 근거다:
      (a) 한 번도 발화하지 않는 제약 — 가치 검증 불가
      (b) 잘못 발화하는 제약 — 노이즈
    장기 미발화 제약은 주기 리뷰에서 유지/폐기를 판단한다.
    """
    per_field: dict[str, dict] = {}
    per_cq: dict[str, dict] = {}
    for r in rows:
        spec = onto.fields.get(r.field_name)
        fired = r.verdict in ("VALUE_MISMATCH", "MISSING_IN_SUMMARY")
        entry = per_field.setdefault(r.field_name, {"checked": 0, "fired": 0, "verdict": ""})
        entry["checked"] += 1
        entry["fired"] += int(fired)
        entry["verdict"] = r.verdict
        for q in (spec.cq if spec else []):
            c = per_cq.setdefault(q, {"checked": 0, "fired": 0})
            c["checked"] += 1
            c["fired"] += int(fired)
    return {"per_field": per_field, "per_cq": per_cq,
            "never_fired": sorted(k for k, v in per_field.items() if v["fired"] == 0)}


def _label_seen(records: list[dict], name: str) -> bool:
    n = cmp.normalize_text(name)
    return any(cmp.normalize_text(r.get("label", "")) == n for r in records)


def _derived_row(name: str, spec, contract_facts: dict, s: Optional[Fact],
                 onto: Ontology) -> ReconcileRow:
    """파생값 — 계산식으로만 존재하는 필드(§B7). 계산상 일관인지 본다.

    계산은 `derive.evaluate` 가 온톨로지의 식을 **해석해서** 한다. 여기서 끝점을
    골라잡지 않는다 — 그러면 식이 주석이 되고 제약이 코드로 새어든다(§C8 완료기준 1).
    """
    base = next((contract_facts.get(b) for b in derive.referenced_fields(spec.derived)
                 if contract_facts.get(b)), None)
    raws = {k: f.raw for k, f in contract_facts.items() if f.raw}
    calc = derive.evaluate(spec.derived, onto.fields, raws)

    if not calc.ok or s is None:
        note = (f"파생 필드({spec.derived}) — 요약서에 값이 없습니다" if calc.ok
                else f"파생값을 계산하지 못했습니다: {calc.reason}")
        return ReconcileRow(
            field_name=name, value_type=spec.value_type,
            contract_value=base.raw if base else None,
            contract_source=base.source if base else None,
            summary_value=s.raw if s else None,
            summary_source=s.source if s else None,
            verdict="NEEDS_REVIEW", note=note)

    # 비교도 필드의 value_type 이 정한 비교기로 한다(날짜 고정 아님).
    res = cmp.compare(spec.value_type, str(calc.value), s.raw)
    prefix = {"MATCH": "계산상 일관", "VALUE_MISMATCH": "계산상 불일치"}.get(
        res.verdict, "계산 결과 판정 보류")
    detail = "" if res.verdict == "MATCH" else f" — 요약서 대조 {res.note}"
    src = contract_facts.get(calc.basis[0]) if calc.basis else base
    return ReconcileRow(
        field_name=name, value_type=spec.value_type,
        contract_value=src.raw if src else None,
        contract_source=src.source if src else None,
        summary_value=s.raw, summary_source=s.source,
        verdict=res.verdict, note=f"{prefix}: {calc.explain}{detail}")
