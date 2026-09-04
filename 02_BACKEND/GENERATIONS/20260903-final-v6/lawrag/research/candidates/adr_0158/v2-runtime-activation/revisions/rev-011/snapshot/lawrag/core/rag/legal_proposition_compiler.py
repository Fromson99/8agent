"""Fail-closed legal proposition and factual applicability compiler.

This module is intentionally independent from retrieval, answer synthesis,
the API, and MAIN.  It converts an already selected evidence menu into a
machine-checkable legal-review intermediate representation:

    issue -> exact question facts -> exact-source rule atoms
          -> applicability bindings -> coverage/search plan

The compiler never creates a legal conclusion.  A successful compilation is
only ``READY_FOR_ASSESSMENT``.  Free-form legal propositions are not accepted:
the proposition is the exact source quote, while semantic structure is stored
as typed slots whose values must also be exact substrings of that quote.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from lawrag.core.domain_graph import requirements
from lawrag.core.legal_graph.behavior import (
    RELATION_AXIOMS,
    RELATION_BEHAVIOR_POLICIES,
    EvidenceFact,
    assess_relation_behavior,
)
from lawrag.core.legal_graph.model import RelationPredicate
from lawrag.core.rag.answer import Section


SCHEMA_VERSION = "legal-proposition-applicability-v1"
PRODUCT_MODEL = "claude-haiku-4-5-20251001"
ISSUE_CAP = 4
GLOBAL_RULE_CAP = 12
QUOTE_CHARS_MAX = 1800
QUESTION_SPAN_CHARS_MAX = 600


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class LegalRole(StrEnum):
    GOVERNING_RULE = "GOVERNING_RULE"
    ACTOR_SCOPE = "ACTOR_SCOPE"
    DEFINITION = "DEFINITION"
    CONDITION = "CONDITION"
    EXCEPTION = "EXCEPTION"
    TEMPORAL = "TEMPORAL"
    NUMERIC = "NUMERIC"
    PROCEDURE = "PROCEDURE"
    LEGAL_EFFECT = "LEGAL_EFFECT"
    SANCTION = "SANCTION"
    AUTHORITY = "AUTHORITY"
    COMPANION = "COMPANION"


class FactKind(StrEnum):
    ACTOR = "ACTOR"
    ACTION = "ACTION"
    OBJECT = "OBJECT"
    CONDITION = "CONDITION"
    TEMPORAL = "TEMPORAL"
    NUMERIC = "NUMERIC"
    SCOPE = "SCOPE"
    OTHER = "OTHER"


class SlotKind(StrEnum):
    ACTOR = "ACTOR"
    ACTION = "ACTION"
    OBJECT = "OBJECT"
    CONDITION = "CONDITION"
    EXCEPTION = "EXCEPTION"
    TEMPORAL = "TEMPORAL"
    NUMERIC = "NUMERIC"
    SCOPE = "SCOPE"
    PROCEDURE = "PROCEDURE"
    EFFECT = "EFFECT"
    AUTHORITY = "AUTHORITY"


class ApplicabilityState(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CompilerStatus(StrEnum):
    BLOCKED_MISSING_COVERAGE = "BLOCKED_MISSING_COVERAGE"
    BLOCKED_UNRESOLVED_FACTS = "BLOCKED_UNRESOLVED_FACTS"
    READY_FOR_ASSESSMENT = "READY_FOR_ASSESSMENT"


class CoverageState(StrEnum):
    SATISFIED = "SATISFIED"
    MISSING = "MISSING"


class SearchRoute(StrEnum):
    RELATION = "RELATION"
    DOCUMENT_SEARCH = "DOCUMENT_SEARCH"
    GLOBAL_SEARCH = "GLOBAL_SEARCH"
    STRUCTURE_MOVE = "STRUCTURE_MOVE"


CORE_ROLES = (LegalRole.GOVERNING_RULE, LegalRole.LEGAL_EFFECT)
ROLE_QUOTAS: Mapping[LegalRole, int] = {
    LegalRole.GOVERNING_RULE: 2,
    LegalRole.ACTOR_SCOPE: 1,
    LegalRole.DEFINITION: 1,
    LegalRole.CONDITION: 2,
    LegalRole.EXCEPTION: 2,
    LegalRole.TEMPORAL: 1,
    LegalRole.NUMERIC: 1,
    LegalRole.PROCEDURE: 1,
    LegalRole.LEGAL_EFFECT: 1,
    LegalRole.SANCTION: 1,
    LegalRole.AUTHORITY: 1,
    LegalRole.COMPANION: 1,
}

_REQUIREMENT_ROLE = {
    "CONDITION": LegalRole.CONDITION,
    "EXCEPTION": LegalRole.EXCEPTION,
    "TIME": LegalRole.TEMPORAL,
    "QUANTITY": LegalRole.NUMERIC,
    "METHOD": LegalRole.PROCEDURE,
    "EFFECT": LegalRole.LEGAL_EFFECT,
}
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,95}$")


COMPILER_SYSTEM = """너는 최종 법률답변을 작성하지 않는 법률명제·사실포섭 compiler다.
질문과 서버가 검증한 evidence 메뉴만 사용한다.

