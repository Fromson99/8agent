"""기각된 ROLE:Concept Assertion shortcut 실험.

운영 LegalClosure는 proof-carrying Assertion id shortcut만 사용한다. 이 형식은
교차 질문 재현율이 충분하지 않았으므로 평가 재현을 위해서만 보존한다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from lawrag.core.domain_graph.model import stable_id
from lawrag.core.rag.assertion_shortcuts import Coordinate, ShortcutHit, ShortcutProof


@dataclass(frozen=True)
class TypedShortcutEntry:
    required_parts: tuple[str, ...]
    targets: tuple[Coordinate, ...]
    proofs: tuple[ShortcutProof, ...]
    corpus_fingerprint: str
    source_trace: str = ""
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            object.__setattr__(self, "id", stable_id(
                "typed-assertion-shortcut", self.required_parts, self.targets,
                self.corpus_fingerprint))

    def as_dict(self) -> dict:
        return asdict(self)


class TypedShortcutIndex:
    def __init__(self, entries):
        self.entries = tuple(entries)
        inverted: dict[str, list[TypedShortcutEntry]] = {}
        for entry in self.entries:
            for part in entry.required_parts:
                inverted.setdefault(part, []).append(entry)
        self.inverted = {part: tuple(rows) for part, rows in inverted.items()}

    def lookup(self, parts, *, cap: int = 8,
               exclude_traces: set[str] | None = None) -> list[ShortcutHit]:
        ordered = tuple(dict.fromkeys(str(part) for part in parts if part))
        present = set(ordered)
        excluded = exclude_traces or set()
        candidates = {
            entry.id: entry
            for part in ordered
            for entry in self.inverted.get(part, ())
        }
        matched = [entry for entry in candidates.values()
                   if entry.source_trace not in excluded
                   and set(entry.required_parts).issubset(present)]
        routes = {entry.targets for entry in matched}
        if len(routes) != 1:
            return []
        matched.sort(key=lambda entry: (-len(entry.required_parts), entry.id))
        if not matched:
            return []
        entry = matched[0]
        return [ShortcutHit(entry.id, target, entry.required_parts, entry.source_trace)
                for target in entry.targets[:max(1, int(cap))]]
