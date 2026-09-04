"""GenOS 코드 서빙 진입점 — 게이트웨이의 단일 JSON 계약을 우리 API 전체로 넓힌다.

GenOS 는 임의의 uvicorn 앱을 서빙하지 않는다. 계약은 이 파일의
`async def service(config, data)` 하나이고, 게이트웨이가 그것을
    POST https://<GenOS>/api/gateway/code_serving/<번호>/json
    Authorization: Bearer <인증키>
로 노출한다 (JSON in/out). 화면도, 임의 경로도, /docs 도 그 문으로는 못 나간다.

그래서 이 진입점은 **터널**이다 — 다만 활성 release 는 아래 조회 호출만
열고, upload/apply 및 임의 POST 터널은 legacy 호환 모드에서만 허용한다:

    {"op": "ping"}                                  기동·rev 확인
    {"op": "call", "method": "GET", "path": "/v1/rag/search",
     "params": {"q": "질문", "mode": "auto"}}    GET 파라미터도 JSON 으로
    {"op": "call", "method": "POST",
     "path": "/v1/rag/ask", "json": {...}}          JSON 몸통은 json 으로,
                                                    파일은 body_b64 로
    {"op": "upload", "filename": "내규.pdf",
     "file_b64": "…", "form": {"folder": "내규"}}  작은 문서 업로드
    {"op": "ls", "path": "/mnt/…"}                  진단 — 볼륨 공유 판별
    {"op": "report"}                                정적 현황 HTML 한 장
    {"op": "snapshot"}                              상태 tar.gz → b64 로 반출
    {"op": "snapshot_to", "path": "/mnt/…"}         공유 볼륨에 쓰기 (b64 한계 우회)
    {"op": "apply", "tar_b64": "…"}                 아웃박스 재생 → 건별 리포트
    {"op": "apply_from", "path": "/mnt/…"}          공유 볼륨에서 읽어 재생

호출은 네트워크가 아니라 ASGI 로 앱 자신을 부른다(lawrag/api/ops.py 의 자기 호출) —
포트도 프록시도 없이 게이트웨이 한 문으로 전부 지나간다.

기본 판정은 코드 결정론이라는 원칙은 여기서도 같다: 이 파일은 아무것도
해석하지 않는다. 받은 것을 앱에 넘기고, 앱이 낸 것을 그대로 돌려준다.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Mapping

_ROOT = Path(__file__).resolve().parent

_RELEASE_BINDING: Dict[str, Any] | None = None
_RELEASE_BOOTSTRAP_ERROR: str | None = None
_RELEASE_STORE = None
_RELEASE_RUNTIME_BINDING = None

_RELEASE_GET_ALLOWLIST = frozenset(
    {
        "/health",
        "/v1/rag/search",
        "/v1/rag/links/summary",
        "/v1/rag/section",
        "/v1/rag/scopes",
        "/v1/rag/nodes",
        "/v1/knowledge/summary",
        "/v1/knowledge/search",
        "/v1/knowledge/neighborhood",
    }
)
_RELEASE_POST_ALLOWLIST = frozenset({"/v1/rag/ask"})


def _strict_release_required() -> bool:
    return os.environ.get("LAWRAG_RELEASE_REQUIRED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _bootstrap_release() -> Dict[str, Any]:
    """Pin one verified release before any lawrag router or store is imported.

    Absence of a release store is the only legacy compatibility case.  Once a
    store is configured, an absent/corrupt pointer never falls back to mutable
    legacy data.  The deployment layer supplies the already materialized store
    paths; this bootstrap verifies they are absolute existing paths and pins
    the release identity for the process lifetime.
    """

    global _RELEASE_STORE, _RELEASE_RUNTIME_BINDING

    store_value = os.environ.get("LAWRAG_RELEASE_STORE", "").strip()
    if not store_value:
        if _strict_release_required():
            raise RuntimeError("strict GenOS startup requires LAWRAG_RELEASE_STORE")
        return {"mode": "legacy", "ready": True, "release": None}

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
    store = ReleaseStore(
        store_path,
        target="genos",
        code_package_root=code_root,
        read_only=True,
    )
    pointer, release, runtime_binding = store.load_active_runtime()
    runtime_root = store.runtime_root(release.release_id)
    resolved_paths = runtime_binding.resolved_paths(runtime_root)
    for key, value in resolved_paths.items():
        configured = os.environ.get(key, "").strip()
        if configured and str(Path(configured).resolve()) != value:
            raise RuntimeError(f"{key} conflicts with the active release binding")
        os.environ[key] = value
    os.environ["LAWRAG_CODE_PACKAGE_ROOT"] = str(code_root)
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
        },
        "runtime_paths": resolved_paths,
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
        _RELEASE_STORE.verify_runtime_ready(
            str(release["release_id"]),
            expected_binding_sha256=str(release["runtime_binding_sha256"]),
        )


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


# Legacy defaults are used only when no release store was configured.  GenOS
# loads service.py directly, so this still has to happen before any lawrag
# import in compatibility mode.
if (_RELEASE_BINDING or {}).get("mode") == "legacy":
    os.environ.setdefault("STRUCTURE_STORE", str(_ROOT / "data" / "structure"))
    os.environ.setdefault("STRUCTURE_CUSTOM_DIR", str(_ROOT / "data" / "custom"))
    os.environ.setdefault("GLOSSARY_STORE", str(_ROOT / "data" / "glossary.json"))
    os.environ.setdefault("RAG_LINKS_STORE", str(_ROOT / "data" / "links.json"))

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


async def _do_upload(data: Dict[str, Any]) -> Dict[str, Any]:
    """JSON 게이트웨이에서 작은 문서를 multipart 업로드로 바꾼다."""
    encoded = data.get("file_b64")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("file_b64 가 필요합니다")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("file_b64 가 올바른 base64가 아닙니다") from exc

    filename = Path(str(data.get("filename") or "document.bin")).name
    filename = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
    form = data.get("form") or {}
    if not isinstance(form, dict):
        raise ValueError("form 은 JSON 객체여야 합니다")
    allowed = {"root", "families", "ladder", "order", "use_llm",
               "folder", "engine", "status", "series"}
    unknown = sorted(set(form) - allowed)
    if unknown:
        raise ValueError("허용하지 않는 form 필드: " + ", ".join(unknown))

    boundary = "----8agent-" + secrets.token_hex(12)
    chunks: list[bytes] = []
    for key, value in form.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"), b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"),
        b"Content-Type: application/octet-stream\r\n\r\n",
        raw, b"\r\n", f"--{boundary}--\r\n".encode(),
    ])
    status, response = await _ops()._call_self(
        _app(), "POST", "/v1/structure/documents", "",
        f"multipart/form-data; boundary={boundary}", b"".join(chunks),
    )
    out: Dict[str, Any] = {"status": status, "ok": status < 400}
    try:
        out["json"] = json.loads(response.decode("utf-8"))
    except Exception:
        out["body_b64"] = base64.b64encode(response).decode()
    return out


async def _do_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    ops = _ops()
    _app()                                   # 라우터 임포트 = 경로 정본 적재
    tmp, meta = ops.build_snapshot()
    try:
        if data.get("op") == "snapshot_to":
            dst = Path(data["path"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, dst)
            return {"meta": meta, "path": str(dst),
                    "bytes": dst.stat().st_size}
        blob = tmp.read_bytes()
        # 게이트웨이가 삼킬 수 있는 몸집이 아니면 b64 로 부풀리기 전에 말한다.
        # 그때의 길은 snapshot_to 로 공유 볼륨에 떨구고 IDE 로 내려받는 것이다.
        return {"meta": meta, "bytes": len(blob),
                "tar_b64": base64.b64encode(blob).decode()}
    finally:
        tmp.unlink(missing_ok=True)


async def _do_apply(data: Dict[str, Any]) -> Dict[str, Any]:
    ops = _ops()
    force = bool(data.get("force"))
    stop_on_error = bool(data.get("stop_on_error"))
    if data.get("op") == "apply_from":
        return await ops._apply_archive(_app(), Path(data["path"]),
                                        force, stop_on_error)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
        f.write(base64.b64decode(data["tar_b64"]))
        tmp = Path(f.name)
    try:
        return await ops._apply_archive(_app(), tmp, force, stop_on_error)
    finally:
        tmp.unlink(missing_ok=True)


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
                    "rev": ops._rev(),
                    "record": ops.RECORD, "outbox": len(ops._read_ops(ops._OPS_FILE)),
                    "store": os.environ.get("STRUCTURE_STORE", "")}
        _require_ready()
        if _release_mode():
            if op in {"upload", "apply", "apply_from", "snapshot_to"}:
                raise PermissionError(
                    f"active release service is query-only; blocked op: {op}"
                )
            if op == "report" and data.get("path"):
                raise PermissionError(
                    "active release service cannot write a report path"
                )
            if op == "call":
                _require_query_only_call(data)
        if (
            _release_mode()
            and not _release_export_allowed()
            and op in {"ls", "report", "snapshot", "snapshot_to"}
        ):
            raise PermissionError(
                "active SourceSet export policy blocks this diagnostic operation"
            )
        if op == "ls":
            # 진단용 — 공유 볼륨이 서빙 컨테이너에 물렸는지 이걸로 확인한다.
            p = Path(data.get("path") or ".").resolve()
            if p.is_dir():
                rows = [{"name": c.name, "dir": c.is_dir(),
                         "bytes": c.stat().st_size if c.is_file() else None}
                        for c in sorted(p.iterdir())[:200]]
                return {"path": str(p), "dir": True, "entries": rows}
            if p.exists():
                return {"path": str(p), "dir": False, "bytes": p.stat().st_size}
            return {"path": str(p), "exists": False}
        if op == "call":
            return await _do_call(data)
        if op == "upload":
            return await _do_upload(data)
        if op == "report":
            # 정적 현황 HTML — 파일로 떨궈 브라우저로만 연다:
            #   curl … -d '{"op":"report"}' | jq -r .html > 현황.html
            html = await _ops().build_report(_app())
            if data.get("path"):                 # 공유 볼륨에 바로 쓰기
                dst = Path(data["path"])
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(html, encoding="utf-8")
                return {"path": str(dst), "bytes": dst.stat().st_size}
            return {"html": html}
        if op in ("snapshot", "snapshot_to"):
            return await _do_snapshot(data)
        if op in ("apply", "apply_from"):
            return await _do_apply(data)
        available_ops = (
            ["ping", "ls", "call", "report", "snapshot"]
            if _release_mode()
            else ["ping", "ls", "call", "upload", "report", "snapshot",
                  "snapshot_to", "apply", "apply_from"]
        )
        return {"error": f"모르는 op 입니다: {op}", "ops": available_ops}
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        if detail is not None:      # HTTPException — 기준 충돌(409)·규약 위반(400)
            return {"error": detail, "status": getattr(exc, "status_code", 500),
                    "op": op}
        return {"error": f"{type(exc).__name__}: {exc}", "op": op}
