"""GENOS code-serving entry point for the active semantic runtime.

GENOS exposes only ``async def service(config, data)`` through its JSON
gateway. Startup stays lazy so ``ping`` and ``connections`` work before a
published data generation is mounted. Application calls use an explicit
``GENOS_GENERATION`` when set, otherwise the current generation published
below ``GENOS_DATA_ROOT``.
"""
from __future__ import annotations

import asyncio
import ast
from contextlib import nullcontext
import hashlib
import importlib.util
import json
import logging
import os
import platform
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from contextvars import copy_context


_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "02_BACKEND"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from semantic_runtime import observability as obs
from semantic_runtime import request_report

_APP = None
_BINDING: dict[str, Any] | None = None
_APP_BOOTSTRAP_LOCK = threading.Lock()
_WARMUP_LOCK = threading.Lock()
_WARMUP_STATE: dict[str, Any] = {"state": "NOT_STARTED"}
_PROCESS_INSTANCE_ID = uuid.uuid4().hex
_BARE_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

_GET_ALLOWLIST = frozenset(
    {
        "/health",
        "/v1/pipeline/status",
        "/v1/rag/search",
        "/v1/rag/section",
        "/v1/rag/scopes",
        "/v1/rag/teams",
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
        "WARMUP",
        "WARMUP_STATUS",
        "CONNECTIONS",
        "DIAGNOSTICS",
        "HEALTH",
        "RAG_SEARCH",
        "RAG_ASK",
        "LEGAL_AGENT",
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


def _require_pecab_generation(generation: Path, code_root: Path | None = None) -> None:
    """Reject an incompatible bound index before importing any frozen runtime."""
    if code_root is not None:
        for name in ('fulltext.py', 'term_morph.py'):
            module = code_root / '02_BACKEND/semantic_runtime' / name
            if not module.is_file():
                continue
            for node in ast.walk(ast.parse(module.read_bytes(), filename=str(module))):
                modules = ([n.name for n in node.names] if isinstance(node, ast.Import) else
                           [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
                if any(n.startswith('kiwipiepy') for n in modules):
                    raise RuntimeError('PeCab runtime required; selected frozen code imports an unsupported tokenizer')
    binding = _json(generation / 'manifest.json').get('fulltext')
    if not binding:
        return  # Profiles without fulltext retain their own readiness checks.
    index = (generation / binding['path']).resolve()
    index.relative_to(generation.resolve())
    manifest = _json(index / 'manifest.json')
    tokenizer = manifest.get('tokenizer', {})
    if (manifest.get('schema_version') not in {'semantic-fulltext-v2', 'semantic-unit-fulltext-v1'} or
            tokenizer.get('name') != 'pecab' or tokenizer.get('version') != '1.0.8'):
        raise RuntimeError('PeCab 1.0.8 fulltext v2 or unit fulltext generation required; rebuild a new generation with --rebuild')


def _genos_v5_wait_profile(value):
    """Extend GENOS waits without rewriting a pinned profile or local release."""
    raw = os.environ.get('GENOS_RAG_WALL_SECONDS', '').strip()
    try:
        seconds = int(raw) if raw else max(value['wall_seconds'], 1800)
    except ValueError as exc:
        raise ValueError('GENOS_RAG_WALL_SECONDS must be a positive integer') from exc
    if seconds < 1:
        raise ValueError('GENOS_RAG_WALL_SECONDS must be a positive integer')
    return {**value, 'wall_seconds': seconds}


def _genos_v5_admission_profile(value):
    """Disable the GENOS request-count gate without deployment environment settings."""
    return {**value, 'max_concurrent_requests_per_process': 0}


def _genos_v5_environment_binding(request_profile=None):
    """Build a v5 model binding in memory for a GENOS data generation."""

    configured = any(os.environ.get(key, "").strip() for key in (
        "GENOS_LLM_URL", "GENOS_LLM_SERVING_ID", "GENOS_LLM_KEY", "GENOS_LLM_MODEL",
    ))
    if not configured:
        return None
    from semantic_runtime.genos import advertised_model, from_env
    from semantic_runtime.legal_agent.transport import GenosTransport
    from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE, profile

    raw_output_tokens = os.environ.get("GENOS_RAG_MAX_OUTPUT_TOKENS", "").strip()
    if raw_output_tokens:
        try:
            output_tokens = int(raw_output_tokens)
        except ValueError as exc:
            raise ValueError("GENOS_RAG_MAX_OUTPUT_TOKENS must be a positive integer") from exc
        if output_tokens < 1:
            raise ValueError("GENOS_RAG_MAX_OUTPUT_TOKENS must be a positive integer")
    else:
        output_tokens = DEFAULT_PROFILE["max_output_tokens"]

    request_profile = _genos_v5_admission_profile({**(request_profile or DEFAULT_PROFILE),
        'bounded_source_selection_enabled': True})

    target, configured_model = from_env("llm")
    if not os.environ.get("GENOS_LLM_KEY", "").strip():
        raise ValueError("GENOS_LLM_KEY is required for GENOS v5 model execution")
    model = configured_model or advertised_model(target)
    model_binding = {
        "provider": "genos", "model": model,
        "adapter_version": "genos-single-send-v1",
        "endpoint_identity": hashlib.sha256(target.root.encode()).hexdigest(),
        "trust_zone": "internal",
    }
    configured_profile = profile(_genos_v5_wait_profile({**request_profile, "model_binding": model_binding,
                                  "max_output_tokens": output_tokens}), require_model=True)
    return configured_profile, GenosTransport(target, model_binding)


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
    if manifest.get("schema_version") not in {"term-source-generation-v1", "term-source-generation-v2"}:
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
        "release_manifest_sha256": pointer["release_manifest_sha256"],
        "code_sha256": hashlib.sha256(json.dumps(release["files"],sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "profile_sha256": _sha(code_root / "00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json") if (code_root / "00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json").is_file() else None,
        "data_manifest_sha256": release["data_manifest_sha256"],
        "source_generation_id": _json(generation / "manifest.json")["generation_id"],
        "fulltext_manifest_sha256": (_json(generation / "manifest.json").get("fulltext") or {}).get("manifest_sha256"),
        "search_policy_sha256": hashlib.sha256(json.dumps({"directory_order":"best-own-block-match-v1" if (code_root / "02_BACKEND/semantic_runtime/legal_agent/investigation_chain.py").is_file() else "legacy", "candidate_navigation":_json(code_root / "00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json").get("candidate_navigation",{})} if (code_root / "00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json").is_file() else {},sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps({p:h for p,h in release["files"].items() if p.startswith("00_SYSTEM/SCHEMAS/")},sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "process_instance_id": _PROCESS_INSTANCE_ID,
        "process_id": os.getpid(),
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
        required = (("GENOS_LLM_KEY",) if os.environ.get("GENOS_LLM_URL", "").strip()
                    else ("GENOS_BASE_URL", "GENOS_LLM_SERVING_ID", "GENOS_LLM_KEY"))
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
        _require_pecab_generation(generation, code_root)
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
            if (binding.get("mode") == "local-release" and
                    (code_root / "00_SYSTEM/LEGAL_AGENT/local-gemma-public.json").is_file()):
                raise ValueError("GENOS_RAG_IMPLEMENTATION requires an explicit GENOS generation; local releases retain their pinned configuration")
            if implementation not in {"navigation-loop-v1", "document-navigation-v1", "legal-agent-v1", "legal-agent-tools-v2", "legal-agent-tools-v3", "legal-agent-tools-v4", "legal-agent-tools-v5","legal-agent-unified-v6"}:
                raise ValueError("unsupported GENOS_RAG_IMPLEMENTATION")
            options["implementation"] = implementation
        selected_implementation = implementation or _json(code_root / "00_SYSTEM/PIPELINE.json")["profiles"]["legal-rag"]["nodes"][0]["parameters"]["term_agent"].get("implementation")
        if selected_implementation in ("legal-agent-tools-v5","legal-agent-unified-v6"):
            # Immutable code and mutable workspace routing are separate bindings.
            options.update(workspace_root=_ROOT, runtime_root=runtime)
            if binding.get("mode") == "local-release":
                v5_profile = importlib.import_module(package_name + ".legal_agent.workflow_tiers_policy").profile
                local_model_module = importlib.import_module(package_name + ".legal_agent.local_gemma")
                transport_type = getattr(local_model_module, "LocalQwen38Transport",
                                         local_model_module.LocalGemmaTransport)
                local_transport = transport_type(code_root, _ROOT)
                pinned_profile = _json(code_root / ("00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json" if selected_implementation=='legal-agent-unified-v6' else "00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json"))
                options["legal_agent_profile"] = v5_profile({
                    **pinned_profile,
                    "model_binding": local_transport.binding,
                    "max_output_tokens": local_transport.policy["max_output_tokens"],
                    "max_transport_retries": 0,
                }, require_model=True)
                options["legal_agent_transport"] = local_transport
        if selected_implementation in ("legal-agent-v1", "legal-agent-tools-v2", "legal-agent-tools-v3", "legal-agent-tools-v4", "legal-agent-tools-v5","legal-agent-unified-v6"):
            profile_path = os.environ.get("LEGAL_AGENT_PROFILE", "")
            profile_hash = os.environ.get("LEGAL_AGENT_PROFILE_SHA256", "")
            if profile_path or profile_hash or (implementation and selected_implementation not in {"legal-agent-tools-v5", "legal-agent-unified-v6"}):
                if binding.get("mode") == "local-release":
                    raise ValueError("local releases retain their pinned model profile")
                from semantic_runtime.legal_agent.domain import load_bound, profile
                if selected_implementation in ("legal-agent-tools-v5","legal-agent-unified-v6"):
                    from semantic_runtime.legal_agent.workflow_tiers_policy import profile
                elif selected_implementation == "legal-agent-tools-v4":
                    from semantic_runtime.legal_agent.tiers_policy import profile
                elif selected_implementation == "legal-agent-tools-v3":
                    from semantic_runtime.legal_agent.relations_policy import profile
                elif selected_implementation == "legal-agent-tools-v2":
                    from semantic_runtime.legal_agent.tools_policy import profile
                if not profile_path or not profile_hash:
                    raise ValueError(selected_implementation+" requires LEGAL_AGENT_PROFILE and LEGAL_AGENT_PROFILE_SHA256")
                options["legal_agent_profile"] = profile(load_bound(code_root, {
                    "path": profile_path, "sha256": profile_hash}), require_model=True)
            elif selected_implementation in {"legal-agent-tools-v5", "legal-agent-unified-v6"} and binding.get("mode") in ("genos-generation", "genos-data-current"):
                environment_binding = (_genos_v5_environment_binding(
                    _json(code_root / "00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json"))
                    if selected_implementation == "legal-agent-unified-v6"
                    else _genos_v5_environment_binding())
                if environment_binding is not None:
                    options["legal_agent_profile"], options["legal_agent_transport"] = environment_binding
        if selected_implementation in ('legal-agent-tools-v5','legal-agent-unified-v6') and binding.get('mode') in ('genos-generation', 'genos-data-current'):
            from semantic_runtime.legal_agent.workflow_tiers_policy import profile as v5_profile
            configured_profile = options.get('legal_agent_profile') or _json(code_root / ('00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json' if selected_implementation=='legal-agent-unified-v6' else '00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json'))
            options['legal_agent_profile'] = v5_profile(_genos_v5_wait_profile(
                _genos_v5_admission_profile(configured_profile)))
            obs.event(log, 'runtime.request_budget', wall_seconds=options['legal_agent_profile']['wall_seconds'],
                      implementation=selected_implementation, binding_mode=binding['mode'],
                      timeout_revision='timeout-sync-20260928-r1')
            obs.event(log, 'runtime.request_admission',
                      max_concurrent_requests_per_process=options['legal_agent_profile']['max_concurrent_requests_per_process'],
                      unlimited=options['legal_agent_profile']['max_concurrent_requests_per_process'] == 0)
        _APP = create_app(
            runtime,
            generation,
            contracts_root=code_root,
            release=binding,
            provider=_provider(_ROOT, runtime, manifest),
            vector=vector,
            **options,
        )
        if not (selected_implementation == 'legal-agent-tools-v5' and
                binding.get('mode') in ('genos-generation', 'genos-data-current')):
            agent = getattr(getattr(getattr(_APP, 'state', None), 'pipeline', None), 'term_agent', None)
            effective_profile = getattr(agent, 'profile', None) or getattr(agent, 'limits', None) or getattr(agent, 'config', {}).get('limits', {})
            obs.event(log, 'runtime.request_budget', wall_seconds=effective_profile.get('wall_seconds'),
                      implementation=selected_implementation, binding_mode=binding['mode'],
                      timeout_revision='timeout-sync-20260928-r1')
        if selected_implementation in ('legal-agent-tools-v5','legal-agent-unified-v6') and binding.get('mode') in ('genos-generation', 'genos-data-current'):
            # ASGITransport does not drive FastAPI lifespan. Recover completed
            # FINAL journals in the background so this cannot delay a new ask.
            loaded_app = _APP
            def recover_publications():
                try:
                    from semantic_runtime.legal_agent.publication import recover
                    from semantic_runtime.legal_agent.source_bundle import validate_current
                    pipeline = loaded_app.state.pipeline
                    with obs.step(log, 'runtime.publication_recover'):
                        recover(runtime/'legal-agent/runs', runtime/'runs',
                                publication_guard=lambda repo, value: validate_current(repo, value, pipeline.store),
                                contracts=pipeline.contracts, release=binding)
                        if selected_implementation=='legal-agent-unified-v6' and (runtime/'case-memory'/'cases-v3.sqlite').is_file():
                            from semantic_runtime.legal_agent.case_repository import CaseRepository
                            cases=CaseRepository(runtime/'case-memory'/'cases-v3.sqlite',None,None)
                            try:cases.recover_requests()
                            finally:cases.close()
                except Exception:
                    obs.event(log, 'runtime.publication_recover.failed', level=logging.ERROR,
                              exc_info=True)
            threading.Thread(target=recover_publications, daemon=True,
                             name='genos-publication-recovery').start()
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


def _bootstrap_application():
    # Concurrent cold requests must share one verified app and data binding.
    with _APP_BOOTSTRAP_LOCK:
        return application()


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Accept both the repository op envelope and GENOS-style API_TYPE calls."""

    if data.get("op") or not data.get("API_TYPE"):
        return data
    api_type = str(data.get("API_TYPE", "")).strip().upper()
    if api_type == "PING":
        return {"op": "ping"}
    if api_type in {"WARMUP", "WARMUP_STATUS"}:
        return {"op": api_type.lower()}
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
            "params": {key: data[key] for key in ("q", "doc_id", "limit", "scope", "team_id") if key in data},
        }
    if api_type in {"RAG_ASK", "LEGAL_AGENT", "ELS_QUERY"}:
        body = data.get("json")
        if body is None:
            body = {key: value for key, value in data.items() if key != "API_TYPE"}
        if api_type == "LEGAL_AGENT" and isinstance(body, dict):
            control = str(body.get("question") or "").strip().upper()
            if control in {"WARMUP", "WARMUP_STATUS"}:
                return {"op": control.lower()}
        if api_type in {"LEGAL_AGENT", "ELS_QUERY"} and isinstance(body, dict):
            removed = {"channel"} if body.get("memory") is True or 'memory_authorization' in body else {"channel", "session_id", "request_id", "user_id"}
            body = {key: value for key, value in body.items() if key not in removed}
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


def _warm_resources():
    """Use the same request-local resource path, without asking a model a question."""
    if not (os.environ.get("GENOS_GENERATION", "").strip() or
            os.environ.get("GENOS_DATA_ROOT", "").strip()):
        raise ValueError("warmup requires an explicit GENOS data selection")
    app = _bootstrap_application()
    if (_BINDING or {}).get("mode") == "local-release":
        raise ValueError("warmup cannot fall back to a local frozen release")
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.storage import Store
    from semantic_runtime.term_morph import tokenize
    from semantic_runtime.team_scope import prepared_catalogue
    from semantic_runtime.multi_entry_navigation import validate_structure

    pipeline = app.state.pipeline
    obs.event(log,'warmup.environment',**obs.environment_facts(pipeline.store.path/'store.sqlite'))
    guard = pipeline.term_agent.admit() if hasattr(pipeline.term_agent,'admit') else nullcontext()
    with guard:
        store = Store(pipeline.store.path, verify=False)
        try:
            if store.manifest != pipeline.store.manifest:
                raise ValueError("source generation binding changed")
            proxy = SimpleNamespace(store=store, contracts=pipeline.contracts)
            agent = ServingDocumentAgent(proxy, pipeline.term_agent.config)
            scope = sorted(prepared_catalogue(store)['ids'])
            with agent.resources(scope) as (_, _, _, matcher):
                validate_structure(matcher,scope)
                tokenize("용어 색인 준비")
            return {"generation_path": str(store.path), "document_count": len(scope)}
        finally:
            store.close()


def _run_warmup():
    started = time.perf_counter()
    try:
        with obs.step(log, "warmup.resources"):
            detail = _warm_resources()
        state = {"state": "READY", **detail}
    except Exception as exc:
        obs.event(log, "warmup.failed", level=logging.ERROR, exc_info=True,
                  error_type=type(exc).__name__)
        state = {"state": "FAILED", "error_type": type(exc).__name__}
    state["duration_ms"] = int((time.perf_counter() - started) * 1000)
    with _WARMUP_LOCK:
        _WARMUP_STATE.update(state)


def _warmup(start=False):
    with _WARMUP_LOCK:
        if start and _WARMUP_STATE["state"] in {"NOT_STARTED", "FAILED"}:
            _WARMUP_STATE.clear()
            _WARMUP_STATE.update(state="RUNNING")
            context = copy_context()
            thread = threading.Thread(target=lambda: context.run(_run_warmup),
                                      daemon=True, name="genos-resource-warmup")
            try:
                thread.start()
            except RuntimeError:
                _WARMUP_STATE.update(state="FAILED", error_type="RuntimeError")
        state = dict(_WARMUP_STATE)
    return {"status": 202 if state["state"] == "RUNNING" else 200,
            "body": {**state, "process_id": os.getpid(), "worker_id": _PROCESS_INSTANCE_ID,
                     "process_local": True}}


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
    if method == "POST" and path == "/v1/rag/ask":
        body = data.get("json")
        question = body.get("question") if isinstance(body, dict) else None
        if isinstance(question, str) and _BARE_UUID.fullmatch(question.strip()):
            obs.event(log, "question.rejected", level=logging.WARNING, reason="bare_uuid")
            return {"status": 422, "body": {"error": "실제 질문 문장을 입력해 주세요.",
                                            "error_type": "InvalidQuestion"}}
    obs.event(log, "runtime.request.started", method=method, path=path)
    try:
        with obs.step(log, "runtime.bootstrap"):
            # App construction validates the pinned model with a synchronous
            # asyncio.Runner. Keep it off the gateway's running event loop.
            app = await asyncio.to_thread(_bootstrap_application)
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
                "code": "RUNTIME_BOOTSTRAP_ERROR",
                "error_type": type(exc).__name__,
                "hint": "inspect runtime.bootstrap.failed in code-serving logs to identify the failed initialization step",
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
            "body": {"error": "runtime request failed", "code": "RUNTIME_REQUEST_ERROR",
                     "error_type": type(exc).__name__,
                     "detail": obs._redact_secrets(str(exc))[:1000]},
        }


async def _dispatch(config: dict, data: dict) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"status": 400, "body": {"error": "data must be an object"}}
    request = _normalize(data)
    op = request.get("op")
    if op == "ping":
        return _ping()
    if op in {"warmup", "warmup_status"}:
        return _warmup(start=op == "warmup")
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


def _ad_control():
    """Load administration from the selected release, independent of legal bootstrap."""
    code_root = _ROOT
    pointer = _ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    if not (os.environ.get('GENOS_GENERATION') or os.environ.get('GENOS_DATA_ROOT')) and pointer.is_file():
        active = _json(pointer)
        manifest_path = _ROOT / active['manifest_path']
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != active['release_manifest_sha256']:
            raise RuntimeError('AD_RELEASE: selected manifest hash mismatch')
        manifest = _json(manifest_path)
        code_root = _ROOT / manifest['code_root']
    config = _json(code_root / '00_SYSTEM/PIPELINE.json')
    if not config.get('ad_management', {}).get('enabled'):
        # No management writes using an old release after rollback.
        from types import SimpleNamespace
        def disabled(data, *_):
            b = data.get('json') if isinstance(data.get('json'),dict) else data
            if str(b.get('question', b.get('q',''))).strip() == '[AD모드 시작]':
                return {'status':200,'body':{'response_schema':'ad-mode-v1','ad_mode':False,'answer_status':'error','text':'AD_RELEASE: selected release does not enable AD administration.'}}
            return None
        return SimpleNamespace(intercept=disabled,start_worker=lambda *_:None)
    if code_root == _ROOT:
        return importlib.import_module('semantic_runtime.ad_gateway')
    package = '_ad_release_' + hashlib.sha256(str(code_root).encode()).hexdigest()[:16]
    if package not in sys.modules:
        path = code_root / '02_BACKEND/semantic_runtime'
        spec = importlib.util.spec_from_file_location(package,path/'__init__.py',submodule_search_locations=[str(path)])
        module = importlib.util.module_from_spec(spec);sys.modules[package]=module;spec.loader.exec_module(module)
    return importlib.import_module(package+'.ad_gateway')


async def service(config: dict, data: dict) -> dict[str, Any]:
    """GENOS JSON gateway contract with one correlated event stream per request."""
    # GENOS_NFS_PROBE_HOOK_V1
    if isinstance(data, dict) and str(data.get("API_TYPE", "")).strip().upper() == "NFS_DATA_PROBE":
        import importlib.util as _nfs_util
        _nfs_path = _ROOT / "02_BACKEND/semantic_runtime/nfs_data_probe.py"
        _nfs_spec = _nfs_util.spec_from_file_location("_genos_nfs_data_probe", _nfs_path)
        _nfs_module = _nfs_util.module_from_spec(_nfs_spec)
        _nfs_spec.loader.exec_module(_nfs_module)
        return await _nfs_module.gateway(data, code_root=_ROOT)

    gateway = _ad_control()
    intercept, start_worker = gateway.intercept, gateway.start_worker
    runtime_value = os.environ.get('GENOS_RUNTIME_DIR','').strip()
    ad_runtime = Path(runtime_value).resolve() if runtime_value else (_ROOT/'90_RUNTIME/semantic')
    start_worker(ad_runtime, application)
    ad_result = await asyncio.to_thread(intercept,data if isinstance(data,dict) else {},ad_runtime,application)
    if ad_result is not None:return ad_result
    if str(data.get('API_TYPE','')).upper()=='AD_PROBE':return {'status':200,'body':{'ad_handled':False}}
    # Transport-only identifiers never enter legal schemas, context or logs.
    data = dict(data or {})
    if isinstance(data.get('json'),dict):data['json']={k:v for k,v in data['json'].items() if k not in ('ad_session_id','ad_channel')}
    else:data={k:v for k,v in data.items() if k not in ('ad_session_id','ad_channel')}
    started = time.perf_counter()
    payload = data if isinstance(data, dict) else {}
    question_body = payload.get("json") if isinstance(payload.get("json"), dict) else payload
    request_id = obs.new_request_id(payload.get("request_id"))
    api_type = str(payload.get("API_TYPE") or payload.get("op") or "").strip().upper()
    shared_root = os.environ.get("GENOS_SHARED_LOG_DIR", "").strip()
    if _normalize(payload).get("op") in {"warmup", "warmup_status"}:
        # Resource preparation/status must respond without depending on NFS logs.
        shared_root = ""
    runtime_value = os.environ.get("GENOS_RUNTIME_DIR", "").strip()
    runtime = Path(runtime_value).resolve() if runtime_value else (_ROOT / "90_RUNTIME/semantic")
    capture = request_report.capture_events(request_id) if shared_root else nullcontext([])
    with capture as events, obs.context(request_id=request_id, api_type=api_type):
        report_context = request_report.DeferredReport(
            Path(shared_root), runtime, request_id=request_id, api_type=api_type,
            request=payload, events=events) if shared_root else nullcontext(None)
        with report_context as report:
            result = await _reported_dispatch(config, data, payload, question_body, started, report, request_id, api_type)
            obs.event(log, "request.returning",
                      duration_ms=int((time.perf_counter() - started) * 1000))
            return result


async def _reported_dispatch(config, data, payload, question_body, started, report, request_id, api_type):
    obs.event(
        log,
        "request.started",
        worker_id=_PROCESS_INSTANCE_ID,
        process_id=os.getpid(),
        input_keys=sorted(str(key) for key in payload),
        question_chars=len(str(question_body.get("question") or question_body.get("q") or "")),
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
                "code": "CODE_SERVING_ERROR",
                "error_type": type(exc).__name__,
                "detail": obs._redact_secrets(str(exc))[:1000],
                "request_id": request_id,
            },
        }
    if report:
        report.detach()
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
    if report:
        report.complete(result)
    return result

__all__ = ["application", "service"]

# The GENOS revision imports service.py once per worker. Start its expensive
# immutable resource preparation while the worker is idle after deployment.
# Questions still work if the platform imports lazily at first request; in that
# case the first real request may pay the cold cost. Each worker warms itself.
if (os.environ.get("GENOS_GENERATION", "").strip() or os.environ.get("GENOS_DATA_ROOT", "").strip()) and os.environ.get("GENOS_AUTO_WARMUP", "1").strip().lower() not in {"0", "false", "off"}:
    _warmup(start=True)

# Recover SQL schedules at code-serving worker import, including after restart.
if os.environ.get("AD_WORKER_ENABLED", "1") != "0":
    _ad_control().start_worker(Path(os.environ.get("GENOS_RUNTIME_DIR") or _ROOT / "90_RUNTIME/semantic"), application)
