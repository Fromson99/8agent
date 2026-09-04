"""GenOS 코드 서빙 진입점 — 게이트웨이의 단일 JSON 계약을 우리 API 전체로 넓힌다.

GenOS 는 임의의 uvicorn 앱을 서빙하지 않는다. 계약은 이 파일의
`async def service(config, data)` 하나이고, 게이트웨이가 그것을
    POST https://<GenOS>/api/gateway/code_serving/<번호>/json
    Authorization: Bearer <인증키>
로 노출한다 (JSON in/out). 화면도, 임의 경로도, /docs 도 그 문으로는 못 나간다.

그래서 이 진입점은 **봉인된 조회 터널**이다. GenOS 배포물에는 legacy
호환 모드나 파일 운반·적용 연산이 없고 아래 두 호출만 존재한다:

    {"op": "ping"}                                  기동·rev 확인
    {"op": "call", "method": "GET", "path": "/v1/rag/search",
     "params": {"q": "질문", "mode": "auto"}}    GET 파라미터도 JSON 으로
    {"op": "call", "method": "POST",
     "path": "/v1/rag/ask", "json": {...}}          JSON 몸통은 json 으로,
                                                    파일은 body_b64 로
호출은 네트워크가 아니라 ASGI 로 앱 자신을 부른다(lawrag/api/ops.py 의 자기 호출) —
포트도 프록시도 없이 게이트웨이 한 문으로 전부 지나간다.

기본 판정은 코드 결정론이라는 원칙은 여기서도 같다: 이 파일은 아무것도
해석하지 않는다. 받은 것을 앱에 넘기고, 앱이 낸 것을 그대로 돌려준다.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import stat
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Mapping

_ROOT = Path(__file__).resolve().parent

_RELEASE_BINDING: Dict[str, Any] | None = None
_RELEASE_BOOTSTRAP_ERROR: str | None = None
_RELEASE_STORE = None
_RELEASE_RUNTIME_BINDING = None
_CONTENT_SNAPSHOT = None
_SEALED_SECRET_DIGESTS: Dict[str, str] = {}

_RELEASE_GET_ALLOWLIST = frozenset(
    {
        "/health",
        "/v1/rag/search",
        "/v1/rag/links/summary",
        "/v1/rag/section",
        "/v1/rag/scopes",
        "/v1/rag/nodes",
    }
)
_RELEASE_POST_ALLOWLIST = frozenset({"/v1/rag/ask"})


def _pin_env_path(name: str, expected: Path) -> str:
    """Pin one path-valued process input without accepting an aliasing override."""

    expected_text = str(expected.resolve(strict=False))
    configured = os.environ.get(name, "").strip()
    if configured and str(Path(configured).resolve(strict=False)) != expected_text:
        raise RuntimeError(f"{name} conflicts with the active release binding")
    os.environ[name] = expected_text
    return expected_text


def _pin_env_value(name: str, expected: str) -> str:
    configured = os.environ.get(name, "").strip()
    if configured and configured != expected:
        raise RuntimeError(f"{name} conflicts with the active release binding")
    os.environ[name] = expected
    return expected


def _require_deployment_descriptor_admission(
    service_name: str, descriptor_sha256: object
) -> None:
    """Require an ops-controlled hash independent of release and ACL bytes."""

    expected = str(descriptor_sha256 or "")
    if len(expected) != 64 or any(
        character not in "0123456789abcdef" for character in expected
    ):
        raise RuntimeError(f"{service_name} descriptor SHA-256 is invalid")
    key = "LAWRAG_ADMITTED_" + service_name.upper() + "_DESCRIPTOR_SHA256"
    configured = os.environ.get(key, "").strip()
    if configured != expected:
        raise RuntimeError(
            f"{key} must independently admit the release descriptor"
        )


def _require_plain_path(path: Path, *, kind: str, field: str) -> Path:
    """Reject relative paths and every symlink component before admission."""

    if not path.is_absolute():
        raise RuntimeError(f"{field} must be absolute")
    chain = [path, *path.parents]
    for current in chain:
        if current.is_symlink():
            raise RuntimeError(f"{field} contains a symlink")
    if kind == "file" and not path.is_file():
        raise RuntimeError(f"{field} must name an existing regular file")
    if kind == "directory" and not path.is_dir():
        raise RuntimeError(f"{field} must name an existing directory")
    return path.resolve()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _stable_file_sha256(path: Path, *, field: str) -> str:
    """Hash one non-symlink regular file and detect a concurrent replacement."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"cannot open {field}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"{field} must be a regular file")
        if before.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise RuntimeError(f"{field} must not be group/world writable")
        digest = hashlib.sha256()
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(fd)
        identity_before = (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        )
        identity_after = (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        )
        if identity_before != identity_after:
            raise RuntimeError(f"{field} changed while it was verified")
        return digest.hexdigest()
    finally:
        os.close(fd)


