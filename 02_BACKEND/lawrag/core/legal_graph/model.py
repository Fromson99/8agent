"""Schema vocabulary and local validation for ``legal-graph-v1``.

This module contains no corpus or database access.  It is shared by the
streaming compiler and the independent validator so malformed coordinates,
unsupported predicates, and uncertainty lost during serialization fail
before publication.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from .ids import validate_id


SCHEMA_VERSION = "legal-graph-v1"
COMPILER_CONTRACT_VERSION = "legal-graph-compiler-v4-clause-span"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SchemaValidationError(ValueError):
    """A row violates the local ``legal-graph-v1`` contract."""


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class Layer(StrEnum):
    CANONICAL = "canonical"
    OBSERVATION = "observation"
    PROJECTION = "projection"
    RUNTIME = "runtime"


class RowType(StrEnum):
    # Transitional aggregate rows let the first sidecar preserve existing
    # registries without pretending they already have the finer v1 semantics.
    INSTRUMENT = "instrument"
    INSTRUMENT_SERIES = "instrument_series"
    INSTRUMENT_VERSION = "instrument_version"
    PROVISION_SERIES = "provision_series"
    PROVISION_VERSION = "provision_version"
    STRUCTURAL_UNIT = "structural_unit"
    CLAUSE_SPAN = "clause_span"
    EVIDENCE = "evidence"
    LEGAL_ENTITY = "legal_entity"
    LEGAL_ENTITY_REVISION = "legal_entity_revision"
    TERM_SENSE = "term_sense"
    RULE_ASSERTION = "rule_assertion"
    RELATION_ASSERTION = "relation_assertion"
    REQUIREMENT = "requirement"
    ASSESSMENT = "assessment"
    SEMANTIC_CONCEPT = "semantic_concept"
    TAXONOMY_ASSERTION = "taxonomy_assertion"
    LEGACY_CONCEPT = "legacy_concept"
    LEGACY_ASSERTION = "legacy_assertion"
    LEGACY_TAXONOMY = "legacy_taxonomy"
    ENTITY_MENTION = "entity_mention"
    RELATION_CANDIDATE = "relation_candidate"
    LEGACY_BINDING = "legacy_binding"
    UNRESOLVED_RELATION = "unresolved_relation"
    OBSERVATION = "observation"
    DEFINITION_OBSERVATION = "definition_observation"
    FRAME_OBSERVATION = "frame_observation"
    REQUIREMENT_OBSERVATION = "requirement_observation"
    RELATION_OBSERVATION = "relation_observation"
    OBSERVATION_ASSERTION_LINK = "observation_assertion_link"
    SOURCE_INVENTORY = "source_inventory"
    PROVISION_CARD = "provision_card"
    CLOSURE_PROJECTION = "closure_projection"
    INVERSE_RELATION = "inverse_relation"
    LEGACY_RELATION_VIEW = "legacy_relation_view"
    RULE_BUNDLE_PROJECTION = "rule_bundle_projection"
    SEMANTIC_CARD = "semantic_card"
    COMPATIBILITY = "compatibility"
    QUERY_FRAME = "query_frame"
    LANDING = "landing"
    ACTIVATION_DECISION = "activation_decision"
    DECISION_BUNDLE = "decision_bundle"
    RETRIEVAL_TRACE = "retrieval_trace"


CANONICAL_ROW_TYPES = frozenset({
    RowType.INSTRUMENT,
    RowType.INSTRUMENT_SERIES, RowType.INSTRUMENT_VERSION,
    RowType.PROVISION_SERIES, RowType.PROVISION_VERSION,
    RowType.STRUCTURAL_UNIT, RowType.CLAUSE_SPAN, RowType.EVIDENCE,
    RowType.LEGAL_ENTITY, RowType.LEGAL_ENTITY_REVISION, RowType.TERM_SENSE,
    RowType.RULE_ASSERTION, RowType.RELATION_ASSERTION, RowType.REQUIREMENT,
    RowType.ASSESSMENT, RowType.SEMANTIC_CONCEPT, RowType.TAXONOMY_ASSERTION,
    RowType.LEGACY_CONCEPT, RowType.LEGACY_ASSERTION,
    RowType.LEGACY_TAXONOMY,
})
OBSERVATION_ROW_TYPES = frozenset({
    RowType.ENTITY_MENTION, RowType.RELATION_CANDIDATE,
    RowType.LEGACY_BINDING, RowType.UNRESOLVED_RELATION, RowType.OBSERVATION,
    RowType.DEFINITION_OBSERVATION, RowType.FRAME_OBSERVATION,
    RowType.REQUIREMENT_OBSERVATION, RowType.RELATION_OBSERVATION,
    RowType.OBSERVATION_ASSERTION_LINK, RowType.SOURCE_INVENTORY,
})
PROJECTION_ROW_TYPES = frozenset({
    RowType.PROVISION_CARD, RowType.CLOSURE_PROJECTION,
    RowType.INVERSE_RELATION, RowType.LEGACY_RELATION_VIEW,
    RowType.RULE_BUNDLE_PROJECTION, RowType.COMPATIBILITY,
    RowType.SEMANTIC_CARD,
})
RUNTIME_ROW_TYPES = frozenset({
    RowType.QUERY_FRAME, RowType.LANDING, RowType.ACTIVATION_DECISION,
    RowType.DECISION_BUNDLE, RowType.RETRIEVAL_TRACE,
})
ROW_LAYER = {
    **{row_type: Layer.CANONICAL for row_type in CANONICAL_ROW_TYPES},
    **{row_type: Layer.OBSERVATION for row_type in OBSERVATION_ROW_TYPES},
    **{row_type: Layer.PROJECTION for row_type in PROJECTION_ROW_TYPES},
    **{row_type: Layer.RUNTIME for row_type in RUNTIME_ROW_TYPES},
}


class Precision(StrEnum):
    EXACT_SPAN = "EXACT_SPAN"
    EXACT_UNIT = "EXACT_UNIT"
    ARTICLE_FALLBACK = "ARTICLE_FALLBACK"
    DOCUMENT_ONLY = "DOCUMENT_ONLY"
    UNRESOLVED = "UNRESOLVED"


class ClaimStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    LEGACY_BACKED = "LEGACY_BACKED"
    CANDIDATE = "CANDIDATE"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class EndpointKind(StrEnum):
    INSTRUMENT_SERIES = "INSTRUMENT_SERIES"
    INSTRUMENT_VERSION = "INSTRUMENT_VERSION"
    PROVISION_SERIES = "PROVISION_SERIES"
    PROVISION_VERSION = "PROVISION_VERSION"
    STRUCTURAL_UNIT = "STRUCTURAL_UNIT"
    CLAUSE_SPAN = "CLAUSE_SPAN"
    LEGAL_ENTITY = "LEGAL_ENTITY"
    LEGAL_ENTITY_REVISION = "LEGAL_ENTITY_REVISION"
    TERM_SENSE = "TERM_SENSE"
    RULE_ASSERTION = "RULE_ASSERTION"
    DOCUMENT = "DOCUMENT"
    UNRESOLVED = "UNRESOLVED"


class EvidenceKind(StrEnum):
    SOURCE_TEXT = "SOURCE_TEXT"
    STRUCTURE = "STRUCTURE"
    OFFICIAL_LINK = "OFFICIAL_LINK"
    DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"
    LEGACY_RECORD = "LEGACY_RECORD"
    MODEL_OBSERVATION = "MODEL_OBSERVATION"


class SemanticEntityType(StrEnum):
    """Closed semantic entity vocabulary materialized from source observations."""

    FORMULA_EXPRESSION = "FORMULA_EXPRESSION"
    QUANTITY_CONSTRAINT = "QUANTITY_CONSTRAINT"
    TEMPORAL_CONSTRAINT = "TEMPORAL_CONSTRAINT"
    DOCUMENT_REQUIREMENT = "DOCUMENT_REQUIREMENT"
    AUTHORITY_ALLOCATION = "AUTHORITY_ALLOCATION"
    CLASSIFICATION_CRITERION = "CLASSIFICATION_CRITERION"
    EXCEPTION_ASSERTION = "EXCEPTION_ASSERTION"
    DEFINITION_SENSE = "DEFINITION_SENSE"


class AssessmentStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INDETERMINATE = "INDETERMINATE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class AssessmentReasoningMode(StrEnum):
    DIRECT_RULE = "DIRECT_RULE"
    RULE_COMBINATION = "RULE_COMBINATION"
    ABSENCE_WITHIN_CLOSED_BUNDLE = "ABSENCE_WITHIN_CLOSED_BUNDLE"
    FACT_APPLICATION = "FACT_APPLICATION"


class RelationFamily(StrEnum):
    NORMATIVE_RULE = "NORMATIVE_RULE"
    DEFINITION_CLASSIFICATION = "DEFINITION_CLASSIFICATION"
    LEGISLATIVE_LINK = "LEGISLATIVE_LINK"
    COMPETENCE_TASK = "COMPETENCE_TASK"
    RULE_USE = "RULE_USE"
    QUALIFICATION = "QUALIFICATION"
    LEGAL_EFFECT = "LEGAL_EFFECT"
    TEMPORAL = "TEMPORAL"
    SANCTION = "SANCTION"
    AMENDMENT = "AMENDMENT"
    INTERPRETATION = "INTERPRETATION"


class RelationPredicate(StrEnum):
    REGULATES_ACTION = "REGULATES_ACTION"
    ALLOCATES_AUTHORITY = "ALLOCATES_AUTHORITY"
    REQUIRES_SUBMISSION_OF = "REQUIRES_SUBMISSION_OF"
    COMPUTES_VALUE = "COMPUTES_VALUE"
    TRIGGERS_WHEN_THRESHOLD_MET = "TRIGGERS_WHEN_THRESHOLD_MET"
    DEFINES = "DEFINES"
    ALIASES_AS = "ALIASES_AS"
    SETS_CLASSIFICATION_CRITERIA_FOR = "SETS_CLASSIFICATION_CRITERIA_FOR"
    IS_A = "IS_A"
    LEGISLATIVE_DELEGATION = "LEGISLATIVE_DELEGATION"
    LEGISLATIVE_REDELEGATION = "LEGISLATIVE_REDELEGATION"
    SUPPLEMENTS_BY_ADMINISTRATIVE_RULE = "SUPPLEMENTS_BY_ADMINISTRATIVE_RULE"
    DELEGATES_ADMINISTRATIVE_AUTHORITY = "DELEGATES_ADMINISTRATIVE_AUTHORITY"
    ENTRUSTS_TASK = "ENTRUSTS_TASK"
    APPOINTS_TO_POSITION = "APPOINTS_TO_POSITION"
    ALLOCATES_INTERNAL_APPROVAL = "ALLOCATES_INTERNAL_APPROVAL"
    RECEIVES_FROM = "RECEIVES_FROM"
    DIRECTLY_APPLIES = "DIRECTLY_APPLIES"
    INCORPORATES_MUTATIS_MUTANDIS = "INCORPORATES_MUTATIS_MUTANDIS"
    FOLLOWS_EXAMPLE_OF = "FOLLOWS_EXAMPLE_OF"
    DEPENDS_ON_REQUIREMENTS_OF = "DEPENDS_ON_REQUIREMENTS_OF"
    LEGAL_BASIS_IN = "LEGAL_BASIS_IN"
    REFERENCES = "REFERENCES"
    USES_DEFINITION = "USES_DEFINITION"
    ISSUED_UNDER_INSTRUMENT = "ISSUED_UNDER_INSTRUMENT"
    QUALIFIES_RULE = "QUALIFIES_RULE"
    EXCEPTION_TO = "EXCEPTION_TO"
    EXCLUDES_APPLICATION_OF = "EXCLUDES_APPLICATION_OF"
    OVERRIDES_NOTWITHSTANDING = "OVERRIDES_NOTWITHSTANDING"
    FALLBACK_TO = "FALLBACK_TO"
    EXPLICIT_PRIORITY_OVER = "EXPLICIT_PRIORITY_OVER"
    DEEMS_AS = "DEEMS_AS"
    PRESUMES_AS = "PRESUMES_AS"
    SUBSTITUTES_FOR = "SUBSTITUTES_FOR"
    EXEMPTS_FROM = "EXEMPTS_FROM"
    ALLOWS_OMISSION_OF = "ALLOWS_OMISSION_OF"
    EFFECTIVE_FROM = "EFFECTIVE_FROM"
    EFFECTIVE_UNTIL = "EFFECTIVE_UNTIL"
    EFFECTIVE_FOR = "EFFECTIVE_FOR"
    APPLIES_TO = "APPLIES_TO"
    TRANSITION_FOR = "TRANSITION_FOR"
    SUPERSEDES = "SUPERSEDES"
    SUPERSEDES_VERSION = "SUPERSEDES_VERSION"
    AMENDS = "AMENDS"
    REPEALS = "REPEALS"
    IMPOSES_SANCTION = "IMPOSES_SANCTION"
    SANCTIONS_VIOLATION_OF = "SANCTIONS_VIOLATION_OF"
    INTERPRETS = "INTERPRETS"


_FAMILY_PREDICATES = {
    RelationFamily.NORMATIVE_RULE: {
        RelationPredicate.REGULATES_ACTION, RelationPredicate.ALLOCATES_AUTHORITY,
        RelationPredicate.REQUIRES_SUBMISSION_OF, RelationPredicate.COMPUTES_VALUE,
        RelationPredicate.TRIGGERS_WHEN_THRESHOLD_MET,
    },
    RelationFamily.DEFINITION_CLASSIFICATION: {
        RelationPredicate.DEFINES, RelationPredicate.ALIASES_AS,
        RelationPredicate.SETS_CLASSIFICATION_CRITERIA_FOR, RelationPredicate.IS_A,
    },
    RelationFamily.LEGISLATIVE_LINK: {
        RelationPredicate.LEGISLATIVE_DELEGATION,
        RelationPredicate.LEGISLATIVE_REDELEGATION,
        RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE,
    },
    RelationFamily.COMPETENCE_TASK: {
        RelationPredicate.DELEGATES_ADMINISTRATIVE_AUTHORITY,
        RelationPredicate.ENTRUSTS_TASK, RelationPredicate.APPOINTS_TO_POSITION,
        RelationPredicate.ALLOCATES_INTERNAL_APPROVAL, RelationPredicate.RECEIVES_FROM,
    },
    RelationFamily.RULE_USE: {
        RelationPredicate.DIRECTLY_APPLIES,
        RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS,
        RelationPredicate.FOLLOWS_EXAMPLE_OF,
        RelationPredicate.DEPENDS_ON_REQUIREMENTS_OF,
        RelationPredicate.LEGAL_BASIS_IN, RelationPredicate.REFERENCES,
        RelationPredicate.USES_DEFINITION, RelationPredicate.ISSUED_UNDER_INSTRUMENT,
    },
    RelationFamily.QUALIFICATION: {
        RelationPredicate.QUALIFIES_RULE, RelationPredicate.EXCEPTION_TO,
        RelationPredicate.EXCLUDES_APPLICATION_OF,
        RelationPredicate.OVERRIDES_NOTWITHSTANDING,
        RelationPredicate.FALLBACK_TO, RelationPredicate.EXPLICIT_PRIORITY_OVER,
    },
    RelationFamily.LEGAL_EFFECT: {
        RelationPredicate.DEEMS_AS, RelationPredicate.PRESUMES_AS,
        RelationPredicate.SUBSTITUTES_FOR, RelationPredicate.EXEMPTS_FROM,
        RelationPredicate.ALLOWS_OMISSION_OF,
    },
    RelationFamily.TEMPORAL: {
        RelationPredicate.EFFECTIVE_FROM, RelationPredicate.EFFECTIVE_UNTIL,
        RelationPredicate.EFFECTIVE_FOR, RelationPredicate.APPLIES_TO,
        RelationPredicate.TRANSITION_FOR,
    },
    RelationFamily.SANCTION: {
        RelationPredicate.IMPOSES_SANCTION,
        RelationPredicate.SANCTIONS_VIOLATION_OF,
    },
    RelationFamily.AMENDMENT: {
        RelationPredicate.SUPERSEDES, RelationPredicate.SUPERSEDES_VERSION,
        RelationPredicate.AMENDS,
        RelationPredicate.REPEALS,
    },
    RelationFamily.INTERPRETATION: {RelationPredicate.INTERPRETS},
}
RELATION_FAMILY_BY_PREDICATE = {
    predicate: family
    for family, predicates in _FAMILY_PREDICATES.items()
    for predicate in predicates
}
if set(RELATION_FAMILY_BY_PREDICATE) != set(RelationPredicate):
    raise RuntimeError("every relation predicate must have exactly one family")


class ClosureMode(StrEnum):
    REQUIRED_WHEN_ACTIVATED = "REQUIRED_WHEN_ACTIVATED"
    CONTEXTUAL = "CONTEXTUAL"
    NON_CLOSURE = "NON_CLOSURE"


_REQUIRED_CLOSURE = {
    RelationPredicate.LEGISLATIVE_DELEGATION,
    RelationPredicate.LEGISLATIVE_REDELEGATION,
    RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE,
    RelationPredicate.DIRECTLY_APPLIES,
    RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS,
    RelationPredicate.DEPENDS_ON_REQUIREMENTS_OF,
    RelationPredicate.QUALIFIES_RULE,
    RelationPredicate.EXCEPTION_TO,
    RelationPredicate.EXCLUDES_APPLICATION_OF,
    RelationPredicate.OVERRIDES_NOTWITHSTANDING,
    RelationPredicate.FALLBACK_TO,
    RelationPredicate.EXPLICIT_PRIORITY_OVER,
    RelationPredicate.USES_DEFINITION,
    RelationPredicate.SANCTIONS_VIOLATION_OF,
    RelationPredicate.EFFECTIVE_FOR,
    RelationPredicate.APPLIES_TO,
    RelationPredicate.TRANSITION_FOR,
}
_CONTEXTUAL_CLOSURE = {
    RelationPredicate.DEFINES, RelationPredicate.ALIASES_AS,
    RelationPredicate.SETS_CLASSIFICATION_CRITERIA_FOR,
    RelationPredicate.FOLLOWS_EXAMPLE_OF, RelationPredicate.LEGAL_BASIS_IN,
    RelationPredicate.REFERENCES,
}
DEFAULT_CLOSURE_POLICY = {
    predicate: (
        ClosureMode.REQUIRED_WHEN_ACTIVATED if predicate in _REQUIRED_CLOSURE
        else ClosureMode.CONTEXTUAL if predicate in _CONTEXTUAL_CLOSURE
        else ClosureMode.NON_CLOSURE
    )
    for predicate in RelationPredicate
}
PREDICATE_CLOSURE_POLICY = DEFAULT_CLOSURE_POLICY
CLOSURE_POLICY_BY_PREDICATE = DEFAULT_CLOSURE_POLICY

# Existing unified-relation and document-graph names are observations.  This
# table records their semantic normalization; it does not authorize automatic
# acceptance or inversion of an assertion.
LEGACY_KIND_TO_PREDICATE = {
    "REFERENCES": RelationPredicate.REFERENCES,
    "BASED_ON": RelationPredicate.LEGAL_BASIS_IN,
    "INCORPORATES": RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS,
    "EXCLUDES": RelationPredicate.EXCLUDES_APPLICATION_OF,
    "DEEMS": RelationPredicate.DEEMS_AS,
    "RECEIVES_FROM": RelationPredicate.RECEIVES_FROM,
    "DELEGATES_TO": RelationPredicate.LEGISLATIVE_DELEGATION,
    "USES_DEFINITION": RelationPredicate.USES_DEFINITION,
    "VIOLATION_SANCTIONED_BY": RelationPredicate.SANCTIONS_VIOLATION_OF,
    "HAS_EXCEPTION": RelationPredicate.EXCEPTION_TO,
    "EFFECTIVE_FOR": RelationPredicate.EFFECTIVE_FOR,
    "APPLIES_TO": RelationPredicate.APPLIES_TO,
    "TRANSITION_FOR": RelationPredicate.TRANSITION_FOR,
    "AMENDS": RelationPredicate.AMENDS,
    "IMPLEMENTED_BY": RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE,
    "ISSUED_UNDER": RelationPredicate.ISSUED_UNDER_INSTRUMENT,
    "SUPERSEDES": RelationPredicate.SUPERSEDES_VERSION,
    "VALID_FROM": RelationPredicate.EFFECTIVE_FROM,
}
RELATION_PREDICATE_BY_LEGACY_KIND = LEGACY_KIND_TO_PREDICATE


def _enum(enum_type: type[StrEnum], value: Any, field_name: str) -> StrEnum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise SchemaValidationError(f"invalid {field_name}: {value!r}") from exc


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{field_name} must be a non-empty string")
    return value


def _sha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise SchemaValidationError(f"{field_name} must be a lowercase SHA-256")
    return value


def _plain_props(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise SchemaValidationError("props must be a mapping with string keys")
    return dict(value)


@dataclass(frozen=True)
class Selector:
    """A corpus-local coordinate, optionally narrowed to an exact text span."""

    document_id: str
    node_id: int | str | None = None
    block_id: int | str | None = None
    start: int | None = None
    end: int | None = None
    quote_sha256: str | None = None
    coordinate: str | None = None

    def validate(self) -> "Selector":
        _nonempty(self.document_id, "selector.document_id")
        for name in ("node_id", "block_id"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise SchemaValidationError(f"selector.{name} must be int, str, or null")
            if isinstance(value, int) and value < 0:
                raise SchemaValidationError(f"selector.{name} cannot be negative")
            if isinstance(value, str) and not value.strip():
                raise SchemaValidationError(f"selector.{name} cannot be empty")
        if (self.start is None) != (self.end is None):
            raise SchemaValidationError("selector.start and end must appear together")
        if self.start is not None:
            if (isinstance(self.start, bool) or isinstance(self.end, bool)
                    or not isinstance(self.start, int) or not isinstance(self.end, int)
                    or self.start < 0 or self.end <= self.start):
                raise SchemaValidationError("selector span must satisfy 0 <= start < end")
            if self.node_id is None or self.block_id is None:
                raise SchemaValidationError("selector span requires node_id and block_id")
        if self.quote_sha256 is not None:
            _sha256(self.quote_sha256, "selector.quote_sha256")
            if self.start is None:
                raise SchemaValidationError("selector.quote_sha256 requires a span")
        if self.coordinate is not None and not self.coordinate.strip():
            raise SchemaValidationError("selector.coordinate cannot be empty")
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        out: dict[str, Any] = {"document_id": self.document_id}
        for key in ("node_id", "block_id", "start", "end", "quote_sha256", "coordinate"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Selector":
        if not isinstance(value, Mapping):
            raise SchemaValidationError("selector must be an object")
        allowed = {
            "document_id", "node_id", "block_id", "start", "end",
            "quote_sha256", "coordinate",
        }
        extra = set(value) - allowed
        if extra:
            raise SchemaValidationError(f"unknown selector fields: {sorted(extra)}")
        try:
            return cls(**dict(value)).validate()
        except TypeError as exc:
            raise SchemaValidationError(f"malformed selector: {exc}") from exc


@dataclass(frozen=True)
class Endpoint:
    kind: EndpointKind
    precision: Precision
    ref_id: str | None = None
    selector: Selector | None = None
    label: str = ""

    def validate(self) -> "Endpoint":
        kind = _enum(EndpointKind, self.kind, "endpoint.kind")
        precision = _enum(Precision, self.precision, "endpoint.precision")
        selector = self.selector
        if selector is not None:
            if not isinstance(selector, Selector):
                raise SchemaValidationError("endpoint.selector must be a Selector")
            selector.validate()
        if self.ref_id is not None:
            try:
                validate_id(self.ref_id)
            except ValueError as exc:
                raise SchemaValidationError(str(exc)) from exc
        if precision == Precision.EXACT_SPAN:
            if (selector is None or selector.node_id is None
                    or selector.block_id is None or selector.start is None):
                raise SchemaValidationError(
                    "EXACT_SPAN requires document, node, block, and offsets"
                )
            if selector.quote_sha256 is None:
                raise SchemaValidationError("EXACT_SPAN requires quote_sha256")
        elif precision in {Precision.EXACT_UNIT, Precision.ARTICLE_FALLBACK}:
            if selector is None or selector.node_id is None:
                raise SchemaValidationError(f"{precision.value} requires document and node")
            if selector.start is not None:
                raise SchemaValidationError(f"{precision.value} cannot carry span offsets")
        elif precision == Precision.DOCUMENT_ONLY:
            if (selector is None or selector.node_id is not None
                    or selector.block_id is not None):
                raise SchemaValidationError("DOCUMENT_ONLY requires only document_id")
        elif precision == Precision.UNRESOLVED:
            if kind != EndpointKind.UNRESOLVED or self.ref_id is not None:
                raise SchemaValidationError("UNRESOLVED endpoint cannot assert a ref_id")
        if kind == EndpointKind.UNRESOLVED and precision != Precision.UNRESOLVED:
            raise SchemaValidationError("UNRESOLVED kind requires UNRESOLVED precision")
        if precision != Precision.UNRESOLVED and self.ref_id is None:
            raise SchemaValidationError("resolved endpoint requires ref_id")
        if self.label and not isinstance(self.label, str):
            raise SchemaValidationError("endpoint.label must be a string")
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        out: dict[str, Any] = {"kind": str(self.kind), "precision": str(self.precision)}
        if self.ref_id is not None:
            out["ref_id"] = self.ref_id
        if self.selector is not None:
            out["selector"] = self.selector.to_dict()
        if self.label:
            out["label"] = self.label
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Endpoint":
        if not isinstance(value, Mapping):
            raise SchemaValidationError("endpoint must be an object")
        allowed = {"kind", "precision", "ref_id", "selector", "label"}
        extra = set(value) - allowed
        if extra:
            raise SchemaValidationError(f"unknown endpoint fields: {sorted(extra)}")
        data = dict(value)
        try:
            data["kind"] = EndpointKind(data["kind"])
            data["precision"] = Precision(data["precision"])
            if data.get("selector") is not None:
                data["selector"] = Selector.from_dict(data["selector"])
            return cls(**data).validate()
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, SchemaValidationError):
                raise
            raise SchemaValidationError(f"malformed endpoint: {exc}") from exc


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: EvidenceKind
    source: Endpoint
    quote_text: str | None = None
    method: str = ""
    props: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> "Evidence":
        try:
            validate_id(self.id, prefix="evidence")
        except ValueError as exc:
            raise SchemaValidationError(str(exc)) from exc
        kind = _enum(EvidenceKind, self.kind, "evidence.kind")
        if not isinstance(self.source, Endpoint):
            raise SchemaValidationError("evidence.source must be an Endpoint")
        self.source.validate()
        if self.source.precision == Precision.UNRESOLVED:
            raise SchemaValidationError("evidence source cannot be unresolved")
        if self.quote_text is not None:
            if not isinstance(self.quote_text, str) or not self.quote_text:
                raise SchemaValidationError("evidence.quote_text cannot be empty")
            selector = self.source.selector
            if selector is None or selector.quote_sha256 is None:
                raise SchemaValidationError("quote_text requires selector.quote_sha256")
            actual = hashlib.sha256(self.quote_text.encode("utf-8")).hexdigest()
            if actual != selector.quote_sha256:
                raise SchemaValidationError("quote_text does not match quote_sha256")
        if kind == EvidenceKind.SOURCE_TEXT and self.source.precision not in {
            Precision.EXACT_SPAN, Precision.EXACT_UNIT, Precision.ARTICLE_FALLBACK,
        }:
            raise SchemaValidationError("SOURCE_TEXT evidence requires a text-bearing unit")
        if self.method and not isinstance(self.method, str):
            raise SchemaValidationError("evidence.method must be a string")
        _plain_props(self.props)
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        out: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "row_type": RowType.EVIDENCE.value,
            "id": self.id,
            "kind": str(self.kind),
            "source": self.source.to_dict(),
        }
        if self.quote_text is not None:
            out["quote_text"] = self.quote_text
        if self.method:
            out["method"] = self.method
        if self.props:
            out["props"] = _plain_props(self.props)
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Evidence":
        if not isinstance(value, Mapping):
            raise SchemaValidationError("evidence must be an object")
        # Generation/lineage columns are row envelope metadata, not Evidence
        # constructor fields.  Other supplemental row columns are intentionally
        # ignored here and remain available to higher-level validators.
        allowed = {"id", "kind", "source", "quote_text", "method", "props"}
        data = {key: item for key, item in value.items() if key in allowed}
        try:
            data["kind"] = EvidenceKind(data["kind"])
            data["source"] = Endpoint.from_dict(data["source"])
            return cls(**data).validate()
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, SchemaValidationError):
                raise
            raise SchemaValidationError(f"malformed evidence: {exc}") from exc


_REQUIRED_FIELDS: dict[RowType, frozenset[str]] = {
    RowType.INSTRUMENT: frozenset({"id", "document_id", "name"}),
    RowType.INSTRUMENT_SERIES: frozenset({"id", "name"}),
    RowType.INSTRUMENT_VERSION: frozenset({"id", "series_id", "document_id"}),
    RowType.PROVISION_SERIES: frozenset({"id", "instrument_series_id", "coordinate"}),
    RowType.PROVISION_VERSION: frozenset({"id", "provision_series_id", "instrument_version_id"}),
    RowType.STRUCTURAL_UNIT: frozenset({"id", "document_id", "node_id", "unit_kind"}),
    RowType.CLAUSE_SPAN: frozenset({"id", "structural_unit_id", "start", "end", "text_sha256"}),
    RowType.EVIDENCE: frozenset({"id", "kind", "source"}),
    RowType.LEGAL_ENTITY: frozenset({"id", "entity_type", "label"}),
    RowType.LEGAL_ENTITY_REVISION: frozenset({"id", "entity_id", "label"}),
    RowType.TERM_SENSE: frozenset({"id", "term", "scope", "evidence_ids"}),
    RowType.RULE_ASSERTION: frozenset({"id", "claim_status", "source", "evidence_ids"}),
    RowType.RELATION_ASSERTION: frozenset({
        "id", "predicate", "family", "source", "target", "claim_status", "evidence_ids",
    }),
    RowType.REQUIREMENT: frozenset({"id", "rule_assertion_id", "operator"}),
    RowType.ASSESSMENT: frozenset({
        "id", "claim_id", "status", "conclusion", "basis_ids",
        "reasoning_mode", "confidence", "requires_review",
    }),
    RowType.SEMANTIC_CONCEPT: frozenset({"id", "label", "concept_type"}),
    RowType.TAXONOMY_ASSERTION: frozenset({"id", "source", "target"}),
    RowType.LEGACY_CONCEPT: frozenset({"id", "legacy_id"}),
    RowType.LEGACY_ASSERTION: frozenset({"id", "legacy_id"}),
    RowType.LEGACY_TAXONOMY: frozenset({"id", "legacy_id"}),
    RowType.ENTITY_MENTION: frozenset({"id", "surface", "source", "claim_status"}),
    RowType.RELATION_CANDIDATE: frozenset({"id", "predicate", "source", "target", "claim_status"}),
    RowType.LEGACY_BINDING: frozenset({"id", "legacy_id", "binding_status"}),
    RowType.UNRESOLVED_RELATION: frozenset({"id", "legacy_id", "reason", "claim_status"}),
    RowType.OBSERVATION: frozenset({"id", "observation_kind"}),
    RowType.DEFINITION_OBSERVATION: frozenset({"id", "source"}),
    RowType.FRAME_OBSERVATION: frozenset({"id", "source"}),
    RowType.REQUIREMENT_OBSERVATION: frozenset({"id", "source"}),
    RowType.RELATION_OBSERVATION: frozenset({"id", "source", "target"}),
    RowType.OBSERVATION_ASSERTION_LINK: frozenset({"id", "observation_id", "assertion_id"}),
    RowType.SOURCE_INVENTORY: frozenset({"id", "source_kind", "source_path"}),
    RowType.PROVISION_CARD: frozenset({"id", "article_root", "facets"}),
    RowType.CLOSURE_PROJECTION: frozenset({"id", "relation_assertion_id", "closure_mode"}),
    RowType.INVERSE_RELATION: frozenset({"id", "relation_assertion_id"}),
    RowType.LEGACY_RELATION_VIEW: frozenset({"id", "relation_assertion_id", "legacy_kind"}),
    RowType.RULE_BUNDLE_PROJECTION: frozenset({"id", "root_rule_id", "member_ids"}),
    RowType.SEMANTIC_CARD: frozenset({
        "id", "source", "article_root", "entity_id", "semantic_type",
        "family_ids", "terms", "assertion_ids", "coverage_keys",
    }),
    RowType.COMPATIBILITY: frozenset({"id", "compatibility_kind"}),
    RowType.QUERY_FRAME: frozenset({"id", "query"}),
    RowType.LANDING: frozenset({"id", "query_frame_id", "endpoint"}),
    RowType.ACTIVATION_DECISION: frozenset({"id", "relation_assertion_id", "activated"}),
    RowType.DECISION_BUNDLE: frozenset({"id", "query_frame_id", "member_ids"}),
    RowType.RETRIEVAL_TRACE: frozenset({"id", "query_frame_id", "events"}),
}


def layer_for_row_type(row_type: RowType | str) -> Layer:
    return ROW_LAYER[_enum(RowType, row_type, "row_type")]


def validate_row(
    row: Mapping[str, Any],
    *,
    expected_type: RowType | str | None = None,
    expected_layer: Layer | str | None = None,
) -> Mapping[str, Any]:
    """Validate one serialized row without consulting other rows or the corpus."""
    if not isinstance(row, Mapping):
        raise SchemaValidationError("row must be an object")
    if row.get("schema_version") != SCHEMA_VERSION:
        raise SchemaValidationError(f"row schema_version must be {SCHEMA_VERSION!r}")
    row_type = _enum(RowType, row.get("row_type"), "row_type")
    if expected_type is not None and row_type != _enum(RowType, expected_type, "expected_type"):
        raise SchemaValidationError(f"expected {expected_type}, got {row_type.value}")
    layer = ROW_LAYER[row_type]
    if "layer" in row and _enum(Layer, row["layer"], "layer") != layer:
        raise SchemaValidationError(
            f"{row_type.value} belongs to layer {layer.value}, not {row['layer']}"
        )
    if expected_layer is not None and layer != _enum(Layer, expected_layer, "expected_layer"):
        raise SchemaValidationError(f"{row_type.value} belongs to {layer.value}, not {expected_layer}")
    missing = _REQUIRED_FIELDS[row_type] - set(row)
    if missing:
        raise SchemaValidationError(f"{row_type.value} missing fields: {sorted(missing)}")
    try:
        validate_id(row["id"])
    except (KeyError, ValueError) as exc:
        raise SchemaValidationError(str(exc)) from exc

    for name in ("source", "target", "scope", "article_root", "endpoint"):
        if name in row:
            Endpoint.from_dict(row[name])
    if "claim_status" in row:
        status = _enum(ClaimStatus, row["claim_status"], "claim_status")
        if row_type in CANONICAL_ROW_TYPES and status in {
            ClaimStatus.CANDIDATE, ClaimStatus.REJECTED, ClaimStatus.UNRESOLVED,
        }:
            raise SchemaValidationError("uncertain/rejected claims belong in observation rows")
    if row_type == RowType.LEGAL_ENTITY:
        _enum(SemanticEntityType, row.get("entity_type"), "entity_type")
    if row_type == RowType.ASSESSMENT:
        _enum(AssessmentStatus, row.get("status"), "assessment.status")
        _enum(
            AssessmentReasoningMode,
            row.get("reasoning_mode"),
            "assessment.reasoning_mode",
        )
        confidence = row.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            raise SchemaValidationError("assessment.confidence must be between 0 and 1")
        if not isinstance(row.get("requires_review"), bool):
            raise SchemaValidationError("assessment.requires_review must be boolean")
    if row_type == RowType.SEMANTIC_CARD:
        card_status = str(row.get("card_status") or "SEMANTIC_READY")
        if card_status not in {"STRUCTURE_ONLY", "SEMANTIC_READY"}:
            raise SchemaValidationError(
                "semantic_card.card_status must be STRUCTURE_ONLY or SEMANTIC_READY"
            )
        if card_status == "STRUCTURE_ONLY":
            if row.get("semantic_type") != "STRUCTURE_ONLY":
                raise SchemaValidationError(
                    "STRUCTURE_ONLY card must use semantic_type STRUCTURE_ONLY"
                )
            if row.get("entity_id") not in {"", None}:
                raise SchemaValidationError(
                    "STRUCTURE_ONLY card cannot claim a semantic entity"
                )
        else:
            _enum(SemanticEntityType, row.get("semantic_type"), "semantic_type")
        for name in ("family_ids", "terms", "assertion_ids", "coverage_keys"):
            values = row.get(name)
            if (
                not isinstance(values, list)
                or any(not isinstance(item, str) or not item for item in values)
                or values != sorted(set(values))
            ):
                raise SchemaValidationError(
                    f"semantic_card.{name} must be a sorted unique string list"
                )
    if row_type == RowType.EVIDENCE:
        Evidence.from_dict(row)
    if "predicate" in row:
        predicate = _enum(RelationPredicate, row["predicate"], "predicate")
        if "family" in row:
            family = _enum(RelationFamily, row["family"], "family")
            expected_family = RELATION_FAMILY_BY_PREDICATE[predicate]
            if family != expected_family:
                raise SchemaValidationError(
                    f"predicate {predicate.value} belongs to {expected_family.value}"
                )
    if "closure_mode" in row:
        _enum(ClosureMode, row["closure_mode"], "closure_mode")
    if row_type == RowType.CLAUSE_SPAN:
        start, end = row["start"], row["end"]
        if (isinstance(start, bool) or isinstance(end, bool)
                or not isinstance(start, int) or not isinstance(end, int)
                or start < 0 or end <= start):
            raise SchemaValidationError("clause_span must satisfy 0 <= start < end")
        _sha256(row["text_sha256"], "text_sha256")
        if "selector" in row:
            selector = Selector.from_dict(row["selector"])
            if selector.start != start or selector.end != end:
                raise SchemaValidationError(
                    "clause_span selector offsets must equal start/end"
                )
            if selector.quote_sha256 != row["text_sha256"]:
                raise SchemaValidationError(
                    "clause_span selector quote_sha256 must equal text_sha256"
                )
        if "text" in row:
            text = row["text"]
            if not isinstance(text, str) or not text:
                raise SchemaValidationError("clause_span text must be non-empty")
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != row["text_sha256"]:
                raise SchemaValidationError("clause_span text does not match text_sha256")
        if row.get("span_kind") not in {None, "CLAUSE", "PROVISO"}:
            raise SchemaValidationError("clause_span span_kind must be CLAUSE or PROVISO")
    for name in ("evidence_ids", "member_ids", "basis_ids"):
        if name in row and (
            not isinstance(row[name], list)
            or any(not isinstance(item, str) or not item for item in row[name])
        ):
            raise SchemaValidationError(f"{name} must be a list of ids")
    return row


def validate_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    expected_type: RowType | str | None = None,
    expected_layer: Layer | str | None = None,
) -> int:
    count = 0
    seen: set[str] = set()
    for count, row in enumerate(rows, 1):
        try:
            validate_row(row, expected_type=expected_type, expected_layer=expected_layer)
        except SchemaValidationError as exc:
            raise SchemaValidationError(f"row {count}: {exc}") from exc
        row_id = str(row["id"])
        if row_id in seen:
            raise SchemaValidationError(f"row {count}: duplicate id {row_id}")
        seen.add(row_id)
    return count


def validate_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the local shape of an immutable generation manifest."""
    if not isinstance(manifest, Mapping):
        raise SchemaValidationError("manifest must be an object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SchemaValidationError(f"manifest schema_version must be {SCHEMA_VERSION!r}")
    _nonempty(manifest.get("generation_id"), "manifest.generation_id")
    _nonempty(manifest.get("authority_generation"), "manifest.authority_generation")
    files = manifest.get("artifacts")
    if files is None:
        # Read compatibility for an unpublished development snapshot.
        files = manifest.get("files")
    if not isinstance(files, Mapping) or not files:
        raise SchemaValidationError("manifest.artifacts must be a non-empty object")
    for path, metadata in files.items():
        _nonempty(path, "manifest file path")
        if path.startswith("/") or ".." in path.split("/"):
            raise SchemaValidationError(f"unsafe manifest file path: {path!r}")
        if not isinstance(metadata, Mapping):
            raise SchemaValidationError(f"manifest file metadata must be an object: {path}")
        _sha256(metadata.get("sha256"), f"files[{path!r}].sha256")
        count = metadata.get("rows")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise SchemaValidationError(f"files[{path!r}].rows must be a non-negative integer")
        size = metadata.get("bytes")
        if size is not None and (
            isinstance(size, bool) or not isinstance(size, int) or size < 0
        ):
            raise SchemaValidationError(f"files[{path!r}].bytes must be a non-negative integer")
        artifact_format = metadata.get("format")
        if artifact_format is not None and artifact_format not in {"json", "jsonl"}:
            raise SchemaValidationError(
                f"files[{path!r}].format must be 'json' or 'jsonl'"
            )
        if "row_type" in metadata:
            _enum(RowType, metadata["row_type"], f"files[{path!r}].row_type")
    return manifest
