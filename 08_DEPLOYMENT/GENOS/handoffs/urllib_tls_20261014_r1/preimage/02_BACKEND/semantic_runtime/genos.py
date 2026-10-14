"""GENOS OpenAI-compatible transport and connection diagnostics.

This module owns endpoint construction, authentication headers, retries, and
response validation. Callers own prompts and interpretation of model output.
No credential or provider response body is included in raised errors.
"""
from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from . import observability as obs


RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_SERVING_PATH = "/api/gateway/rep/serving/{serving_id}"
_KNOWN_SUFFIXES = ("/chat/completions", "/embeddings", "/models")
log = obs.get_logger("transport")


class ServingError(RuntimeError):
    """A classified, credential-safe upstream serving failure."""


@dataclass(frozen=True)
class Endpoint:
    """One OpenAI-compatible API root (the address corresponding to ``/v1``)."""

    root: str
    label: str
    connect_timeout: float = 5.0
    read_timeout: float = 120.0
    max_retries: int = 3
    headers: dict[str, str] = field(default_factory=dict)

    def url(self, path: str) -> str:
        return self.root + "/" + path.lstrip("/")


def _canonical_root(value: str, api_prefix: str = "/v1") -> str:
    raw = value.strip().rstrip("/")
    for suffix in _KNOWN_SUFFIXES:
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)].rstrip("/")
            break
    parsed = urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid GENOS endpoint")
    normalized_prefix = api_prefix.strip()
    if normalized_prefix.casefold() in {"", "none", "off"}:
        return raw
    if normalized_prefix != "/v1":
        raise ValueError("GENOS API prefix must be /v1 or none")
    return raw if raw.endswith("/v1") else raw + "/v1"


def endpoint(
    base_url: str,
    *,
    serving_id: str = "",
    token: str = "",
    user_id: str = "",
    label: str = "GENOS",
    connect_timeout: float = 5.0,
    read_timeout: float = 120.0,
    max_retries: int = 3,
    api_prefix: str | None = None,
) -> Endpoint:
    """Build an endpoint from either a direct serving URL or a GENOS base URL."""

    raw = base_url.strip().rstrip("/")
    if serving_id:
        if not serving_id.isdigit():
            raise ValueError("GENOS serving ID must be numeric")
        raw += _SERVING_PATH.format(serving_id=serving_id)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if user_id:
        headers["x-genos-user-id"] = user_id
    return Endpoint(
        root=_canonical_root(raw, api_prefix if api_prefix is not None else ("none" if serving_id else "/v1")),
        label=label,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        max_retries=max_retries,
        headers=headers,
    )


def from_env(kind: str, *, environ=None) -> tuple[Endpoint, str]:
    """Resolve the LLM or embedding endpoint and configured model from env."""

    if kind not in {"llm", "embed"}:
        raise ValueError("kind must be llm or embed")
    settings = os.environ if environ is None else environ
    prefix = "GENOS_LLM" if kind == "llm" else "GENOS_EMBED"

    def value(suffix: str) -> str:
        return (settings.get(f"{prefix}_{suffix}") or "").strip()

    direct = (settings.get(f"{prefix}_URL") or "").strip()
    serving_id = value("SERVING_ID")
    base = direct or (settings.get("GENOS_BASE_URL") or "").strip()
    if not base:
        raise ValueError(f"{prefix} endpoint is not configured")
    if not direct and not serving_id:
        raise ValueError(f"{prefix} serving ID is not configured")
    connect_timeout = float(settings.get(f'{prefix}_CONNECT_TIMEOUT') or ('60' if kind == 'llm' else '5'))
    if not math.isfinite(connect_timeout) or connect_timeout <= 0:
        raise ValueError(f'{prefix}_CONNECT_TIMEOUT must be positive and finite')
    target = endpoint(
        base,
        serving_id="" if direct else serving_id,
        token=value("KEY"),
        user_id=(
            (settings.get("GENOS_USER_ID") or "").strip()
            if kind == "llm"
            else (settings.get("GENOS_EMBED_TENANT_ID") or "").strip()
        ),
        label=f"GENOS {kind}",
        connect_timeout=connect_timeout,
        read_timeout=float(settings.get(f"{prefix}_TIMEOUT", "120")),
        max_retries=int(settings.get(f"{prefix}_MAX_RETRIES", "3")),
        # Integration branch gateways expose /models and /chat/completions
        # directly. Legacy *_API_PREFIX applies only to direct model servers.
        api_prefix=(
            settings.get("GENOS_GATEWAY_API_PREFIX", "none")
            if not direct or "/api/gateway/rep/serving/" in urlsplit(base).path
            else settings.get(f"{prefix}_API_PREFIX", "/v1")
        ),
    )
    return target, value("MODEL")