def _stable_file_bytes(path: Path, *, field: str) -> bytes:
    """Read the exact bytes admitted by the same no-follow/stability policy."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"cannot open {field}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"{field} must be a regular file")
        if before.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise RuntimeError(f"{field} must not be group/world writable")
        chunks: list[bytes] = []
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.fstat(fd)
        identity_before = (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after:
            raise RuntimeError(f"{field} changed while it was read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _resolve_bound_secret(
    *,
    binding_id: object,
    binding_version: object,
    selected_env: str,
    forbidden_envs: tuple[str, ...] = (),
) -> None:
    """Resolve one credential from its exact deployment binding file.

    Result-affecting clients never guess among fallback key variables.  The
    secret mount uses a deterministic filename derived from the public binding
    ID/version; only that file may populate the selected process variable.
    """

    global _SEALED_SECRET_DIGESTS
    public = {
        "schema_version": "runtime-secret-binding-v1",
        "binding_id": str(binding_id or ""),
        "binding_version": str(binding_version or ""),
    }
    if not public["binding_id"] or not public["binding_version"]:
        raise RuntimeError("runtime credential binding identity is incomplete")
    conflicting = [
        key for key in (selected_env, *forbidden_envs)
        if os.environ.get(key, "")
    ]
    if conflicting:
        raise RuntimeError(
            "ambient credential variables are forbidden in a sealed release: "
            + ", ".join(conflicting)
        )
    root_value = os.environ.get("LAWRAG_SECRET_BINDING_ROOT", "").strip()
    if not root_value:
        raise RuntimeError("sealed remote services require LAWRAG_SECRET_BINDING_ROOT")
    root = _require_plain_path(
        Path(root_value), kind="directory", field="LAWRAG_SECRET_BINDING_ROOT"
    )
    info = root.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError(
            "secret binding root must be owned by the service user with mode 0700"
        )
    filename = hashlib.sha256(
        json.dumps(
            public,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest() + ".secret"
    path = _require_plain_path(
        root / filename, kind="file", field=f"credential binding {selected_env}"
    )
    secret_info = path.stat()
    if (
        secret_info.st_uid != os.geteuid()
        or stat.S_IMODE(secret_info.st_mode) & 0o077
    ):
        raise RuntimeError(
            "credential binding file must be private to the service user"
        )
    raw = _stable_file_bytes(path, field=f"credential binding {selected_env}")
    try:
        secret = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("credential binding must be UTF-8 text") from exc
    if (
        not secret
        or secret != secret.strip()
        or any(ord(character) < 33 or ord(character) == 127 for character in secret)
    ):
        raise RuntimeError("credential binding contains invalid secret text")
    os.environ[selected_env] = secret
    _SEALED_SECRET_DIGESTS[selected_env] = hashlib.sha256(raw).hexdigest()


def _verify_bound_secrets() -> None:
    for key, expected in _SEALED_SECRET_DIGESTS.items():
        current = os.environ.get(key)
        if current is None or hashlib.sha256(current.encode("utf-8")).hexdigest() != expected:
            raise RuntimeError(f"sealed credential changed after bootstrap: {key}")


def _canonical_service_url(value: str, *, field: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(f"{field} must be a credential-free HTTP(S) URL")
    if parsed.scheme == "http" and not _loopback_service_url(value):
        raise RuntimeError(f"{field} must use HTTPS unless it is loopback-only")
    return value.rstrip("/")


def _loopback_service_url(value: str) -> bool:
    hostname = urllib.parse.urlsplit(value).hostname or ""
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _configure_llm_runtime(*, export_allowed: bool) -> Dict[str, Any]:
    """Freeze the product LLM role and prevent restricted-data exfiltration."""

    backend = os.environ.get("LLM_BACKEND", "").strip().lower()
    intent_keys = (
        "LOCAL_LLM_URL",
        "GENOS_LLM_URL",
        "GENOS_LLM_SERVING_ID",
        "GENOS_LLM_PROFILE",
        "OPENROUTER_URL",
        "OPENROUTER_MODEL",
        "ANTHROPIC_MODEL",
    )
    if not backend:
        configured_intent = [key for key in intent_keys if os.environ.get(key, "").strip()]
        if configured_intent:
            raise RuntimeError(
                "sealed product LLM requires explicit LLM_BACKEND when LLM settings exist"
            )
        backend = "disabled"
    if backend not in {"disabled", "anthropic", "local", "genos", "openrouter"}:
        raise RuntimeError(f"unsupported sealed product LLM backend: {backend!r}")
    _pin_env_value("LLM_BACKEND", backend)
    if not export_allowed and backend in {"anthropic", "openrouter"}:
        raise RuntimeError(
            "restricted SourceSet cannot send prompts to an external LLM backend"
        )

    required_model = "claude-haiku-4-5-20251001"
    endpoint = None
    serving_id = None
    tenant_id = None
    trust_zone = "none"
    tracked = ["LLM_BACKEND"]
    credential_keys: tuple[str, ...] = ()
    if backend == "disabled":
        return {
            "enabled": False,
            "backend": backend,
            "model": required_model,
            "endpoint": None,
            "serving_id": None,
            "tenant_id": None,
            "trust_zone": "none",
            "export_allowed": bool(export_allowed),
            "env": {key: os.environ.get(key) for key in tracked},
            "credential_presence": {},
        }
    if backend == "anthropic":
        _pin_env_value("ANTHROPIC_MODEL", required_model)
        endpoint = "https://api.anthropic.com"
        trust_zone = "external"
        tracked.append("ANTHROPIC_MODEL")
        credential_keys = ("ANTHROPIC_API_KEY",)
    elif backend == "local":
        raw_url = os.environ.get("LOCAL_LLM_URL", "").strip()
        if not raw_url:
            raise RuntimeError("LOCAL_LLM_URL is required for the local LLM backend")
        endpoint = _canonical_service_url(raw_url, field="LOCAL_LLM_URL")
        trust_zone = (
            "local" if _loopback_service_url(endpoint)
            else os.environ.get("LOCAL_LLM_TRUST_ZONE", "").strip().lower()
        )
        if trust_zone not in {"local", "internal", "external"}:
            raise RuntimeError(
                "non-loopback local LLM requires an explicit trust zone"
            )
        if not export_allowed and trust_zone == "external":
            raise RuntimeError(
                "restricted SourceSet cannot use an external local-LLM endpoint"
            )
        _pin_env_value("LOCAL_LLM_URL", endpoint)
        _pin_env_value("LOCAL_LLM_TRUST_ZONE", trust_zone)
        _pin_env_value("LOCAL_LLM_MODEL", required_model)
        _pin_env_value("LOCAL_LLM_TEMPERATURE", "0")
        _pin_env_value("LOCAL_LLM_JSON_MODE", "json_schema")
        tracked.extend(
            ("LOCAL_LLM_URL", "LOCAL_LLM_TRUST_ZONE", "LOCAL_LLM_MODEL",
             "LOCAL_LLM_TEMPERATURE", "LOCAL_LLM_JSON_MODE")
        )
        credential_keys = ("LOCAL_LLM_KEY",)
    elif backend == "genos":
        from lawrag.core import llm as llm_mod

        profile = llm_mod._genos_profile()
        serving_key = (
            f"GENOS_{profile}_SERVING_ID" if profile else "GENOS_LLM_SERVING_ID"
        )
        serving_id = os.environ.get(serving_key, "").strip()
        base_value = os.environ.get("GENOS_BASE_URL", "").strip()
        if not base_value or not serving_id.isdigit():
            raise RuntimeError(
                "sealed GenOS LLM requires GENOS_BASE_URL and numeric serving ID"
            )
        base = _canonical_service_url(base_value, field="GENOS_BASE_URL")
        endpoint = f"{base}/api/gateway/rep/serving/{serving_id}"
        configured_endpoint = os.environ.get("GENOS_LLM_URL", "").strip()
        if configured_endpoint and _canonical_service_url(
            configured_endpoint, field="GENOS_LLM_URL"
        ) != endpoint:
            raise RuntimeError(
                "GENOS_LLM_URL conflicts with the admitted GenOS serving ID"
            )
        _pin_env_value("GENOS_BASE_URL", base)
        _pin_env_value("GENOS_LLM_URL", endpoint)
        trust_zone = os.environ.get("GENOS_LLM_TRUST_ZONE", "").strip().lower()
        if trust_zone not in {"internal", "external"}:
            raise RuntimeError(
                "GENOS_LLM_TRUST_ZONE must explicitly be internal or external"
            )
        if not export_allowed and trust_zone != "internal":
            raise RuntimeError(
                "restricted SourceSet GenOS LLM must stay in the internal trust zone"
            )
        _pin_env_value("GENOS_LLM_TRUST_ZONE", trust_zone)
        tenant_id = os.environ.get("GENOS_USER_ID", "").strip()
        if not tenant_id:
            raise RuntimeError("sealed GenOS LLM requires GENOS_USER_ID")
        _pin_env_value("GENOS_USER_ID", tenant_id)
        model_key = f"GENOS_{profile}_MODEL" if profile else "GENOS_LLM_MODEL"
        _pin_env_value(model_key, required_model)
        _pin_env_value("GENOS_LLM_JSON_MODE", "json_schema")
        _pin_env_value("GENOS_LLM_TEMPERATURE", "0")
        tracked.extend(
            ("GENOS_LLM_URL", "GENOS_BASE_URL", serving_key,
             "GENOS_LLM_PROFILE", "GENOS_LLM_TRUST_ZONE", "GENOS_USER_ID",
             model_key, "GENOS_LLM_JSON_MODE", "GENOS_LLM_TEMPERATURE")
        )
        credential_keys = (
            f"GENOS_{profile}_KEY" if profile else "GENOS_LLM_KEY",
            "GENOS_LLM_KEY",
        )
    else:
        raw_url = os.environ.get(
            "OPENROUTER_URL", "https://openrouter.ai/api"
        ).strip()
        endpoint = _canonical_service_url(raw_url, field="OPENROUTER_URL")
        trust_zone = "external"
        _pin_env_value("OPENROUTER_URL", endpoint)
        _pin_env_value("OPENROUTER_MODEL", required_model)
        _pin_env_value("OPENROUTER_TEMPERATURE", "0")
        _pin_env_value("OPENROUTER_JSON_MODE", "json_schema")
        tracked.extend(
            ("OPENROUTER_URL", "OPENROUTER_MODEL", "OPENROUTER_TEMPERATURE",
             "OPENROUTER_JSON_MODE")
        )
        credential_keys = ("OPEN_ROUTER", "OPENROUTER_API_KEY")

    credential_presence = {
        key: bool(os.environ.get(key, "")) for key in dict.fromkeys(credential_keys)
    }
    return {
        "enabled": True,
        "backend": backend,
        "model": required_model,
        "endpoint": endpoint,
        "serving_id": serving_id,
        "tenant_id": tenant_id,
        "trust_zone": trust_zone,
        "export_allowed": bool(export_allowed),
        "env": {key: os.environ.get(key) for key in dict.fromkeys(tracked)},
        "credential_presence": credential_presence,
    }


def _configure_embedding_runtime(
    *, expected_fingerprint: str, export_allowed: bool
) -> Dict[str, Any]:
    """Admit one exact query encoder; ambient endpoints are never authoritative."""

    backend = os.environ.get("EMBED_BACKEND", "").strip().lower()
    if backend not in {"local", "genos"}:
        raise RuntimeError("sealed vector release requires explicit EMBED_BACKEND")
    _pin_env_value("EMBED_BACKEND", backend)
    _pin_env_value("LAWRAG_EMBEDDING_DISABLED", "0")
    tracked = ["EMBED_BACKEND", "LAWRAG_EMBEDDING_DISABLED"]
    credential_keys: tuple[str, ...] = ()
    endpoint = None
    serving_id = None
    tenant_id = None
    trust_zone = "local"
    local_artifact_verified = False

    if backend == "local":
        model_path_value = os.environ.get("EMBED_MODEL_ARTIFACT_PATH", "").strip()
        if not model_path_value:
            raise RuntimeError(
                "sealed local encoder requires EMBED_MODEL_ARTIFACT_PATH"
            )
        raw_model_path = Path(model_path_value)
        model_path = _require_plain_path(
            raw_model_path,
            kind="directory" if raw_model_path.is_dir() else "file",
            field="EMBED_MODEL_ARTIFACT_PATH",
        )
        _pin_env_path("EMBED_MODEL_ARTIFACT_PATH", model_path)
        _pin_env_value("EMBED_LOCAL_FILES_ONLY", "1")
        _pin_env_value("EMBED_DEVICE", "cpu")
        _pin_env_value("EMBED_CPU_THREADS", "4")
        tracked.extend(
            (
                "EMBED_MODEL",
                "EMBED_MODEL_REVISION",
                "EMBED_MODEL_SHA256",
                "EMBED_DIMENSIONS",
                "EMBED_MODEL_ARTIFACT_PATH",
                "EMBED_LOCAL_FILES_ONLY",
                "EMBED_DEVICE",
                "EMBED_CPU_THREADS",
            )
        )
        local_artifact_verified = True
    else:
        base_value = os.environ.get("GENOS_BASE_URL", "").strip()
        serving_id = os.environ.get("GENOS_EMBED_SERVING_ID", "").strip()
        if not base_value or not serving_id.isdigit():
            raise RuntimeError(
                "sealed GenOS encoder requires GENOS_BASE_URL and numeric serving ID"
            )
        base = _canonical_service_url(base_value, field="GENOS_BASE_URL")
        expected_endpoint = (
            f"{base}/api/gateway/rep/serving/{serving_id}"
        )
        configured_endpoint = os.environ.get("GENOS_EMBED_URL", "").strip()
        if configured_endpoint and _canonical_service_url(
            configured_endpoint, field="GENOS_EMBED_URL"
        ) != expected_endpoint:
            raise RuntimeError(
                "GENOS_EMBED_URL conflicts with the admitted GenOS serving ID"
            )
        _pin_env_value("GENOS_BASE_URL", base)
        _pin_env_value("GENOS_EMBED_URL", expected_endpoint)
        endpoint = expected_endpoint
        trust_zone = os.environ.get("GENOS_EMBED_TRUST_ZONE", "").strip().lower()
        if trust_zone not in {"internal", "external"}:
            raise RuntimeError(
                "GENOS_EMBED_TRUST_ZONE must explicitly be internal or external"
            )
        if not export_allowed and trust_zone != "internal":
            raise RuntimeError(
                "restricted SourceSet encoder must stay in the internal trust zone"
            )
        _pin_env_value("GENOS_EMBED_TRUST_ZONE", trust_zone)
        tenant_id = os.environ.get("GENOS_EMBED_TENANT_ID", "").strip()
        if not tenant_id:
            raise RuntimeError("sealed GenOS encoder requires an exact tenant ID")
        _pin_env_value("GENOS_EMBED_TENANT_ID", tenant_id)
        _pin_env_value("GENOS_EMBED_BATCH", "64")
        tracked.extend(
            (
                "GENOS_BASE_URL",
                "GENOS_EMBED_URL",
                "GENOS_EMBED_SERVING_ID",
                "GENOS_EMBED_MODEL",
                "GENOS_EMBED_MODEL_REVISION",
                "GENOS_EMBED_MODEL_SHA256",
                "GENOS_EMBED_DIMENSIONS",
                "GENOS_EMBED_TRUST_ZONE",
                "GENOS_EMBED_TENANT_ID",
                "GENOS_EMBED_BATCH",
            )
        )
        credential_keys = ("GENOS_EMBED_KEY", "GENOS_LLM_KEY")

    from lawrag.core import embedding

    embedding.require_uninitialized_runtime()
    identity = embedding.runtime_identity()
    actual_fingerprint = embedding.runtime_fingerprint()
    if actual_fingerprint != expected_fingerprint:
        raise RuntimeError(
            "deployed query encoder does not match the active vector index"
        )
    _pin_env_value("RAG_EMBEDDING_MODEL_FINGERPRINT", expected_fingerprint)
    tracked.append("RAG_EMBEDDING_MODEL_FINGERPRINT")
    return {
        "backend": backend,
        "endpoint": endpoint,
        "serving_id": serving_id,
        "tenant_id": tenant_id,
        "trust_zone": trust_zone,
        "model_id": identity["model_id"],
        "model_revision": identity["model_revision"],
        "model_artifact_sha256": identity["model_artifact_sha256"],
        "dimensions": identity["dimensions"],
        "local_artifact_verified": local_artifact_verified,
        "env": {key: os.environ.get(key) for key in dict.fromkeys(tracked)},
        "credential_presence": {
            key: bool(os.environ.get(key, ""))
            for key in dict.fromkeys(credential_keys)
        },
    }


def _configure_release_llm_runtime(
    descriptor: Mapping[str, Any],
    *,
    export_allowed: bool,
    acl_receipt: Any,
) -> Dict[str, Any]:
    """Project a release-hashed LLM descriptor into the legacy client env."""

    from lawrag.platform import runtime_services

    _require_deployment_descriptor_admission(
        "llm", descriptor.get("descriptor_sha256")
    )

    backend = str(descriptor["backend"])
    _pin_env_value("LLM_BACKEND", backend)
    model = str(descriptor["model_id"])
    endpoint = descriptor.get("endpoint")
    tracked: dict[str, str] = {}

    def pin(name: str, value: object) -> None:
        text = "" if value is None else str(value)
        _pin_env_value(name, text)
        tracked[name] = text

    if backend == "anthropic":
        pin("ANTHROPIC_MODEL", model)
        pin("ANTHROPIC_MODEL_REVISION", descriptor["model_revision"])
        pin("ANTHROPIC_MODEL_SHA256", descriptor["model_artifact_sha256"])
        pin(
            "ANTHROPIC_CREDENTIAL_BINDING_ID",
            descriptor["credential_binding_id"],
        )
        pin(
            "ANTHROPIC_CREDENTIAL_BINDING_VERSION",
            descriptor["credential_binding_version"],
        )
        pin("ANTHROPIC_TRUST_POLICY_ID", descriptor["trust_policy_id"])
    elif backend == "local":
        pin("LOCAL_LLM_URL", endpoint)
        pin("LOCAL_LLM_TRUST_ZONE", descriptor["trust_zone"])
        pin("LOCAL_LLM_MODEL", model)
        pin("LOCAL_LLM_MODEL_REVISION", descriptor["model_revision"])
        pin("LOCAL_LLM_MODEL_SHA256", descriptor["model_artifact_sha256"])
        pin("LOCAL_LLM_CREDENTIAL_BINDING_ID", descriptor["credential_binding_id"])
        pin(
            "LOCAL_LLM_CREDENTIAL_BINDING_VERSION",
            descriptor["credential_binding_version"],
        )
        pin("LOCAL_LLM_TRUST_POLICY_ID", descriptor["trust_policy_id"])
    elif backend == "genos":
        serving_id = str(descriptor["serving_id"])
        suffix = f"/api/gateway/rep/serving/{serving_id}"
        if not isinstance(endpoint, str) or not endpoint.endswith(suffix):
            raise RuntimeError("GenOS LLM descriptor endpoint/serving ID mismatch")
        pin("GENOS_LLM_PROFILE", "")
        pin("GENOS_BASE_URL", endpoint[: -len(suffix)])
        pin("GENOS_LLM_URL", endpoint)
        pin("GENOS_LLM_SERVING_ID", serving_id)
        pin("GENOS_LLM_MODEL", model)
        pin("GENOS_LLM_TRUST_ZONE", descriptor["trust_zone"])
        pin("GENOS_USER_ID", descriptor["tenant_id"])
        pin("GENOS_LLM_MODEL_REVISION", descriptor["model_revision"])
        pin("GENOS_LLM_MODEL_SHA256", descriptor["model_artifact_sha256"])
        pin("GENOS_LLM_CREDENTIAL_BINDING_ID", descriptor["credential_binding_id"])
        pin(
            "GENOS_LLM_CREDENTIAL_BINDING_VERSION",
            descriptor["credential_binding_version"],
        )
        pin("GENOS_LLM_TRUST_POLICY_ID", descriptor["trust_policy_id"])
    elif backend == "openrouter":
        pin("OPENROUTER_URL", endpoint)
        pin("OPENROUTER_MODEL", model)
        pin("OPENROUTER_MODEL_REVISION", descriptor["model_revision"])
        pin("OPENROUTER_MODEL_SHA256", descriptor["model_artifact_sha256"])
        pin("OPENROUTER_CREDENTIAL_BINDING_ID", descriptor["credential_binding_id"])
        pin(
            "OPENROUTER_CREDENTIAL_BINDING_VERSION",
            descriptor["credential_binding_version"],
        )
        pin("OPENROUTER_TRUST_POLICY_ID", descriptor["trust_policy_id"])

    if backend != "disabled":
        secret_env, forbidden = {
            "anthropic": ("ANTHROPIC_API_KEY", ()),
            "local": ("LOCAL_LLM_KEY", ()),
            "genos": ("GENOS_LLM_KEY", ()),
            "openrouter": (
                "OPENROUTER_API_KEY",
                ("OPEN_ROUTER",),
            ),
        }[backend]
        _resolve_bound_secret(
            binding_id=descriptor["credential_binding_id"],
            binding_version=descriptor["credential_binding_version"],
            selected_env=secret_env,
            forbidden_envs=forbidden,
        )

    runtime = _configure_llm_runtime(export_allowed=export_allowed)
    expected_public = {
        "backend": backend,
        "model": model,
        "endpoint": endpoint,
        "serving_id": descriptor.get("serving_id"),
        "tenant_id": descriptor.get("tenant_id"),
        "trust_zone": descriptor.get("trust_zone"),
    }
    if any(runtime.get(key) != value for key, value in expected_public.items()):
        raise RuntimeError("product LLM env disagrees with its release descriptor")
    if backend != "disabled":
        runtime_services.require_acl_admission(
            acl_receipt, service_name="llm", descriptor=descriptor
        )
        if not any(bool(value) for value in runtime["credential_presence"].values()):
            raise RuntimeError(
                "release-admitted product LLM credential is not injected"
            )
    runtime.update(
        {
            "descriptor_sha256": descriptor["descriptor_sha256"],
            "model_revision": descriptor.get("model_revision"),
            "model_artifact_sha256": descriptor.get("model_artifact_sha256"),
            "credential_binding_id": descriptor.get("credential_binding_id"),
            "credential_binding_version": descriptor.get(
                "credential_binding_version"
            ),
            "trust_policy_id": descriptor.get("trust_policy_id"),
        }
    )
    runtime.setdefault("env", {}).update(tracked)
    runtime["env"]["LAWRAG_ADMITTED_LLM_DESCRIPTOR_SHA256"] = str(
        descriptor["descriptor_sha256"]
    )
    return runtime


def _configure_release_embedding_runtime(
    descriptor: Mapping[str, Any],
    *,
    expected_fingerprint: str,
    export_allowed: bool,
    acl_receipt: Any,
) -> Dict[str, Any]:
    """Project a release-hashed encoder descriptor and verify its actual backend."""

    from lawrag.platform import runtime_services

    _require_deployment_descriptor_admission(
        "encoder", descriptor.get("descriptor_sha256")
    )

    backend = str(descriptor["backend"])

    def pin(name: str, value: object) -> None:
        _pin_env_value(name, "" if value is None else str(value))

    pin("EMBED_BACKEND", backend)
    if backend == "local":
        pin("EMBED_MODEL", descriptor["model_id"])
        pin("EMBED_MODEL_REVISION", descriptor["model_revision"])
        pin("EMBED_MODEL_SHA256", descriptor["model_artifact_sha256"])
        pin("EMBED_DIMENSIONS", descriptor["dimensions"])
    else:
        endpoint = str(descriptor["endpoint"])
        serving_id = str(descriptor["serving_id"])
        suffix = f"/api/gateway/rep/serving/{serving_id}"
        if not endpoint.endswith(suffix):
            raise RuntimeError("GenOS encoder descriptor endpoint/serving ID mismatch")
        pin("GENOS_BASE_URL", endpoint[: -len(suffix)])
        pin("GENOS_EMBED_URL", endpoint)
        pin("GENOS_EMBED_SERVING_ID", serving_id)
        pin("GENOS_EMBED_MODEL", descriptor["model_id"])
        pin("GENOS_EMBED_MODEL_REVISION", descriptor["model_revision"])
        pin("GENOS_EMBED_MODEL_SHA256", descriptor["model_artifact_sha256"])
        pin("GENOS_EMBED_DIMENSIONS", descriptor["dimensions"])
        pin("GENOS_EMBED_TRUST_ZONE", descriptor["trust_zone"])
        pin("GENOS_EMBED_TENANT_ID", descriptor["tenant_id"])
        pin("GENOS_EMBED_CREDENTIAL_BINDING_ID", descriptor["credential_binding_id"])
        pin(
            "GENOS_EMBED_CREDENTIAL_BINDING_VERSION",
            descriptor["credential_binding_version"],
        )
        pin("GENOS_EMBED_TRUST_POLICY_ID", descriptor["trust_policy_id"])
        runtime_services.require_acl_admission(
            acl_receipt, service_name="encoder", descriptor=descriptor
        )
        _resolve_bound_secret(
            binding_id=descriptor["credential_binding_id"],
            binding_version=descriptor["credential_binding_version"],
            selected_env="GENOS_EMBED_KEY",
        )

    runtime = _configure_embedding_runtime(
        expected_fingerprint=expected_fingerprint,
        export_allowed=export_allowed,
    )
    expected = {
        "backend": backend,
        "endpoint": descriptor.get("endpoint"),
        "serving_id": descriptor.get("serving_id"),
        "tenant_id": descriptor.get("tenant_id"),
        "trust_zone": descriptor.get("trust_zone"),
        "model_id": descriptor.get("model_id"),
        "model_revision": descriptor.get("model_revision"),
        "model_artifact_sha256": descriptor.get("model_artifact_sha256"),
        "dimensions": descriptor.get("dimensions"),
    }
    if any(runtime.get(key) != value for key, value in expected.items()):
        raise RuntimeError("encoder env disagrees with its release descriptor")
    if backend == "genos" and not any(
        bool(value) for value in runtime["credential_presence"].values()
    ):
        raise RuntimeError("release-admitted encoder credential is not injected")
    runtime.update(
        {
            "descriptor_sha256": descriptor["descriptor_sha256"],
            "credential_binding_id": descriptor.get("credential_binding_id"),
            "credential_binding_version": descriptor.get(
                "credential_binding_version"
            ),
            "trust_policy_id": descriptor.get("trust_policy_id"),
        }
    )
    runtime.setdefault("env", {}).update(
        {
            key: os.environ.get(key)
            for key in (
                "GENOS_EMBED_CREDENTIAL_BINDING_ID",
                "GENOS_EMBED_CREDENTIAL_BINDING_VERSION",
                "GENOS_EMBED_TRUST_POLICY_ID",
            )
            if os.environ.get(key) is not None
        }
    )
    runtime["env"]["LAWRAG_ADMITTED_ENCODER_DESCRIPTOR_SHA256"] = str(
        descriptor["descriptor_sha256"]
    )
    return runtime


def _configure_sourceset_control_planes(
    snapshot, *, runtime_root: Path, export_allowed: bool, acl_receipt: Any
) -> Dict[str, Any]:
    """Bind semantic inputs, optional observations, and reviewed shortcuts.

    Semantic inputs are part of the immutable release.  Feedback observations
    are external outputs and never read by retrieval.  Reviewed shortcuts are
    a third, read-only control plane whose exact bytes are deployment-pinned.
    """

    semantic_root = _require_plain_path(
        snapshot.runtime_artifact_path("semantics.content"),
        kind="directory",
        field="semantics.content",
    )
    semantic_paths = {
        "LEGAL_GRAPH_STORE": semantic_root,
        "RAG_DOMAIN_GRAPH": semantic_root / "domain_graph" / "graph.sqlite",
        "RAG_CONCEPT_REGISTRY": semantic_root / "domain_graph" / "canonical.json",
        "RAG_DELEGATION_STORE": semantic_root / "delegation.json",
        "RAG_LAW_INDEX_STORE": semantic_root / "law_index.json",
        "RAG_ALIASES_STORE": semantic_root / "aliases.json",
        "RAG_ALIASES": semantic_root / "aliases.json",
        "RAG_FRAMES_DIR": semantic_root / "frames",
        "RAG_TAXONOMY_DIR": semantic_root / "taxonomy",
        "RAG_LEXICON_DIR": semantic_root / "lexicon",
        "WIKI_STORE": semantic_root / "wiki",
        "RAG_RULES_DIR": semantic_root / "rules",
        "RAG_ENGINE_RULES": semantic_root / "rules" / "engine.json",
        "RAG_ASSERTION_SHORTCUT_STORE": (
            semantic_root / "assertion_shortcuts.disabled.json"
        ),
        "RAG_SCOPES_FILE": semantic_root / "scopes.yml",
    }
    pinned_semantics = {
        name: _pin_env_path(name, path) for name, path in semantic_paths.items()
    }
    _pin_env_value("RAG_DOMAIN", "law")
    _pin_env_value("RAG_RULES_MODE", "off")
    _pin_env_value("RAG_LEXICON_COMPILE_MISSING", "0")
    _pin_env_value("RAG_LEXICON_DOCS", "")
    _pin_env_value("RAG_SPOT_MAX_TOKENS", "1000")
    _pin_env_value("RAG_RECOVER_MODEL", "claude-haiku-4-5-20251001")
    _pin_env_value(
        "RAG_LEGALCLOSURE_ASSERTION_MODEL", "claude-haiku-4-5-20251001"
    )
    _pin_env_value("RAG_FRAMES_MODEL", "claude-haiku-4-5-20251001")
    _pin_env_value("RAG_TAXONOMY_MODEL", "claude-haiku-4-5-20251001")
    semantic_values = {
        key: os.environ[key]
        for key in (
            "RAG_DOMAIN",
            "RAG_RULES_MODE",
            "RAG_LEXICON_COMPILE_MISSING",
            "RAG_LEXICON_DOCS",
            "RAG_SPOT_MAX_TOKENS",
            "RAG_RECOVER_MODEL",
            "RAG_LEGALCLOSURE_ASSERTION_MODEL",
            "RAG_FRAMES_MODEL",
            "RAG_TAXONOMY_MODEL",
        )
    }

    canonical = _require_plain_path(
        Path(pinned_semantics["RAG_CONCEPT_REGISTRY"]),
        kind="file",
        field="semantic concept registry",
    )
    from lawrag.core.domain_graph.tier1 import Tier1Registry

    Tier1Registry.load(canonical, strict=True)

    feedback_value = os.environ.get("LAWRAG_FEEDBACK_ROOT", "").strip()
    if feedback_value:
        trust_zone = os.environ.get(
            "LAWRAG_FEEDBACK_TRUST_ZONE", "internal"
        ).strip().lower()
        if trust_zone not in {"internal", "external"}:
            raise RuntimeError(
                "LAWRAG_FEEDBACK_TRUST_ZONE must be internal or external"
            )
        if not export_allowed and trust_zone != "internal":
            raise RuntimeError(
                "restricted SourceSet feedback must remain in the internal trust zone"
            )
        _pin_env_value("LAWRAG_FEEDBACK_TRUST_ZONE", trust_zone)
        feedback_root = _require_plain_path(
            Path(feedback_value), kind="directory", field="LAWRAG_FEEDBACK_ROOT"
        )
        root_stat = feedback_root.stat()
        if (
            root_stat.st_uid != os.geteuid()
            or stat.S_IMODE(root_stat.st_mode) != 0o700
        ):
            raise RuntimeError(
                "feedback output root must be owned by the service user with mode 0700"
            )
        if (
            feedback_root == Path(feedback_root.anchor)
            or _within(Path.home(), feedback_root)
            or _within(feedback_root, runtime_root)
            or _within(runtime_root, feedback_root)
            or _within(feedback_root, _ROOT)
            or _within(_ROOT, feedback_root)
        ):
            raise RuntimeError(
                "feedback output root must be a dedicated non-ancestor directory"
            )
        trust_policy_id = os.environ.get(
            "LAWRAG_FEEDBACK_TRUST_POLICY_ID", ""
        ).strip()
        from lawrag.platform import runtime_services

        feedback_projection = runtime_services.feedback_acl_projection(
            root=feedback_root,
            trust_zone=trust_zone,
            trust_policy_id=trust_policy_id,
            export_allowed=export_allowed,
        )
        admitted_sha = os.environ.get(
            "LAWRAG_ADMITTED_FEEDBACK_ROOT_SHA256", ""
        ).strip()
        if admitted_sha != feedback_projection["root_sha256"]:
            raise RuntimeError(
                "deployment did not independently admit the feedback root"
            )
        runtime_services.require_acl_projection(
            acl_receipt,
            service_name="feedback",
            expected=feedback_projection,
        )
        _pin_env_path("LAWRAG_FEEDBACK_ROOT", feedback_root)
        _pin_env_value(
            "LAWRAG_ADMITTED_FEEDBACK_ROOT_SHA256", admitted_sha
        )
        _pin_env_value(
            "LAWRAG_FEEDBACK_TRUST_POLICY_ID", trust_policy_id
        )
        _pin_env_path("RAG_LOG_DIR", feedback_root)
        _pin_env_path("LOG_DIR", feedback_root / "logs")
        _pin_env_path("RAG_EVENTS_LOG", feedback_root / "logs" / "rag_events.jsonl")
        _pin_env_path(
            "RAG_APPROVAL_RECEIPTS", feedback_root / "approval_receipts.jsonl"
        )
        _pin_env_value("LAWRAG_FEEDBACK_DISABLED", "0")
        feedback_binding: Dict[str, Any] = {
            "enabled": True,
            "root": str(feedback_root),
            "trust_zone": trust_zone,
            "trust_policy_id": trust_policy_id,
            "root_sha256": admitted_sha,
            "log_dir": str((feedback_root / "logs").resolve(strict=False)),
            "events": str(
                (feedback_root / "logs" / "rag_events.jsonl").resolve(strict=False)
            ),
            "approval_receipts": str(
                (feedback_root / "approval_receipts.jsonl").resolve(strict=False)
            ),
        }
    else:
        unexpected_logs = [
            key for key in (
                "RAG_LOG_DIR", "LOG_DIR", "RAG_EVENTS_LOG", "RAG_APPROVAL_RECEIPTS",
                "LAWRAG_ADMITTED_FEEDBACK_ROOT_SHA256",
                "LAWRAG_FEEDBACK_TRUST_POLICY_ID",
            )
            if os.environ.get(key, "").strip()
        ]
        if unexpected_logs:
            raise RuntimeError(
                "feedback log paths require an admitted LAWRAG_FEEDBACK_ROOT: "
                + ", ".join(unexpected_logs)
            )
        _pin_env_value("LAWRAG_FEEDBACK_DISABLED", "1")
        _pin_env_value("LAWRAG_FEEDBACK_TRUST_ZONE", "internal")
        _pin_env_value("LAWRAG_ADMITTED_FEEDBACK_ROOT_SHA256", "")
        _pin_env_value("LAWRAG_FEEDBACK_TRUST_POLICY_ID", "")
        feedback_root = None
        feedback_binding = {"enabled": False, "root": None}

    shortcut_value = os.environ.get("LAWRAG_QUERY_SHORTCUT_STORE", "").strip()
    shortcut_sha = os.environ.get(
        "LAWRAG_QUERY_SHORTCUT_STORE_SHA256", ""
    ).strip()
    if bool(shortcut_value) != bool(shortcut_sha):
        raise RuntimeError(
            "reviewed shortcut path and SHA-256 must be configured together"
        )
    if shortcut_value:
        if len(shortcut_sha) != 64 or any(
            char not in "0123456789abcdef" for char in shortcut_sha
        ):
            raise RuntimeError(
                "LAWRAG_QUERY_SHORTCUT_STORE_SHA256 must be lowercase SHA-256"
            )
        shortcut_path = _require_plain_path(
            Path(shortcut_value), kind="file", field="LAWRAG_QUERY_SHORTCUT_STORE"
        )
        if feedback_root is not None and _within(shortcut_path, feedback_root):
            raise RuntimeError(
                "reviewed shortcut store cannot live in the writable feedback root"
            )
        actual_sha = _stable_file_sha256(
            shortcut_path, field="reviewed shortcut store"
        )
        if actual_sha != shortcut_sha:
            raise RuntimeError("reviewed shortcut store SHA-256 mismatch")
        try:
            shortcut_bytes = _stable_file_bytes(
                shortcut_path, field="reviewed shortcut store"
            )
            if hashlib.sha256(shortcut_bytes).hexdigest() != shortcut_sha:
                raise RuntimeError("reviewed shortcut store SHA-256 mismatch")
            shortcut_blob = json.loads(shortcut_bytes.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("reviewed shortcut store is not valid JSON") from exc
        rows = shortcut_blob.get("candidates") if isinstance(shortcut_blob, dict) else None
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise RuntimeError("reviewed shortcut store has an invalid candidates list")
        current_receipt = snapshot.compact_receipt()
        active_keys: set[tuple[str, str, str]] = set()
        for position, row in enumerate(rows):
            if row.get("content_snapshot") != current_receipt:
                continue  # an append-only store may retain older generations
            doc_id = row.get("doc_id")
            qkey = row.get("qkey")
            node = row.get("node")
            surfaces = row.get("surfaces")
            status_value = row.get("status") or "잠정"
            if (
                not isinstance(qkey, str)
                or not qkey.strip()
                or not isinstance(doc_id, str)
                or not doc_id
                or isinstance(node, bool)
                or not isinstance(node, (str, int))
                or not isinstance(surfaces, list)
                or not surfaces
                or not all(isinstance(surface, str) and surface.strip() for surface in surfaces)
                or status_value not in {"잠정", "활성", "tombstone"}
            ):
                raise RuntimeError(
                    f"reviewed shortcut row {position} has an invalid contract"
                )
            try:
                expected = snapshot.provenance_for_document(doc_id).receipt()
            except Exception as exc:
                raise RuntimeError(
                    f"reviewed shortcut row {position} names an unknown document"
                ) from exc
            if row.get("content_provenance") != expected:
                raise RuntimeError(
                    f"reviewed shortcut row {position} has stale artifact provenance"
                )
            if status_value == "활성":
                active_key = (qkey, doc_id, str(node))
                if active_key in active_keys:
                    raise RuntimeError(
                        f"reviewed shortcut row {position} duplicates an active coordinate"
                    )
                active_keys.add(active_key)
        _pin_env_path("LAWRAG_QUERY_SHORTCUT_STORE", shortcut_path)
        _pin_env_path("RAG_QUERY_SHORTCUT_STORE", shortcut_path)
        _pin_env_value("LAWRAG_QUERY_SHORTCUT_STORE_SHA256", shortcut_sha)
        _pin_env_value("LAWRAG_QUERY_SHORTCUTS_DISABLED", "0")
        shortcut_binding: Dict[str, Any] = {
            "enabled": True,
            "path": str(shortcut_path),
            "sha256": shortcut_sha,
            "rows": len(rows),
        }
    else:
        if os.environ.get("RAG_QUERY_SHORTCUT_STORE", "").strip():
            raise RuntimeError(
                "RAG_QUERY_SHORTCUT_STORE requires deployment SHA admission"
            )
        _pin_env_value("LAWRAG_QUERY_SHORTCUTS_DISABLED", "1")
        shortcut_binding = {
            "enabled": False,
            "path": None,
            "sha256": None,
            "rows": 0,
        }

    return {
        "semantic_paths": pinned_semantics,
        "semantic_values": semantic_values,
        "feedback": feedback_binding,
        "shortcuts": shortcut_binding,
    }


def _bootstrap_release() -> Dict[str, Any]:
    """Pin one verified release before any lawrag router or store is imported.

    ``service.py`` is the production GenOS entry point and has no legacy mode.
    Local development starts ``lawrag.api.structure_app`` directly.  The
    deployment layer supplies the already materialized store paths; this
    bootstrap verifies them and pins the release identity for the process.
    """

    global _RELEASE_STORE, _RELEASE_RUNTIME_BINDING, _CONTENT_SNAPSHOT

    preloaded = sorted(
        name for name in sys.modules
        if name == "lawrag" or name.startswith("lawrag.")
    )
    if preloaded:
        raise RuntimeError(
            "GenOS release bootstrap must run before every lawrag import: "
            + ", ".join(preloaded[:8])
        )

    qdrant_config = None
    control_planes = None
    llm_runtime = None
    vector_runtime_info: Dict[str, Any] = {
        "backend": "file",
        "enabled": False,
        "encoder": None,
        "query_timeout_seconds": None,
    }
    retrieval_runtime = None

    store_value = os.environ.get("LAWRAG_RELEASE_STORE", "").strip()
    if not store_value:
        raise RuntimeError("GenOS startup requires LAWRAG_RELEASE_STORE")

    # Importing a sealed code package must not create unbound __pycache__ bytes.
    sys.dont_write_bytecode = True
    from lawrag.platform.release import ReleaseStore

    store_path = Path(store_value)
    if not store_path.is_absolute():
        raise RuntimeError("LAWRAG_RELEASE_STORE must be absolute")
    code_root_value = os.environ.get("LAWRAG_CODE_PACKAGE_ROOT", "").strip()
    code_root = _ROOT
    if code_root_value:
        configured_code_root = Path(code_root_value)
        if not configured_code_root.is_absolute():
            raise RuntimeError("LAWRAG_CODE_PACKAGE_ROOT must be absolute")
        if configured_code_root.resolve() != code_root:
            raise RuntimeError(
                "LAWRAG_CODE_PACKAGE_ROOT must name the directory containing service.py"
            )
    try:
        Path(ReleaseStore.__init__.__code__.co_filename).resolve().relative_to(
            code_root
        )
    except ValueError as exc:
        raise RuntimeError(
            "loaded release runtime is outside the deployed code package"
        ) from exc
    for relative_asset in (
        Path("lawrag/core/rag/patterns.yaml"),
        Path("lawrag/core/domain_graph/oql_patterns.yaml"),
    ):
        asset = _require_plain_path(
            code_root / relative_asset,
            kind="file",
            field=f"required code asset {relative_asset.as_posix()}",
        )
        try:
            asset.relative_to(code_root)
        except ValueError as exc:
            raise RuntimeError("required code asset escapes the code package") from exc
    store = ReleaseStore(
        store_path,
        target="genos",
        code_package_root=code_root,
        read_only=True,
    )
    pointer, release, runtime_binding = store.load_active_runtime()
    runtime_root = store.runtime_root(release.release_id)
    resolved_paths = runtime_binding.resolved_paths(runtime_root)
    resolved_artifacts = runtime_binding.resolved_artifacts(runtime_root)
    for key, value in resolved_paths.items():
        configured = os.environ.get(key, "").strip()
        if configured and str(Path(configured).resolve()) != value:
            raise RuntimeError(f"{key} conflicts with the active release binding")
        os.environ[key] = value
    main_state_path = resolved_artifacts.get("main.state")
    if not main_state_path:
        raise RuntimeError("active release has no MAIN state artifact")
    configured_main = os.environ.get("RAG_MAIN_PIPELINE_MANIFEST", "").strip()
    if configured_main and str(Path(configured_main).resolve()) != main_state_path:
        raise RuntimeError(
            "RAG_MAIN_PIPELINE_MANIFEST conflicts with the active release binding"
        )
    os.environ["RAG_MAIN_PIPELINE_MANIFEST"] = main_state_path
    os.environ["LAWRAG_SERVING_SEALED"] = "1"
    os.environ["LAWRAG_CODE_PACKAGE_ROOT"] = str(code_root)
    from lawrag.core.rag import main_promotion

    main_state = main_promotion.load_state()
    main_mismatches = []
    if main_state.get("pipeline_id") != release.main.pipeline_id:
        main_mismatches.append("pipeline_id")
    if (
        main_promotion.effective_runtime_profile(main_state)
        != release.main.runtime_profile
    ):
        main_mismatches.append("runtime_profile")
    if main_state.get("generation") != release.main.generation:
        main_mismatches.append("generation")
    if main_promotion.fingerprint(main_state) != release.main.state_sha256:
        main_mismatches.append("state_sha256")
    if main_mismatches:
        raise RuntimeError(
            "active release MAIN state mismatch: " + ", ".join(main_mismatches)
        )
    if release.main.generation > 0:
        receipt_path = resolved_artifacts.get("main.promotion_receipt")
        if not receipt_path:
            raise RuntimeError("promoted MAIN has no release-proved transition chain")
        try:
            chain_bytes = _stable_file_bytes(
                Path(receipt_path), field="MAIN transition chain"
            )
            if hashlib.sha256(chain_bytes).hexdigest() != (
                release.main.promotion_receipt_sha256
            ):
                raise RuntimeError(
                    "MAIN transition chain differs from the release proof"
                )
            chain_blob = json.loads(chain_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("MAIN transition chain is not valid JSON") from exc
        if not isinstance(chain_blob, dict):
            raise RuntimeError("MAIN transition chain root must be an object")
        plan_path = resolved_artifacts.get("main.promotion_plan")
        if not plan_path:
            raise RuntimeError("promoted MAIN has no release-proved promotion plan")
        try:
            plan_bytes = _stable_file_bytes(
                Path(plan_path), field="MAIN promotion plan"
            )
            if hashlib.sha256(plan_bytes).hexdigest() != (
                release.main.promotion_plan_sha256
            ):
                raise RuntimeError(
                    "MAIN promotion plan differs from the release proof"
                )
            plan_blob = json.loads(plan_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("MAIN promotion plan is not valid JSON") from exc
        if not isinstance(plan_blob, dict):
            raise RuntimeError("MAIN promotion plan root must be an object")
        chain_errors = main_promotion.validate_transition_chain(
            chain_blob, main_state
        )
        if chain_errors:
            raise RuntimeError(
                "active release MAIN transition chain mismatch: "
                + "; ".join(chain_errors)
            )
        receipt_blob = main_promotion.transition_chain_tip(chain_blob)
        plan_errors = main_promotion.validate_runtime_promotion_plan(
            plan_blob, receipt_blob, main_state
        )
        if plan_errors:
            raise RuntimeError(
                "active release MAIN promotion plan mismatch: "
                + "; ".join(plan_errors)
            )

    # MAIN is now pinned, so the switch decision cannot accidentally come from
    # a mutable legacy path.  The new adapter is independently rollbackable:
    # an OFF release keeps byte-for-byte legacy retrieval, while ON requires
    # every SourceSet serving proof and fails closed before router import.
    from lawrag.core.rag.switches import (
        bind_sealed_promotion_overrides,
        is_on,
    )

    bind_sealed_promotion_overrides(
        dict(main_state.get("switches") or {}),
        main_state_sha256=release.main.state_sha256,
    )

    if is_on("sourceset_content_snapshot"):
        required_proofs = {
            "lock_sha256": release.source_set.lock_sha256,
            "lock_artifact_sha256": release.source_set.lock_artifact_sha256,
            "materialization_sha256": release.source_set.materialization_sha256,
            "materialization_receipt_sha256": (
                release.source_set.materialization_receipt_sha256
            ),
            "catalog_sha256": release.source_set.catalog_sha256,
            "catalog_artifact_sha256": (
                release.source_set.catalog_artifact_sha256
            ),
        }
        missing = sorted(key for key, value in required_proofs.items() if value is None)
        if missing:
            raise RuntimeError(
                "SourceSet content snapshot requires release proofs: "
                + ", ".join(missing)
            )
        required_artifacts = {
            "source_set.lock",
            "source_set.materialization",
            "source_set.catalog",
        }
        absent_artifacts = sorted(required_artifacts - set(resolved_artifacts))
        if absent_artifacts:
            raise RuntimeError(
                "SourceSet content snapshot requires runtime artifacts: "
                + ", ".join(absent_artifacts)
            )
        from lawrag.core.rag.content_snapshot import (
            bind_content_snapshot,
            bind_retrieval_runtime_receipt,
            create_content_snapshot,
            create_retrieval_runtime_receipt,
        )
        from lawrag.datasets.catalog import (
            load_installed_catalog,
            load_source_set_lock,
            open_materialized_source_set,
        )

        source_set_lock = load_source_set_lock(
            resolved_artifacts["source_set.lock"],
            expected_artifact_sha256=str(
                release.source_set.lock_artifact_sha256
            ),
        )
        installed_catalog = load_installed_catalog(
            resolved_artifacts["source_set.catalog"],
            expected_artifact_sha256=str(
                release.source_set.catalog_artifact_sha256
            ),
        )
        if installed_catalog.catalog_sha256 != release.source_set.catalog_sha256:
            raise RuntimeError(
                "installed catalog canonical hash does not match the active release"
            )
        installed_catalog.resolve_lock(
            source_set_lock,
            expected_source_set_sha256=release.source_set.sha256,
            expected_lock_sha256=str(release.source_set.lock_sha256),
        )
        materialized = open_materialized_source_set(
            resolved_artifacts["source_set.materialization"],
            source_set_lock,
            trusted_root=runtime_root,
        )
        _CONTENT_SNAPSHOT = create_content_snapshot(
            pointer=pointer,
            release=release,
            runtime_binding=runtime_binding,
            source_set_lock=source_set_lock,
            catalog_sha256=installed_catalog.catalog_sha256,
            catalog_artifact_sha256=str(
                release.source_set.catalog_artifact_sha256
            ),
            materialized=materialized,
            runtime_paths=resolved_paths,
            runtime_artifact_paths=resolved_artifacts,
        )
        from lawrag.platform import runtime_services

        acl_receipt = store.load_active_validation_receipt(kind="acl")
        if (
            acl_receipt.release_id != release.release_id
            or acl_receipt.release_manifest_sha256 != release.manifest_sha256
            or acl_receipt.target != release.target
        ):
            raise RuntimeError(
                "active ACL receipt raced with or belongs to another release"
            )
        llm_descriptor_path = _require_plain_path(
            Path(resolved_artifacts["semantics.content"])
            / "runtime"
            / "llm.json",
            kind="file",
            field="release-proved product LLM descriptor",
        )
        llm_descriptor = runtime_services.load_llm_descriptor(
            llm_descriptor_path
        )
        llm_runtime = _configure_release_llm_runtime(
            llm_descriptor,
            export_allowed=bool(release.source_set.export_allowed),
            acl_receipt=acl_receipt,
        )
        control_planes = _configure_sourceset_control_planes(
            _CONTENT_SNAPSHOT,
            runtime_root=runtime_root,
            export_allowed=bool(release.source_set.export_allowed),
            acl_receipt=acl_receipt,
        )
        vector_bindings = [row for row in release.indexes if row.kind == "vector"]
        _pin_env_value("RAG_VECTOR", "1" if vector_bindings else "0")
        if not vector_bindings:
            _pin_env_value("LAWRAG_EMBEDDING_DISABLED", "1")
        release_vector_backend = "file"
        if vector_bindings:
            from lawrag.core.rag import qdrant_store

            release_vector_backend = qdrant_store.bound_backend(_CONTENT_SNAPSHOT)
            qdrant_config = qdrant_store.load_bound_config(_CONTENT_SNAPSHOT)
            if (
                qdrant_config is not None
                and not release.source_set.export_allowed
                and qdrant_config.get("trust_zone") != "internal"
            ):
                raise RuntimeError(
                    "restricted SourceSet Qdrant must stay in the internal trust zone"
                )
            if qdrant_config is not None:
                _require_deployment_descriptor_admission(
                    "qdrant", qdrant_config.get("config_sha256")
                )
                runtime_services.require_acl_projection(
                    acl_receipt,
                    service_name="qdrant",
                    expected=runtime_services.qdrant_acl_projection(
                        qdrant_config
                    ),
                )
                _resolve_bound_secret(
                    binding_id=qdrant_config["credential_binding_id"],
                    binding_version=qdrant_config[
                        "credential_binding_version"
                    ],
                    selected_env="QDRANT_API_KEY",
                )
        configured_vector_backend = os.environ.get(
            "RAG_VECTOR_BACKEND", ""
        ).strip().lower()
        if (
            configured_vector_backend
            and configured_vector_backend != release_vector_backend
        ):
            raise RuntimeError(
                "RAG_VECTOR_BACKEND conflicts with the active release binding"
        )
        os.environ["RAG_VECTOR_BACKEND"] = release_vector_backend
        if qdrant_config is not None:
            for key, config_key in (
                ("QDRANT_URL", "url"),
                ("QDRANT_COLLECTION", "collection"),
            ):
                configured = os.environ.get(key, "").strip()
                expected = str(qdrant_config[config_key])
                if configured and configured != expected:
                    raise RuntimeError(
                        f"{key} conflicts with the active release binding"
                    )
                os.environ[key] = expected
            _pin_env_value(
                "QDRANT_CREDENTIAL_BINDING_ID",
                str(qdrant_config["credential_binding_id"]),
            )
            _pin_env_value(
                "QDRANT_CREDENTIAL_BINDING_VERSION",
                str(qdrant_config["credential_binding_version"]),
            )
            _pin_env_value(
                "QDRANT_TRUST_POLICY_ID",
                str(qdrant_config["trust_policy_id"]),
            )
            _pin_env_value(
                "QDRANT_TRUST_ZONE", str(qdrant_config["trust_zone"])
            )
            _pin_env_value("QDRANT_TIMEOUT", "30")
        encoder_runtime = None
        if vector_bindings:
            if (
                Path(resolved_paths["RAG_VECTOR_STORE"]).resolve()
                != Path(resolved_artifacts["index.vector"]).resolve()
            ):
                raise RuntimeError(
                    "RAG_VECTOR_STORE is not the release-proved vector artifact"
                )
            expected_model = vector_bindings[0].embedding_model_fingerprint
            if not expected_model:
                raise RuntimeError("active vector index has no encoder fingerprint")
            encoder_descriptor_path = _require_plain_path(
                Path(resolved_artifacts["index.vector"]) / "encoder.json",
                kind="file",
                field="release-proved query encoder descriptor",
            )
            encoder_descriptor = runtime_services.load_embedding_descriptor(
                encoder_descriptor_path
            )
            encoder_runtime = _configure_release_embedding_runtime(
                encoder_descriptor,
                expected_fingerprint=expected_model,
                export_allowed=bool(release.source_set.export_allowed),
                acl_receipt=acl_receipt,
            )
        vector_runtime_info = {
            "backend": os.environ.get("RAG_VECTOR_BACKEND", "file"),
            "enabled": os.environ.get("RAG_VECTOR", "0") == "1",
            "config_sha256": (
                qdrant_config["config_sha256"]
                if qdrant_config is not None else None
            ),
            "query_timeout_seconds": (
                30 if qdrant_config is not None else None
            ),
            "trust_zone": (
                qdrant_config.get("trust_zone")
                if qdrant_config is not None else "local"
            ),
            "encoder": encoder_runtime,
            **(
                {
                    "url": os.environ["QDRANT_URL"],
                    "collection": os.environ["QDRANT_COLLECTION"],
                    "credential_binding_id": qdrant_config[
                        "credential_binding_id"
                    ],
                    "credential_binding_version": qdrant_config[
                        "credential_binding_version"
                    ],
                    "trust_policy_id": qdrant_config["trust_policy_id"],
                    "credential_configured": bool(
                        os.environ.get("QDRANT_API_KEY", "")
                    ),
                    "deployment_admission_sha256": os.environ.get(
                        "LAWRAG_ADMITTED_QDRANT_DESCRIPTOR_SHA256"
                    ),
                }
                if qdrant_config is not None else {}
            ),
        }
        bind_content_snapshot(_CONTENT_SNAPSHOT)
        retrieval_runtime = create_retrieval_runtime_receipt(
            _CONTENT_SNAPSHOT,
            llm_runtime=llm_runtime or {},
            vector_runtime=vector_runtime_info,
            shortcut_runtime=(control_planes or {}).get("shortcuts") or {},
        )
        bind_retrieval_runtime_receipt(retrieval_runtime)
    else:
        # Rollback disables the SourceSet adapter, not release identity and
        # network policy.  The GenOS process still consumes the release-proved
        # LLM descriptor and active ACL; it never falls back to ambient env.
        from lawrag.platform import runtime_services

        acl_receipt = store.load_active_validation_receipt(kind="acl")
        if (
            acl_receipt.release_id != release.release_id
            or acl_receipt.release_manifest_sha256 != release.manifest_sha256
            or acl_receipt.target != release.target
        ):
            raise RuntimeError("rollback release has no matching ACL receipt")
        llm_descriptor = runtime_services.load_llm_descriptor(
            _require_plain_path(
                Path(resolved_artifacts["semantics.content"])
                / "runtime"
                / "llm.json",
                kind="file",
                field="release-proved product LLM descriptor",
            )
        )
        llm_runtime = _configure_release_llm_runtime(
            llm_descriptor,
            export_allowed=bool(release.source_set.export_allowed),
            acl_receipt=acl_receipt,
        )
        # The emergency rollback path is a complete, deterministic vector-off
        # binding.  It must work in a clean deployment and must not inherit an
        # encoder or Qdrant intent from the process environment.
        unexpected_vector_intent = sorted(
            key
            for key, value in os.environ.items()
            if value.strip()
            and (
                key.startswith("EMBED_")
                or key.startswith("GENOS_EMBED_")
                or key.startswith("QDRANT_")
                or key
                in {
                    "RAG_EMBEDDING_MODEL_FINGERPRINT",
                    "LAWRAG_ADMITTED_QDRANT_DESCRIPTOR_SHA256",
                }
            )
        )
        if unexpected_vector_intent:
            raise RuntimeError(
                "rollback release cannot bind ambient vector services: "
                + ", ".join(unexpected_vector_intent)
            )
        _pin_env_value("RAG_VECTOR", "0")
        _pin_env_value("RAG_VECTOR_BACKEND", "file")
        _pin_env_value("LAWRAG_EMBEDDING_DISABLED", "1")
        unexpected_feedback = [
            key for key in (
                "LAWRAG_FEEDBACK_ROOT",
                "RAG_LOG_DIR",
                "LOG_DIR",
                "RAG_EVENTS_LOG",
                "RAG_APPROVAL_RECEIPTS",
                "LAWRAG_QUERY_SHORTCUT_STORE",
                "RAG_QUERY_SHORTCUT_STORE",
            )
            if os.environ.get(key, "").strip()
        ]
        if unexpected_feedback:
            raise RuntimeError(
                "rollback release cannot bind mutable feedback planes: "
                + ", ".join(unexpected_feedback)
            )
        _pin_env_value("LAWRAG_FEEDBACK_DISABLED", "1")
        _pin_env_value("LAWRAG_QUERY_SHORTCUTS_DISABLED", "1")
    _RELEASE_STORE = store
    _RELEASE_RUNTIME_BINDING = runtime_binding
    return {
        "mode": "release",
        "ready": True,
        "release": {
            "generation": pointer.generation,
            "release_id": release.release_id,
            "manifest_sha256": release.manifest_sha256,
            "source_set_id": release.source_set.source_set_id,
            "source_set_generation": release.source_set.generation_id,
            "source_set_sha256": release.source_set.sha256,
            "semantic_generation": release.semantics.generation_id,
            "export_allowed": release.source_set.export_allowed,
            "runtime_binding_sha256": runtime_binding.binding_sha256,
            **(
                {"content_snapshot": _CONTENT_SNAPSHOT.compact_receipt()}
                if _CONTENT_SNAPSHOT is not None
                else {}
            ),
        },
        "runtime_paths": resolved_paths,
        "runtime_artifacts": resolved_artifacts,
        "vector_runtime": vector_runtime_info,
        "control_planes": control_planes,
        "llm_runtime": llm_runtime,
        "retrieval_runtime": retrieval_runtime,
        "code_package_root": str(code_root),
    }


try:
    _RELEASE_BINDING = _bootstrap_release()
except Exception as exc:
    _RELEASE_BOOTSTRAP_ERROR = type(exc).__name__
    _RELEASE_BINDING = {"mode": "release", "ready": False, "release": None}


def _require_ready() -> None:
    if _RELEASE_BOOTSTRAP_ERROR is not None:
        raise RuntimeError(
            f"GenOS release bootstrap failed: {_RELEASE_BOOTSTRAP_ERROR}"
        )
    _verify_bound_secrets()
    for key, expected in ((_RELEASE_BINDING or {}).get("runtime_paths") or {}).items():
        if os.environ.get(key) != expected:
            raise RuntimeError(f"active release runtime path changed after bootstrap: {key}")
    if (_RELEASE_BINDING or {}).get("mode") == "release":
        release = (_RELEASE_BINDING or {}).get("release")
        if (
            not isinstance(release, dict)
            or _RELEASE_STORE is None
            or _RELEASE_RUNTIME_BINDING is None
        ):
            raise RuntimeError("active release runtime verifier is unavailable")
        if os.environ.get("LAWRAG_CODE_PACKAGE_ROOT") != (
            (_RELEASE_BINDING or {}).get("code_package_root")
        ):
            raise RuntimeError("active release code package path changed after bootstrap")
        expected_main = ((_RELEASE_BINDING or {}).get("runtime_artifacts") or {}).get(
            "main.state"
        )
        if os.environ.get("RAG_MAIN_PIPELINE_MANIFEST") != expected_main:
            raise RuntimeError("active release MAIN state path changed after bootstrap")
        vector_runtime = (_RELEASE_BINDING or {}).get("vector_runtime") or {}
        if os.environ.get("RAG_VECTOR_BACKEND", "file") != vector_runtime.get(
            "backend", "file"
        ):
            raise RuntimeError("active release vector backend changed after bootstrap")
        if (os.environ.get("RAG_VECTOR") == "1") != bool(
            vector_runtime.get("enabled")
        ):
            raise RuntimeError("active release vector enablement changed after bootstrap")
        encoder_runtime = vector_runtime.get("encoder")
        if isinstance(encoder_runtime, dict):
            for key, expected in (encoder_runtime.get("env") or {}).items():
                if os.environ.get(key) != expected:
                    raise RuntimeError(
                        f"active encoder binding changed after bootstrap: {key}"
                    )
            for key, expected in (
                encoder_runtime.get("credential_presence") or {}
            ).items():
                if bool(os.environ.get(key, "")) != bool(expected):
                    raise RuntimeError(
                        "active encoder credential presence changed after bootstrap: "
                        + key
                    )
        elif os.environ.get("LAWRAG_EMBEDDING_DISABLED") != "1":
            raise RuntimeError("disabled encoder binding changed after bootstrap")
        llm_runtime = (_RELEASE_BINDING or {}).get("llm_runtime") or {}
        for key, expected in (llm_runtime.get("env") or {}).items():
            if os.environ.get(key) != expected:
                raise RuntimeError(
                    f"active product LLM binding changed after bootstrap: {key}"
                )
        for key, expected in (
            llm_runtime.get("credential_presence") or {}
        ).items():
            if bool(os.environ.get(key, "")) != bool(expected):
                raise RuntimeError(
                    f"active product LLM credential presence changed after bootstrap: {key}"
                )
        if vector_runtime.get("backend") == "qdrant":
            if (
                os.environ.get("QDRANT_URL") != vector_runtime.get("url")
                or os.environ.get("QDRANT_COLLECTION")
                != vector_runtime.get("collection")
                or os.environ.get("QDRANT_TIMEOUT")
                != str(vector_runtime.get("query_timeout_seconds"))
                or os.environ.get("QDRANT_CREDENTIAL_BINDING_ID")
                != vector_runtime.get("credential_binding_id")
                or os.environ.get("QDRANT_CREDENTIAL_BINDING_VERSION")
                != vector_runtime.get("credential_binding_version")
                or os.environ.get("QDRANT_TRUST_POLICY_ID")
                != vector_runtime.get("trust_policy_id")
                or os.environ.get("QDRANT_TRUST_ZONE")
                != vector_runtime.get("trust_zone")
                or bool(os.environ.get("QDRANT_API_KEY", ""))
                != bool(vector_runtime.get("credential_configured"))
                or os.environ.get(
                    "LAWRAG_ADMITTED_QDRANT_DESCRIPTOR_SHA256"
                )
                != vector_runtime.get("deployment_admission_sha256")
            ):
                raise RuntimeError(
                    "active release Qdrant binding changed after bootstrap"
                )
        _RELEASE_STORE.verify_runtime_ready(
            str(release["release_id"]),
            expected_binding_sha256=str(release["runtime_binding_sha256"]),
        )
        expected_snapshot = release.get("content_snapshot")
        if expected_snapshot is not None:
            from lawrag.core.rag.content_snapshot import current_content_snapshot

            current = current_content_snapshot(required=True)
            if current.compact_receipt() != expected_snapshot:
                raise RuntimeError("active content snapshot changed after bootstrap")
            from lawrag.core.rag.content_snapshot import (
                current_retrieval_runtime_receipt,
            )

            if current_retrieval_runtime_receipt(required=True) != (
                (_RELEASE_BINDING or {}).get("retrieval_runtime")
            ):
                raise RuntimeError(
                    "active retrieval runtime receipt changed after bootstrap"
                )
        control_planes = (_RELEASE_BINDING or {}).get("control_planes")
        if isinstance(control_planes, dict):
            for key, expected in (
                control_planes.get("semantic_paths") or {}
            ).items():
                if os.environ.get(key) != expected:
                    raise RuntimeError(
                        f"active semantic path changed after bootstrap: {key}"
                    )
            for key, expected in (
                control_planes.get("semantic_values") or {}
            ).items():
                if os.environ.get(key) != expected:
                    raise RuntimeError(
                        f"active semantic value changed after bootstrap: {key}"
                    )
            feedback = control_planes.get("feedback") or {}
            if feedback.get("enabled"):
                expected_root = str(feedback.get("root"))
                if (
                    os.environ.get("LAWRAG_FEEDBACK_ROOT") != expected_root
                    or os.environ.get("RAG_LOG_DIR") != expected_root
                    or os.environ.get("LAWRAG_FEEDBACK_TRUST_ZONE")
                    != feedback.get("trust_zone")
                    or os.environ.get("LAWRAG_FEEDBACK_TRUST_POLICY_ID")
                    != feedback.get("trust_policy_id")
                    or os.environ.get("LAWRAG_ADMITTED_FEEDBACK_ROOT_SHA256")
                    != feedback.get("root_sha256")
                    or os.environ.get("LOG_DIR") != feedback.get("log_dir")
                    or os.environ.get("RAG_EVENTS_LOG") != feedback.get("events")
                    or os.environ.get("RAG_APPROVAL_RECEIPTS")
                    != feedback.get("approval_receipts")
                    or os.environ.get("LAWRAG_FEEDBACK_DISABLED") != "0"
                ):
                    raise RuntimeError(
                        "feedback output binding changed after bootstrap"
                    )
                _require_plain_path(
                    Path(expected_root),
                    kind="directory",
                    field="LAWRAG_FEEDBACK_ROOT",
                )
            elif (
                os.environ.get("LAWRAG_FEEDBACK_DISABLED") != "1"
                or os.environ.get("LAWRAG_FEEDBACK_TRUST_ZONE") != "internal"
                or os.environ.get("LAWRAG_ADMITTED_FEEDBACK_ROOT_SHA256") != ""
                or os.environ.get("LAWRAG_FEEDBACK_TRUST_POLICY_ID") != ""
            ):
                raise RuntimeError("disabled feedback binding changed after bootstrap")
            shortcuts = control_planes.get("shortcuts") or {}
            if shortcuts.get("enabled"):
                expected_path = str(shortcuts.get("path"))
                expected_sha = str(shortcuts.get("sha256"))
                if (
                    os.environ.get("LAWRAG_QUERY_SHORTCUT_STORE") != expected_path
                    or os.environ.get("RAG_QUERY_SHORTCUT_STORE") != expected_path
                    or os.environ.get("LAWRAG_QUERY_SHORTCUT_STORE_SHA256")
                    != expected_sha
                    or os.environ.get("LAWRAG_QUERY_SHORTCUTS_DISABLED") != "0"
                ):
                    raise RuntimeError(
                        "reviewed shortcut binding changed after bootstrap"
                    )
                if _stable_file_sha256(
                    Path(expected_path), field="reviewed shortcut store"
                ) != expected_sha:
                    raise RuntimeError(
                        "reviewed shortcut store changed after bootstrap"
                    )
            elif os.environ.get("LAWRAG_QUERY_SHORTCUTS_DISABLED") != "1":
                raise RuntimeError("disabled shortcut binding changed after bootstrap")


def _release_export_allowed() -> bool:
    release = (_RELEASE_BINDING or {}).get("release")
    return not isinstance(release, dict) or bool(release.get("export_allowed"))


def _release_mode() -> bool:
    return (_RELEASE_BINDING or {}).get("mode") == "release"


def _require_code_module(path: str | os.PathLike[str]) -> None:
    if not _release_mode():
        return
    try:
        Path(path).resolve().relative_to(_ROOT)
    except ValueError as exc:
        raise RuntimeError(
            "release mode imported an application module outside its code package"
        ) from exc


def _require_query_only_call(data: Mapping[str, Any]) -> None:
    """Reject every release-mode call tunnel that can mutate application state."""

    method = str(data.get("method") or "GET").upper()
    raw_path = data.get("path") or "/"
    if not isinstance(raw_path, str):
        raise ValueError("path 는 문자열이어야 합니다")
    if (
        not raw_path.startswith("/")
        or "\\" in raw_path
        or "\x00" in raw_path
        or "?" in raw_path
        or "#" in raw_path
        or "//" in raw_path
        or any(part in {"", ".", ".."} for part in raw_path[1:].split("/"))
    ):
        raise PermissionError("release mode requires a canonical application path")
    if method == "GET":
        if raw_path in _RELEASE_GET_ALLOWLIST:
            return
        raise PermissionError(
            f"release mode GET path is not an approved query route: {raw_path}"
        )
    if method in {"HEAD", "OPTIONS"}:
        raise PermissionError(
            f"release mode does not expose HTTP metadata method: {method}"
        )
    if method != "POST":
        raise PermissionError(f"release mode blocks mutating HTTP method: {method}")
    if raw_path in _RELEASE_POST_ALLOWLIST:
        return
    raise PermissionError(f"release mode POST path is not query-only: {raw_path}")


_APP = None                       # 앱은 첫 호출 때 한 번만 세운다 — 적재가 무겁다


def _app():
    global _APP
    _require_ready()
    if _APP is None:
        from lawrag.api import structure_app
        _require_code_module(structure_app.__file__)
        _APP = structure_app.app
    return _APP


def _ops():
    _require_ready()
    import lawrag.api.ops as ops_mod
    _require_code_module(ops_mod.__file__)
    return ops_mod


async def _do_call(data: Dict[str, Any]) -> Dict[str, Any]:
    ops = _ops()
    method = (data.get("method") or "GET").upper()
    path = data.get("path") or "/"
    query = data.get("query") or ""
    if not query and data.get("params") is not None:
        params = data["params"]
        if not isinstance(params, dict):
            raise ValueError("params 는 JSON 객체여야 합니다")
        query = urllib.parse.urlencode(params, doseq=True)
    if "json" in data:
        body = json.dumps(data["json"], ensure_ascii=False).encode()
        content_type = "application/json"
    elif data.get("body_b64"):
        body = base64.b64decode(data["body_b64"])
        content_type = data.get("content_type") or "application/octet-stream"
    else:
        body, content_type = b"", ""
    status, raw = await ops._call_self(_app(), method, path, query,
                                       content_type, body)
    out: Dict[str, Any] = {"status": status, "ok": status < 400}
    try:
        out["json"] = json.loads(raw.decode("utf-8"))
    except Exception:                       # PNG·tar 같은 이진 응답은 b64 로
        out["body_b64"] = base64.b64encode(raw).decode()
    return out


async def service(config: Dict[str, Any], data: Dict[str, Any]):
    """GenOS 가 부르는 유일한 문. 실패도 JSON 으로 낸다 — 게이트웨이 500 뒤에
    숨으면 그쪽 터미널에서 원인을 볼 길이 없다."""
    op = (data or {}).get("op") or "call"
    try:
        if op == "ping":
            if _RELEASE_BOOTSTRAP_ERROR is not None:
                return {
                    "service": "8-AGENT",
                    "ready": False,
                    "release_mode": (_RELEASE_BINDING or {}).get("mode"),
                    "release_error": _RELEASE_BOOTSTRAP_ERROR,
                }
            ops = _ops()
            return {"service": "8-AGENT", "ready": True,
                    "release_mode": (_RELEASE_BINDING or {}).get("mode"),
                    "release": (_RELEASE_BINDING or {}).get("release"),
                    **(
                        {"retrieval_runtime": (_RELEASE_BINDING or {}).get(
                            "retrieval_runtime"
                        )}
                        if (_RELEASE_BINDING or {}).get("retrieval_runtime") is not None
                        else {}
                    ),
                    "rev": ops._rev(),
                    "record": ops.RECORD, "outbox": len(ops._read_ops(ops._OPS_FILE)),
                    "store": os.environ.get("STRUCTURE_STORE", "")}
        _require_ready()
        if op != "call":
            raise PermissionError(
                f"active release service is query-only; blocked op: {op}"
            )
        _require_query_only_call(data)
        if op == "call":
            return await _do_call(data)
        raise PermissionError(f"unsupported release operation: {op}")
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        if detail is not None:      # HTTPException — 기준 충돌(409)·규약 위반(400)
            return {"error": detail, "status": getattr(exc, "status_code", 500),
                    "op": op}
        return {"error": f"{type(exc).__name__}: {exc}", "op": op}
