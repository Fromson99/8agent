"""T5 + T15. 규칙 기반 태깅 — **온톨로지 구동**.

role/topic/level/refs 를 채운다. 어떤 값이 허용되는지·topic 을 어떻게 만드는지·
별지 필드가 어느 조에 걸리는지는 전부 온톨로지에서 읽는다.
이 모듈에 도메인 상수를 두지 않는 것이 §C8 완료기준 1이다.

LLM 은 쓰지 않는다(§12 "규칙 기반 우선"). 세부 의미역 보강은 tag_llm.py 가 플래그 뒤에서 한다.
"""

from __future__ import annotations

from typing import Optional

import recognizers as rec
from chunk import RawChunk
from ontology import Ontology
from schema import Chunk, Item, Option, Provenance


def _topic(onto: Ontology, article: Optional[str], title: str, fallback: str) -> str:
    """온톨로지의 파생 공식으로 topic 을 만든다 (properties.topic.formula)."""
    if not article:
        return fallback
    formula = onto.topic_formula()
    return formula.format(article_title=title or article, article=f"제{article}조")


def _chunk_id(c: RawChunk, onto: Ontology, used: set[str]) -> str:
    body_role = onto.default_role()
    if c.part_role == body_role:
        base = f"body-a{int(c.article):02d}" if c.article else f"body-x{c.seq:03d}"
        if c.clause:
            idx = rec.CIRCLED.find(c.clause)
            base += f"-p{idx + 1}" if idx >= 0 else f"-{c.clause}"
    else:
        prefix = "app1" if "1" in c.part_role else "app2"
        raw = c.field_name or (c.heading_path[-1] if c.heading_path else "")
        slug = "".join(ch for ch in raw if ch.isalnum() or "가" <= ch <= "힣")[:16]
        kind = "grid" if c.structure_kind == "checkbox_grid" else "field"
        base = f"{prefix}-{kind}-{slug}" if slug else f"{prefix}-{kind}-{c.seq:03d}"

    cid, n = base, 2
    while cid in used:
        cid = f"{base}-{n}"
        n += 1
    used.add(cid)
    return cid


def tag(chunks: list[RawChunk], onto: Ontology) -> tuple[list[Chunk], list[str]]:
    """RawChunk[] → Chunk[] (+ 경고). 온톨로지 enum 밖의 값은 경고로 남긴다."""
    roles = set(onto.enum("role"))
    levels = set(onto.enum("level"))
    warnings: list[str] = []
    used: set[str] = set()
    out: list[Chunk] = []

    # 별지 필드 → 조 링크. 온톨로지 fields.*.article 이 1차 근거,
    # 문서의 `계약서제N조` 셀이 2차 근거다(§3 "명시적 연결").
    field_article = {name: spec.article for name, spec in onto.fields.items() if spec.article}
    article_titles: dict[str, str] = {}
    for c in chunks:
        if c.article and c.article_title:
            article_titles.setdefault(c.article, c.article_title)

    for c in chunks:
        if c.part_role not in roles:
            warnings.append(f"role '{c.part_role}' 가 온톨로지 classes.role 에 없습니다")
        if c.level not in levels:
            warnings.append(f"level '{c.level}' 가 온톨로지 classes.level 에 없습니다")

        article = c.article
        title = c.article_title
        cross = None

        if c.part_role != onto.default_role():
            # 별지: 문서의 cross-ref 셀 → 없으면 온톨로지 선언
            if c.cross_ref_cell:
                cross = f"계약서{c.cross_ref_cell}"
                article = c.cross_ref_cell.strip("제조")
            elif c.field_name and c.field_name in field_article:
                declared = field_article[c.field_name]
                cross = f"계약서{declared}"
                article = declared.strip("제조")
            if article:
                title = article_titles.get(article, title)

        refs = rec.find_refs(c.text)
        # 온톨로지 properties.refs.range == [조, 별지] 이므로 항 단독 참조는 조로 승격한다.
        # "제1항의 중도해지" 는 같은 조(自條)의 항을 가리킨다 — 정본 body-a15-p3 이 이 경우다.
        if rec.has_bare_clause_ref(c.text) and c.article:
            a = f"제{c.article}조"
            if a not in refs:
                refs.append(a)
        if cross and article:
            a = f"제{article}조"
            if a not in refs:
                refs.append(a)
        # 별지 청크는 자기가 속한 별지를 refs 에 담는다 — 정본이 이렇게 모델링한다
        # (app1-runmethod-checklist refs = ["제5조", "별지1"]). 소속 간선이다.
        if c.part_role != onto.default_role():
            own = next((f"별지{p.appendix_no}" for p in onto.appendix_parts()
                        if p.role == c.part_role and p.appendix_no), None)
            if own and own not in refs:
                refs.append(own)

        topic = _topic(onto, article, title,
                       fallback=(c.heading_path[-1] if c.heading_path else c.part_role))

        out.append(Chunk(
            chunk_id=_chunk_id(c, onto, used),
            role=c.part_role,
            level=c.level,
            article=f"제{article}조" if article else None,
            article_title=title or None,
            clause=c.clause,
            topic=topic,
            heading_path=c.heading_path,
            refs=refs,
            cross_ref_explicit=cross,
            provenance=Provenance(page=c.page, bbox=c.bbox),
            text=c.text,
            items=[Item(**i) for i in c.items] if c.items else None,
            options=[Option(**o) for o in c.options] if c.options else None,
            table_options=c.table_options,
            structure=c.structure_kind,
            value_template=c.value_template,
            char_count=c.size(),
            block_ids=[e.doc_ref for e in c.elements if e.doc_ref],
        ))
    return out, warnings
