"""GENOS code-serving entry point for the active semantic runtime.

GENOS exposes only ``async def service(config, data)`` through its JSON
gateway. Startup stays lazy so ``ping`` and ``connections`` work before a
published data generation is mounted. Application calls use an explicit
``GENOS_GENERATION`` when set, otherwise the current generation published
below ``GENOS_DATA_ROOT``.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import logging
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "02_BACKEND"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from semantic_runtime import observability as obs

_APP = None
_BINDING: dict[str, Any] | None = None

_GET_ALLOWLIST = frozenset(
    {
        "/health",
        "/v1/pipeline/status",
        "/v1/rag/search",
        "/v1/rag/section",
        "/v1/rag/scopes",
        "/v1/rag/nodes",
        "/v1/rag/documents",
        "/v1/rag/document/outline",
        "/v1/rag/document/read",
        "/v1/rag/links/summary",
        "/v1/rag/links",
    }
)
_POST_ALLOWLIST = frozenset({"/v1/rag/ask"})
_API_TYPES = frozenset(
    {
        "PING",
        "CONNECTIONS",
        "DIAGNOSTICS",
        "HEALTH",
        "RAG_SEARCH",
        "RAG_ASK",
        "ELS_QUERY",
        "PIPELINE_BOOTSTRAP_EXTERNAL",
        "PIPELINE_EXTERNAL",
        "PIPELINE_INTERNAL",
        "PIPELINE_PUBLISH",
        "PIPELINE_STATUS",
    }
)

log = obs.get_logger("service")
obs.event(
    log,
    "boot.loaded",
    python=platform.python_version(),
    code_root=str(_ROOT),
    data_root=os.environ.get("GENOS_DATA_ROOT", ""),
    generation_configured=bool(os.environ.get("GENOS_GENERATION", "").strip()),
    llm_backend=os.environ.get("SEMANTIC_LLM_BACKEND", "anthropic").strip().lower(),
)


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object")
    return value


def _explicit_generation() -> tuple[Path, Path, dict[str, Any]] | None:
    configured = os.environ.get("GENOS_GENERATION", "").strip()
    if not configured:
        return None
    path = Path(configured)
    if not path.is_absolute():
        raise RuntimeError("GENOS_GENERATION must be an absolute path")
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("GENOS_GENERATION must be an existing non-symlink directory")
    generation = path.resolve()
    manifest = _json(generation / "manifest.json")
    if manifest.get("schema_version") != "term-source-generation-v1":
        raise RuntimeError("GENOS_GENERATION has an unsupported manifest")
    return _ROOT, generation, {
        "mode": "genos-generation",
        "generation_id": manifest.get("generation_id"),
        "data_status": manifest.get("data_status"),
    }


def _data_generation() -> tuple[Path, Path, dict[str, Any]] | None:
    configured = os.environ.get("GENOS_DATA_ROOT", "").strip()
    if not configured:
        return None
    data_root = Path(configured)
    if not data_root.is_absolute() or data_root.is_symlink():
        raise RuntimeError("GENOS_DATA_ROOT must be an absolute non-symlink path")
    data_root = data_root.resolve()
    pointer_path = data_root / "generations/CURRENT.json"
    if not pointer_path.is_file():
        return None
    pointer = _json(pointer_path)
    if pointer.get("schema_version") != "genos-current-generation-v1":
        raise RuntimeError("GENOS data generation pointer is unsupported")
    generation = Path(str(pointer.get("path") or ""))
    if not generation.is_absolute() or generation.is_symlink():
        raise RuntimeError("GENOS data generation path is invalid")
    generation = generation.resolve()
    generation.relative_to(data_root)
    if _sha(generation / "manifest.json") != pointer.get("manifest_sha256"):
        raise RuntimeError("GENOS data generation manifest hash mismatch")
    return _ROOT, generation, {
        "mode": "genos-data-current",
        "generation_id": pointer.get("generation_id"),
    }


def _local_release() -> tuple[Path, Path, dict[str, Any]]:
    pointer = _json(_ROOT / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json")
    if pointer.get("schema_version") != "semantic-runtime-active-v2":
        raise RuntimeError("local semantic release is not active")
    manifest_path = (_ROOT / str(pointer["manifest_path"])).resolve()
    manifest_path.relative_to(_ROOT)
    if _sha(manifest_path) != pointer.get("release_manifest_sha256"):
        raise RuntimeError("local release hash mismatch")
    release = _json(manifest_path)
    code_root = (_ROOT / str(release["code_root"])).resolve()
    code_root.relative_to(_ROOT)
    for relative, expected in release.get("files", {}).items():
        path = (code_root / relative).resolve()
        path.relative_to(code_root)
        if _sha(path) != expected:
            raise RuntimeError("local release code/schema mismatch")
    generation = (_ROOT / str(release["data_path"])).resolve()
    generation.relative_to(_ROOT)
    if _sha(generation / "manifest.json") != release.get("data_manifest_sha256"):
        raise RuntimeError("local release data manifest mismatch")
    return code_root, generation, {
        "mode": "local-release",
        "release_id": pointer.get("release_id"),
        "generation": pointer.get("generation"),
    }


def _resolve_binding() -> tuple[Path, Path, dict[str, Any]]:
    explicit = _explicit_generation()
    if explicit is not None:
        return explicit
    current = _data_generation()
    return current if current is not None else _local_release()


def _source_only_provider(
    root: Path, runtime: Path, export_allowed: bool, message: str
):
    from semantic_runtime.provider import Haiku

    class SourceOnly(Haiku):
        def call(self, *args, **kwargs):
            raise ValueError(message)

    return SourceOnly(
        root,
        runtime / "provider",
        export_allowed,
        backend="source-only",
        trust_zone="internal",
    )


def _provider(root: Path, runtime: Path, manifest: dict[str, Any]):
    backend = os.environ.get("SEMANTIC_LLM_BACKEND", "anthropic").strip().lower()
    if backend not in {"anthropic", "genos"}:
        raise ValueError("SEMANTIC_LLM_BACKEND must be anthropic or genos")
    export_allowed = bool(manifest.get("export_allowed"))
    from semantic_runtime.provider import Haiku

    if backend == "genos":
        required = ("GENOS_BASE_URL", "GENOS_QWEN_SERVING_ID", "GENOS_QWEN_KEY")
        missing = [name for name in required if not os.environ.get(name, "").strip()]
        if missing:
            return _source_only_provider(
                root,
                runtime,
                export_allowed,
                "RAG answer LLM is not configured; set " + ", ".join(missing),
            )
        return Haiku(
            root,
            runtime / "provider",
            export_allowed,
            backend="genos",
            trust_zone="internal",
        )

    return Haiku(
        root,
        runtime / "provider",
        export_allowed,
        backend="anthropic",
        endpoint=os.environ.get("SEMANTIC_LLM_ENDPOINT") or None,
        trust_zone=os.environ.get("SEMANTIC_LLM_TRUST_ZONE", "external"),
    )


def application():
    """Create and cache the ASGI app after verifying code and generation binding."""

    global _APP, _BINDING
    if _APP is not None:
        obs.event(log, "runtime.cache.hit", binding=_BINDING)
        return _APP
    with obs.step(log, "binding.resolve"):
        code_root, generation, binding = _resolve_binding()
    obs.event(
        log,
        "binding.resolved",
        mode=binding.get("mode"),
        generation_id=binding.get("generation_id") or binding.get("generation"),
        generation_path=str(generation),
    )
    backend = code_root / "02_BACKEND"
    if not (backend / "semantic_runtime/app.py").is_file():
        raise RuntimeError("semantic_runtime is missing from the deployed code bundle")
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    with obs.step(log, "generation.validate"):
        manifest = _json(generation / "manifest.json")
    runtime_value = os.environ.get("GENOS_RUNTIME_DIR", "").strip()
    runtime = Path(runtime_value).resolve() if runtime_value else (_ROOT / "90_RUNTIME/semantic")
    runtime.mkdir(parents=True, exist_ok=True)
    if binding.get("mode") == "local-release":
        # Import the verified release as its own package. The bootstrap logger
        # already imports workspace semantic_runtime; sys.path alone cannot
        # change that package's search path to the selected release.
        package_path = backend / "semantic_runtime"
        package_name = "_lawrag_release_" + hashlib.sha256(str(code_root).encode()).hexdigest()[:16]
        if package_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                package_name, package_path / "__init__.py",
                submodule_search_locations=[str(package_path)],
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[package_name] = module
            spec.loader.exec_module(module)
        create_app = importlib.import_module(package_name + ".app").create_app
    else:
        from semantic_runtime.app import create_app

    # A published generation may carry an optional local vector artifact. The
    # Python 3.11 base serving install intentionally omits NumPy; lexical search
    # and health must still boot. Installing requirements-vector enables Dense.
    vector = None if ((manifest.get("vectors") or {}).get("format") == "genos-sqlite-v1"
                      or importlib.util.find_spec("numpy") is not None) else False
    with obs.step(log, "runtime.create"):
        options = {}
        implementation = os.environ.get("GENOS_RAG_IMPLEMENTATION", "").strip()
        if implementation:
            if binding.get("mode") == "local-release":
                raise ValueError("GENOS_RAG_IMPLEMENTATION requires an explicit GENOS generation; local releases retain their pinned configuration")
            if implementation not in {"navigation-loop-v1", "document-navigation-v1"}:
                raise ValueError("unsupported GENOS_RAG_IMPLEMENTATION")
            options["implementation"] = implementation
        _APP = create_app(
            runtime,
            generation,
            contracts_root=code_root,
            release=binding,
            provider=_provider(_ROOT, runtime, manifest),
            vector=vector,
            **options,
        )
    _BINDING = binding
    obs.event(
        log,
        "runtime.ready",
        binding=binding,
        data_status=manifest.get("data_status"),
        counts=manifest.get("counts", {}),
        vector_status="ENABLED" if vector is not False else "DEPENDENCY_MISSING",
        llm_backend=os.environ.get("SEMANTIC_LLM_BACKEND", "anthropic").strip().lower(),
        runtime_dir=str(runtime),
    )
    return _APP


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Accept both the repository op envelope and GENOS-style API_TYPE calls."""

    if data.get("op") or not data.get("API_TYPE"):
        return data
    api_type = str(data.get("API_TYPE", "")).strip().upper()
    if api_type == "PING":
        return {"op": "ping"}
    if api_type == "CONNECTIONS":
        return {"op": "connections", "execute": data.get("execute", False)}
    if api_type == "DIAGNOSTICS":
        return {"op": "diagnostics"}
    if api_type == "HEALTH":
        return {"op": "call", "method": "GET", "path": "/health"}
    if api_type == "RAG_SEARCH":
        return {
            "op": "call",
            "method": "GET",
            "path": "/v1/rag/search",
            "params": {key: data[key] for key in ("q", "doc_id", "limit") if key in data},
        }
    if api_type in {"RAG_ASK", "ELS_QUERY"}:
        body = data.get("json")
        if body is None:
            body = {key: value for key, value in data.items() if key != "API_TYPE"}
        return {"op": "call", "method": "POST", "path": "/v1/rag/ask", "json": body}
    if api_type == "PIPELINE_BOOTSTRAP_EXTERNAL":
        return {"op": "pipeline-bootstrap-external"}
    if api_type == "PIPELINE_EXTERNAL":
        return {"op": "pipeline-external", "stages": data.get("stages")}
    if api_type == "PIPELINE_INTERNAL":
        return {
            "op": "pipeline-internal",
            "files": data.get("files", data.get("genosUploaded")),
            "stages": data.get("stages"),
        }
    if api_type == "PIPELINE_PUBLISH":
        return {"op": "pipeline-publish"}
    if api_type == "PIPELINE_STATUS":
        return {"op": "pipeline-status"}
    return {"op": "invalid-api-type", "API_TYPE": api_type}


