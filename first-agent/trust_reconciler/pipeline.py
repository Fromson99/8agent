"""P2~P4 — 태깅, 1단계 섹션 대응, 2단계 값 비교.

    P2 tag_document      블록 → 섹션(메인 태그) → 세부 요소(typed value)
    P3 pair_sections     "실제로 동일한 부분인가"
    P4 compare_elements  "실제로 값이 일치하는가"

정규표현식을 쓰지 않는다. 문서 내용의 해석은 전부 LLM 호출이고,
코드는 묶기·후보 축소·구조화된 값 비교만 한다.
"""

from __future__ import annotations

from typing import Optional

from .docmodel import (ROLE_PRIORITY, ROLE_PROVISION, VALUE_BEARING, ElementComparison,
                       ElementValue, ParsedDocument, Provenance, SectionPair,
                       TaggedDocument, TaggedElement, TaggedSection)
from .glossary import Glossary
from .textkit import set_jaccard, truncate
from . import units

# 태깅 시 한 번에 넘길 블록 수. 문서가 길면 나눠 부르고 결과를 이어 붙인다.
TAG_BATCH = 40
# 요소 추출 시 섹션 본문 최대 길이
SECTION_TEXT_LIMIT = 6000
# 1단계 후보로 올릴 최소 공유 용어 수 (태그가 같으면 이 조건 없이 후보가 된다)
MIN_SHARED_TERMS = 1
UNCERTAIN_BELOW = 0.70


# ===========================================================================
# P2 — 태깅
# ===========================================================================

def _schema_index(schema: dict) -> dict[str, dict]:
    return {s["id"]: s for s in schema.get("sections", [])}


def _tag_payload(doc: ParsedDocument, batch, schema: dict, glossary: Glossary) -> dict:
    return {
        "doc_role": doc.doc_role,
        "blocks": [{"block_id": b.block_id, "kind": b.kind,
                    "page": b.provenance.page, "text": truncate(b.content(), 400)}
                   for b in batch],
        "schema": {"sections": [{k: s.get(k) for k in
                                 ("id", "display", "scope", "hints", "confusable_with")}
                                for s in schema.get("sections", [])]},
        "glossary": [{"canonical": t.canonical, "display": t.display,
                      "surfaces": t.surfaces[:8]} for t in glossary.terms.values()],
    }


def _group_sections(doc: ParsedDocument, assignments: dict[str, dict],
                    glossary: Glossary) -> list[TaggedSection]:
    """같은 태그가 붙은 **연속** 블록을 하나의 섹션으로 묶는다.

    연속 조건이 중요하다. 문서 앞뒤에 흩어진 같은 태그를 하나로 합치면
    "제11조의 보수"와 "별지1의 보수율"이 뭉개져 출처를 잃는다. 각각 별개 섹션으로 두고,
    1:N 대응은 P3 가 처리한다.
    """
    sections: list[TaggedSection] = []
    cur: Optional[TaggedSection] = None
    prev_key = object()

    for b in doc.blocks:
        a = assignments.get(b.block_id) or {}
        tag = a.get("tag")
        if not tag:
            cur, prev_key = None, object()
            continue
        role = a.get("role") or "value"
        # 태그가 같아도 역할이 바뀌면 다른 섹션이다.
        # 제2조(관련 조항)와 별지1(실제 값)은 둘 다 trust_amount 지만 성격이 다르다.
        key = (tag, role)
        if key != prev_key:
            cur = TaggedSection(
                section_id=f"{doc.doc_id}_s{len(sections):03d}",
                tag=tag, role=role, title=a.get("title") or "",
                tag_confidence=float(a.get("confidence") or 0.0),
                rationale=a.get("rationale", ""),
                provenance=Provenance(page=b.provenance.page, doc_ref=b.provenance.doc_ref))
            sections.append(cur)
            prev_key = key
        cur.block_ids.append(b.block_id)
        # 확신도는 구간 내 최댓값을 쓴다 (한 블록이라도 분명하면 그 섹션은 분명하다)
        cur.tag_confidence = max(cur.tag_confidence, float(a.get("confidence") or 0.0))

    for s in sections:
        text = "\n".join((doc.block(bid).content() if doc.block(bid) else "")
                         for bid in s.block_ids)
        s.terms = glossary.find_in(text)
    return sections