1. issue.question_span과 fact.question_span은 질문의 연속 exact span만 복사한다.
2. rule은 닫힌 evidence_id와 issue_id만 사용한다. source_quote는 evidence text의 연속
   exact quote이고 proposition을 새로 쓰지 않는다.
3. slots의 모든 값은 source_quote 안의 연속 exact span이다. actor/action/object/condition/
   exception/temporal/numeric/scope/procedure/effect/authority만 사용한다.
4. issue마다 GOVERNING_RULE과 LEGAL_EFFECT를 요구하고 질문에 필요한 정의·조건·예외·시점·
   수치·절차 역할만 더 요구한다. rule은 보통 전체 4~12개다.
5. applicability는 rule과 질문 fact의 관계를 제안만 한다. 검증되지 않은 제안은 코드가
   UNRESOLVED로 낮춘다. 법률 결론이나 새로운 사실을 만들지 않는다.
6. 질문에 명시된 시장과 충돌하는 다른 시장 rule을 선택하지 않는다."""


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    evidence_id: str
    doc_id: str
    node: int | None
    document: str
    path: str
    text: str
    scope_id: str = ""
    verified: bool = True

    def __post_init__(self) -> None:
        if not _valid_id(self.evidence_id):
            raise ValueError(f"invalid evidence_id: {self.evidence_id!r}")
        if not self.doc_id or not self.text:
            raise ValueError("evidence requires doc_id and text")

    def public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CompilationResult:
    status: CompilerStatus
    issues: tuple[dict[str, Any], ...]
    facts: tuple[dict[str, Any], ...]
    rules: tuple[dict[str, Any], ...]
    applicability: tuple[dict[str, Any], ...]
    coverage: tuple[dict[str, Any], ...]
    search_plan: tuple[dict[str, Any], ...]
    clarification_requests: tuple[dict[str, Any], ...]
    relation_behaviors: tuple[dict[str, Any], ...]
    validation_errors: tuple[str, ...]
    diagnostics: Mapping[str, Any]
    direct_legal_conclusion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status.value,
            "issues": list(self.issues),
            "facts": list(self.facts),
            "rules": list(self.rules),
            "applicability": list(self.applicability),
            "coverage": list(self.coverage),
            "search_plan": list(self.search_plan),
            "clarification_requests": list(self.clarification_requests),
            "relation_behaviors": list(self.relation_behaviors),
            "validation_errors": list(self.validation_errors),
            "diagnostics": dict(self.diagnostics),
            "direct_legal_conclusion_allowed": False,
        }


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value.strip()))


def _scope_id(document: str, doc_id: str) -> str:
    name = str(document or "")
    for surface, scope in (
        ("코스닥시장", "MARKET:KOSDAQ"),
        ("유가증권시장", "MARKET:KOSPI"),
        ("코넥스시장", "MARKET:KONEX"),
    ):
        if surface in name:
            return scope
    return f"INSTRUMENT:{doc_id}"


def _explicit_market_scopes(question: str) -> frozenset[str]:
    scopes: set[str] = set()
    if "코스닥" in question:
        scopes.add("MARKET:KOSDAQ")
    if "유가증권시장" in question or "코스피" in question:
        scopes.add("MARKET:KOSPI")
    if "코넥스" in question:
        scopes.add("MARKET:KONEX")
    return frozenset(scopes)


def evidence_from_sections(sections: Sequence[Section]) -> tuple[EvidenceSpan, ...]:
    """Build stable closed evidence IDs without modifying ``Section`` objects."""

    rows: list[EvidenceSpan] = []
    used: set[str] = set()
    for section in sections:
        identity = f"{section.doc_id}:{section.node}:{section.block}:{section.n}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        evidence_id = f"EV-{digest}"
        if evidence_id in used:
            raise ValueError(f"duplicate section evidence identity: {identity}")
        used.add(evidence_id)
        meta = dict(section.legal_meta or {})
        verified = not bool(meta.get("verification_error"))
        rows.append(EvidenceSpan(
            evidence_id=evidence_id,
            doc_id=str(section.doc_id),
            node=section.node,
            document=str(section.doc),
            path=str(section.path),
            text=str(section.text or ""),
            scope_id=str(meta.get("scope_id") or _scope_id(section.doc, section.doc_id)),
            verified=verified,
        ))
    return tuple(rows)


def compiler_schema(
    evidence_ids: Iterable[str],
    relation_coverage_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """Return the provider-compatible closed-menu structured-output schema."""

    evidence_menu = list(dict.fromkeys(str(value) for value in evidence_ids))
    coverage_menu = list(dict.fromkeys(str(value) for value in relation_coverage_keys))
    rule_properties: dict[str, Any] = {
        "rule_id": {"type": "string"},
        "issue_id": {"type": "string"},
        "role": {"type": "string", "enum": [role.value for role in LegalRole]},
        "evidence_id": {"type": "string", "enum": evidence_menu},
        "source_quote": {"type": "string"},
        "slots": {
            "type": "object",
            "properties": {
                kind.value: {
                    "type": "array",
                    "items": {"type": "string"},
                }
                for kind in SlotKind
            },
            "additionalProperties": False,
        },
    }
    rule_required = [
        "rule_id", "issue_id", "role", "evidence_id", "source_quote", "slots",
    ]
    # Anthropic rejects ``enum: []``.  When no relation predicate was requested,
    # omit the field entirely under additionalProperties:false instead of
    # inventing a fake sentinel ID.
    if coverage_menu:
        rule_properties["relation_coverage_keys"] = {
            "type": "array",
            "items": {"type": "string", "enum": coverage_menu},
        }
        rule_required.append("relation_coverage_keys")
    return {
        "type": "object",
        "properties": {
            "issues": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string"},
                    "question_span": {"type": "string"},
                    "required_roles": {"type": "array", "items": {
                        "type": "string", "enum": [role.value for role in LegalRole],
                    }},
                    "facts": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "fact_id": {"type": "string"},
                            "kind": {"type": "string", "enum": [kind.value for kind in FactKind]},
                            "question_span": {"type": "string"},
                        },
                        "required": ["fact_id", "kind", "question_span"],
                        "additionalProperties": False,
                    }},
                },
                "required": ["issue_id", "question_span", "required_roles", "facts"],
                "additionalProperties": False,
            }},
            "rules": {"type": "array", "items": {
                "type": "object",
                "properties": rule_properties,
                "required": rule_required,
                "additionalProperties": False,
            }},
            "applicability": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "binding_id": {"type": "string"},
                    "issue_id": {"type": "string"},
                    "rule_id": {"type": "string"},
                    "fact_id": {"type": "string"},
                    "state": {"type": "string", "enum": [state.value for state in ApplicabilityState]},
                },
                "required": ["binding_id", "issue_id", "rule_id", "fact_id", "state"],
                "additionalProperties": False,
            }},
        },
        "required": ["issues", "rules", "applicability"],
        "additionalProperties": False,
    }


def _relation_contract(
    predicates: Iterable[RelationPredicate | str],
) -> tuple[tuple[RelationPredicate, ...], frozenset[str]]:
    canonical = tuple(dict.fromkeys(RelationPredicate(value) for value in predicates))
    keys = frozenset(
        f"relation:{predicate.value}:{coverage_key}"
        for predicate in canonical
        for coverage_key in RELATION_BEHAVIOR_POLICIES[predicate].required_coverage
    )
    return canonical, keys


def _requested_roles(question: str) -> tuple[LegalRole, ...]:
    roles = list(CORE_ROLES)
    for kind in requirements.requested_kinds(question):
        role = _REQUIREMENT_ROLE[kind]
        if role not in roles:
            roles.append(role)
    return tuple(roles)


def _sanitize_issues(
    question: str,
    raw: Mapping[str, Any],
    errors: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    issue_ids: set[str] = set()
    fact_ids: set[str] = set()
    inferred = _requested_roles(question)
    for index, value in enumerate(raw.get("issues") or (), 1):
        if not isinstance(value, Mapping):
            errors.append(f"issue_not_object:{index}")
            continue
        issue_id = str(value.get("issue_id") or "").strip()
        span = str(value.get("question_span") or "").strip()
        if not _valid_id(issue_id) or issue_id in issue_ids:
            errors.append(f"invalid_or_duplicate_issue_id:{issue_id}")
            continue
        if not span or span not in question:
            errors.append(f"question_span_not_exact:{issue_id}")
            continue
        requested: list[LegalRole] = list(inferred)
        for role_value in value.get("required_roles") or ():
            try:
                role = LegalRole(str(role_value))
            except ValueError:
                errors.append(f"invalid_required_role:{issue_id}:{role_value}")
                continue
            if role not in requested:
                requested.append(role)
        issue_ids.add(issue_id)
        issue_fact_ids: list[str] = []
        for fact_value in value.get("facts") or ():
            if not isinstance(fact_value, Mapping):
                errors.append(f"fact_not_object:{issue_id}")
                continue
            fact_id = str(fact_value.get("fact_id") or "").strip()
            fact_span = str(fact_value.get("question_span") or "").strip()
            try:
                fact_kind = FactKind(str(fact_value.get("kind") or ""))
            except ValueError:
                errors.append(f"invalid_fact_kind:{fact_id}")
                continue
            if not _valid_id(fact_id) or fact_id in fact_ids:
                errors.append(f"invalid_or_duplicate_fact_id:{fact_id}")
                continue
            if not fact_span or fact_span not in question:
                errors.append(f"fact_span_not_exact:{fact_id}")
                continue
            fact_ids.add(fact_id)
            issue_fact_ids.append(fact_id)
            facts.append({
                "fact_id": fact_id,
                "issue_id": issue_id,
                "kind": fact_kind.value,
                "question_span": fact_span[:QUESTION_SPAN_CHARS_MAX],
            })
        issues.append({
            "issue_id": issue_id,
            "question_span": span[:QUESTION_SPAN_CHARS_MAX],
            "required_roles": [role.value for role in requested],
            "fact_ids": issue_fact_ids,
        })
        if len(issues) >= ISSUE_CAP:
            break
    if not issues:
        fallback_span = question.strip()[:QUESTION_SPAN_CHARS_MAX] or "질문"
        issues.append({
            # Never reuse an LLM-proposed issue ID here.  Otherwise rules that
            # referred to a rejected issue could accidentally attach to the
            # system fallback and satisfy its coverage.
            "issue_id": "I_FALLBACK",
            "question_span": fallback_span,
            "required_roles": [role.value for role in inferred],
            "fact_ids": [],
        })
        errors.append("no_valid_issue:fallback_created")
    return issues, facts


def _sanitize_slots(
    rule_id: str,
    quote: str,
    value: object,
    errors: list[str],
) -> dict[str, list[str]] | None:
    if not isinstance(value, Mapping):
        errors.append(f"slots_not_object:{rule_id}")
        return None
    slots: dict[str, list[str]] = {}
    for raw_kind, raw_values in value.items():
        try:
            kind = SlotKind(str(raw_kind))
        except ValueError:
            errors.append(f"invalid_slot_kind:{rule_id}:{raw_kind}")
            return None
        if not isinstance(raw_values, Sequence) or isinstance(raw_values, (str, bytes)):
            errors.append(f"slot_values_not_array:{rule_id}:{kind.value}")
            return None
        accepted: list[str] = []
        for raw_span in raw_values:
            span = str(raw_span).strip()
            if not span or span not in quote:
                errors.append(f"slot_span_not_exact:{rule_id}:{kind.value}")
                return None
            if span not in accepted:
                accepted.append(span)
        if accepted:
            slots[kind.value] = accepted
    return slots


def _sanitize_rules(
    question: str,
    raw: Mapping[str, Any],
    issues: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, EvidenceSpan],
    relation_keys: frozenset[str],
    errors: list[str],
    *,
    role_quotas: Mapping[LegalRole, int],
    global_cap: int,
) -> list[dict[str, Any]]:
    issue_ids = {str(issue["issue_id"]) for issue in issues}
    explicit_scopes = _explicit_market_scopes(question)
    role_counts: Counter[tuple[str, LegalRole]] = Counter()
    rule_ids: set[str] = set()
    rules: list[dict[str, Any]] = []
    for index, value in enumerate(raw.get("rules") or (), 1):
        if not isinstance(value, Mapping):
            errors.append(f"rule_not_object:{index}")
            continue
        rule_id = str(value.get("rule_id") or "").strip()
        issue_id = str(value.get("issue_id") or "").strip()
        evidence_id = str(value.get("evidence_id") or "").strip()
        quote = str(value.get("source_quote") or "").strip()
        try:
            role = LegalRole(str(value.get("role") or ""))
        except ValueError:
            errors.append(f"invalid_rule_role:{rule_id}")
            continue
        if not _valid_id(rule_id) or rule_id in rule_ids:
            errors.append(f"invalid_or_duplicate_rule_id:{rule_id}")
            continue
        if issue_id not in issue_ids:
            errors.append(f"rule_issue_outside_menu:{rule_id}:{issue_id}")
            continue
        source = evidence.get(evidence_id)
        if source is None:
            errors.append(f"rule_evidence_outside_menu:{rule_id}:{evidence_id}")
            continue
        if not source.verified:
            errors.append(f"rule_evidence_unverified:{rule_id}:{evidence_id}")
            continue
        if not quote or quote not in source.text:
            errors.append(f"source_quote_not_exact:{rule_id}")
            continue
        if explicit_scopes and source.scope_id.startswith("MARKET:") \
                and source.scope_id not in explicit_scopes:
            errors.append(f"explicit_scope_conflict:{rule_id}:{source.scope_id}")
            continue
        slots = _sanitize_slots(rule_id, quote, value.get("slots"), errors)
        if slots is None:
            continue
        quota = max(0, int(role_quotas.get(role, 0)))
        key = (issue_id, role)
        if role_counts[key] >= quota:
            errors.append(f"role_quota_exceeded:{issue_id}:{role.value}:{rule_id}")
            continue
        if len(rules) >= global_cap:
            errors.append(f"global_rule_cap_exceeded:{rule_id}")
            continue
        declared_relation_keys = list(dict.fromkeys(
            str(item) for item in value.get("relation_coverage_keys") or ()
        ))
        invalid_relation_keys = sorted(set(declared_relation_keys) - relation_keys)
        if invalid_relation_keys:
            errors.extend(
                f"relation_coverage_outside_menu:{rule_id}:{item}"
                for item in invalid_relation_keys
            )
            declared_relation_keys = [
                item for item in declared_relation_keys if item in relation_keys
            ]
        rule_ids.add(rule_id)
        role_counts[key] += 1
        rules.append({
            "rule_id": rule_id,
            "issue_id": issue_id,
            "role": role.value,
            "evidence_id": evidence_id,
            "scope_id": source.scope_id,
            "source_quote": quote[:QUOTE_CHARS_MAX],
            "proposition": quote[:QUOTE_CHARS_MAX],
            "normalization_status": "SOURCE_EXACT",
            "slots": slots,
            "coverage_keys": [
                f"role:{issue_id}:{role.value}", *declared_relation_keys,
            ],
        })
    return rules


def _sanitize_applicability(
    raw: Mapping[str, Any],
    issues: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    rules: Sequence[Mapping[str, Any]],
    verified_binding_ids: frozenset[str],
    errors: list[str],
) -> list[dict[str, Any]]:
    issue_ids = {str(issue["issue_id"]) for issue in issues}
    fact_by_id = {str(fact["fact_id"]): fact for fact in facts}
    rule_by_id = {str(rule["rule_id"]): rule for rule in rules}
    binding_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, value in enumerate(raw.get("applicability") or (), 1):
        if not isinstance(value, Mapping):
            errors.append(f"binding_not_object:{index}")
            continue
        binding_id = str(value.get("binding_id") or "").strip()
        issue_id = str(value.get("issue_id") or "").strip()
        rule_id = str(value.get("rule_id") or "").strip()
        fact_id = str(value.get("fact_id") or "").strip()
        try:
            proposed = ApplicabilityState(str(value.get("state") or ""))
        except ValueError:
            errors.append(f"invalid_applicability_state:{binding_id}")
            continue
        if not _valid_id(binding_id) or binding_id in binding_ids:
            errors.append(f"invalid_or_duplicate_binding_id:{binding_id}")
            continue
        rule = rule_by_id.get(rule_id)
        fact = fact_by_id.get(fact_id)
        if issue_id not in issue_ids or rule is None or fact is None:
            errors.append(f"binding_reference_outside_menu:{binding_id}")
            continue
        if rule["issue_id"] != issue_id or fact["issue_id"] != issue_id:
            errors.append(f"binding_cross_issue:{binding_id}")
            continue
        verified = binding_id in verified_binding_ids
        effective = proposed if verified else ApplicabilityState.UNRESOLVED
        if not verified and proposed != ApplicabilityState.UNRESOLVED:
            errors.append(f"unverified_applicability_downgraded:{binding_id}")
        binding_ids.add(binding_id)
        rows.append({
            "binding_id": binding_id,
            "issue_id": issue_id,
            "rule_id": rule_id,
            "fact_id": fact_id,
            "proposed_state": proposed.value,
            "state": effective.value,
            "verified": verified,
            "rule_evidence_id": rule["evidence_id"],
            "fact_question_span": fact["question_span"],
        })
    return rows


def _coverage_rows(
    issues: Sequence[Mapping[str, Any]],
    rules: Sequence[Mapping[str, Any]],
    relation_keys: frozenset[str],
) -> list[dict[str, Any]]:
    evidence_by_key: dict[str, list[str]] = defaultdict(list)
    rule_by_key: dict[str, list[str]] = defaultdict(list)
    for rule in rules:
        for key in rule.get("coverage_keys") or ():
            evidence_by_key[str(key)].append(str(rule["evidence_id"]))
            rule_by_key[str(key)].append(str(rule["rule_id"]))
    required: list[tuple[str, str, str]] = []
    for issue in issues:
        issue_id = str(issue["issue_id"])
        for role in issue.get("required_roles") or ():
            required.append((issue_id, f"role:{issue_id}:{role}", str(role)))
    for key in sorted(relation_keys):
        required.append(("RELATION", key, key.rsplit(":", 1)[-1]))
    rows = []
    for issue_id, key, required_role in required:
        evidence_ids = list(dict.fromkeys(evidence_by_key.get(key, ())))
        rule_ids = list(dict.fromkeys(rule_by_key.get(key, ())))
        rows.append({
            "issue_id": issue_id,
            "coverage_key": key,
            "required_role": required_role,
            "state": (
                CoverageState.SATISFIED.value if evidence_ids
                else CoverageState.MISSING.value
            ),
            "rule_ids": rule_ids,
            "evidence_ids": evidence_ids,
        })
    return rows


def _route_for_role(role: str) -> SearchRoute:
    if role in {LegalRole.DEFINITION.value, LegalRole.PROCEDURE.value,
                LegalRole.TEMPORAL.value, LegalRole.NUMERIC.value,
                LegalRole.SANCTION.value}:
        return SearchRoute.DOCUMENT_SEARCH
    if role in {LegalRole.EXCEPTION.value, LegalRole.CONDITION.value,
                LegalRole.AUTHORITY.value, LegalRole.COMPANION.value}:
        return SearchRoute.RELATION
    if role in {LegalRole.ACTOR_SCOPE.value}:
        return SearchRoute.STRUCTURE_MOVE
    return SearchRoute.GLOBAL_SEARCH


def _search_plan(
    issues: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    coverage: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    issue_by_id = {str(issue["issue_id"]): issue for issue in issues}
    all_question_spans = [str(issue["question_span"]) for issue in issues]
    facts_by_issue: dict[str, list[str]] = defaultdict(list)
    for fact in facts:
        facts_by_issue[str(fact["issue_id"])].append(str(fact["question_span"]))
    rows: list[dict[str, Any]] = []
    for row in coverage:
        if row["state"] != CoverageState.MISSING.value:
            continue
        issue_id = str(row["issue_id"])
        issue = issue_by_id.get(issue_id)
        spans = (
            list(all_question_spans)
            if issue_id == "RELATION"
            else ([] if issue is None else [str(issue["question_span"])])
        )
        spans.extend(facts_by_issue.get(issue_id, ()))
        rows.append({
            "issue_id": issue_id,
            "coverage_key": row["coverage_key"],
            "required_role": row["required_role"],
            "route": (
                SearchRoute.RELATION.value
                if issue_id == "RELATION"
                else _route_for_role(str(row["required_role"])).value
            ),
            "query_spans": list(dict.fromkeys(spans)),
            "generated_search_terms": [],
        })
    return rows


def _relation_behaviors(
    predicates: Sequence[RelationPredicate],
    rules: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for predicate in predicates:
        bindings: dict[str, EvidenceFact] = {}
        for coverage_key in RELATION_BEHAVIOR_POLICIES[predicate].required_coverage:
            full_key = f"relation:{predicate.value}:{coverage_key}"
            evidence_ids = tuple(dict.fromkeys(
                str(rule["evidence_id"])
                for rule in rules if full_key in (rule.get("coverage_keys") or ())
            ))
            if evidence_ids:
                bindings[coverage_key] = EvidenceFact(
                    value=coverage_key, evidence_ids=evidence_ids, verified=True,
                )
        assessment = assess_relation_behavior(predicate, bindings)
        row = assessment.to_dict()
        row["axiom_meaning"] = RELATION_AXIOMS[predicate].meaning
        rows.append(row)
    return rows


def compile_legal_review(
    question: str,
    evidence: Sequence[EvidenceSpan],
    raw: Mapping[str, Any] | None,
    *,
    relation_predicates: Iterable[RelationPredicate | str] = (),
    verified_binding_ids: Iterable[str] = (),
    role_quotas: Mapping[LegalRole | str, int] | None = None,
    global_rule_cap: int = GLOBAL_RULE_CAP,
) -> CompilationResult:
    """Validate and compile one legal-review packet without making a conclusion."""

    question = str(question or "")
    if not question.strip():
        raise ValueError("question must be non-empty")
    evidence_by_id: dict[str, EvidenceSpan] = {}
    for item in evidence:
        if not isinstance(item, EvidenceSpan):
            raise TypeError("evidence must contain EvidenceSpan objects")
        if item.evidence_id in evidence_by_id:
            raise ValueError(f"duplicate evidence_id: {item.evidence_id}")
        evidence_by_id[item.evidence_id] = item
    predicates, relation_keys = _relation_contract(relation_predicates)
    normalized_quotas = dict(ROLE_QUOTAS)
    for key, value in (role_quotas or {}).items():
        normalized_quotas[LegalRole(key)] = max(0, int(value))
    global_cap = max(0, min(int(global_rule_cap), GLOBAL_RULE_CAP))
    value = raw if isinstance(raw, Mapping) else {}
    errors: list[str] = []
    if raw is not None and not isinstance(raw, Mapping):
        errors.append("compiler_output_not_object")
    issues, facts = _sanitize_issues(question, value, errors)
    rules = _sanitize_rules(
        question, value, issues, evidence_by_id, relation_keys, errors,
        role_quotas=normalized_quotas, global_cap=global_cap,
    )
    applicability = _sanitize_applicability(
        value, issues, facts, rules,
        frozenset(str(item) for item in verified_binding_ids), errors,
    )
    coverage = _coverage_rows(issues, rules, relation_keys)
    missing = [row for row in coverage if row["state"] == CoverageState.MISSING.value]
    search_plan = _search_plan(issues, facts, coverage)

    bindings_by_fact: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for binding in applicability:
        bindings_by_fact[str(binding["fact_id"])].append(binding)
    unresolved_fact_ids = [
        str(fact["fact_id"]) for fact in facts
        if not bindings_by_fact.get(str(fact["fact_id"]))
        or any(
            row["state"] == ApplicabilityState.UNRESOLVED.value
            for row in bindings_by_fact[str(fact["fact_id"])]
        )
    ]
    clarification = [{
        "issue_id": str(fact["issue_id"]),
        "fact_id": str(fact["fact_id"]),
        "question_span": str(fact["question_span"]),
        "reason": "UNRESOLVED_APPLICABILITY",
    } for fact in facts if str(fact["fact_id"]) in set(unresolved_fact_ids)]

    relation_behaviors = _relation_behaviors(predicates, rules)
    if missing:
        status = CompilerStatus.BLOCKED_MISSING_COVERAGE
    elif unresolved_fact_ids:
        status = CompilerStatus.BLOCKED_UNRESOLVED_FACTS
    else:
        status = CompilerStatus.READY_FOR_ASSESSMENT
    diagnostics = {
        "evidence_menu_count": len(evidence_by_id),
        "issue_count": len(issues),
        "fact_count": len(facts),
        "rule_count": len(rules),
        "binding_count": len(applicability),
        "missing_coverage_count": len(missing),
        "unresolved_fact_count": len(unresolved_fact_ids),
        "search_plan_count": len(search_plan),
        "context_claim_count": 0,
        "global_rule_cap": global_cap,
        "role_quotas": {role.value: count for role, count in normalized_quotas.items()},
    }
    return CompilationResult(
        status=status,
        issues=tuple(issues),
        facts=tuple(facts),
        rules=tuple(rules),
        applicability=tuple(applicability),
        coverage=tuple(coverage),
        search_plan=tuple(search_plan),
        clarification_requests=tuple(clarification),
        relation_behaviors=tuple(relation_behaviors),
        validation_errors=tuple(errors),
        diagnostics=diagnostics,
        direct_legal_conclusion_allowed=False,
    )


def compile_with_llm(
    question: str,
    evidence: Sequence[EvidenceSpan],
    llm: Any,
    *,
    relation_predicates: Iterable[RelationPredicate | str] = (),
    verified_binding_ids: Iterable[str] = (),
    max_tokens: int = 6000,
) -> tuple[CompilationResult, dict[str, Any]]:
    """Call the product-model compiler once, then apply the deterministic gate.

    Applicability proposals remain unresolved unless a separate trusted layer
    supplies ``verified_binding_ids``.  This function is not wired to MAIN.
    """

    predicates, relation_keys = _relation_contract(relation_predicates)
    menu = [item.public() for item in evidence]
    schema = compiler_schema((item.evidence_id for item in evidence), relation_keys)
    user = (
        f"[질문]\n{question}\n\n[verified evidence 메뉴]\n"
        f"{json.dumps(menu, ensure_ascii=False, separators=(',', ':'))}"
    )
    raw = None if llm is None else llm.structured(
        "rag.legal_proposition_applicability.compiler",
        COMPILER_SYSTEM,
        user,
        schema,
        max_tokens=max_tokens,
        effort="low",
        model=PRODUCT_MODEL,
    )
    result = compile_legal_review(
        question,
        evidence,
        raw,
        relation_predicates=predicates,
        verified_binding_ids=verified_binding_ids,
    )
    return result, {
        "model": PRODUCT_MODEL,
        "raw_output": raw,
        "evidence_menu": menu,
        "relation_coverage_menu": sorted(relation_keys),
        "validation_errors": list(result.validation_errors),
        "main_wiring": "unchanged",
    }


__all__ = [
    "ApplicabilityState",
    "COMPILER_SYSTEM",
    "CompilerStatus",
    "CompilationResult",
    "CoverageState",
    "EvidenceSpan",
    "FactKind",
    "GLOBAL_RULE_CAP",
    "LegalRole",
    "PRODUCT_MODEL",
    "ROLE_QUOTAS",
    "SCHEMA_VERSION",
    "SearchRoute",
    "SlotKind",
    "compile_legal_review",
    "compile_with_llm",
    "compiler_schema",
    "evidence_from_sections",
]
