"""표면형을 표준 개념으로 묶는 명시적 레지스트리."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .model import Node, normalize_surface, stable_id


@dataclass
class ConceptEntry:
    id: str
    label: str
    type: str = "domain_term"
    surfaces: list[str] = field(default_factory=list)
    source: str = "registry"
    status: str = "active"
    confidence: str = ""
    scope_docs: list[str] = field(default_factory=list)
    props: dict = field(default_factory=dict)

    def node(self) -> Node:
        return Node(self.id, "Concept", self.label, {
            "concept_type": self.type,
            "source": self.source,
            "status": self.status,
            "knowledge_grade": 1
            if self.source == "registry" and self.status == "active" else 2,
            "confidence": self.confidence,
            "scope_docs": self.scope_docs,
            **self.props,
        })


class CanonicalRegistry:
    """자동 의미 병합을 하지 않는다. 이 레지스트리에 적힌 병합만 확정한다."""

    def __init__(self, entries: list[ConceptEntry] | None = None):
        self.entries = entries or []
        self.by_surface: dict[str, list[ConceptEntry]] = {}
        for entry in self.entries:
            for surface in dict.fromkeys([entry.label, *entry.surfaces]):
                key = normalize_surface(surface)
                if key:
                    self.by_surface.setdefault(key, []).append(entry)

    @classmethod
    def load(cls, *, registry_path: str | Path | None = None,
             glossary_path: str | Path | None = None) -> "CanonicalRegistry":
        entries: list[ConceptEntry] = []
        if registry_path and Path(registry_path).is_file():
            blob = json.loads(Path(registry_path).read_text(encoding="utf-8"))
            for row in blob.get("concepts", []):
                label = str(row.get("label") or "").strip()
                if not label:
                    continue
                cid = str(row.get("id") or stable_id("concept", row.get("type", "domain_term"), label))
                if not cid.startswith("concept:"):
                    cid = f"concept:{cid}"
                entries.append(ConceptEntry(
                    id=cid, label=label, type=row.get("type", "domain_term"),
                    surfaces=list(row.get("surfaces") or row.get("aliases") or []),
                    source="registry",
                    status=row.get("status", "active"), confidence=row.get("confidence", ""),
                    scope_docs=list((row.get("scope") or {}).get("docs") or row.get("scope_docs") or []),
                    props={k: v for k, v in row.items() if k not in {
                        "id", "label", "type", "surfaces", "aliases", "status",
                        "confidence", "scope", "scope_docs"
                    }},
                ))
        if glossary_path and Path(glossary_path).is_file():
            blob = json.loads(Path(glossary_path).read_text(encoding="utf-8"))
            for row in blob.get("terms", []):
                if row.get("status") not in (None, "활성", "active"):
                    continue
                label = str(row.get("term") or "").strip()
                if not label:
                    continue
                key = str(row.get("key") or normalize_surface(label))
                entries.append(ConceptEntry(
                    id=stable_id("concept", "glossary", key), label=label,
                    type=row.get("type", "domain_term"),
                    surfaces=list(row.get("surfaces") or [label]), source="glossary",
                    status=row.get("status", "활성"), confidence=row.get("confidence", ""),
                    scope_docs=list((row.get("scope") or {}).get("docs") or []),
                    props={"key": key, "note": row.get("note", "")},
                ))
        return cls(entries)

    def match(self, surface: str, *, doc_id: str = "") -> list[ConceptEntry]:
        rows = [r for r in self.by_surface.get(normalize_surface(surface), [])
                if r.status in ("active", "활성", "approved", "reviewed")]
        if not doc_id:
            return list(rows)
        return [r for r in rows if not r.scope_docs or doc_id in r.scope_docs]
