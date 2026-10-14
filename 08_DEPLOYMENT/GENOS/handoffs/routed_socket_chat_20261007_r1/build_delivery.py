"""Freeze the routed Socket.IO code over the selected generation-44 handoff."""
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
PARENT = OUT.parent / "investigation_completion_20261007_r1"
NAME = "GENOS_ROUTED_SOCKET_CHAT_20261007_R1"
ZIP = OUT / (NAME + ".zip")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encode(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


if ZIP.exists():
    raise ValueError("Published handoff is immutable; use a new revision")
parent_record = json.loads((PARENT / "HANDOFF.json").read_text())
parent_zip = PARENT / (parent_record["version"] + ".zip")
assert sha(parent_zip.read_bytes()) == parent_record["code_zip_sha256"]
with zipfile.ZipFile(parent_zip) as archive:
    parent_manifest_raw = archive.read("CODE_MANIFEST.json")
    assert sha(parent_manifest_raw) == parent_record["code_manifest_sha256"]
    parent = json.loads(parent_manifest_raw)
    payload = {row["path"]: archive.read(row["path"]) for row in parent["files"]}

changed = "08_DEPLOYMENT/GENOS/start_sse.py"
added = (
    "main_router.py",
    "main_integrated.py",
    "08_DEPLOYMENT/GENOS/requirements-socketio.txt",
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_ROUTED_SOCKET_CHAT_20261007.md",
)
for path in payload:
    if path != changed:
        assert (ROOT / path).read_bytes() == payload[path], "Working code drift: " + path
assert (ROOT / changed).read_bytes() != payload[changed]
original = {row["path"]: row for row in parent["files"]}
rows = {path: dict(row) for path, row in original.items()}
old_digest = sha(payload[changed])
payload[changed] = (ROOT / changed).read_bytes()
rows[changed].update(sha256=sha(payload[changed]), bytes=len(payload[changed]),
                     allowed_predecessors=sorted({old_digest, *rows[changed].get("allowed_predecessors", [])}))
for path in added:
    raw = (ROOT / path).read_bytes()
    payload[path] = raw
    rows[path] = {"path": path, "sha256": sha(raw), "bytes": len(raw),
                  "allow_missing_predecessor": True}

for path, raw in payload.items():
    assert sha(raw) == rows[path]["sha256"]
    if path.endswith(".py"):
        compile(raw, path, "exec")
        ast.parse(raw, filename=path, feature_version=(3, 10) if "/workflow/" in path else (3, 11))
    assert Path(path).suffix.lower() not in {".js", ".jsx", ".mjs", ".cjs", ".db", ".sqlite", ".key", ".pem"}

pointer = json.loads((ROOT / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json").read_text())
assert pointer == parent["main_basis"]["pointer"]
assert pointer["generation"] == 44
candidate_files = dict(parent["main_basis"]["serving_files"])
candidate_files[changed] = rows[changed]["sha256"]
candidate_files.update({path: rows[path]["sha256"] for path in added if path.endswith(".py")})
manifest = {**parent,
    "id": NAME,
    "files": [rows[path] for path in sorted(rows)],
    "parent_code_zip_sha256": parent_record["code_zip_sha256"],
    "main_basis": {**parent["main_basis"], "candidate_serving_files": candidate_files,
                   "local_active_pointer_changed": False, "quality_experiment": False},
    "field_deployment_status": "NOT_RUN",
    "scope": {"new_socketio_code": list(added), "updated_entrypoint": changed,
              "unchanged_parent_code_files": len(original) - 1},
    "socket_chat": {"entrypoint": "main_router:app", "default_mode": "existing",
                    "integrated_mode": "integrated", "route": "/chat",
                    "socketio_path_default": "/socket.io", "field_rendering": "NOT_VERIFIED"},
}
manifest_raw = encode(manifest)
with zipfile.ZipFile(ZIP, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path, raw in sorted({**payload, "CODE_MANIFEST.json": manifest_raw}.items()):
        archive.writestr(path, raw)

script = (PARENT / "APPLY_TEMPLATE.txt").read_text()
script = script.replace('task_mode="${1:-all}"', 'task_mode="${1:-check}"')
script = script.replace("investigation-completion-r1-logs", "routed-socket-chat-r1-logs")
script = script.replace("INVESTIGATION_CONTROL_EXIT", "ROUTED_CHAT_EXIT")
script = script.replace("Integrate validated investigation completion from local MAIN generation 44",
                        "Add routed Socket.IO chat over local MAIN generation 44")
script = script.replace("workflow_editor='NOT_APPLIED'", "chat_binding='NOT_SELECTED'")
script = script.replace("Complete the code-serving revision deployment and workflow editor replacement, then test only in the workflow screen.",
    "Deploy a new code-serving revision with main_router:app, GENOS_MAIN_MODE=integrated, then select /chat and test only in the workflow screen.")
marker = "print('SERVICE_LOADER_CONTRACT PASS',binding['mode'],str(generation),flush=True)"
assert script.count(marker) == 1
script = script.replace(marker, marker + """
import main_router
assert main_router.MODE in ('existing','integrated')
if main_router.MODE=='integrated':
 import main_integrated
 assert main_router.app is main_integrated.app
print('ROUTED_CHAT_CONTRACT PASS',main_router.MODE,flush=True)""")
script = script.replace("@NAME@", NAME).replace("@ZIP_SHA256@", sha(ZIP.read_bytes()))
loader = script.split("<<'LOADER_PY'\n", 1)[1].rsplit("\nLOADER_PY", 1)[0]
ast.parse(loader, feature_version=(3, 11))
(OUT / (NAME + "_APPLY.txt")).write_text(script)
(OUT / "CODE_MANIFEST.json").write_bytes(manifest_raw)
record = {"version": NAME, "created_at": datetime.now(timezone.utc).isoformat(),
    "code_zip_sha256": sha(ZIP.read_bytes()), "code_zip_bytes": ZIP.stat().st_size,
    "code_manifest_sha256": sha(manifest_raw), "code_files": len(rows),
    "apply_txt_sha256": sha(script.encode()),
    "parent_code_zip_sha256": parent_record["code_zip_sha256"],
    "selected_local_baseline": pointer, "local_active_pointer_changed": False,
    "source_code_root": str(ROOT),
    "source_git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "source_has_uncommitted_changes": True,
    "changed_payload_files": [changed, *added],
    "actual_selected_generation": None, "actual_generation_manifest_sha256": None,
    "push_commit": None, "code_serving_revision": None, "chat_binding": "NOT_SELECTED",
    "genos_deployed": False, "field_socketio": "NOT_VERIFIED", "external_model_calls": 0}
(OUT / "HANDOFF.json").write_bytes(encode(record))
print(json.dumps({"version": NAME, "files": len(rows), "zip_sha256": record["code_zip_sha256"]}, ensure_ascii=False))