def _section_text(doc: ParsedDocument, section: TaggedSection) -> str:
    parts = [doc.block(bid).content() for bid in section.block_ids if doc.block(bid)]
    return "\n".join(parts)[:SECTION_TEXT_LIMIT]


def tag_document(doc: ParsedDocument, schema: dict, glossary: Glossary, llm) -> TaggedDocument:
    """블록 → 섹션(메인 태그) → 세부 요소."""
    out = TaggedDocument(doc_id=doc.doc_id, doc_role=doc.doc_role,
                         schema_version=schema.get("version", ""), backend=llm.name)
    assignments: dict[str, dict] = {}

    for i in range(0, len(doc.blocks), TAG_BATCH):
        batch = doc.blocks[i:i + TAG_BATCH]
        res = llm.tag_blocks(_tag_payload(doc, batch, schema, glossary))
        for a in res.get("assignments") or []:
            if a.get("block_id"):
                assignments[a["block_id"]] = a
        for s in res.get("suggestions") or []:
            out.suggestions.append({**s, "doc_role": doc.doc_role})
        applied = glossary.absorb(res.get("glossary_suggestions") or [])
        for a in applied:
            out.suggestions.append({"kind": "glossary", **a})

    out.sections = _group_sections(doc, assignments, glossary)
    if not out.sections:
        out.warnings.append("어떤 블록에도 태그가 붙지 않았습니다 — 스키마와 문서가 맞는지 확인하세요")

    # 섹션별 세부 요소 추출
    index = _schema_index(schema)
    for section in out.sections:
        spec = index.get(section.tag)
        if not spec or not spec.get("elements"):
            continue
        payload = {
            "doc_role": doc.doc_role,
            "tag": section.tag,
            "tag_display": spec.get("display", section.tag),
            "text": _section_text(doc, section),
            "elements": [{k: e.get(k) for k in ("id", "display", "value_type", "key")}
                         for e in spec["elements"]],
            "value_types": schema.get("value_types", {}),
            "glossary": [{"canonical": t.canonical, "display": t.display,
                          "surfaces": t.surfaces[:6]} for t in glossary.terms.values()],
        }
        res = llm.extract_elements(payload)
        by_id = {e["id"]: e for e in spec["elements"]}
        for e in res.get("elements") or []:
            eid = e.get("element_id")
            if eid not in by_id:
                continue
            section.elements.append(TaggedElement(
                element_id=eid,
                display=by_id[eid].get("display", eid),
                value=ElementValue(
                    value_type=e.get("value_type") or by_id[eid].get("value_type", "text"),
                    raw=e.get("raw", ""), data=e.get("data") or {}),
                status=e.get("status", "found"),
                confidence=float(e.get("confidence") or 0.0),
                note=e.get("note", ""),
                provenance=section.provenance))
    return out


# ===========================================================================
# P3 — 1단계: 섹션 대응
# ===========================================================================

def _candidates(c_doc: TaggedDocument, s_doc: TaggedDocument) -> list[dict]:
    """전수 조합 대신 후보만 만든다.

    같은 태그이거나 용어를 공유하는 조합만 올린다.
    섹션이 각각 40개면 전수는 1,600 쌍이다. LLM 에 그걸 다 물을 수는 없다.
    """
    out = []
    for cs in c_doc.sections:
        for ss in s_doc.sections:
            shared = sorted(set(cs.terms) & set(ss.terms))
            same_tag = cs.tag and cs.tag == ss.tag
            if not same_tag and len(shared) < MIN_SHARED_TERMS:
                continue
            out.append({"contract": cs, "statement": ss, "shared": shared,
                        "same_tag": bool(same_tag)})
    return out