def _ping() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "8-AGENT",
        "runtime": "genos-semantic-v2",
        "python": platform.python_version(),
        "generation_configured": bool(os.environ.get("GENOS_GENERATION", "").strip()),
        "app_loaded": _APP is not None,
        "binding": _BINDING,
    }


async def _connections(execute: bool) -> dict[str, Any]:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from semantic_runtime.genos import smoke

    with obs.step(log, "connections.check", execute=execute):
        result = await asyncio.to_thread(smoke, execute=execute)
    obs.event(log, "connections.result", ok=result.get("ok"), checks=result.get("checks", []))
    return {"status": 200 if result["ok"] else 502, "body": result}


async def _diagnostics() -> dict[str, Any]:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from semantic_runtime.genos import diagnostics

    with obs.step(log, "diagnostics.check"):
        result = await asyncio.to_thread(diagnostics)
    obs.event(log, "diagnostics.result", ok=result.get("ok"), checks=result.get("checks", []))
    return {"status": 200 if result["ok"] else 502, "body": result}


def _upload_paths(value: Any) -> list[str]:
    """Read GenOS upload descriptors without treating arbitrary metadata as paths."""

    out: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, str):
            if item.strip():
                out.append(item.strip())
            return
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if isinstance(item, dict):
            for key in ("file_path", "local_path", "uploaded_path", "path"):
                if key in item:
                    visit(item[key])

    visit(value)
    return list(dict.fromkeys(out))


