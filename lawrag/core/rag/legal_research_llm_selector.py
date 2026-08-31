"""Provider-neutral selectors for the hierarchical legal-research runtime.

The structural atlas and controllers intentionally do not import an LLM.  This
module is the narrow experiment adapter between those pure state machines and
a profiled product model.  It keeps five boundaries explicit:

* every call is pinned to an explicit backend/model profile with transport
  retries disabled;
* one canonical schema is projected for Anthropic or OpenAI-compatible Qwen
  without changing the local closed-menu and coverage validation boundary;
* one client/log belongs to one worker thread, so parallel page receipts cannot
  be attached to the wrong call;
* model JSON is parsed without Python truthiness or string coercion and is then
  passed through the existing closed-menu validators; and
* article menus contain only query/plan-term windows with exact source offsets,
  never an unbounded article body or a gold/reference field.

The adapter is independent from MAIN and from the API router.  Creating an
instance does not call a provider; the default client is initialized lazily on
the first ``structured`` call in each worker thread.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
import re
from threading import Lock, local
from typing import Any, Callable, Mapping, Protocol, Sequence

from lawrag.core.rag import query_grounding
from lawrag.core.rag.legal_instrument_routing import (
    ClosedRouteMenuViolation,
    InstrumentRouteBranch,
    InstrumentRouteChoice,
    InstrumentRouteDecision,
    InstrumentRoutePage,
    RouteModelRequest,
    build_route_model_request,
    validate_route_decision,
)
from lawrag.core.rag.legal_research_atlas import InstrumentRole
from lawrag.core.rag.legal_research_controller import (
    CandidatePage,
    ClosedMenuViolation,
    PageDecision,
    decision_schema,
    validate_page_decision,
)


HAIKU_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_BACKEND = "anthropic"
GENOS_BACKEND = "genos"
OPENROUTER_BACKEND = "openrouter"
TRANSPORT_MAX_RETRIES = 0
TRANSPORT_TIMEOUT_SECONDS = 120.0
ANTHROPIC_SCHEMA_PROFILE = "anthropic-official"
QWEN_NATIVE_SCHEMA_PROFILE = "qwen-openai-native"
QWEN_REDUCED_SCHEMA_PROFILE = "qwen-openai-reduced"
_QWEN_REDUCED_UNSUPPORTED = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minItems", "maxItems", "uniqueItems", "minLength", "maxLength",
    "pattern", "multipleOf",
})

ARTICLE_SYSTEM = """너는 대한민국 금융규제 리서치의 조문 탐색 라우터다.
법률 결론이나 최종 적용 여부를 단정하지 말고 현재 페이지의 실제 ID만 분류한다.
컨테이너는 descend_ids, defer_ids, rejected_ids 중 하나에, 조문은 selected_ids,
defer_ids, rejected_ids 중 하나에 정확히 한 번 넣는다. coverage는 선택한 조문이 현재
쟁점의 어느 확인 항목과 관련 있어 보이는지 표시하는 검색 주장일 뿐 검증된 법률 결론이
아니다. 제공된 evidence_windows 밖의 조문 내용을 추정하지 않는다. page cap은 최종
후보 제한이 아니므로 has_more가 있으면 route_complete를 true로 만들지 않는다.
defer_ids가 있거나 보수적으로 다시 볼 경로가 남아 있으면 route_complete는 false다.
route_complete는 현재 법령의 targeted path 탐색을 마친다는 뜻일 뿐, 법 전체에 관련
근거가 없다는 결론이 아니다.
현재 페이지에 ARTICLE item이 없으면 selected_ids와 coverage는 반드시 빈 배열이다.
실제 ID가 없는 필드를 채우기 위한 placeholder나 sentinel을 만들지 않는다.
제공되지 않은 ID, 법명, 조문 내용 또는 coverage key를 만들지 않는다."""


class LegalResearchLLMError(RuntimeError):
    """The product model or its auditable call contract failed closed."""


class ArticleTextResolver(Protocol):
    def __call__(self, instrument_id: str, node_id: object) -> str: ...


class StructuredClient(Protocol):
    backend: str
    model: str
    transport_max_retries: int
    log: list[Any]

    def structured(
        self,
        kind: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int = 16000,
        effort: str | None = "high",
        images: list[str] | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class StructuredOutputProfile:
    """Provider capability contract; canonical validation stays elsewhere."""

    backend: str
    model: str | None
    schema_profile: str
    transport_max_retries: int = TRANSPORT_MAX_RETRIES

    def __post_init__(self) -> None:
        if self.backend not in {ANTHROPIC_BACKEND, GENOS_BACKEND, OPENROUTER_BACKEND}:
            raise ValueError(f"unsupported structured-output backend: {self.backend}")
        if self.model is not None and (type(self.model) is not str or not self.model):
            raise ValueError("profile model must be a non-empty string or None")
        allowed = {
            ANTHROPIC_SCHEMA_PROFILE,
            QWEN_NATIVE_SCHEMA_PROFILE,
            QWEN_REDUCED_SCHEMA_PROFILE,
        }
        if self.schema_profile not in allowed:
            raise ValueError(f"unsupported schema profile: {self.schema_profile}")
        if self.backend == ANTHROPIC_BACKEND:
            if self.schema_profile != ANTHROPIC_SCHEMA_PROFILE:
                raise ValueError("anthropic backend requires the official schema profile")
        elif self.schema_profile == ANTHROPIC_SCHEMA_PROFILE:
            raise ValueError("OpenAI-compatible backends cannot use Anthropic projection")
        if self.transport_max_retries != TRANSPORT_MAX_RETRIES:
            raise ValueError("legal-research transport retries must remain zero")


def anthropic_haiku_profile() -> StructuredOutputProfile:
    return StructuredOutputProfile(
        backend=ANTHROPIC_BACKEND,
        model=HAIKU_MODEL,
        schema_profile=ANTHROPIC_SCHEMA_PROFILE,
    )


def onsite_qwen_profile(
    model: str | None = None,
    *,
    reduced_schema: bool = True,
) -> StructuredOutputProfile:
    """Profile for the GenOS/OpenAI-compatible onsite Qwen serving path."""

    return StructuredOutputProfile(
        backend=GENOS_BACKEND,
        model=model,
        schema_profile=(
            QWEN_REDUCED_SCHEMA_PROFILE
            if reduced_schema else QWEN_NATIVE_SCHEMA_PROFILE
        ),
    )


def selector_profile_from_environment() -> StructuredOutputProfile:
    """Resolve the selector profile without making an LLM request."""

    from lawrag.core import llm as llm_mod

    llm_mod.load_env()
    selected_backend = llm_mod.backend()
    if selected_backend == ANTHROPIC_BACKEND:
        return anthropic_haiku_profile()
    if selected_backend == GENOS_BACKEND:
        raw = os.environ.get("GENOS_LLM_SCHEMA_PROFILE", "reduced").strip().lower()
        if raw not in {"native", "reduced"}:
            raise LegalResearchLLMError(
                "GENOS_LLM_SCHEMA_PROFILE must be native or reduced"
            )
        return onsite_qwen_profile(
            os.environ.get("GENOS_LLM_MODEL") or None,
            reduced_schema=raw == "reduced",
        )
    if selected_backend == OPENROUTER_BACKEND:
        raw = os.environ.get("OPENROUTER_SCHEMA_PROFILE", "native").strip().lower()
        if raw not in {"native", "reduced"}:
            raise LegalResearchLLMError(
                "OPENROUTER_SCHEMA_PROFILE must be native or reduced"
            )
        return StructuredOutputProfile(
            backend=OPENROUTER_BACKEND,
            model=(
                os.environ.get("OPENROUTER_MODEL")
                or llm_mod.OPENROUTER_MODEL
            ),
            schema_profile=(
                QWEN_REDUCED_SCHEMA_PROFILE
                if raw == "reduced" else QWEN_NATIVE_SCHEMA_PROFILE
            ),
        )
    raise LegalResearchLLMError(f"unsupported selector backend: {selected_backend}")


def _constraint_description(values: Mapping[str, Any]) -> str:
    rendered = ", ".join(f"{key}: {value!r}" for key, value in values.items())
    return "{" + rendered + "}"


def _reduced_openai_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Project unsupported constraints into descriptions, preserving names."""

    def walk(value: Any, *, schema_node: bool = True) -> Any:
        if isinstance(value, list):
            return [walk(item, schema_node=schema_node) for item in value]
        if not isinstance(value, dict):
            return deepcopy(value)
        if not schema_node:
            return {key: walk(item, schema_node=True) for key, item in value.items()}

        result: dict[str, Any] = {}
        removed: dict[str, Any] = {}
        for key, item in value.items():
            if key in _QWEN_REDUCED_UNSUPPORTED:
                removed[key] = deepcopy(item)
                continue
            if key in {"properties", "patternProperties", "$defs", "definitions"}:
                result[key] = walk(item, schema_node=False)
            elif key in {
                "items", "additionalProperties", "contains", "not",
                "if", "then", "else", "propertyNames",
            } and isinstance(item, dict):
                result[key] = walk(item, schema_node=True)
            elif key in {"allOf", "anyOf", "oneOf", "prefixItems"}:
                result[key] = [walk(row, schema_node=True) for row in item]
            else:
                result[key] = deepcopy(item)
        if removed:
            constraint = _constraint_description(removed)
            description = str(result.get("description") or "")
            result["description"] = (
                f"{description}\n\n{constraint}" if description else constraint
            )
        return result

    return walk(deepcopy(schema))


