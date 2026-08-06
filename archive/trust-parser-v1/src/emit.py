"""T7. 출력·검증 — pydantic 검증 후 chunks.json 직렬화."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import chunk as chunking
import parse_stage
import structure
import tag_rules
import validate
from ontology import Ontology
from schema import ChunkDocument


def run(pdf_path: str, onto: Ontology, document_name: Optional[str] = None):
    """PDF → (ChunkDocument, violations, meta). 파이프라인 T1–T5 + T16 을 잇는다."""
    parsed = parse_stage.parse(pdf_path)
    st = structure.build(parsed, onto)
    raw = chunking.build(st, onto)
    chunks, tag_warnings = tag_rules.tag(raw, onto)

    doc = ChunkDocument(
        document=document_name or f"{onto.doc_type} ({Path(pdf_path).stem})",
        schema_version="facet-v1",
        source_pdf=Path(pdf_path).name,
        chunks=chunks)

    violations = validate.run(doc, onto)
    meta = {
        "parser": parsed.parser,
        "born_digital": parsed.born_digital,
        "parse_stats": parsed.stats,
        "parse_warnings": parsed.warnings,
        "structure_warnings": st.warnings,
        "tag_warnings": tag_warnings,
        "parts": {p.role: len(p.elements) for p in st.parts},
        "articles": len(st.all_articles()),
        "chunks": len(chunks),
        "violations": validate.summarize(violations),
    }
    return doc, violations, meta


def write(doc: ChunkDocument, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc.dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