async def _pipeline(request: dict[str, Any]) -> dict[str, Any]:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from lawrag.pipeline import genos_unified

    try:
        if request["op"] == "pipeline-bootstrap-external":
            result = await asyncio.to_thread(genos_unified.bootstrap_external)
        elif request["op"] == "pipeline-external":
            stages = request.get("stages")
            if stages is not None and not isinstance(stages, str):
                return {"status": 400, "body": {"error": "stages must be a string"}}
            result = await asyncio.to_thread(
                genos_unified.process_external,
                stages=stages or genos_unified.COMMON_STAGES,
            )
        elif request["op"] == "pipeline-status":
            result = await asyncio.to_thread(genos_unified.status)
        elif request["op"] == "pipeline-publish":
            result = await asyncio.to_thread(genos_unified.publish_source_only)
            global _APP, _BINDING
            _APP = None
            _BINDING = None
        else:
            files = _upload_paths(request.get("files"))
            upload_root = os.environ.get("GENOS_UPLOAD_ROOT", "").strip()
            if not upload_root:
                return {
                    "status": 503,
                    "body": {"error": "GENOS_UPLOAD_ROOT is not configured"},
                }
            stages = request.get("stages")
            if stages is not None and not isinstance(stages, str):
                return {"status": 400, "body": {"error": "stages must be a string"}}
            result = await asyncio.to_thread(
                genos_unified.process_internal,
                files,
                allowed_root=upload_root,
                stages=stages or genos_unified.COMMON_STAGES,
            )
        return {"status": 200 if result.get("ok") else 500, "body": result}
    except (ValueError, FileNotFoundError) as exc:
        return {
            "status": 400,
            "body": {"error": str(exc), "error_type": type(exc).__name__},
        }
    except Exception as exc:  # noqa: BLE001
        obs.event(
            log,
            "pipeline.failed",
            level=logging.ERROR,
            exc_info=True,
            error_type=type(exc).__name__,
        )
        return {
            "status": 500,
            "body": {"error": "pipeline request failed", "error_type": type(exc).__name__},
        }