def project_outbound_schema(
    schema: dict[str, Any],
    profile: StructuredOutputProfile,
) -> dict[str, Any]:
    """Create a provider schema while leaving the canonical input immutable."""

    if profile.schema_profile == ANTHROPIC_SCHEMA_PROFILE:
        from anthropic import transform_schema

        return transform_schema(deepcopy(schema))
    if profile.schema_profile == QWEN_NATIVE_SCHEMA_PROFILE:
        return deepcopy(schema)
    if profile.schema_profile == QWEN_REDUCED_SCHEMA_PROFILE:
        return _reduced_openai_schema(schema)
    raise LegalResearchLLMError(f"unknown schema profile: {profile.schema_profile}")


@dataclass(frozen=True)
class StructuredRequest:
    kind: str
    model: str
    system: str
    user: str
    schema: Mapping[str, Any]
    max_tokens: int = 2400
    effort: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "model": self.model,
            "system": self.system,
            "user": self.user,
            "schema": deepcopy(dict(self.schema)),
            "max_tokens": self.max_tokens,
            "effort": self.effort,
        }


def _default_llm_factory(profile: StructuredOutputProfile) -> StructuredClient:
    """Create the profiled product transport lazily, without making a request."""

    from lawrag.core import llm as llm_mod

    llm_mod.load_env()
    selected_backend = llm_mod.backend()
    if selected_backend != profile.backend:
        raise LegalResearchLLMError(
            f"selector profile requires {profile.backend}, got {selected_backend}"
        )
    if not llm_mod.available():
        raise LegalResearchLLMError(f"product LLM unavailable: {llm_mod.MISSING_HINT}")

    real = llm_mod.LLM(model=profile.model)
    if profile.backend == ANTHROPIC_BACKEND:
        import anthropic

        # The SDK default retry policy would make one logical selector invocation
        # an unknown number of provider attempts.  OpenAI-compatible requests
        # already use a requests.Session with no automatic retry adapter.
        real._client = anthropic.Anthropic(  # noqa: SLF001 - transport contract
            timeout=TRANSPORT_TIMEOUT_SECONDS,
            max_retries=TRANSPORT_MAX_RETRIES,
        )
    real.transport_max_retries = TRANSPORT_MAX_RETRIES
    return real