def pair_sections(c_doc: TaggedDocument, s_doc: TaggedDocument,
                  schema: dict, glossary: Glossary, llm,
                  verify_all: bool = False) -> list[SectionPair]:
    """→ SectionPair[]

    verify_all=False 면 태그가 같고 확신도가 높은 쌍은 LLM 확인 없이 통과시킨다(비용 절감).
    태그가 다르거나 확신도가 낮은 쌍만 LLM 이 본다.
    """
    index = _schema_index(schema)
    pairs: list[SectionPair] = []
    n = 0

    # --- 1차: 태그별로 묶는다. 같은 태그는 **하나의 쌍**이다. -----------------
    # 섹션 단위로 교차 조합하면 안 된다. 실측에서 겪은 일:
    # 설명서의 "▶ 신탁보수, 비용 및 수수료" 한 섹션이 계약서의 제11조(신탁보수)·
    # 제12조(선취보수)·제16조(중도해지수수료) 각각과 쌍을 이뤄 21쌍이 생겼고,
    # 신탁보수 값이 선취보수·중도해지수수료와 비교되어 가짜 불일치가 3건 났다.
    # 태그별로 묶으면 계약서 여러 조항 ↔ 설명서 한 문단이 자연스럽게 1:N 이 된다.
    c_by_tag: dict[str, list] = {}
    s_by_tag: dict[str, list] = {}
    for sec in c_doc.sections:
        if sec.tag:
            c_by_tag.setdefault(sec.tag, []).append(sec)
    for sec in s_doc.sections:
        if sec.tag:
            s_by_tag.setdefault(sec.tag, []).append(sec)

    for tag in sorted(set(c_by_tag) & set(s_by_tag)):
        cs_list, ss_list = c_by_tag[tag], s_by_tag[tag]
        conf = min(max(x.tag_confidence for x in cs_list),
                   max(x.tag_confidence for x in ss_list))
        shared = sorted({t for x in cs_list for t in x.terms} &
                        {t for x in ss_list for t in x.terms})
        n += 1
        display = index.get(tag, {}).get("display", tag)
        note = "" if len(cs_list) == 1 and len(ss_list) == 1 \
            else f" (계약서 {len(cs_list)}곳 ↔ 설명서 {len(ss_list)}곳, 종합 대사)"
        pairs.append(SectionPair(
            pair_id=f"p{n:03d}", tag=tag,
            contract_sections=[x.section_id for x in cs_list],
            statement_sections=[x.section_id for x in ss_list],
            method="tag", confidence=conf,
            evidence=f"양쪽 모두 '{display}' 로 태깅됨{note}",
            shared_terms=shared,
            flag="ok" if conf >= UNCERTAIN_BELOW else "uncertain"))

    # --- 2차: 한쪽에만 있는 태그끼리 의미 매칭 (태그가 서로 다른 경우) --------
    paired_tags = set(c_by_tag) & set(s_by_tag)
    leftover_c = [x for t, v in c_by_tag.items() if t not in paired_tags for x in v]
    leftover_s = [x for t, v in s_by_tag.items() if t not in paired_tags for x in v]
    need_llm = []
    for cs in leftover_c:
        for ss in leftover_s:
            shared = sorted(set(cs.terms) & set(ss.terms))
            if len(shared) >= MIN_SHARED_TERMS:
                need_llm.append({"contract": cs, "statement": ss, "shared": shared})

    if need_llm:
        payload = {
            "candidates": [{
                "candidate_id": f"c{i:03d}",
                "contract": {"section_id": c["contract"].section_id, "tag": c["contract"].tag,
                             "title": c["contract"].title,
                             "preview": truncate(c["contract"].rationale, 200),
                             "terms": c["shared"]},
                "statement": {"section_id": c["statement"].section_id, "tag": c["statement"].tag,
                              "title": c["statement"].title,
                              "preview": truncate(c["statement"].rationale, 200),
                              "terms": c["shared"]},
                "shared_terms": c["shared"],
            } for i, c in enumerate(need_llm)],
            "glossary": [{"canonical": t.canonical, "display": t.display}
                         for t in glossary.terms.values()],
        }
        res = llm.pair_sections(payload)
        for p in res.get("pairs") or []:
            if not p.get("same"):
                continue
            conf = float(p.get("confidence") or 0.0)
            c_ids = p.get("contract_section_ids") or []
            s_ids = p.get("statement_section_ids") or []
            if not c_ids or not s_ids:
                continue
            n += 1
            tag = next((s.tag for s in c_doc.sections if s.section_id in c_ids), None)
            pairs.append(SectionPair(
                pair_id=f"p{n:03d}", tag=tag,
                contract_sections=c_ids, statement_sections=s_ids,
                method="llm_semantic", confidence=conf,
                evidence=p.get("evidence", ""),
                flag="ok" if conf >= UNCERTAIN_BELOW else "uncertain"))

    # 짝을 못 찾은 섹션도 남긴다 — 완결성(a)과 별개로 "대사 불가"를 보고해야 한다
    paired_c = {sid for p in pairs for sid in p.contract_sections}
    paired_s = {sid for p in pairs for sid in p.statement_sections}
    for sec, side in [(c_doc.sections, "contract"), (s_doc.sections, "statement")]:
        for s in sec:
            done = paired_c if side == "contract" else paired_s
            if s.section_id in done or not s.tag:
                continue
            spec = index.get(s.tag, {})
            if spec.get("scope") in ("contract_only", "statement_only"):
                continue        # 한쪽에만 있는 것이 정상인 항목
            n += 1
            pairs.append(SectionPair(
                pair_id=f"p{n:03d}", tag=s.tag,
                contract_sections=[s.section_id] if side == "contract" else [],
                statement_sections=[s.section_id] if side == "statement" else [],
                method="tag", confidence=0.0,
                evidence=f"{'설명서' if side == 'contract' else '계약서'}에서 대응 섹션을 찾지 못함",
                flag=f"{side}_only"))
    return pairs


