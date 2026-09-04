"""엄격하게 발행되는 1급 지식: Concept, ConceptRelation, Assertion.

glossary의 ``활성``은 검색 표면형의 상태일 뿐 1급 의미 승인이 아니다. 이 모듈은
``data/domain_graph/canonical.json``에 사람이 명시한 항목만 읽는다. 런타임은 읽기
전용이며 후보를 자동 승격하지 않는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path


ACTIVE = "active"
STATUSES = frozenset({"candidate", "reviewed", ACTIVE, "deprecated", "rejected"})
CONCEPT_TYPES = frozenset({
    "entity", "person_role", "organization_role", "document", "artifact",
    "action", "method", "modality", "condition", "legal_effect", "quantity",
    "norm_function", "domain_term", "legal_operation", "procedure_stage",
    "sanction", "authority", "legal_status", "applicability",
    "temporal_constraint",
})
ASSERTION_ROLES = frozenset({
    "ACTOR", "PREDICATE", "OBJECT", "TARGET", "METHOD", "MODALITY",
    "CONDITION", "EFFECT", "SUBJECT", "FUNCTION", "EXCEPTION",
})
CONCEPT_RELATIONS = frozenset({
    "IS_A", "EQUIVALENT_TO", "REALIZES", "SATISFIES", "OPPOSITE_OF",
})
ROLE_EDGE_KINDS = tuple(sorted(ASSERTION_ROLES))
_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{2,127}$")


def concept_id(value: str) -> str:
    value = str(value or "").strip()
    return value if value.startswith("concept:") else f"concept:{value}"


@dataclass(frozen=True)
class Tier1Concept:
    id: str
    label: str
    type: str
    status: str
    aliases: tuple[str, ...] = ()
    definitions: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    negative_aliases: tuple[str, ...] = ()
    scope_docs: tuple[str, ...] = ()
    version: int = 1
    approved_by: str = ""
    review_state: str = ""
    evidence_type: str = ""

    @property
    def surfaces(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.label, *self.aliases, *self.examples)))


@dataclass(frozen=True)
class Tier1Relation:
    id: str
    type: str
    src: str
    dst: str
    status: str
    evidence: tuple[dict, ...] = ()
    confidence: float = 1.0
    approved_by: str = ""
    review_state: str = ""
    evidence_type: str = ""


@dataclass(frozen=True)
class Tier1Assertion:
    id: str
    status: str
    roles: dict[str, tuple[str, ...]]
    source: dict
    confidence: float = 1.0
    approved_by: str = ""
    note: str = ""
    query_cues: tuple[str, ...] = ()
    version: int = 1
    review_state: str = ""
    evidence_type: str = ""


@dataclass
class Tier1Registry:
    version: int = 1
    concepts: dict[str, Tier1Concept] = field(default_factory=dict)
    relations: list[Tier1Relation] = field(default_factory=list)
    assertions: list[Tier1Assertion] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path, *, strict: bool = True) -> "Tier1Registry":
        path = Path(path)
        if not path.is_file():
            return cls()
        blob = json.loads(path.read_text(encoding="utf-8"))
        reg = cls(version=int(blob.get("schema_version") or 1))
        errors: list[str] = []
        for pos, row in enumerate(blob.get("concepts") or []):
            try:
                item = _concept(row)
                if item.id in reg.concepts:
                    raise ValueError(f"중복 concept id {item.id}")
                reg.concepts[item.id] = item
            except ValueError as exc:
                errors.append(f"concepts[{pos}]: {exc}")
        for pos, row in enumerate(blob.get("relations") or []):
            try:
                reg.relations.append(_relation(row, reg.concepts))
            except ValueError as exc:
                errors.append(f"relations[{pos}]: {exc}")
        for pos, row in enumerate(blob.get("assertions") or []):
            try:
                reg.assertions.append(_assertion(row, reg.concepts))
            except ValueError as exc:
                errors.append(f"assertions[{pos}]: {exc}")
        errors.extend(_is_a_cycles(reg.relations))
        if errors and strict:
            raise ValueError("1급 지식 레지스트리 검증 실패:\n- " + "\n- ".join(errors))
        return reg

    @cached_property
    def active_concepts(self) -> dict[str, Tier1Concept]:
        return {cid: c for cid, c in self.concepts.items() if c.status == ACTIVE}

    @cached_property
    def active_relations(self) -> list[Tier1Relation]:
        active = self.active_concepts
        return [r for r in self.relations
                if r.status == ACTIVE and r.src in active and r.dst in active]

    @cached_property
    def active_assertions(self) -> list[Tier1Assertion]:
        active = self.active_concepts
        return [a for a in self.assertions if a.status == ACTIVE
                and all(cid in active for ids in a.roles.values() for cid in ids)]

    @cached_property
    def active_assertions_by_id(self) -> dict[str, Tier1Assertion]:
        return {assertion.id: assertion for assertion in self.active_assertions}

    @cached_property
    def assertion_concepts(self) -> dict[str, frozenset[str]]:
        return {a.id: frozenset(cid for ids in a.roles.values() for cid in ids)
                for a in self.active_assertions}

    @cached_property
    def concept_assertions(self) -> dict[str, frozenset[str]]:
        found: dict[str, set[str]] = {}
        for aid, cids in self.assertion_concepts.items():
            for cid in cids:
                found.setdefault(cid, set()).add(aid)
        return {cid: frozenset(aids) for cid, aids in found.items()}

    def shared_assertions(self, concept_ids: set[str]) -> int:
        if len(concept_ids) < 2:
            return 0
        groups = [self.concept_assertions.get(cid, frozenset()) for cid in concept_ids]
        return len(set.intersection(*(set(group) for group in groups))) if groups else 0

    def connected_concepts(self, concept_ids: set[str]) -> set[str]:
        """주어진 후보 집합 안에서 같은 active Assertion을 공유하는 Concept."""
        connected: set[str] = set()
        for cid in concept_ids:
            for aid in self.concept_assertions.get(cid, ()):
                peers = self.assertion_concepts.get(aid, frozenset()) & concept_ids
                if len(peers) >= 2:
                    connected.update(peers)
        return connected


def _status(row: dict) -> str:
    value = str(row.get("status") or "candidate")
    if value not in STATUSES:
        raise ValueError(f"허용되지 않은 status {value!r}")
    return value


def _identifier(value: object, what: str) -> str:
    text = str(value or "").strip()
    if not _ID.fullmatch(text):
        raise ValueError(f"잘못된 {what} {text!r}")
    return text


def _strings(value) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(x).strip() for x in (value or []) if str(x).strip()))


def _concept(row: dict) -> Tier1Concept:
    cid = concept_id(_identifier(row.get("id"), "concept id"))
    label = str(row.get("label") or "").strip()
    ctype, status = str(row.get("type") or ""), _status(row)
    if not label:
        raise ValueError(f"{cid}: label 없음")
    if ctype not in CONCEPT_TYPES:
        raise ValueError(f"{cid}: 허용되지 않은 type {ctype!r}")
    approved = str(row.get("approved_by") or "").strip()
    if status == ACTIVE and not approved:
        raise ValueError(f"{cid}: active는 approved_by 필수")
    scope = row.get("scope") or {}
    return Tier1Concept(
        cid, label, ctype, status,
        aliases=_strings(row.get("aliases") or row.get("surfaces")),
        definitions=_strings(row.get("definitions")), examples=_strings(row.get("examples")),
        negative_aliases=_strings(row.get("negative_aliases")),
        scope_docs=_strings(scope.get("docs") or row.get("scope_docs")),
        version=int(row.get("version") or 1), approved_by=approved,
        review_state=str(row.get("review_state") or ""),
        evidence_type=str(row.get("evidence_type") or ""),
    )


def _evidence(rows) -> tuple[dict, ...]:
    out = []
    for row in rows or []:
        if not row.get("doc_id") or row.get("node") is None:
            raise ValueError("evidence는 doc_id·node 필수")
        out.append({"doc_id": str(row["doc_id"]), "node": row["node"],
                    **({"note": row["note"]} if row.get("note") else {})})
    return tuple(out)


def _relation(row: dict, concepts: dict[str, Tier1Concept]) -> Tier1Relation:
    rid = _identifier(row.get("id"), "relation id")
    kind, status = str(row.get("type") or ""), _status(row)
    if kind not in CONCEPT_RELATIONS:
        raise ValueError(f"{rid}: 허용되지 않은 relation {kind!r}")
    src, dst = concept_id(row.get("src")), concept_id(row.get("dst"))
    if src not in concepts or dst not in concepts:
        raise ValueError(f"{rid}: 존재하지 않는 concept endpoint")
    evidence = _evidence(row.get("evidence"))
    approved = str(row.get("approved_by") or "").strip()
    if status == ACTIVE and (not evidence or not approved):
        raise ValueError(f"{rid}: active는 evidence·approved_by 필수")
    return Tier1Relation(
        rid, kind, src, dst, status, evidence,
        float(row.get("confidence", 1.0)), approved,
        str(row.get("review_state") or ""),
        str(row.get("evidence_type") or ""))


def _assertion(row: dict, concepts: dict[str, Tier1Concept]) -> Tier1Assertion:
    aid = _identifier(row.get("id"), "assertion id")
    status = _status(row)
    roles: dict[str, tuple[str, ...]] = {}
    for role, values in (row.get("roles") or {}).items():
        if role not in ASSERTION_ROLES:
            raise ValueError(f"{aid}: 허용되지 않은 role {role!r}")
        ids = tuple(concept_id(x) for x in (values if isinstance(values, list) else [values]))
        if any(cid not in concepts for cid in ids):
            raise ValueError(f"{aid}: {role}에 존재하지 않는 concept")
        if ids:
            roles[role] = ids
    if "PREDICATE" not in roles:
        raise ValueError(f"{aid}: PREDICATE 필수")
    if any(concepts[cid].type != "action" for cid in roles["PREDICATE"]):
        raise ValueError(f"{aid}: PREDICATE는 action concept만 가능")
    source = dict(row.get("source") or {})
    if not source.get("doc_id") or source.get("node") is None:
        raise ValueError(f"{aid}: source.doc_id·node 필수")
    approved = str(row.get("approved_by") or "").strip()
    confidence = float(row.get("confidence", 1.0))
    if not 0 <= confidence <= 1:
        raise ValueError(f"{aid}: confidence는 0..1")
    if status == ACTIVE and not approved:
        raise ValueError(f"{aid}: active는 approved_by 필수")
    return Tier1Assertion(
        aid, status, roles, source, confidence, approved,
        str(row.get("note") or ""), _strings(row.get("query_cues")),
        int(row.get("version") or 1),
        str(row.get("review_state") or ""),
        str(row.get("evidence_type") or ""))


def _is_a_cycles(relations: list[Tier1Relation]) -> list[str]:
    graph: dict[str, set[str]] = {}
    for r in relations:
        if r.status == ACTIVE and r.type == "IS_A":
            graph.setdefault(r.src, set()).add(r.dst)
    errors = []
    visiting, done = set(), set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"IS_A 순환: {node}")
            return
        if node in done:
            return
        visiting.add(node)
        for nxt in graph.get(node, ()):
            visit(nxt)
        visiting.remove(node)
        done.add(node)

    for node in graph:
        visit(node)
    return errors
