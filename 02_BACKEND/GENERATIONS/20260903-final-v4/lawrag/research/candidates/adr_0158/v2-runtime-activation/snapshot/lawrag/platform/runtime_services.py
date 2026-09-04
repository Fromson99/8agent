"""Release-proved descriptors and active ACL admission for result-affecting services."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping
from urllib.parse import urlsplit


class RuntimeServiceContractError(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RuntimeServiceContractError(f"{field} must be exact non-empty text")
    if any(ord(character) < 32 for character in value):
        raise RuntimeServiceContractError(f"{field} contains a control character")
    return value


def _url(value: object, field: str) -> str:
    text = _text(value, field)
    parsed = urlsplit(text)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or text.endswith("/")
    ):
        raise RuntimeServiceContractError(
            f"{field} must be a canonical credential-free HTTP(S) URL"
        )
    if parsed.scheme == "http":
        hostname = parsed.hostname or ""
        try:
            loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            loopback = hostname.casefold() == "localhost"
        if not loopback:
            raise RuntimeServiceContractError(
                f"{field} must use HTTPS unless it is loopback-only"
            )
    return text


def _stable_json(path: Path) -> Mapping[str, Any]:
    try:
        before = path.lstat()
    except OSError as exc:
        raise RuntimeServiceContractError(f"cannot stat runtime descriptor: {path}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeServiceContractError("runtime descriptor must be a regular file")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeServiceContractError("runtime descriptor reads require no-follow opens")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | no_follow,
        )
    except OSError as exc:
        raise RuntimeServiceContractError("cannot safely open runtime descriptor") from exc
    try:
        opened = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if identity(before) != identity(opened):
            raise RuntimeServiceContractError("runtime descriptor changed before read")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if identity(opened) != identity(os.fstat(descriptor)):
            raise RuntimeServiceContractError("runtime descriptor changed during read")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeServiceContractError("runtime descriptor is not valid JSON") from exc
    if not isinstance(value, Mapping):
        raise RuntimeServiceContractError("runtime descriptor root must be an object")
    return value


_COMMON = {
    "schema_version",
    "backend",
    "model_id",
    "model_revision",
    "model_artifact_sha256",
    "endpoint",
    "serving_id",
    "tenant_id",
    "credential_binding_id",
    "credential_binding_version",
    "trust_policy_id",
    "trust_zone",
    "descriptor_sha256",
}


def _validate_hash(value: Mapping[str, Any], *, schema: str, fields: set[str]) -> dict[str, Any]:
    if set(value) != fields or value.get("schema_version") != schema:
        raise RuntimeServiceContractError("runtime descriptor shape is invalid")
    core = dict(value)
    declared = core.pop("descriptor_sha256", None)
    if not _sha256(declared) or digest(core) != declared:
        raise RuntimeServiceContractError("runtime descriptor self-hash mismatch")
    return dict(value)


def load_llm_descriptor(path: str | os.PathLike[str]) -> dict[str, Any]:
    value = _validate_hash(
        _stable_json(Path(path)),
        schema="runtime-llm-binding-v1",
        fields=_COMMON | {"temperature", "json_mode"},
    )
    backend = value.get("backend")
    if backend not in {"disabled", "anthropic", "local", "genos", "openrouter"}:
        raise RuntimeServiceContractError("unsupported product LLM backend")
    if value.get("model_id") != "claude-haiku-4-5-20251001":
        raise RuntimeServiceContractError("product LLM descriptor must select Haiku 4.5")
    if value.get("temperature") != 0 or value.get("json_mode") != "json_schema":
        raise RuntimeServiceContractError("product LLM must use deterministic JSON settings")
    optional_remote = (
        "endpoint", "serving_id", "tenant_id", "credential_binding_id",
        "credential_binding_version", "trust_policy_id",
    )
    if backend == "disabled":
        if any(value.get(field) is not None for field in optional_remote):
            raise RuntimeServiceContractError("disabled LLM has remote service fields")
        if value.get("model_revision") is not None or value.get("model_artifact_sha256") is not None:
            raise RuntimeServiceContractError("disabled LLM has a model artifact")
        if value.get("trust_zone") != "none":
            raise RuntimeServiceContractError("disabled LLM trust zone must be none")
        return value
    _text(value.get("model_revision"), "LLM model_revision")
    if not _sha256(value.get("model_artifact_sha256")):
        raise RuntimeServiceContractError("LLM model artifact SHA-256 is invalid")
    _url(value.get("endpoint"), "LLM endpoint")
    if value.get("trust_zone") not in {"local", "internal", "external"}:
        raise RuntimeServiceContractError("LLM trust zone is invalid")
    if backend == "genos":
        if not _text(value.get("serving_id"), "LLM serving_id").isdigit():
            raise RuntimeServiceContractError("GenOS LLM serving_id must be numeric")
        _text(value.get("tenant_id"), "LLM tenant_id")
    elif value.get("serving_id") is not None or value.get("tenant_id") is not None:
        raise RuntimeServiceContractError("non-GenOS LLM has GenOS identity fields")
    for field in ("credential_binding_id", "credential_binding_version", "trust_policy_id"):
        _text(value.get(field), f"LLM {field}")
    return value


def load_embedding_descriptor(path: str | os.PathLike[str]) -> dict[str, Any]:
    value = _validate_hash(
        _stable_json(Path(path)),
        schema="runtime-embedding-binding-v1",
        fields=_COMMON | {
            "dimensions", "normalized", "document_profile", "query_profile"
        },
    )
    if value.get("backend") not in {"local", "genos"}:
        raise RuntimeServiceContractError("unsupported embedding backend")
    _text(value.get("model_id"), "embedding model_id")
    _text(value.get("model_revision"), "embedding model_revision")
    if not _sha256(value.get("model_artifact_sha256")):
        raise RuntimeServiceContractError("embedding model artifact SHA-256 is invalid")
    dimensions = value.get("dimensions")
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0:
        raise RuntimeServiceContractError("embedding dimensions are invalid")
    if value.get("normalized") is not True:
        raise RuntimeServiceContractError("embedding descriptor must require normalization")
    _text(value.get("document_profile"), "embedding document_profile")
    _text(value.get("query_profile"), "embedding query_profile")
    if value["backend"] == "local":
        for field in (
            "endpoint", "serving_id", "tenant_id", "credential_binding_id",
            "credential_binding_version", "trust_policy_id",
        ):
            if value.get(field) is not None:
                raise RuntimeServiceContractError("local embedding has remote service fields")
        if value.get("trust_zone") != "local":
            raise RuntimeServiceContractError("local embedding trust zone must be local")
    else:
        _url(value.get("endpoint"), "embedding endpoint")
        if not _text(value.get("serving_id"), "embedding serving_id").isdigit():
            raise RuntimeServiceContractError("GenOS embedding serving_id must be numeric")
        _text(value.get("tenant_id"), "embedding tenant_id")
        for field in ("credential_binding_id", "credential_binding_version", "trust_policy_id"):
            _text(value.get(field), f"embedding {field}")
        if value.get("trust_zone") not in {"internal", "external"}:
            raise RuntimeServiceContractError("GenOS embedding trust zone is invalid")
    return value


def acl_service_projection(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """Non-secret identity an independent ACL receipt must attest."""

    return {
        field: descriptor.get(field)
        for field in (
            "descriptor_sha256",
            "backend",
            "endpoint",
            "serving_id",
            "tenant_id",
            "model_id",
            "model_revision",
            "model_artifact_sha256",
            "credential_binding_id",
            "credential_binding_version",
            "trust_policy_id",
            "trust_zone",
        )
    }


def require_acl_admission(
    acl_receipt: Any,
    *,
    service_name: str,
    descriptor: Mapping[str, Any],
) -> None:
    """Require an active, release-bound ACL receipt to attest one remote service."""

    require_acl_projection(
        acl_receipt,
        service_name=service_name,
        expected=acl_service_projection(descriptor),
    )


def qdrant_acl_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    """Project the release-proved Qdrant identity into the common ACL ledger."""

    return {
        "descriptor_sha256": config.get("config_sha256"),
        "backend": "qdrant",
        "endpoint": config.get("url"),
        "serving_id": config.get("collection"),
        "tenant_id": None,
        "model_id": None,
        "model_revision": None,
        "model_artifact_sha256": None,
        "credential_binding_id": config.get("credential_binding_id"),
        "credential_binding_version": config.get("credential_binding_version"),
        "trust_policy_id": config.get("trust_policy_id"),
        "trust_zone": config.get("trust_zone"),
    }


def feedback_acl_projection(
    *,
    root: str | os.PathLike[str],
    trust_zone: str,
    trust_policy_id: str,
    export_allowed: bool,
) -> dict[str, Any]:
    """Identity an independently admitted, write-only feedback sink."""

    path = Path(root)
    if not path.is_absolute():
        raise RuntimeServiceContractError("feedback root must be absolute")
    exact_root = str(path.resolve())
    if trust_zone not in {"internal", "external"}:
        raise RuntimeServiceContractError("feedback trust zone is invalid")
    policy_id = _text(trust_policy_id, "feedback trust_policy_id")
    return {
        "schema_version": "feedback-output-binding-v1",
        "root": exact_root,
        "root_sha256": digest(
            {
                "schema_version": "feedback-output-root-v1",
                "root": exact_root,
            }
        ),
        "trust_zone": trust_zone,
        "trust_policy_id": policy_id,
        "export_allowed": bool(export_allowed),
    }


def require_acl_projection(
    acl_receipt: Any,
    *,
    service_name: str,
    expected: Mapping[str, Any],
) -> None:
    """Require the active ACL receipt to attest one exact public identity."""

    if acl_receipt is None or getattr(acl_receipt, "kind", None) != "acl":
        raise RuntimeServiceContractError("active release has no ACL admission receipt")
    details = getattr(acl_receipt, "details", None)
    services = details.get("runtime_services") if isinstance(details, Mapping) else None
    if not isinstance(services, Mapping):
        raise RuntimeServiceContractError("ACL receipt has no runtime service admissions")
    expected_projection = dict(expected)
    if services.get(service_name) != expected_projection:
        raise RuntimeServiceContractError(
            f"ACL receipt does not admit runtime service: {service_name}"
        )
    result = {
        "schema_version": "runtime-services-admission-v1",
        "runtime_services": dict(services),
    }
    if getattr(acl_receipt, "result_sha256", None) != digest(result):
        raise RuntimeServiceContractError("ACL runtime-service result hash is invalid")