async def _call(data: dict[str, Any]) -> dict[str, Any]:
    method = str(data.get("method", "GET")).upper()
    path = str(data.get("path", ""))
    allowed = (method == "GET" and path in _GET_ALLOWLIST) or (
        method == "POST" and path in _POST_ALLOWLIST
    )
    if not allowed:
        obs.event(log, "route.rejected", level=logging.WARNING, method=method, path=path)
        return {"status": 403, "body": {"error": "route not allowed"}}
    obs.event(log, "runtime.request.started", method=method, path=path)
    try:
        with obs.step(log, "runtime.bootstrap"):
            app = application()
    except Exception as exc:
        obs.event(
            log,
            "runtime.bootstrap.failed",
            level=logging.ERROR,
            exc_info=True,
            error_type=type(exc).__name__,
        )
        return {
            "status": 503,
            "body": {
                "error": "generation/runtime unavailable",
                "error_type": type(exc).__name__,
                "hint": "configure GENOS_GENERATION and verify the deployed code/data package",
            },
        }
    import httpx

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://semantic.local"
        ) as client:
            response = await client.request(
                method,
                path,
                params=data.get("params"),
                json=data.get("json"),
            )
        try:
            body = response.json()
        except ValueError:
            body = {"error": "runtime returned non-JSON response"}
        answer = body.get("answer") if isinstance(body, dict) else None
        answer_text = answer.get("text") if isinstance(answer, dict) else ""
        assembly = body.get("assembly") if isinstance(body, dict) else None
        contexts = assembly.get("context") if isinstance(assembly, dict) else []
        obs.event(
            log,
            "runtime.request.finished",
            method=method,
            path=path,
            http_status=response.status_code,
            run_id=body.get("run_id") if isinstance(body, dict) else None,
            answer_chars=len(answer_text or ""),
            context_count=len(contexts) if isinstance(contexts, list) else 0,
            detail=body.get("detail") if response.status_code >= 400 and isinstance(body, dict) else None,
        )
        return {"status": response.status_code, "body": body}
    except Exception as exc:
        obs.event(
            log,
            "runtime.request.failed",
            level=logging.ERROR,
            exc_info=True,
            method=method,
            path=path,
            error_type=type(exc).__name__,
        )
        return {
            "status": 500,
            "body": {"error": "runtime request failed", "error_type": type(exc).__name__},
        }