# ===========================================================================
# P4 — 2단계: 값 비교
# ===========================================================================

def _merge_elements(doc: TaggedDocument,
                    section_ids: list[str]) -> tuple[dict[str, TaggedElement], dict[str, str]]:
    """1:N 대응일 때 여러 섹션의 요소를 합친다.

    **역할이 확신도보다 우선한다.** 별지1의 "금 100,000,000원정"(value)이
    제2조의 "별지1에 기재된 금액"(provision)을 이긴다. 확신도만 보면 조항 쪽이
    더 또렷하게 쓰여 있어 이기는 일이 생기고, 그러면 값 비교가 성립하지 않는다.
    """
    out: dict[str, TaggedElement] = {}
    origin: dict[str, str] = {}
    for sid in section_ids:
        sec = doc.section(sid)
        if not sec:
            continue
        rank = ROLE_PRIORITY.get(sec.role, 1)
        for e in sec.elements:
            if e.status != "found":
                continue
            cur = out.get(e.element_id)
            cur_rank = ROLE_PRIORITY.get(
                (doc.section(origin[e.element_id]).role if cur else ROLE_PROVISION), 1)
            if cur is None or (rank, e.confidence) > (cur_rank, cur.confidence):
                out[e.element_id] = e
                origin[e.element_id] = sid
    return out, origin


