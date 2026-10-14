"""Freeze a cumulative, no-Socket.IO correction over the delivered R2 bytes."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent / "routed_socket_chat_20261007_r2"
NAME = "GENOS_NO_SOCKET_CHAT_20261007_R3"
ZIP = OUT / (NAME + ".zip")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encode(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one replacement: {old[:80]}")
    return source.replace(old, new)


def main() -> None:
    if ZIP.exists():
        raise ValueError("Frozen R3 ZIP already exists; use a new revision")
    parent_record = json.loads((PARENT / "HANDOFF.json").read_text())
    parent_zip = PARENT / (parent_record["version"] + ".zip")
    assert sha(parent_zip.read_bytes()) == parent_record["code_zip_sha256"]
    with zipfile.ZipFile(parent_zip) as archive:
        parent_manifest_raw = archive.read("CODE_MANIFEST.json")
        assert sha(parent_manifest_raw) == parent_record["code_manifest_sha256"]
        parent = json.loads(parent_manifest_raw)
        payload = {row["path"]: archive.read(row["path"]) for row in parent["files"]}
    rows = {row["path"]: dict(row) for row in parent["files"]}
    changed = (
        "main_router.py",
        "main_integrated.py",
        "08_DEPLOYMENT/GENOS/start_sse.py",
        "08_DEPLOYMENT/GENOS/requirements-socketio.txt",
        "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py",
    )
    added = ("07_DOCS/REFERENCE/OPERATIONS/GENOS_NO_SOCKET_CHAT_MODES_20261007_R3.md",)
    for path, raw in payload.items():
        if path not in changed:
            assert (ROOT / path).read_bytes() == raw, "Unrelated source drift: " + path
    for path in changed:
        raw = (ROOT / path).read_bytes()
        assert raw != payload[path], "Expected changed source: " + path
        allowed = {sha(payload[path]), *rows[path].get("allowed_predecessors", [])}
        payload[path] = raw
        rows[path].update(sha256=sha(raw), bytes=len(raw), allowed_predecessors=sorted(allowed))
    for path in added:
        raw = (ROOT / path).read_bytes()
        payload[path] = raw
        rows[path] = {"path": path, "sha256": sha(raw), "bytes": len(raw),
                      "allow_missing_predecessor": True}
    for path, raw in payload.items():
        assert sha(raw) == rows[path]["sha256"]
        assert Path(path).suffix.lower() not in {".js", ".jsx", ".mjs", ".cjs", ".db", ".sqlite", ".pem", ".key"}
        if path.endswith(".py"):
            ast.parse(raw, filename=path, feature_version=(3, 10) if "/workflow/" in path else (3, 11))
    for path in changed:
        if path.endswith(".py"):
            assert b"import socketio" not in payload[path]
            assert b"from main_socketio import" not in payload[path]
    pointer = json.loads((ROOT / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json").read_text())
    assert pointer == parent_record["selected_local_baseline"] and pointer["generation"] == 44
    candidate = dict(parent["main_basis"]["candidate_serving_files"])
    candidate.update({path: rows[path]["sha256"] for path in changed if path.endswith(".py")})
    manifest = {**parent,
        "id": NAME,
        "files": [rows[path] for path in sorted(rows)],
        "parent_code_zip_sha256": parent_record["code_zip_sha256"],
        "main_basis": {**parent["main_basis"], "candidate_serving_files": candidate,
                       "local_active_pointer_changed": False},
        "scope": {"updated_files": list(changed), "added_files": list(added),
                  "unchanged_parent_code_files": len(parent["files"]) - len(changed)},
        "socket_chat": {"enabled": False, "retired_after_r2": True},
        "chat_modes": {"entrypoint": "main_router:app", "default_mode": "workflow",
                       "integrated": {"executor": "in-process-rag", "route": "/chat", "transport": "json"},
                       "workflow": {"executor": "external-genos-python-workflow", "route": "/stream",
                                    "backend_transport": "http-sse", "final_transport": "json"},
                       "platform_socketio": False, "platform_binding_switch": "MANUAL_PLATFORM_CONFIGURATION"},
        "field_deployment_status": "NOT_VERIFIED"}
    manifest_raw = encode(manifest)
    with zipfile.ZipFile(ZIP, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, raw in sorted({**payload, "CODE_MANIFEST.json": manifest_raw}.items()):
            archive.writestr(path, raw)
    (OUT / "CODE_MANIFEST.json").write_bytes(manifest_raw)

    prior_script = PARENT / (parent_record["version"] + "_APPLY.txt")
    script = prior_script.read_text()
    assert sha(script.encode()) == parent_record["apply_txt_sha256"]
    script = script.replace(parent_record["version"], NAME)
    script = script.replace(parent_record["code_zip_sha256"], sha(ZIP.read_bytes()))
    script = replace_once(script, "routed-socket-chat-r2-logs", "no-socket-chat-r3-logs")
    script = script.replace("ROUTED_CHAT_EXIT", "NO_SOCKET_CHAT_EXIT")
    script = replace_once(script,
        "Select workflow SSE or integrated Socket.IO over local MAIN generation 44",
        "Restore workflow SSE or integrated JSON over local MAIN generation 44")
    script = replace_once(script,
        "if main_router.MODE=='integrated':\n import main_integrated\n assert main_router.app is main_integrated.app",
        "if main_router.MODE=='integrated':\n import main\n assert main_router.app is main.app")
    script = replace_once(script,
        "print('ROUTED_CHAT_CONTRACT PASS',main_router.MODE,flush=True)",
        "assert 'socketio' not in sys.modules\nprint('NO_SOCKET_CHAT_CONTRACT PASS',main_router.MODE,flush=True)")
    script = replace_once(script,
        "Deploy main_router:app with GENOS_MAIN_MODE=workflow or integrated; match the separate platform workflow/chat binding and Socket.IO option, then test only in the workflow screen.",
        "Deploy main_router:app with GENOS_MAIN_MODE=workflow or integrated; turn off the platform Socket.IO option for both, match the workflow/chat binding, and test only in the workflow screen.")
    loader = script.split("<<'LOADER_PY'\n", 1)[1].rsplit("\nLOADER_PY", 1)[0]
    ast.parse(loader, feature_version=(3, 11))
    (OUT / (NAME + "_APPLY.txt")).write_text(script)
    workflow = payload["08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py"]
    (OUT / (NAME + "_WORKFLOW_PASTE_ALL.txt")).write_bytes(workflow)
    push = (PARENT / (parent_record["version"] + "_PUSH_NEW_REMOTE.txt")).read_text()
    push = push.replace(parent_record["version"], NAME).replace("R2", "R3")
    (OUT / (NAME + "_PUSH_NEW_REMOTE.txt")).write_text(push)
    handoff = {**parent_record,
        "version": NAME,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "code_zip_sha256": sha(ZIP.read_bytes()),
        "code_zip_bytes": ZIP.stat().st_size,
        "code_manifest_sha256": sha(manifest_raw),
        "code_files": len(rows),
        "apply_txt_sha256": sha(script.encode()),
        "parent_code_zip_sha256": parent_record["code_zip_sha256"],
        "workflow_txt_sha256": sha(workflow),
        "source_git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "changed_payload_files": list((*changed, *added)),
        "reported_field_state": {"r2_apply": "USER_REPORTED", "r2_push": "NOT_DONE",
                                 "r2_code_serving_revision": "NOT_DEPLOYED"},
        "actual_selected_generation": None,
        "actual_generation_manifest_sha256": None,
        "push_commit": None,
        "code_serving_revision": None,
        "chat_binding": "NOT_SELECTED",
        "genos_deployed": False,
        "field_socketio": "DISABLE_REQUIRED_NOT_VERIFIED",
        "email_status": "NOT_SENT",
        "local_active_pointer_changed": False,
    }
    (OUT / "HANDOFF.json").write_bytes(encode(handoff))
    print(json.dumps({"files": len(rows), "zip_sha256": handoff["code_zip_sha256"],
                      "zip_bytes": ZIP.stat().st_size}))


if __name__ == "__main__":
    main()