def request_json(
    target: Endpoint,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    session=None,
) -> dict[str, Any]:
    """Issue one GET/POST request, retrying only network, 429, and transient 5xx."""

    import httpx

    owned = session is None
    client = session if session is not None else httpx.Client(trust_env=True, follow_redirects=False)
    last = ""
    last_exception = None
    try:
        for attempt in range(1, target.max_retries + 1):
            attempt_started = time.monotonic()
            obs.event(
                log,
                "transport.request.started",
                label=target.label,
                method="GET" if payload is None else "POST",
                endpoint=target.url(path),
                attempt=attempt,
                max_retries=target.max_retries,
                connect_timeout=target.connect_timeout,
                read_timeout=target.read_timeout,
            )
            try:
                response = client.request(
                    "GET" if payload is None else "POST",
                    target.url(path),
                    headers=target.headers,
                    json=payload,
                    timeout=httpx.Timeout(target.read_timeout, connect=target.connect_timeout),
                    follow_redirects=False,
                )
            except httpx.RequestError as exc:
                last = type(exc).__name__
                last_exception = exc
                obs.event(
                    log,
                    "transport.request.error",
                    level=40,
                    label=target.label,
                    attempt=attempt,
                    duration_ms=int((time.monotonic() - attempt_started) * 1000),
                    error_type=type(exc).__name__,
                )
            else:
                obs.event(
                    log,
                    "transport.response.received",
                    level=20 if response.status_code < 400 else 30,
                    label=target.label,
                    attempt=attempt,
                    http_status=response.status_code,
                    duration_ms=int((time.monotonic() - attempt_started) * 1000),
                    content_type=getattr(response, "headers", {}).get("content-type", ""),
                    response_bytes=len(getattr(response, "content", b"")),
                )
                if 200 <= response.status_code < 300:
                    try:
                        value = response.json()
                    except ValueError as exc:
                        raise ServingError(f"{target.label} returned invalid JSON") from exc
                    if not isinstance(value, dict):
                        raise ServingError(f"{target.label} returned a non-object JSON response")
                    return value
                if response.status_code not in RETRY_STATUS:
                    raise ServingError(f"{target.label} HTTP {response.status_code}")
                last = f"HTTP {response.status_code}"
                last_exception = None
            if attempt < target.max_retries:
                time.sleep(2.0 * attempt)
        raise ServingError(
            f"{target.label} request failed after {target.max_retries} attempts: {last}"
        ) from last_exception
    finally:
        if owned:
            client.close()


def advertised_model(target: Endpoint, configured: str = "") -> str:
    value = request_json(target, "/models")
    rows = value.get("data")
    if not isinstance(rows, list):
        raise ServingError(f"{target.label} returned an invalid model list")
    ids = [
        row["id"]
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and row["id"]
    ]
    if configured:
        if configured not in ids:
            raise ServingError(f"{target.label} configured model is not advertised")
        return configured
    if len(ids) != 1:
        raise ServingError(
            f"{target.label} requires an explicit model when {len(ids)} models are advertised"
        )
    return ids[0]