class ThreadLocalStructuredRecorder:
    """StructuredLLM-compatible profiled recorder with one client per thread.

    ``lawrag.core.llm.LLM.log`` is append-only, but selecting ``log[before]``
    is unsafe when several threads share one client.  A thread-local client
    makes the one-call/one-Exchange invariant deterministic without serializing
    independent legal-research branches.
    """

    def __init__(
        self,
        llm_factory: Callable[[], StructuredClient] | None = None,
        *,
        profile: StructuredOutputProfile | None = None,
    ) -> None:
        self.profile = profile or (
            anthropic_haiku_profile()
            if llm_factory is not None
            else selector_profile_from_environment()
        )
        self._factory = llm_factory or (lambda: _default_llm_factory(self.profile))
        self._local = local()
        self._lock = Lock()
        self._sequence = 0
        self.audit: list[dict[str, Any]] = []

    def _next_call_id(self) -> str:
        with self._lock:
            self._sequence += 1
            return f"legal-research-llm-{self._sequence:06d}"

    def _client(self) -> StructuredClient:
        client = getattr(self._local, "client", None)
        if client is None:
            client = self._factory()
            self._validate_client(client)
            self._local.client = client
        return client

    def _validate_client(self, client: StructuredClient) -> None:
        if getattr(client, "backend", None) != self.profile.backend:
            raise LegalResearchLLMError(
                f"selector backend must be {self.profile.backend}: "
                f"{getattr(client, 'backend', None)}"
            )
        expected_model = self.profile.model or getattr(client, "model", None)
        if not expected_model or getattr(client, "model", None) != expected_model:
            raise LegalResearchLLMError(
                f"selector model must be {expected_model}: "
                f"{getattr(client, 'model', None)}"
            )
        if (
            getattr(client, "transport_max_retries", None)
            != self.profile.transport_max_retries
        ):
            raise LegalResearchLLMError("selector transport max_retries must be 0")
        if not isinstance(getattr(client, "log", None), list):
            raise LegalResearchLLMError("selector client must expose an append-only log list")

    @property
    def backend(self) -> str:
        return self.profile.backend

    @property
    def model(self) -> str:
        if self.profile.model:
            return self.profile.model
        return str(getattr(self._client(), "model", ""))

    @property
    def receipts(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(self.audit))

    def structured(
        self,
        kind: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int = 16000,
        effort: str | None = "high",
        images: list[str] | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        if type(kind) is not str or not kind:
            raise TypeError("kind must be a non-empty string")
        if type(system) is not str or type(user) is not str:
            raise TypeError("system and user must be strings")
        if type(schema) is not dict:
            raise TypeError("schema must be a dict")
        if type(max_tokens) is not int or max_tokens < 1:
            raise TypeError("max_tokens must be a positive integer")
        if effort is not None and type(effort) is not str:
            raise TypeError("effort must be a string or None")
        if images is not None and type(images) is not list:
            raise TypeError("images must be a list or None")

        call_id = self._next_call_id()
        client = self._client()
        expected_model = self.profile.model or str(getattr(client, "model", ""))
        requested_model = model or expected_model
        if requested_model != expected_model:
            raise LegalResearchLLMError(
                f"profiled selector model must be {expected_model}: {requested_model}"
            )
        canonical_schema = deepcopy(schema)
        outbound_schema = project_outbound_schema(canonical_schema, self.profile)
        before = len(client.log)
        result: dict[str, Any] | None = None
        caught: Exception | None = None
        try:
            result = client.structured(
                kind,
                system,
                user,
                outbound_schema,
                max_tokens=max_tokens,
                effort=effort,
                images=images,
                model=expected_model,
            )
        except Exception as exc:  # preserve the exact request before propagating
            caught = exc

        new_exchanges = client.log[before:]
        exchange = new_exchanges[0] if len(new_exchanges) == 1 else None
        wrapper_errors: list[str] = []
        if caught is not None:
            wrapper_errors.append(f"{type(caught).__name__}: {caught}")
        if exchange is None:
            wrapper_errors.append(
                f"expected exactly one provider Exchange, observed {len(new_exchanges)}"
            )

        if exchange is not None and callable(getattr(exchange, "dump", None)):
            provider = deepcopy(exchange.dump())
        elif exchange is not None:
            provider = {
                key: deepcopy(getattr(exchange, key, default))
                for key, default in (
                    ("kind", kind), ("at", ""), ("model", ""), ("usage", {}),
                    ("stop_reason", ""), ("images", 0), ("dur_ms", 0),
                    ("ttft_ms", 0), ("system", system), ("user", user),
                    ("raw_response", ""), ("error", ""),
                )
            }
        else:
            provider = {
                "kind": kind,
                "at": "",
                "model": "",
                "usage": {},
                "stop_reason": "",
                "images": len(images or ()),
                "dur_ms": 0,
                "ttft_ms": 0,
                "system": system,
                "user": user,
                "raw_response": "",
                "error": "missing_provider_exchange",
            }

        provider_model = provider.get("model")
        if exchange is not None and provider_model != expected_model:
            wrapper_errors.append(
                f"provider exchange model mismatch: {provider_model!r}"
            )
        request = StructuredRequest(
            kind=kind,
            model=expected_model,
            system=system,
            user=user,
            schema=outbound_schema,
            max_tokens=max_tokens,
            effort=effort,
        ).to_dict()
        request_sha256 = hashlib.sha256(
            json.dumps(
                request, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        receipt = {
            "schema_version": "legal-research-llm-call-v2",
            "call_id": call_id,
            "kind": kind,
            "backend": self.profile.backend,
            "requested_model": expected_model,
            "provider_model": provider_model,
            "transport_max_retries": self.profile.transport_max_retries,
            "schema_profile": self.profile.schema_profile,
            "canonical_schema": canonical_schema,
            "outbound_schema": deepcopy(outbound_schema),
            "request_sha256": request_sha256,
            "request": request,
            "provider": provider,
            "structured_output": deepcopy(result),
            "wrapper_error": "; ".join(wrapper_errors),
        }
        with self._lock:
            self.audit.append(receipt)

        if caught is not None:
            raise caught
        if exchange is None:
            raise LegalResearchLLMError(receipt["wrapper_error"])
        if provider_model != expected_model:
            raise LegalResearchLLMError(receipt["wrapper_error"])
        return result


def _anthropic_outbound_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Transform one caller-owned schema with the official SDK projection."""

    return project_outbound_schema(schema, anthropic_haiku_profile())


def _require_object(
    value: object,
    *,
    required: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an object")
    keys = set(value)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing or extra:
        raise ValueError(f"{label} fields mismatch; missing={missing}, extra={extra}")
    return value


def _require_string(value: object, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be a string")
    return value


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{label} must be a boolean")
    return value


def _require_int(value: object, label: str) -> int:
    # bool is a subclass of int; exact type is intentional at this boundary.
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    return value


def _require_list(value: object, label: str) -> list[Any]:
    if type(value) is not list:
        raise TypeError(f"{label} must be an array")
    return value


def _string_list(value: object, label: str) -> list[str]:
    rows = _require_list(value, label)
    for index, row in enumerate(rows):
        _require_string(row, f"{label}[{index}]")
    return rows


def parse_instrument_route_decision(
    page: InstrumentRoutePage,
    value: Mapping[str, Any] | object,
) -> InstrumentRouteDecision:
    """Strictly parse a provider object, then reuse the closed law validator."""

    raw = _require_object(
        value,
        required=frozenset({
            "page_id", "choices", "rejected_menu_ids", "route_complete",
            "rationale",
        }),
        label="instrument route decision",
    )
    choices: list[InstrumentRouteChoice] = []
    for index, row in enumerate(_require_list(raw["choices"], "choices")):
        item = _require_object(
            row,
            required=frozenset({"menu_id", "fallback_rank"}),
            label=f"choices[{index}]",
        )
        choices.append(InstrumentRouteChoice(
            menu_id=_require_string(item["menu_id"], f"choices[{index}].menu_id"),
            fallback_rank=_require_int(
                item["fallback_rank"], f"choices[{index}].fallback_rank",
            ),
        ))
    decision = InstrumentRouteDecision(
        page_id=_require_string(raw["page_id"], "page_id"),
        choices=tuple(choices),
        rejected_menu_ids=tuple(_string_list(
            raw["rejected_menu_ids"], "rejected_menu_ids",
        )),
        route_complete=_require_bool(raw["route_complete"], "route_complete"),
        rationale=_require_string(raw["rationale"], "rationale"),
    )
    validate_route_decision(page, decision)
    return decision


def parse_article_page_decision(
    page: CandidatePage,
    value: Mapping[str, Any] | object,
) -> PageDecision:
    """Strict page parser that forbids implicit loss before controller apply."""

    raw = _require_object(
        value,
        required=frozenset({
            "page_id", "selected_ids", "descend_ids", "defer_ids",
            "rejected_ids", "coverage", "route_complete", "rationale",
        }),
        label="article page decision",
    )
    normalized: dict[str, Any] = {
        "page_id": _require_string(raw["page_id"], "page_id"),
        "selected_ids": _string_list(raw["selected_ids"], "selected_ids"),
        "descend_ids": _string_list(raw["descend_ids"], "descend_ids"),
        "defer_ids": _string_list(raw["defer_ids"], "defer_ids"),
        "rejected_ids": _string_list(raw["rejected_ids"], "rejected_ids"),
        "coverage": [],
        "route_complete": _require_bool(raw["route_complete"], "route_complete"),
        "rationale": _require_string(raw["rationale"], "rationale"),
    }
    coverage_ids: set[str] = set()
    for index, row in enumerate(_require_list(raw["coverage"], "coverage")):
        item = _require_object(
            row,
            required=frozenset({"id", "keys"}),
            label=f"coverage[{index}]",
        )
        item_id = _require_string(item["id"], f"coverage[{index}].id")
        if item_id in coverage_ids:
            raise ClosedMenuViolation(f"duplicate coverage row for {item_id}")
        coverage_ids.add(item_id)
        normalized["coverage"].append({
            "id": item_id,
            "keys": _string_list(item["keys"], f"coverage[{index}].keys"),
        })

    dispositions = (
        normalized["selected_ids"] + normalized["descend_ids"]
        + normalized["defer_ids"] + normalized["rejected_ids"]
    )
    offered = {item.id for item in page.items}
    supplied = set(dispositions)
    unknown = sorted(supplied - offered)
    if unknown:
        raise ClosedMenuViolation(
            f"page disposition contains unknown IDs: {unknown}"
        )
    missing = sorted(offered - supplied)
    if missing:
        raise ClosedMenuViolation(
            f"every page item needs an explicit disposition: {missing}"
        )
    if normalized["route_complete"] and normalized["defer_ids"]:
        raise ClosedMenuViolation(
            "route_complete cannot discard explicitly deferred items"
        )

    decision = PageDecision.from_mapping(page, normalized)
    # ``from_mapping`` already validates, but keeping this call visible makes
    # the dependency on the controller's runtime boundary explicit.
    validate_page_decision(page, decision)
    return decision


_AUTHORITY_FAMILIES = frozenset({
    "AUTHORITY", "LEGAL_BASIS", "DELEGATION", "ENTRUSTMENT",
    "NEGATIVE_AUTHORITY",
})
_DETAIL_FAMILIES = frozenset({
    "FORMULA", "THRESHOLD", "TEMPORAL", "FILING_DOCUMENT",
})


def _roles_for_family(family_id: str) -> tuple[InstrumentRole, ...]:
    if family_id in _AUTHORITY_FAMILIES:
        return (
            InstrumentRole.PRIMARY_ACT,
            InstrumentRole.CROSS_CUTTING_ACT,
            InstrumentRole.DELEGATED_LEGISLATION,
            InstrumentRole.SUPERVISORY_RULE,
        )
    if family_id in _DETAIL_FAMILIES:
        return (
            InstrumentRole.SELF_REGULATORY_RULE,
            InstrumentRole.SUPERVISORY_RULE,
            InstrumentRole.IMPLEMENTATION_DETAIL,
            InstrumentRole.DELEGATED_LEGISLATION,
            InstrumentRole.PRIMARY_ACT,
        )
    return (
        InstrumentRole.PRIMARY_ACT,
        InstrumentRole.DELEGATED_LEGISLATION,
        InstrumentRole.SUPERVISORY_RULE,
        InstrumentRole.IMPLEMENTATION_DETAIL,
    )


def _clean_hint(value: object, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _plan_projection(plan: Mapping[str, Any] | None) -> dict[str, Any]:
    """Whitelist product-plan fields; reference/gold keys cannot enter a call."""

    value = plan if isinstance(plan, Mapping) else {}
    families: list[str] = []
    for row in value.get("family_hypotheses") or ():
        if not isinstance(row, Mapping):
            continue
        family = str(row.get("family_id") or "")
        if family in query_grounding.FAMILY_IDS and family not in families:
            families.append(family)
        if len(families) >= 4:
            break

    predicates: list[str] = []
    for row in value.get("predicate_hypotheses") or ():
        if not isinstance(row, Mapping):
            continue
        predicate = str(row.get("predicate") or "")
        if predicate in query_grounding.PREDICATE_IDS and predicate not in predicates:
            predicates.append(predicate)
        if len(predicates) >= 8:
            break

    mentions: list[dict[str, Any]] = []
    for row in value.get("mentions") or ():
        if not isinstance(row, Mapping):
            continue
        surface = _clean_hint(row.get("surface"), 120)
        start, end = row.get("start"), row.get("end")
        role = str(row.get("role") or "OTHER")
        if (
            surface and type(start) is int and type(end) is int
            and role in query_grounding.MENTION_ROLES
        ):
            mentions.append({
                "surface": surface, "start": start, "end": end, "role": role,
            })
        if len(mentions) >= 16:
            break

    expansions: dict[str, list[str]] = {"exact": [], "fulltext": [], "vector": []}
    nested = value.get("expansion_terms")
    if isinstance(nested, Mapping):
        sources = {
            "exact": nested.get("exact"),
            "fulltext": nested.get("fulltext"),
            "vector": nested.get("vector"),
        }
    else:
        sources = {
            "exact": value.get("exact_terms"),
            "fulltext": value.get("fulltext_queries"),
            "vector": value.get("vector_queries"),
        }
    caps = {"exact": (10, 80), "fulltext": (3, 220), "vector": (3, 160)}
    for kind, rows in sources.items():
        cap, limit = caps[kind]
        if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
            continue
        for row in rows:
            cleaned = _clean_hint(row, limit)
            if cleaned and cleaned not in expansions[kind]:
                expansions[kind].append(cleaned)
            if len(expansions[kind]) >= cap:
                break
    return {
        "family_hypotheses": families,
        "predicate_hypotheses": predicates,
        "mentions": mentions,
        "expansion_terms": expansions,
    }


def _topic_hints(projection: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for row in projection.get("mentions") or ():
        if isinstance(row, Mapping):
            values.append(str(row.get("surface") or ""))
    expansions = projection.get("expansion_terms") or {}
    if isinstance(expansions, Mapping):
        for key in ("exact", "fulltext", "vector"):
            values.extend(str(item) for item in expansions.get(key) or ())
    accepted: list[str] = []
    for value in values:
        cleaned = _clean_hint(value, 160)
        if cleaned and cleaned not in accepted:
            accepted.append(cleaned)
        if len(accepted) >= 12:
            break
    return tuple(accepted)


def branches_from_query_plan(
    plan: Mapping[str, Any] | None,
) -> tuple[InstrumentRouteBranch, ...]:
    """Convert a product query plan to at most four gold-free issue branches."""

    projection = _plan_projection(plan)
    families = list(projection["family_hypotheses"][:4])
    if not families:
        families = ["GENERAL_LEGAL_RESEARCH"]
    hints = _topic_hints(projection)
    return tuple(
        InstrumentRouteBranch(
            branch_id=f"qf-{position:02d}-{family.lower().replace('_', '-')}",
            issue_axis=family,
            preferred_roles=_roles_for_family(family),
            topic_hints=hints,
            preferred_instrument_ids=(),
            required=True,
        )
        for position, family in enumerate(families, 1)
    )


def plan_question(
    recorder: ThreadLocalStructuredRecorder,
    question: str,
) -> dict[str, Any]:
    """Run the existing schema-grounded, question-only product plan call."""

    if type(question) is not str or not question.strip():
        raise ValueError("question must be a non-empty string")
    return query_grounding.plan_query(recorder, question, model=recorder.model)


@dataclass(frozen=True)
class _SearchTerm:
    value: str
    source: str
    priority: int


_QUESTION_TOKEN = re.compile(r"[0-9A-Za-z가-힣_·-]{2,}")
_QUESTION_QUANTITY = re.compile(r"\d+\s*분의\s*\d+|\d+(?:\.\d+)?\s*%")


def _window_terms(
    question: str,
    projection: Mapping[str, Any],
) -> tuple[_SearchTerm, ...]:
    candidates: list[_SearchTerm] = []
    expansions = projection.get("expansion_terms") or {}
    if isinstance(expansions, Mapping):
        for source, priority in (("exact", 0), ("fulltext", 1), ("vector", 2)):
            for value in expansions.get(source) or ():
                candidates.append(_SearchTerm(str(value), f"plan.{source}", priority))
    for row in projection.get("mentions") or ():
        if isinstance(row, Mapping):
            candidates.append(_SearchTerm(
                str(row.get("surface") or ""), "plan.mention", 0,
            ))
    for match in _QUESTION_QUANTITY.finditer(question):
        candidates.append(_SearchTerm(match.group(0), "question.quantity", 1))
    if 2 <= len(question.strip()) <= 180:
        candidates.append(_SearchTerm(question.strip(), "question.full", 3))
    for token in _QUESTION_TOKEN.findall(question):
        candidates.append(_SearchTerm(token, "question.token", 4))

    accepted: list[_SearchTerm] = []
    seen: set[str] = set()
    for row in sorted(candidates, key=lambda item: (item.priority, -len(item.value))):
        value = _clean_hint(row.value, 220)
        key = value.casefold()
        if len(value) < 2 or key in seen:
            continue
        seen.add(key)
        accepted.append(_SearchTerm(value, row.source, row.priority))
        if len(accepted) >= 40:
            break
    return tuple(accepted)


def _term_matches(text: str, term: _SearchTerm) -> list[dict[str, Any]]:
    pieces = re.split(r"\s+", term.value.strip())
    pattern = r"\s+".join(re.escape(piece) for piece in pieces if piece)
    if not pattern:
        return []
    matches = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        matches.append({
            "query_term": term.value,
            "source": term.source,
            "start": match.start(),
            "end": match.end(),
            "matched_text": text[match.start():match.end()],
        })
        if len(matches) >= 2:
            break
    return matches


_WINDOW_RADIUS = 220
_MAX_WINDOWS_PER_ITEM = 4
_MAX_WINDOW_CHARS_PER_ITEM = 2200
_HEAD_FALLBACK_CHARS = 320


def _evidence_windows(
    text: str,
    terms: Sequence[_SearchTerm],
) -> list[dict[str, Any]]:
    hits: list[tuple[int, int, dict[str, Any]]] = []
    for order, term in enumerate(terms):
        for match in _term_matches(text, term):
            hits.append((term.priority, order, match))
    hits.sort(key=lambda row: (row[0], row[1], row[2]["start"]))

    ranges: list[list[int]] = []
    for _priority, _order, match in hits:
        start = max(0, int(match["start"]) - _WINDOW_RADIUS)
        end = min(len(text), int(match["end"]) + _WINDOW_RADIUS)
        overlap = next(
            (row for row in ranges if start <= row[1] and end >= row[0]),
            None,
        )
        if overlap is not None:
            proposed_start = min(overlap[0], start)
            proposed_end = max(overlap[1], end)
            total = sum(row[1] - row[0] for row in ranges if row is not overlap)
            if total + proposed_end - proposed_start <= _MAX_WINDOW_CHARS_PER_ITEM:
                overlap[0], overlap[1] = proposed_start, proposed_end
            continue
        if len(ranges) >= _MAX_WINDOWS_PER_ITEM:
            continue
        if sum(row[1] - row[0] for row in ranges) + end - start > _MAX_WINDOW_CHARS_PER_ITEM:
            continue
        ranges.append([start, end])

    if not ranges and text:
        ranges = [[0, min(len(text), _HEAD_FALLBACK_CHARS)]]
    ranges.sort(key=lambda row: row[0])

    windows: list[dict[str, Any]] = []
    all_matches = [row[2] for row in hits]
    for index, (start, end) in enumerate(ranges, 1):
        matched = [
            deepcopy(row) for row in all_matches
            if start <= int(row["start"]) and int(row["end"]) <= end
        ][:24]
        windows.append({
            "window_id": f"window-{index}",
            "char_start": start,
            "char_end": end,
            "text": text[start:end],
            "matched_terms": matched,
            "window_kind": "TERM_MATCH" if matched else "HEAD_FALLBACK",
        })
    return windows


def _kind_value(item: object) -> str:
    kind = getattr(item, "kind", "")
    return str(getattr(kind, "value", kind)).upper()


def _coordinate(item: object) -> str:
    value = getattr(item, "coordinate", None)
    if isinstance(value, str) and value:
        return value
    return f"{getattr(item, 'instrument_id')}:{getattr(item, 'node_id')}"


class AtlasArticleTextResolver:
    """Read exact article text from the atlas's current, scoped index."""

    def __init__(self, atlas: object) -> None:
        self.atlas = atlas

    def __call__(self, instrument_id: str, node_id: object) -> str:
        index = getattr(self.atlas, "current_index", None)
        views = getattr(index, "entry_docs", None) or getattr(index, "docs", None)
        view = views.get(str(instrument_id)) if isinstance(views, Mapping) else None
        node = getattr(view, "by_id", {}).get(node_id) if view is not None else None
        if view is None or node is None:
            raise LegalResearchLLMError(
                f"article text unavailable for {instrument_id}:{node_id}"
            )
        text = view.section_text(dict(node), cap=10**9)
        if type(text) is not str:
            raise LegalResearchLLMError(
                f"article text resolver returned {type(text).__name__}"
            )
        return text


def _article_item_payload(
    item: object,
    *,
    terms: Sequence[_SearchTerm],
    text_resolver: ArticleTextResolver,
) -> dict[str, Any]:
    kind = _kind_value(item)
    row = {
        "id": getattr(item, "id"),
        "instrument_id": getattr(item, "instrument_id"),
        "node_id": getattr(item, "node_id"),
        "parent_node_id": getattr(item, "parent_node_id"),
        "coordinate": _coordinate(item),
        "path": str(getattr(item, "path", "")),
        "label": str(getattr(item, "label", "")),
        "kind": kind,
        "has_children": bool(getattr(item, "has_children", False)),
    }
    if kind != "ARTICLE":
        row["source"] = {
            "status": "STRUCTURAL_ONLY",
            "text_length": 0,
            "text_sha256": None,
            "evidence_windows": [],
        }
        return row

    text = text_resolver(str(getattr(item, "instrument_id")), getattr(item, "node_id"))
    if type(text) is not str:
        raise LegalResearchLLMError("article text resolver must return a string")
    row["source"] = {
        "status": "EXACT_WINDOWED_SOURCE",
        "text_length": len(text),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "evidence_windows": _evidence_windows(text, terms),
    }
    return row


def build_article_model_request(
    question: str,
    page: CandidatePage,
    query_plan: Mapping[str, Any] | None,
    text_resolver: ArticleTextResolver,
    *,
    model: str = HAIKU_MODEL,
) -> StructuredRequest:
    """Build a gold-free closed-page request from exact, bounded source windows."""

    if type(question) is not str or not question.strip():
        raise ValueError("question must be a non-empty string")
    projection = _plan_projection(query_plan)
    terms = _window_terms(question, projection)
    page_value = page.to_dict()
    page_value["items"] = [
        _article_item_payload(item, terms=terms, text_resolver=text_resolver)
        for item in page.items
    ]
    payload = {
        "question": question,
        "query_plan": projection,
        "window_terms": [
            {"term": term.value, "source": term.source} for term in terms
        ],
        "article_page": page_value,
        "instruction": (
            "각 item을 정확히 한 disposition에 넣고, 조문 내용은 exact source "
            "offset이 붙은 evidence_windows만 근거로 사용한다. ARTICLE item이 없으면 "
            "selected_ids와 coverage를 빈 배열로 두고 placeholder를 만들지 않는다."
        ),
    }
    return StructuredRequest(
        kind="rag.legal_research.article_route",
        model=model,
        system=ARTICLE_SYSTEM,
        user=json.dumps(payload, ensure_ascii=False, indent=2),
        schema=decision_schema(page),
        max_tokens=2600,
        effort=None,
    )


def _execute_request(
    recorder: ThreadLocalStructuredRecorder,
    request: StructuredRequest | RouteModelRequest,
) -> dict[str, Any]:
    raw = recorder.structured(
        request.kind,
        request.system,
        request.user,
        dict(request.schema),
        max_tokens=request.max_tokens,
        effort=request.effort,
        model=request.model,
    )
    if type(raw) is not dict:
        provider_error = ""
        if recorder.audit:
            provider_error = str(recorder.audit[-1].get("provider", {}).get("error") or "")
        raise LegalResearchLLMError(
            f"structured selector returned no JSON object: {provider_error or type(raw).__name__}"
        )
    return raw


class InstrumentRouteSelector:
    def __init__(self, recorder: ThreadLocalStructuredRecorder) -> None:
        self.recorder = recorder

    def select(
        self,
        question: str,
        page: InstrumentRoutePage,
    ) -> InstrumentRouteDecision:
        request = build_route_model_request(
            question, page, model=self.recorder.model,
        )
        raw = _execute_request(self.recorder, request)
        return parse_instrument_route_decision(page, raw)


class ArticlePageSelector:
    def __init__(
        self,
        recorder: ThreadLocalStructuredRecorder,
        query_plan: Mapping[str, Any] | None,
        text_resolver: ArticleTextResolver,
    ) -> None:
        self.recorder = recorder
        self.query_plan = deepcopy(dict(query_plan or {}))
        self.text_resolver = text_resolver

    def select(self, question: str, page: CandidatePage) -> PageDecision:
        request = build_article_model_request(
            question, page, self.query_plan, self.text_resolver,
            model=self.recorder.model,
        )
        raw = _execute_request(self.recorder, request)
        return parse_article_page_decision(page, raw)


# Backward-compatible names for ADR-0110 callers.  The implementations are now
# profiled rather than Haiku-specific.
HaikuInstrumentRouteSelector = InstrumentRouteSelector
HaikuArticlePageSelector = ArticlePageSelector


__all__ = [
    "ANTHROPIC_BACKEND",
    "ANTHROPIC_SCHEMA_PROFILE",
    "ARTICLE_SYSTEM",
    "ArticlePageSelector",
    "AtlasArticleTextResolver",
    "GENOS_BACKEND",
    "HAIKU_MODEL",
    "HaikuArticlePageSelector",
    "HaikuInstrumentRouteSelector",
    "LegalResearchLLMError",
    "OPENROUTER_BACKEND",
    "QWEN_NATIVE_SCHEMA_PROFILE",
    "QWEN_REDUCED_SCHEMA_PROFILE",
    "StructuredRequest",
    "StructuredOutputProfile",
    "ThreadLocalStructuredRecorder",
    "TRANSPORT_MAX_RETRIES",
    "TRANSPORT_TIMEOUT_SECONDS",
    "branches_from_query_plan",
    "anthropic_haiku_profile",
    "build_article_model_request",
    "onsite_qwen_profile",
    "parse_article_page_decision",
    "parse_instrument_route_decision",
    "plan_question",
    "project_outbound_schema",
    "selector_profile_from_environment",
    "InstrumentRouteSelector",
]
