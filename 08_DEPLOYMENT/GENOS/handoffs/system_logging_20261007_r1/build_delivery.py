"""Freeze cumulative GENOS process logging over the existing latency R3 handoff."""
from __future__ import annotations

import ast
import base64
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent / "query_latency_20261007_r3"
NAME = "GENOS_SYSTEM_LOGGING_20261007_R1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def embedded_module(name, raw):
    packed = base64.b64encode(zlib.compress(raw, 9)).decode()
    return (f"_raw=zlib.decompress(base64.b64decode({packed!r}))\n"
            f"assert hashlib.sha256(_raw).hexdigest()=={sha(raw)!r}\n"
            f"_mod=types.ModuleType({name!r})\n"
            f"_mod.__file__=str(Path.cwd()/{(name + '.py')!r})\n"
            f"sys.modules[{name!r}]=_mod\n"
            f"exec(compile(_raw,_mod.__file__,'exec'),_mod.__dict__)\n")


def main():
    output = OUT / (NAME + ".zip")
    if output.exists():
        raise ValueError("Frozen ZIP exists; create a new revision")
    prior = json.loads((PARENT / "HANDOFF.json").read_text())
    parent_zip = PARENT / (prior["version"] + ".zip")
    assert sha(parent_zip.read_bytes()) == prior["code_zip_sha256"]
    with zipfile.ZipFile(parent_zip) as archive:
        parent_raw = archive.read("CODE_MANIFEST.json")
        assert sha(parent_raw) == prior["code_manifest_sha256"]
        parent = json.loads(parent_raw)
        payload = {row["path"]: archive.read(row["path"]) for row in parent["files"]}
    rows = {row["path"]: dict(row) for row in parent["files"]}
    baseline = json.loads((OUT / "WORKING_BASELINE.json").read_text())
    # Preserve the already tested serving bytes when unrelated development
    # advances in the shared checkout during this task. Do not import those
    # pending features into a logging-only deployment without validation.
    frozen = OUT / "drafts/draft-9ae3c3d162a47d77.zip"
    with zipfile.ZipFile(frozen) as archive:
        verified = json.loads(archive.read("CODE_MANIFEST.json"))
        verified_payload = {row["path"]: archive.read(row["path"]) for row in verified["files"]}
    preserved_drift = []
    owned = {*baseline, "00_SYSTEM/PIPELINE.json", "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py",
             *(row["path"] for row in parent["files"] if row["path"].startswith(
                 ("02_BACKEND/ENGINES/legal_agent/", "02_BACKEND/ENGINES/term_runtime/")))}
    changed = []
    for path, old in tuple(payload.items()):
        current = (ROOT / path).read_bytes()
        pin = path == "00_SYSTEM/PIPELINE.json" or path.startswith("02_BACKEND/ENGINES/")
        new = verified_payload[path] if path not in owned or pin else current
        if new != current:
            preserved_drift.append({"path": path, "working_sha256": sha(current), "delivery_sha256": sha(new)})
        if old == new:
            continue
        assert path in owned, "Unexpected tested-base change: " + path
        predecessors = {sha(old), *rows[path].get("allowed_predecessors", [])}
        if path in baseline:
            predecessors.add(baseline[path])
        payload[path] = new
        rows[path].update(sha256=sha(new), bytes=len(new), allowed_predecessors=sorted(predecessors))
        changed.append(path)
    added = ("genos_diagnostics.py", "genos_log_runner.py",
             "06_TOOLS/COMMANDS/code_ship.py",
             "07_DOCS/REFERENCE/OPERATIONS/GENOS_SYSTEM_LOGGING_20261007.md")
    for path in added:
        raw = (ROOT / path).read_bytes()
        assert path not in payload
        payload[path] = raw
        rows[path] = {"path": path, "bytes": len(raw), "sha256": sha(raw), "allow_missing_predecessor": True}
        if path in baseline:
            rows[path]["allowed_predecessors"] = [baseline[path]]
    for path, raw in payload.items():
        assert sha(raw) == rows[path]["sha256"]
        if path.endswith(".py"):
            compile(raw, path, "exec")
            ast.parse(raw, feature_version=(3, 10) if "/workflow/" in path else (3, 11))
    pointer = json.loads((ROOT / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json").read_text())
    assert pointer == prior["selected_local_baseline"] and pointer["generation"] == 45
    candidate = dict(parent["main_basis"]["candidate_serving_files"])
    candidate.update({path: rows[path]["sha256"] for path in (*changed, *added) if path.endswith(".py")})
    required = {row["path"]: row for row in parent["required_files"]}
    for path in (*required, *added):
        required[path] = {"path": path, "sha256": rows[path]["sha256"]}
    manifest = {**parent, "id": NAME, "files": [rows[path] for path in sorted(rows)],
        "required_files": [required[path] for path in sorted(required)],
        "parent_code_zip_sha256": prior["code_zip_sha256"],
        "main_basis": {**parent["main_basis"], "candidate_serving_files": candidate},
        "scope": {"updated_files": changed, "added_files": list(added),
                  "unchanged_parent_code_files": len(parent["files"]) - len(changed),
                  "unrelated_working_drift_preserved_excluded": preserved_drift,
                  "tested_serving_basis_zip_sha256": sha(frozen.read_bytes())},
        "system_logging": {"revision": "genos-system-logging-20261007-r1",
            "default_root": "/nfs-root/diamo/8-agent/logs/system", "raw_traceback_truncated": False,
            "nfs_io_on_request_thread": False, "local_spool": "fsync-until-nfs-byte-verified",
            "platform_before_process_start": "REQUIRES_PLATFORM_LOG_EXPORT"},
        "field_deployment_status": "NOT_VERIFIED"}
    manifest_raw = encode(manifest)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, raw in sorted({**payload, "CODE_MANIFEST.json": manifest_raw}.items()):
            archive.writestr(path, raw)
    zip_raw = buffer.getvalue()
    inner = (PARENT / (prior["version"] + "_APPLY.txt")).read_text()
    assert sha(inner.encode()) == prior["apply_txt_sha256"]
    inner = inner.replace(prior["version"], NAME).replace(prior["code_zip_sha256"], sha(zip_raw))
    inner = inner.replace("query-latency-r3-logs", "system-logging-r1-artifacts")
    inner = inner.replace("QUERY_LATENCY_EXIT", "SYSTEM_LOGGING_EXIT")
    inner = inner.replace('exec > >(tee -a "$task_log") 2>&1\n', '')
    inner = inner.replace('task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$task_mode-$$.log"',
                          'task_log="${GENOS_SYSTEM_LOG_DIR}/${GENOS_LOG_RUN_ID}"')
    inner = inner.replace('task_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"',
                          'task_dir="${GENOS_SYSTEM_HANDOFF_DIR:?}"')
    inner = inner.replace('mkdir -p "$task_logs"',
        'if ! mkdir -p "$task_logs"; then\n'
        '  task_logs="${GENOS_LOG_SPOOL_DIR:-${TMPDIR:-/tmp}/8-agent-system-logs}/handoff-${GENOS_LOG_RUN_ID}"\n'
        '  mkdir -p "$task_logs"\nfi', 1)
    assert "GENOS_SYSTEM_HANDOFF_DIR" in inner
    header = "import base64,hashlib,os,sys,types,zlib\nfrom pathlib import Path\n"
    bootstrap = header + embedded_module("genos_diagnostics", payload["genos_diagnostics.py"])
    bootstrap += embedded_module("genos_log_runner", payload["genos_log_runner.py"])
    compressed_inner = base64.b64encode(zlib.compress(inner.encode(), 9)).decode()
    bootstrap += ("os.environ['GENOS_SYSTEM_HANDOFF_DIR']=str(Path(sys.argv[1]).resolve().parent)\n"
        f"os.environ.setdefault('GENOS_SYSTEM_LOG_DIR',{manifest['system_logging']['default_root']!r})\n"
        "os.environ.setdefault('GENOS_LOG_RUN_ID','deploy-'+sys.modules['genos_diagnostics'].uuid.uuid4().hex[:16])\n"
        "os.environ.setdefault('GENOS_HANDOFF_LOG_DIR',str(Path(os.environ['GENOS_SYSTEM_LOG_DIR'])/os.environ['GENOS_LOG_RUN_ID']/'deployment-artifacts'))\n"
        f"_script=zlib.decompress(base64.b64decode({compressed_inner!r})).decode()\n"
        f"assert hashlib.sha256(_script.encode()).hexdigest()=={sha(inner.encode())!r}\n"
        "raise SystemExit(sys.modules['genos_log_runner'].main(['--phase','deploy','--','bash','-c',_script,sys.argv[1],*sys.argv[2:]]))\n")
    script = ("#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n"
        'if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; '
        'elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\n'
        'python3 - "${BASH_SOURCE[0]}" "$@" <<\'SYSTEM_LOG_BOOTSTRAP\'\n' + bootstrap + "SYSTEM_LOG_BOOTSTRAP\n")
    workflow = header + embedded_module("genos_diagnostics", payload["genos_diagnostics.py"])
    workflow += payload["08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py"].decode()
    ast.parse(workflow, feature_version=(3, 10))
    ast.parse(bootstrap, feature_version=(3, 11))
    ast.parse(inner.split("<<'LOADER_PY'\n", 1)[1].rsplit("\nLOADER_PY", 1)[0], feature_version=(3, 11))
    output.write_bytes(zip_raw)
    (OUT / "CODE_MANIFEST.json").write_bytes(manifest_raw)
    (OUT / (NAME + "_APPLY.txt")).write_text(script)
    (OUT / (NAME + "_WORKFLOW_PASTE_ALL.txt")).write_text(workflow)
    (OUT / "INNER_APPLY.txt").write_text(inner)
    subprocess.run(["bash", "-n", str(OUT / (NAME + "_APPLY.txt"))], check=True)
    record = {"version": NAME, "created_at": datetime.now(timezone.utc).isoformat(),
        "parent": prior["version"], "parent_code_zip_sha256": prior["code_zip_sha256"],
        "code_zip_sha256": sha(zip_raw), "code_manifest_sha256": sha(manifest_raw), "code_files": len(rows),
        "code_zip_bytes": len(zip_raw), "apply_txt_sha256": sha(script.encode()),
        "workflow_txt_sha256": sha(workflow.encode()), "inner_apply_txt_sha256": sha(inner.encode()),
        "working_code_root": str(ROOT), "selected_local_baseline": pointer,
        "source_git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "scope": manifest["scope"], "genos_checkout": "~/DEV", "field_generation": None,
        "field_generation_manifest_sha256": None, "field_commit": None, "field_codeserving_revision": None,
        "genos_applied": False, "genos_pushed": False, "genos_deployed": False,
        "onsite_workflow_verified": False, "local_active_pointer_changed": False, "email_sent": False}
    (OUT / "HANDOFF.json").write_bytes(encode(record))
    names = (output.name, NAME + "_APPLY.txt", NAME + "_WORKFLOW_PASTE_ALL.txt", "CODE_MANIFEST.json", "HANDOFF.json")
    (OUT / "SHA256SUMS").write_text("".join(sha((OUT / path).read_bytes()) + "  " + path + "\n" for path in names))
    print(json.dumps({"zip": str(output), "files": len(rows), "changed": len(changed), "bytes": len(zip_raw)}))


if __name__ == "__main__":
    main()