def check(
    kind: str, *, execute: bool = False, _vector_sink: list[float] | None = None
) -> dict[str, Any]:
    """Model-list diagnostic, or tiny inference (gateway POST skips discovery)."""

    started = time.monotonic()
    result: dict[str, Any] = {"component": kind, "generation_requested": execute}
    try:
        target, configured = from_env(kind)
        if execute and "/api/gateway/rep/serving/" in urlsplit(target.root).path:
            # Match the integration branch: serving ID routes the request;
            # model discovery is a separate diagnostic, not a POST prerequisite.
            model = configured or "genos"
            result.update(model=model, models="NOT_RUN")
        else:
            model = advertised_model(target, configured)
            result.update(model=model, models="PASS")
        if execute:
            payload = (
                {
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 32,
                    "temperature": 0,
                    "stream": False,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
                if kind == "llm"
                else {"model": model, "input": ["GENOS connectivity check"]}
            )
            value = request_json(
                target,
                "/chat/completions" if kind == "llm" else "/embeddings",
                payload,
            )
            if kind == "llm":
                content = value["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ServingError("GENOS llm returned empty content")
                result["response_chars"] = len(content)
                result["usage"] = value.get("usage") or {}
            else:
                vector = value["data"][0]["embedding"]
                if (
                    not isinstance(vector, list)
                    or not vector
                    or any(
                        type(item) not in {int, float} or not math.isfinite(item)
                        for item in vector
                    )
                ):
                    raise ServingError("GENOS embed returned an invalid vector")
                if _vector_sink is not None:
                    _vector_sink.extend(float(item) for item in vector)
                result["dimensions"] = len(vector)
            result["inference"] = "PASS"
        else:
            result["inference"] = "NOT_RUN"
        result["status"] = "PASS"
    except Exception as exc:
        from .genos_backend import error_detail
        result.update(status="FAIL", error=type(exc).__name__, error_detail=error_detail(exc))
    result["seconds"] = round(time.monotonic() - started, 3)
    return result


def _vdb_endpoint() -> tuple[Endpoint, str]:
    """Resolve the direct Weaviate endpoint used by the GENOS vector DB."""

    raw = os.environ.get("GENOS_VDB_URL", "").strip()
    collection = os.environ.get("GENOS_VDB_COLLECTION", "").strip()
    if not raw:
        raise ValueError("GENOS_VDB_URL is not configured")
    if "/api/gateway/rep/serving/" in raw:
        raise ValueError("GENOS_VDB_URL must be the direct Weaviate URL")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", collection):
        raise ValueError("GENOS_VDB_COLLECTION is missing or invalid")
    target = endpoint(
        raw,
        token=os.environ.get("GENOS_VDB_TOKEN", "").strip(),
        label="GENOS vdb",
        read_timeout=float(os.environ.get("GENOS_VDB_TIMEOUT", "30")),
        max_retries=int(os.environ.get("GENOS_VDB_MAX_RETRIES", "2")),
        api_prefix="/v1",
    )
    return target, collection


def check_vdb(vector: list[float]) -> dict[str, Any]:
    """Verify schema access and execute one read-only nearVector query."""

    started = time.monotonic()
    result: dict[str, Any] = {"component": "vdb", "query": "nearVector"}
    try:
        if not vector or any(
            type(item) not in {int, float} or not math.isfinite(item) for item in vector
        ):
            raise ValueError("embedding vector is invalid")
        target, collection = _vdb_endpoint()
        schema = request_json(target, f"/schema/{collection}")
        advertised = schema.get("class") or schema.get("name")
        if advertised not in {None, collection}:
            raise ServingError("GENOS vdb returned a different collection")
        literal = ",".join(format(float(item), ".9g") for item in vector)
        query = (
            "{Get{" + collection + "(nearVector:{vector:[" + literal
            + "]},limit:1){_additional{id distance}}}}"
        )
        value = request_json(target, "/graphql", {"query": query})
        errors = value.get("errors")
        if errors:
            raise ServingError("GENOS vdb rejected the nearVector query")
        data = value.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("Get"), dict):
            raise ServingError("GENOS vdb returned an invalid GraphQL response")
        rows = data["Get"].get(collection)
        if not isinstance(rows, list):
            raise ServingError("GENOS vdb returned an invalid collection result")
        result.update(
            status="PASS",
            schema="PASS",
            vector_query="PASS",
            collection=collection,
            objects_returned=len(rows),
            dimensions=len(vector),
        )
    except Exception as exc:
        from .genos_backend import error_detail
        result.update(status="FAIL", error=type(exc).__name__, error_detail=error_detail(exc))
    result["seconds"] = round(time.monotonic() - started, 3)
    return result


def diagnostics() -> dict[str, Any]:
    """Run one real LLM, embedding, and VDB vector-read connectivity check."""

    llm = check("llm", execute=True)
    vector: list[float] = []
    embed = check("embed", execute=True, _vector_sink=vector)
    vdb = check_vdb(vector)
    checks = [llm, embed, vdb]
    return {"ok": all(row["status"] == "PASS" for row in checks), "checks": checks}


def smoke(*, execute: bool = False) -> dict[str, Any]:
    if type(execute) is not bool:
        raise ValueError("execute must be boolean")
    checks = [check("llm", execute=execute), check("embed", execute=execute)]
    return {"ok": all(row["status"] == "PASS" for row in checks), "checks": checks}


__all__ = [
    "Endpoint",
    "RETRY_STATUS",
    "ServingError",
    "advertised_model",
    "check",
    "check_vdb",
    "diagnostics",
    "endpoint",
    "from_env",
    "request_json",
    "smoke",
]