def compare_elements(pairs: list[SectionPair], c_doc: TaggedDocument, s_doc: TaggedDocument,
                     schema: dict, mapping_table: dict, llm) -> list[ElementComparison]:
    index = _schema_index(schema)
    results: list[ElementComparison] = []

    for pair in pairs:
        spec = index.get(pair.tag or "")
        if not spec:
            continue
        display_tag = spec.get("display", pair.tag)

        if not pair.contract_sections or not pair.statement_sections:
            side = "설명서" if not pair.statement_sections else "계약서"
            results.append(ElementComparison(
                pair_id=pair.pair_id, tag=pair.tag or "", display=display_tag,
                verdict="missing_side", method="missing",
                reason=f"{side}에 대응 섹션이 없어 대조할 수 없음 (문서 버전 차이일 수 있음)",
                confidence=0.3, evidence={"pair_evidence": pair.evidence}))
            continue

        c_el, c_origin = _merge_elements(c_doc, pair.contract_sections)
        s_el, s_origin = _merge_elements(s_doc, pair.statement_sections)
        # 관련 조항은 값이 아니라 근거다. 리포트에 함께 실어 담당자가 규정을 확인할 수 있게 한다.
        provisions = [c_doc.section(sid).title or sid for sid in pair.contract_sections
                      if c_doc.section(sid) and c_doc.section(sid).role == ROLE_PROVISION]

        for espec in spec.get("elements", []):
            eid = espec["id"]
            a, b = c_el.get(eid), s_el.get(eid)
            base = ElementComparison(
                pair_id=pair.pair_id, tag=pair.tag or "", element_id=eid,
                display=espec.get("display", eid),
                value_type=espec.get("value_type", "text"),
                is_key=bool(espec.get("key")),
                contract_raw=a.value.raw if a else "",
                statement_raw=b.value.raw if b else "",
                evidence={"contract_section": pair.contract_sections,
                          "statement_section": pair.statement_sections,
                          "pair_method": pair.method, "pair_confidence": pair.confidence,
                          "contract_provisions": provisions,
                          "contract_value_from": c_origin.get(eid),
                          "statement_value_from": s_origin.get(eid)})

            if a is None or b is None:
                # 핵심 요소가 한쪽에만 있으면 보고하고, 부수 요소면 조용히 넘어간다
                if not base.is_key:
                    continue
                side = "설명서" if b is None else "계약서"
                base.verdict = "missing_side"
                base.method = "missing"
                base.reason = f"{side}에서 '{base.display}' 값을 찾지 못함"
                base.confidence = 0.3
                results.append(base)
                continue

            mapping = mapping_table.get(espec.get("mapping_key") or spec.get("mapping_key") or "")
            verdict, reason = units.compare(base.value_type, a.value.data, b.value.data, mapping)
            base.verdict, base.reason = verdict, reason
            base.method = "mapping_table" if (mapping and base.value_type == "enum") \
                else "typed_compare"
            base.confidence = round(min(a.confidence, b.confidence) * max(pair.confidence, 0.5), 2)

            if units.needs_llm(verdict, base.value_type):
                res = llm.compare_values({
                    "tag": pair.tag, "element_id": eid, "display": base.display,
                    "value_type": base.value_type,
                    "contract": {"raw": a.value.raw, "data": a.value.data},
                    "statement": {"raw": b.value.raw, "data": b.value.data},
                    "context": {"contract_section": pair.contract_sections,
                                "statement_section": pair.statement_sections,
                                "mapping_note": f"매핑표 적용 결과 판정 불가" if mapping else "",
                                "code_reason": reason},
                })
                v = res.get("verdict")
                base.verdict = v if v in ("match", "mismatch", "uncertain") else "uncertain"
                base.method = "llm_semantic"
                base.reason = res.get("reason", "") or reason
                base.confidence = round(float(res.get("confidence") or 0.0)
                                        * max(pair.confidence, 0.5), 2)

            # 섹션 대응 자체가 불확실하면 불일치를 확정하지 않는다.
            # 잘못 짝지은 두 섹션을 비교하면 반드시 "불일치"가 나오기 때문이다.
            if pair.flag == "uncertain" and base.verdict == "mismatch":
                base.verdict = "uncertain"
                base.reason = f"{base.reason} / 섹션 대응이 불확실하여 확정하지 않음"

            results.append(base)
    return results
