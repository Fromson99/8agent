"""Canonical proof-cell basis completion and guarded exchange.

This is an experiment-only selector for ADR-0073.  It never searches the
corpus and never receives gold labels.  The input ground set is the frozen
ADR-0068 evidence pool.  Coordinates are first collapsed to canonical article
roots, exact source spans and typed relation edges are rebuilt from the live
index, and only then may the presentation basis change.

The solver treats proof coverage as a finite join lattice.  A replacement is
allowed only when every cell in the old basis is preserved at an equal or
better quality and at least one cell is gained.  Baseline-core coordinates and
hard companion edges therefore act as unique witnesses unless an equivalent
replacement exists.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import re
from typing import Iterable, Mapping

from lawrag.core.rag import grounded_witness, legal_coordinates, relations
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


PRESENTED_MAX = 20
ADMISSION_MAX = 4
EXCHANGE_MAX = 4
HARD_DEPENDENCY_MAX = 2
SPAN_CHARS = 520

# ``BASED_ON`` and definition/temporal edges are not globally mandatory.  They
# become dependencies only when the candidate has a question-grounded span.
HARD_CLOSURE_KINDS = frozenset({
    "INCORPORATES", "EXCLUDES", "DEEMS", "RECEIVES_FROM",
    "DELEGATES_TO", "VIOLATION_SANCTIONED_BY", "HAS_EXCEPTION",
})
CONDITIONAL_DEPENDENCY_KINDS = frozenset({
    "BASED_ON", "USES_DEFINITION", "EFFECTIVE_FOR", "APPLIES_TO",
    "TRANSITION_FOR",
})

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_SPACE = re.compile(r"\s+")
_STOP = frozenset({
    "관련", "경우", "여부", "질의", "사항", "회사", "당사", "상기",
    "다음", "어떻게", "있는", "하는", "하려고", "그리고", "또는",
})
_ROLE_PATTERNS = {
    "definition": re.compile(r"정의|이란|란\s"),
    "exception": re.compile(r"예외|제외|면제|다만|적용하지|아니한"),
    "condition": re.compile(r"요건|조건|경우|때에는|한정"),
    "duty": re.compile(r"의무|하여야|해야|책임|준수"),
    "prohibition": re.compile(r"금지|하여서는 아니|할 수 없"),
    "delegation": re.compile(r"위탁|수탁|위임|대통령령|정하는 바"),
    "procedure": re.compile(r"신청|보고|통지|제출|교부|등록"),
    "calculation": re.compile(r"산정|계산|비율|가격|금액|괴리율"),
    "sanction": re.compile(r"벌칙|과태료|과징금|정지|취소|시정명령"),
}


@dataclass(frozen=True)
class QueryAtom:
    text: str
    quality: int


@dataclass(frozen=True)
class EdgeReceipt:
    edge_id: str
    kind: str
    direction: str
    other_coordinate: tuple[str, object]
    other_candidate_id: str
    dependency_class: str
    provenance: tuple[str, ...]

    def public(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "kind": self.kind,
            "direction": self.direction,
            "other_coordinate": list(self.other_coordinate),
            "other_candidate_id": self.other_candidate_id,
            "dependency_class": self.dependency_class,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True)
class ProofRecord:
    candidate_id: str
    row: termexplore.TermBranch
    pool_rank: int
    source_sha256: str
    source_chars: int
    span_id: str
    span_start: int
    span_end: int
    span_text: str
    query_cells: tuple[tuple[str, int], ...]
    role_cells: tuple[tuple[str, int], ...]
    relevance: int
    edges: tuple[EdgeReceipt, ...] = ()

    @property
    def coordinate(self) -> tuple[str, object]:
        return self.row.coordinate

    def public(self, *, include_edges: bool = True) -> dict:
        value = {
            "candidate_id": self.candidate_id,
            "coordinate": list(self.coordinate),
            "document": self.row.doc,
            "path": self.row.path,
            "origin": self.row.origin,
            "pool_rank": self.pool_rank,
            "source_sha256": self.source_sha256,
            "source_chars": self.source_chars,
            "span_id": self.span_id,
            "source_span": [self.span_start, self.span_end],
            "span_text": self.span_text,
            "query_cells": [key for key, _quality in self.query_cells],
            "role_cells": [key for key, _quality in self.role_cells],
            "relevance": self.relevance,
            "canonical_source_valid": True,
        }
        if include_edges:
            value["edges"] = [edge.public() for edge in self.edges]
        return value


def _clean(value: object) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def _question_atoms(question: str) -> tuple[QueryAtom, ...]:
    values: dict[str, int] = {}
    for raw in _TOKEN.findall(str(question or "")):
        token = raw.casefold()
        if token in _STOP:
            continue
        values[token] = max(values.get(token, 0), min(12, len(token) + 4))
        normalized = token.replace("위수탁", "위탁")
        if normalized != token:
            values[normalized] = max(values.get(normalized, 0),
                                     min(11, len(normalized) + 4))
        # A short compound backoff remains tied to literal question text.  It
        # is lower-quality than an exact or normalized whole-token match.
        if re.fullmatch(r"[가-힣]{5,}", normalized):
            for size in (4, 3):
                for start in range(0, len(normalized) - size + 1):
                    part = normalized[start:start + size]
                    if part not in _STOP:
                        values[part] = max(values.get(part, 0), size - 1)
    return tuple(QueryAtom(text, quality) for text, quality in sorted(
        values.items(), key=lambda item: (-item[1], item[0])))


def _roles(text: str) -> set[str]:
    return {name for name, pattern in _ROLE_PATTERNS.items()
            if pattern.search(text)}


def _candidate_id(coordinate: tuple[str, object]) -> str:
    digest = hashlib.sha256(
        f"{coordinate[0]}:{coordinate[1]}".encode("utf-8")).hexdigest()
    return f"C-{digest[:16]}"


def _canonical_branch(index: Index, row: termexplore.TermBranch) \
        -> termexplore.TermBranch | None:
    view = index.docs.get(str(row.doc_id or ""))
    if view is None or row.node not in view.by_id:
        return None
    root = legal_coordinates.article_root(view, row.node)
    branch = legal_coordinates.article_branch(
        index, row.doc_id, root, tuple(row.terms or ()),
        origin=row.origin or "proof-basis", reason=row.relation_reason or row.path)
    if branch is None:
        return None
    return replace(
        branch,
        mandatory=bool(row.mandatory),
        mandatory_reason=str(row.mandatory_reason or ""),
        source_doc_id=str(row.source_doc_id or ""),
        source_node=row.source_node,
    )


def canonicalize(index: Index, rows: Iterable[termexplore.TermBranch]) \
        -> tuple[list[termexplore.TermBranch], list[dict]]:
    out: list[termexplore.TermBranch] = []
    errors: list[dict] = []
    seen: set[tuple[str, object]] = set()
    for position, raw in enumerate(rows, 1):
        row = _canonical_branch(index, raw)
        if row is None:
            errors.append({
                "position": position,
                "coordinate": [str(raw.doc_id or ""), raw.node],
                "code": "canonical_coordinate_unresolvable",
            })
            continue
        if row.coordinate in seen:
            continue
        seen.add(row.coordinate)
        out.append(row)
    return out, errors


def _span(source: str, atoms: tuple[QueryAtom, ...]) \
        -> tuple[int, int, str, list[tuple[str, int]]]:
    folded = source.casefold()
    matches: list[tuple[str, int, int]] = []
    for atom in atoms:
        start = folded.find(atom.text)
        if start >= 0:
            matches.append((atom.text, atom.quality, start))
    if matches:
        matches.sort(key=lambda item: (-item[1], item[2], item[0]))
        _text, _quality, anchor = matches[0]
    else:
        anchor = 0
    line_start = source.rfind("\n", 0, anchor) + 1
    line_end = source.find("\n", anchor)
    if line_end < 0:
        line_end = len(source)
    if line_end - line_start > SPAN_CHARS:
        line_start = max(0, anchor - SPAN_CHARS // 3)
        line_end = min(len(source), line_start + SPAN_CHARS)
    if line_end <= line_start:
        line_start, line_end = 0, min(len(source), SPAN_CHARS)
    return line_start, line_end, source[line_start:line_end], [
        (text, quality) for text, quality, _start in matches]


def _record(index: Index, row: termexplore.TermBranch, rank: int,
            atoms: tuple[QueryAtom, ...], question_roles: set[str]) \
        -> ProofRecord | None:
    view = index.docs.get(row.doc_id)
    if view is None or row.node not in view.by_id:
        return None
    source = legal_coordinates.subtree_text(view, row.node, cap=None)
    if not source:
        return None
    start, end, text, matches = _span(source, atoms)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    candidate_id = _candidate_id(row.coordinate)
    span_id = "S-" + hashlib.sha256(
        f"{candidate_id}:{digest}:{start}:{end}".encode("utf-8")).hexdigest()[:20]
    query_cells: dict[str, int] = {}
    for token, quality in matches:
        query_cells[f"query:{token}"] = max(
            query_cells.get(f"query:{token}", 0), quality)
    source_roles = _roles(f"{row.path}\n{source}")
    role_cells = {f"role:{role}": 2 for role in source_roles & question_roles}
    relevance = sum(query_cells.values()) + 4 * len(role_cells)
    return ProofRecord(
        candidate_id=candidate_id,
        row=row,
        pool_rank=rank,
        source_sha256=digest,
        source_chars=len(source),
        span_id=span_id,
        span_start=start,
        span_end=end,
        span_text=text,
        query_cells=tuple(sorted(query_cells.items())),
        role_cells=tuple(sorted(role_cells.items())),
        relevance=relevance,
    )


def _dependency_class(kind: str) -> str:
    if kind in HARD_CLOSURE_KINDS:
        return "hard_closure"
    if kind in CONDITIONAL_DEPENDENCY_KINDS:
        return "conditional_dependency"
    return "optional_navigation"


def build_registry(index: Index, question: str,
                   pool: Iterable[termexplore.TermBranch]) \
        -> tuple[list[ProofRecord], list[dict]]:
    canonical, errors = canonicalize(index, pool)
    atoms = _question_atoms(question)
    question_roles = _roles(question)
    records: list[ProofRecord] = []
    for rank, row in enumerate(canonical, 1):
        record = _record(index, row, rank, atoms, question_roles)
        if record is None:
            errors.append({
                "coordinate": list(row.coordinate),
                "code": "canonical_source_unavailable",
            })
        else:
            records.append(record)
    by_coordinate = {record.coordinate: record for record in records}
    enriched: list[ProofRecord] = []
    for record in records:
        outgoing, incoming = relations.incident(index, *record.coordinate)
        edge_rows: list[EdgeReceipt] = []
        seen_edges: set[str] = set()
        for direction, rows in (("out", outgoing), ("in", incoming)):
            for edge in rows:
                status = str(edge.props.get("status") or "")
                if edge.kind.startswith("MAY_") or status not in {"", "resolved"}:
                    continue
                other = ((edge.dst_doc, edge.dst_node) if direction == "out"
                         else (edge.src_doc, edge.src_node))
                target = by_coordinate.get(other)
                if target is None or target.coordinate == record.coordinate:
                    continue
                edge_id = grounded_witness.stable_edge_id(edge, direction)
                if edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)
                provenance = edge.props.get("provenance") or ()
                if isinstance(provenance, str):
                    provenance = (provenance,)
                edge_rows.append(EdgeReceipt(
                    edge_id=edge_id,
                    kind=edge.kind,
                    direction=direction,
                    other_coordinate=target.coordinate,
                    other_candidate_id=target.candidate_id,
                    dependency_class=_dependency_class(edge.kind),
                    provenance=tuple(str(value) for value in provenance if value),
                ))
        enriched.append(replace(record, edges=tuple(edge_rows)))
    return enriched, errors


def validate_span(index: Index, record: ProofRecord) -> bool:
    view = index.docs.get(record.row.doc_id)
    if view is None or record.row.node not in view.by_id:
        return False
    source = legal_coordinates.subtree_text(view, record.row.node, cap=None)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return (
        digest == record.source_sha256
        and 0 <= record.span_start < record.span_end <= len(source)
        and source[record.span_start:record.span_end] == record.span_text
        and record.span_id == "S-" + hashlib.sha256(
            f"{record.candidate_id}:{digest}:{record.span_start}:{record.span_end}"
            .encode("utf-8")).hexdigest()[:20]
    )


def _edge_to(record: ProofRecord, coordinates: set[tuple[str, object]],
             dependency_class: str) -> tuple[EdgeReceipt, ...]:
    return tuple(edge for edge in record.edges
                 if edge.dependency_class == dependency_class
                 and edge.other_coordinate in coordinates)


def _cells(record: ProofRecord, selected_coordinates: set[tuple[str, object]],
           floor_coordinates: set[tuple[str, object]]) -> dict[str, int]:
    cells = dict(record.query_cells)
    for key, quality in record.role_cells:
        cells[key] = max(cells.get(key, 0), quality)
    if record.coordinate in floor_coordinates:
        cells[f"floor:{record.candidate_id}"] = 4
    for edge in record.edges:
        if edge.other_coordinate not in selected_coordinates:
            continue
        if edge.dependency_class == "hard_closure":
            cells[f"edge:{edge.edge_id}"] = 3
        elif edge.dependency_class == "conditional_dependency" \
                and record.query_cells:
            cells[f"edge:{edge.edge_id}"] = 2
    return cells


def _span_lattice(records: Iterable[ProofRecord],
                  floor_coordinates: set[tuple[str, object]]) -> dict[str, int]:
    values = list(records)
    selected = {record.coordinate for record in values}
    out: dict[str, int] = {}
    for record in values:
        for cell, quality in _cells(record, selected, floor_coordinates).items():
            out[cell] = max(out.get(cell, 0), quality)
    return out


def _dominates(after: Mapping[str, int], before: Mapping[str, int]) -> bool:
    return all(after.get(cell, 0) >= quality
               for cell, quality in before.items())


def _candidate_order(records: list[ProofRecord], selected: list[ProofRecord],
                     floor_coordinates: set[tuple[str, object]]) \
        -> list[tuple[str, ProofRecord]]:
    selected_coordinates = {record.coordinate for record in selected}
    remaining = [record for record in records
                 if record.coordinate not in selected_coordinates]
    hard = [record for record in remaining
            if record.query_cells and _edge_to(
                record, selected_coordinates, "hard_closure")]
    hard.sort(key=lambda record: (-record.relevance, record.pool_rank,
                                  record.candidate_id))
    recovery = [record for record in remaining
                if record.coordinate in floor_coordinates and record not in hard]
    recovery.sort(key=lambda record: (record.pool_rank, -record.relevance,
                                      record.candidate_id))
    conditional = [record for record in remaining
                   if record.query_cells and _edge_to(
                       record, selected_coordinates, "conditional_dependency")
                   and record not in hard and record not in recovery]
    conditional.sort(key=lambda record: (-record.relevance, record.pool_rank,
                                         record.candidate_id))
    direct = [record for record in remaining
              if record.query_cells and record not in hard
              and record not in recovery and record not in conditional]
    direct.sort(key=lambda record: (-record.relevance, record.pool_rank,
                                    record.candidate_id))
    ordered = [*(('hard_closure', record)
                  for record in hard[:HARD_DEPENDENCY_MAX]),
               *(('floor_recovery', record) for record in recovery),
               *(('conditional_dependency', record) for record in conditional),
               *(('direct_span', record) for record in direct)]
    out: list[tuple[str, ProofRecord]] = []
    seen: set[tuple[str, object]] = set()
    for reason, record in ordered:
        if record.coordinate in seen:
            continue
        seen.add(record.coordinate)
        out.append((reason, record))
    return out


def _receipt(reason: str, added: ProofRecord,
             evicted: ProofRecord | None, before: Mapping[str, int],
             after: Mapping[str, int]) -> dict:
    gained = sorted(cell for cell, quality in after.items()
                    if quality > before.get(cell, 0))
    lost = sorted(cell for cell, quality in before.items()
                  if after.get(cell, 0) < quality)
    return {
        "reason": reason,
        "added": added.public(),
        "evicted": evicted.public() if evicted else None,
        "gained_cells": gained,
        "lost_cells": lost,
        "componentwise_non_decreasing": not lost,
        "before_span_cells": len(before),
        "after_span_cells": len(after),
    }


def solve(records: list[ProofRecord], incumbent: list[ProofRecord],
          floor_coordinates: set[tuple[str, object]], *, cap: int,
          allow_exchange: bool) -> tuple[list[ProofRecord], list[dict]]:
    selected = list(incumbent[:max(1, int(cap))])
    receipts: list[dict] = []
    admissions = 0

    # Vacancies are completed first.  This is the add-only control and the
    # common starting point for the exchange arm.
    for reason, candidate in _candidate_order(records, selected, floor_coordinates):
        if admissions >= ADMISSION_MAX or len(selected) >= cap:
            break
        before = _span_lattice(selected, floor_coordinates)
        trial = [*selected, candidate]
        after = _span_lattice(trial, floor_coordinates)
        if not _dominates(after, before) or after == before:
            continue
        selected = trial
        admissions += 1
        receipts.append(_receipt(reason, candidate, None, before, after))

    if not allow_exchange:
        return selected, receipts

    exchanges = 0
    for reason, candidate in _candidate_order(records, selected, floor_coordinates):
        if exchanges >= EXCHANGE_MAX:
            break
        if candidate.coordinate in {record.coordinate for record in selected}:
            continue
        before = _span_lattice(selected, floor_coordinates)
        choices: list[tuple[int, int, str, ProofRecord, dict[str, int]]] = []
        for position, evicted in enumerate(selected):
            # Baseline-core coordinates are unique floor witnesses.  Unknown
            # or invalid records never reach this solver and cannot be evicted.
            if evicted.coordinate in floor_coordinates:
                continue
            trial = [record for record in selected if record is not evicted]
            trial.append(candidate)
            after = _span_lattice(trial, floor_coordinates)
            if not _dominates(after, before) or after == before:
                continue
            choices.append((evicted.relevance, -position,
                            evicted.candidate_id, evicted, after))
        if not choices:
            continue
        _score, _position, _cid, evicted, after = min(choices)
        selected = [record for record in selected if record is not evicted]
        selected.append(candidate)
        exchanges += 1
        receipts.append(_receipt(reason, candidate, evicted, before, after))
    return selected, receipts


def run(index: Index, question: str,
        incumbent: Iterable[termexplore.TermBranch],
        evidence_pool: Iterable[termexplore.TermBranch],
        baseline_core: Iterable[termexplore.TermBranch], *,
        cap: int = PRESENTED_MAX, allow_exchange: bool = True) \
        -> tuple[list[termexplore.TermBranch], dict]:
    raw_incumbent = list(incumbent)
    raw_pool = list(evidence_pool)
    raw_core = list(baseline_core)
    canonical_incumbent, incumbent_errors = canonicalize(index, raw_incumbent)
    canonical_core, core_errors = canonicalize(index, raw_core)
    records, registry_errors = build_registry(index, question, raw_pool)
    by_coordinate = {record.coordinate: record for record in records}
    incumbent_records = [by_coordinate[row.coordinate]
                         for row in canonical_incumbent
                         if row.coordinate in by_coordinate]
    floor_coordinates = {row.coordinate for row in canonical_core
                         if row.coordinate in by_coordinate}
    selected_records, receipts = solve(
        records, incumbent_records, floor_coordinates,
        cap=max(1, int(cap)), allow_exchange=bool(allow_exchange))
    selected = [record.row for record in selected_records]
    selected_coordinates = {record.coordinate for record in selected_records}
    raw_pool_roots, _ = canonicalize(index, raw_pool)
    pool_coordinates = {row.coordinate for row in raw_pool_roots}
    witness_ok = all(validate_span(index, record) for record in selected_records)
    lost_cells = [cell for receipt in receipts
                  for cell in receipt.get("lost_cells") or ()]
    actions = Counter(receipt["reason"] for receipt in receipts)
    return selected, {
        "enabled": True,
        "strategy": ("proof-contribution-basis-exchange" if allow_exchange
                     else "verified-add-only"),
        "ran": True,
        "status": "complete" if not (
            incumbent_errors or core_errors or registry_errors) else "partial",
        "reason": "canonical_proof_lattice_solved",
        "raw_incumbent_count": len(raw_incumbent),
        "canonical_incumbent_count": len(canonical_incumbent),
        "raw_pool_count": len(raw_pool),
        "canonical_pool_count": len(records),
        "raw_core_count": len(raw_core),
        "canonical_core_count": len(floor_coordinates),
        "selected_count": len(selected_records),
        "selected_subset_of_pool": selected_coordinates <= pool_coordinates,
        "canonical_pool_preserved": (
            {record.coordinate for record in records} == pool_coordinates),
        "canonical_source_witnesses_valid": witness_ok,
        "componentwise_non_decreasing": not lost_cells,
        "unique_witness_losses": lost_cells,
        "actions": receipts,
        "action_counts": dict(actions),
        "promoted": [receipt["added"] for receipt in receipts],
        "evicted": [receipt["evicted"] for receipt in receipts
                    if receipt.get("evicted")],
        "selected_receipts": [record.public() for record in selected_records],
        "registry_count": len(records),
        "registry_errors": [*incumbent_errors, *core_errors, *registry_errors],
        "gold_fields_received": False,
        "llm_calls": 0,
    }


__all__ = [
    "ADMISSION_MAX", "EXCHANGE_MAX", "HARD_CLOSURE_KINDS",
    "PRESENTED_MAX", "ProofRecord", "build_registry", "canonicalize",
    "run", "solve", "validate_span",
]