async def _dispatch(config: dict, data: dict) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"status": 400, "body": {"error": "data must be an object"}}
    request = _normalize(data)
    op = request.get("op")
    if op == "ping":
        return _ping()
    if op == "connections":
        execute = request.get("execute", False)
        if type(execute) is not bool:
            return {"status": 400, "body": {"error": "execute must be boolean"}}
        return await _connections(execute)
    if op == "diagnostics":
        return await _diagnostics()
    if op == "call":
        return await _call(request)
    if op in {"pipeline-bootstrap-external", "pipeline-external", "pipeline-internal", "pipeline-publish", "pipeline-status"}:
        return await _pipeline(request)
    if op == "invalid-api-type":
        return {
            "status": 400,
            "body": {
                "error": f"unknown API_TYPE: {request.get('API_TYPE')!r}",
                "supported": sorted(_API_TYPES),
            },
        }
    return {"status": 403, "body": {"error": "operation not allowed"}}


async def service(config: dict, data: dict) -> dict[str, Any]:
    """GENOS JSON gateway contract with one correlated event stream per request."""

    started = time.perf_counter()
    payload = data if isinstance(data, dict) else {}
    request_id = obs.new_request_id(payload.get("request_id"))
    api_type = str(payload.get("API_TYPE") or payload.get("op") or "").strip().upper()
    with obs.context(request_id=request_id, api_type=api_type):
        obs.event(
            log,
            "request.started",
            input_keys=sorted(str(key) for key in payload),
            question_chars=len(str(payload.get("question") or payload.get("q") or "")),
        )
        try:
            result = await _dispatch(config, data)
        except Exception as exc:  # noqa: BLE001
            obs.event(
                log,
                "request.crashed",
                level=logging.ERROR,
                exc_info=True,
                error_type=type(exc).__name__,
            )
            result = {
                "status": 500,
                "body": {
                    "error": "unhandled code-serving error",
                    "error_type": type(exc).__name__,
                    "request_id": request_id,
                },
            }
        status = result.get("status", 200) if isinstance(result, dict) else 500
        body = result.get("body") if isinstance(result, dict) else None
        obs.event(
            log,
            "request.finished",
            duration_ms=int((time.perf_counter() - started) * 1000),
            http_status=status,
            ok=status < 400,
            error_type=body.get("error_type") if isinstance(body, dict) else None,
        )
        return result


__all__ = ["application", "service"]
