"""완결성 검증(검증 a) + 통합 리포트.

완결성은 설명서 "혼자" 보는 검증이고, 정합성(P3·P4)은 두 문서를 대조하는 검증이다.
성격이 다르므로 따로 계산하고 리포트에서만 합친다.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .docmodel import (CompletenessResult, ElementComparison, Finding, ParsedDocument,
                       Report, SectionPair, TaggedDocument, to_jsonable)
from .textkit import truncate

VERSION_GAP_DAYS = 365


# ===========================================================================
# 완결성 (검증 a)
# ===========================================================================

def _required(rule, product_type: Optional[str]) -> tuple[bool, str]:
    if rule in (None, "always"):
        return True, "상시 필수"
    if rule == "never":
        return False, "필수 항목이 아님"
    if isinstance(rule, dict):
        pt = product_type or "일반"
        if "product_type_in" in rule:
            allow = rule["product_type_in"]
            if pt in allow:
                return True, f"상품유형 '{pt}' 이 필수 조건 {allow} 에 해당"
            return False, f"상품유형 '{pt}' 은 필수 조건 {allow} 에 없음 — 누락이 정상"
        if "product_type_not_in" in rule:
            deny = rule["product_type_not_in"]
            if pt in deny:
                return False, f"상품유형 '{pt}' 은 제외 대상 {deny} — 해당없음"
            return True, f"상품유형 '{pt}' 은 제외 대상 {deny} 에 없음"
    return True, "규칙 해석 불가 — 보수적으로 필수 처리"


def check_completeness(s_doc: TaggedDocument, schema: dict,
                       product_type: Optional[str]) -> list[CompletenessResult]:
    present = s_doc.tags()
    out: list[CompletenessResult] = []
    for spec in schema.get("sections", []):
        if spec.get("scope") == "contract_only":
            continue
        tag = spec["id"]
        required, why = _required(spec.get("required_in_statement"), product_type)
        has = tag in present
        verdict = "not_applicable" if not required else ("ok" if has else "missing")
        loc = "-"
        if has:
            sec = s_doc.by_tag(tag)[0]
            loc = f"{sec.title or tag} ({sec.provenance.label()})"
        out.append(CompletenessResult(
            tag=tag, display=spec.get("display", tag), present=has, required=required,
            verdict=verdict, location=loc,
            reason=why if verdict != "missing" else f"{why} — 설명서에서 찾지 못함"))
    return out


# ===========================================================================
# 리포트
# ===========================================================================

def _days_between(a: str, b: str) -> Optional[int]:
    try:
        ya, ma, da = (int(x) for x in a.split("-"))
        yb, mb, db = (int(x) for x in b.split("-"))
        return abs((date(ya, ma, da) - date(yb, mb, db)).days)
    except Exception:
        return None


def _severity(comp: ElementComparison) -> str:
    if comp.verdict == "mismatch":
        return "high" if comp.is_key else "med"
    if comp.verdict == "missing_side":
        return "med" if comp.is_key else "low"
    return "med" if comp.is_key else "low"


def build(c_parsed: ParsedDocument, s_parsed: ParsedDocument,
          c_tagged: TaggedDocument, s_tagged: TaggedDocument,
          pairs: list[SectionPair], comparisons: list[ElementComparison],
          completeness: list[CompletenessResult], schema: dict,
          authority: str = "contract", backend: str = "",
          glossary_pending: Optional[list] = None) -> Report:
    warnings: list[str] = []

    cv, sv = c_parsed.meta.version_date, s_parsed.meta.version_date
    if cv and sv:
        gap = _days_between(cv, sv)
        if gap is not None and gap >= VERSION_GAP_DAYS:
            warnings.append(f"문서 기준일 차이 {gap}일 — 계약서 {cv} vs 설명서 {sv}. "
                            f"'설명서에 없는 항목'이 서식 버전 차이일 수 있으니 확인 필요")
    else:
        miss = [n for n, v in (("계약서", cv), ("설명서", sv)) if not v]
        warnings.append(f"기준일을 확인하지 못한 문서: {', '.join(miss)} — 버전 정합성 미검증")

    if c_parsed.meta.issuer and s_parsed.meta.issuer and \
            c_parsed.meta.issuer != s_parsed.meta.issuer:
        warnings.append(f"발행사가 다름 — 계약서 '{c_parsed.meta.issuer}' vs "
                        f"설명서 '{s_parsed.meta.issuer}'. 동일 상품 쌍인지 확인 필요")
    if c_parsed.meta.product_type != s_parsed.meta.product_type:
        warnings.append(f"상품유형 추정이 다름 — 계약서 '{c_parsed.meta.product_type}' vs "
                        f"설명서 '{s_parsed.meta.product_type}'. 조건부 필수 판정에 영향")

    for label, doc in (("계약서", c_parsed), ("설명서", s_parsed)):
        for w in doc.warnings:
            warnings.append(f"[{label} 파싱] {w}")
    for label, doc in (("계약서", c_tagged), ("설명서", s_tagged)):
        for w in doc.warnings:
            warnings.append(f"[{label} 태깅] {w}")

    findings: list[Finding] = []
    tag_display = {s["id"]: s.get("display", s["id"]) for s in schema.get("sections", [])}

    for c in comparisons:
        if c.verdict == "match":
            continue
        findings.append(Finding(
            type=c.verdict if c.verdict != "missing_side" else "unpaired",
            tag=c.tag, display=f"{tag_display.get(c.tag, c.tag)} · {c.display}",
            severity=_severity(c),
            detail={"pair_id": c.pair_id, "element_id": c.element_id,
                    "contract_value": c.contract_raw, "statement_value": c.statement_raw,
                    "method": c.method, "reason": c.reason, "confidence": c.confidence,
                    "is_key": c.is_key}))

    for r in completeness:
        if r.verdict != "missing":
            continue
        findings.append(Finding(type="missing", tag=r.tag, display=r.display,
                                severity="high", detail={"reason": r.reason}))

    for p in pairs:
        if p.flag == "uncertain":
            findings.append(Finding(
                type="uncertain", tag=p.tag or "", display=tag_display.get(p.tag, p.tag or "?"),
                severity="low",
                detail={"pair_id": p.pair_id, "reason": "섹션 대응이 불확실",
                        "evidence": p.evidence, "confidence": p.confidence}))

    suggestions = list(c_tagged.suggestions) + list(s_tagged.suggestions)
    for s in suggestions:
        if s.get("kind") == "glossary":
            continue
        findings.append(Finding(
            type="suggestion", tag=s.get("proposed_id", ""),
            display=s.get("display", s.get("proposed_id", "")), severity="low",
            detail={"why": s.get("why", ""), "doc_role": s.get("doc_role", "")}))

    order = {"high": 0, "med": 1, "low": 2}
    findings.sort(key=lambda f: (order.get(f.severity, 3), f.type, f.tag))

    summary = {
        "sections_contract": len(c_tagged.sections),
        "sections_statement": len(s_tagged.sections),
        "pairs": sum(1 for p in pairs if p.contract_sections and p.statement_sections),
        "unpaired": sum(1 for p in pairs if not (p.contract_sections and p.statement_sections)),
        "elements_compared": len(comparisons),
        "match": sum(1 for c in comparisons if c.verdict == "match"),
        "mismatch": sum(1 for c in comparisons if c.verdict == "mismatch"),
        "uncertain": sum(1 for c in comparisons if c.verdict == "uncertain"),
        "required": sum(1 for r in completeness if r.required),
        "completeness_ok": sum(1 for r in completeness if r.verdict == "ok"),
        "missing": sum(1 for r in completeness if r.verdict == "missing"),
        "not_applicable": sum(1 for r in completeness if r.verdict == "not_applicable"),
        "high_severity": sum(1 for f in findings if f.severity == "high"),
        "schema_suggestions": sum(1 for f in findings if f.type == "suggestion"),
    }

    return Report(
        summary=summary, warnings=warnings, findings=findings, authority=authority,
        documents={
            "contract": to_jsonable(c_parsed.meta) | {"parser": c_parsed.parser,
                                                      "blocks": len(c_parsed.blocks)},
            "statement": to_jsonable(s_parsed.meta) | {"parser": s_parsed.parser,
                                                       "blocks": len(s_parsed.blocks)},
        },
        backend=backend, schema_version=schema.get("version", ""),
        pairs=pairs, comparisons=comparisons, completeness=completeness,
        suggestions=suggestions + [{"kind": "glossary_pending", **g}
                                   for g in (glossary_pending or [])])


# ===========================================================================
# 마크다운
# ===========================================================================

_SEV = {"high": "🔴", "med": "🟠", "low": "🟡"}
_V = {"match": "✅", "mismatch": "❌", "uncertain": "❓", "missing_side": "➖"}


def to_markdown(rep: Report) -> str:
    s = rep.summary
    c, st = rep.documents["contract"], rep.documents["statement"]
    o: list[str] = []
    o.append("# 신탁계약서 ↔ 핵심상품설명서 대사 리포트\n")
    o.append(f"- **정답 문서**: {'신탁계약서' if rep.authority == 'contract' else rep.authority}")
    o.append(f"- **계약서**: {c.get('title') or '-'} / {c.get('issuer') or '발행사 미상'} "
             f"/ 기준일 {c.get('version_date') or '미상'} / {c.get('product_type') or '-'}"
             f"  ·  파서 `{c.get('parser')}`")
    o.append(f"- **설명서**: {st.get('title') or '-'} / {st.get('issuer') or '발행사 미상'} "
             f"/ 기준일 {st.get('version_date') or '미상'} / {st.get('product_type') or '-'}"
             f"  ·  파서 `{st.get('parser')}`")
    o.append(f"- **LLM 백엔드**: `{rep.backend}`  ·  태그 스키마 v{rep.schema_version}\n")

    if rep.warnings:
        o.append("## ⚠️ 경고\n")
        o += [f"- {w}" for w in rep.warnings]
        o.append("")

    o.append("## 요약\n")
    o.append("| 구분 | 지표 | 값 |")
    o.append("|---|---|---|")
    o.append(f"| 파싱 | 섹션 (계약서 / 설명서) | {s['sections_contract']} / {s['sections_statement']} |")
    o.append(f"| 1단계 | 대응된 섹션 쌍 | {s['pairs']} |")
    o.append(f"| 1단계 | 짝 없는 섹션 | {s['unpaired']} |")
    o.append(f"| 2단계 | 비교한 요소 | {s['elements_compared']} |")
    o.append(f"| 2단계 | ✅ 일치 | {s['match']} |")
    o.append(f"| 2단계 | ❌ 불일치 | {s['mismatch']} |")
    o.append(f"| 2단계 | ❓ 불확실 | {s['uncertain']} |")
    o.append(f"| 완결성 | 필수 / 충족 / 누락 / 해당없음 | "
             f"{s['required']} / {s['completeness_ok']} / {s['missing']} / {s['not_applicable']} |")
    o.append(f"| 전체 | 🔴 high | {s['high_severity']} |")
    o.append(f"| 전체 | 스키마 추가 제안 | {s['schema_suggestions']} |\n")

    acts = [f for f in rep.findings if f.type != "suggestion"]
    o.append("## 조치 필요 항목\n")
    if not acts:
        o.append("없음 — 대사 결과 이상 없습니다.\n")
    for f in acts:
        d = f.detail
        o.append(f"### {_SEV.get(f.severity, '•')} [{f.type}] {f.display} (`{f.tag}`)\n")
        if f.type in ("mismatch", "uncertain") and d.get("contract_value") is not None:
            o.append(f"- 계약서: `{truncate(d.get('contract_value'), 200)}`")
            o.append(f"- 설명서: `{truncate(d.get('statement_value'), 200)}`")
            o.append(f"- 판정근거: {d.get('reason')} "
                     f"(method=`{d.get('method')}`, confidence={d.get('confidence')})")
        else:
            o.append(f"- 사유: {d.get('reason') or d.get('evidence') or '-'}")
        o.append("")

    sug = [f for f in rep.findings if f.type == "suggestion"]
    if sug:
        o.append("## 스키마 추가 제안 (선언에 없지만 문서에 있던 것)\n")
        o.append("| 제안 id | 내용 | 발견 문서 | 이유 |")
        o.append("|---|---|---|---|")
        for f in sug:
            o.append(f"| `{f.tag}` | {f.display} | {f.detail.get('doc_role','-')} "
                     f"| {truncate(f.detail.get('why'), 70)} |")
        o.append("")

    o.append("## 2단계 상세 — 요소별 값 비교\n")
    o.append("| 태그 | 요소 | 판정 | 계약서 | 설명서 | 방법 | 확신도 |")
    o.append("|---|---|---|---|---|---|---|")
    for cmp_ in rep.comparisons:
        o.append(f"| {cmp_.tag} | {cmp_.display}{' ★' if cmp_.is_key else ''} "
                 f"| {_V.get(cmp_.verdict, '')} {cmp_.verdict} "
                 f"| {_cell(cmp_.contract_raw)} | {_cell(cmp_.statement_raw)} "
                 f"| `{cmp_.method}` | {cmp_.confidence} |")
    o.append("\n★ = 태그 스키마에서 key=true 로 선언된 핵심 요소\n")

    o.append("## 완결성 상세 (검증 a)\n")
    o.append("| 필수 항목 | 필수 | 존재 | 판정 | 위치/사유 |")
    o.append("|---|---|---|---|---|")
    for r in rep.completeness:
        mark = {"ok": "✅", "missing": "❌", "not_applicable": "➖"}.get(r.verdict, "")
        o.append(f"| {r.display} | {'필수' if r.required else '해당없음'} "
                 f"| {'O' if r.present else 'X'} | {mark} {r.verdict} "
                 f"| {_cell(r.location if r.verdict == 'ok' else r.reason, 60)} |")
    o.append("")
    o.append("> AI 1차 스크리닝 결과입니다. ❌/❓ 항목은 담당자 최종 확인이 필요합니다.")
    return "\n".join(o)


def _cell(text: str, limit: int = 80) -> str:
    t = (text or "").replace("|", "\\|").replace("\n", " ").strip()
    return truncate(t, limit) if t else "-"
