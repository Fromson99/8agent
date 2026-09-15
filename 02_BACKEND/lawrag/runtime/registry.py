"""Production-only runtime component registry.

ADR research modules are deliberately not accepted here.  A candidate becomes
selectable only after its reviewed code is copied into ``lawrag.runtime.components``
and registered below; MAIN promotion then switches the stable profile ID.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable


PRODUCTION_PREFIX = "lawrag.runtime.components."


@dataclass(frozen=True)
class RuntimeSpec:
    profile_id: str
    module: str
    callable_name: str
    source_adr: str
    description: str


_SPECS = {
    "legalclosure-v2": RuntimeSpec(
        profile_id="legalclosure-v2",
        module="lawrag.runtime.components.legalclosure_v2",
        callable_name="retrieve",
        source_adr="ADR-0021",
        description="현재 운영 LegalClosure 기준선; 연구 extension은 실행하지 않음",
    ),
    "ontology-rag-v1": RuntimeSpec(
        profile_id="ontology-rag-v1",
        module="lawrag.runtime.components.ontology_rag_v1",
        callable_name="retrieve",
        source_adr="ADR-0175",
        description="모호 surface를 차단하고 검증된 DefinitionProjection ClauseSpan만 LegalClosure 바닥에 가산",
    ),
}


def specs() -> list[dict[str, str]]:
    return [spec.__dict__.copy() for spec in _SPECS.values()]


def validate_profile_id(profile_id: str) -> None:
    spec = _SPECS.get(profile_id)
    if spec is None:
        raise ValueError(f"unregistered production runtime profile: {profile_id}")
    if not spec.module.startswith(PRODUCTION_PREFIX):
        raise ValueError(
            f"production profile must live under {PRODUCTION_PREFIX}: {spec.module}"
        )


def current_profile_id() -> str:
    from lawrag.platform import main_promotion

    profile_id = main_promotion.runtime_profile_id()
    validate_profile_id(profile_id)
    return profile_id


def load(profile_id: str) -> Callable[..., Any]:
    validate_profile_id(profile_id)
    spec = _SPECS[profile_id]
    module = import_module(spec.module)
    target = getattr(module, spec.callable_name, None)
    if not callable(target):
        raise ValueError(
            f"runtime component callable missing: {spec.module}:{spec.callable_name}"
        )
    return target


def retrieve(*args, **kwargs):
    """Run the atomically selected production profile."""
    return load(current_profile_id())(*args, **kwargs)
