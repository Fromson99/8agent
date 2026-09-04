#!/usr/bin/env bash
# Permanent v2 host launcher.  It bootstraps only from the lifecycle receipts
# named by 00_SYSTEM/WORKSPACE.json, then imports the exact receipt-bound code.
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace_root"
export PYTHONDONTWRITEBYTECODE=1

retirement_receipt_rel="$(
  "$workspace_root/.venv/bin/python" -c \
    'import json; print((json.load(open("00_SYSTEM/WORKSPACE.json"))["lifecycle"])["retirement_receipt"])'
)"
export LAWRAG_LAYOUT_RETIREMENT_RECEIPT="$workspace_root/$retirement_receipt_rel"

backend_app_dir="$(
  "$workspace_root/.venv/bin/python" - "$workspace_root" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
manifest_raw = (root / "00_SYSTEM/WORKSPACE.json").read_bytes()
manifest = json.loads(manifest_raw)
lifecycle = manifest.get("lifecycle") or {}
activation_value = lifecycle.get("activation_receipt")
if not isinstance(activation_value, str) or not activation_value:
    raise SystemExit("workspace lifecycle.activation_receipt is not configured")
activation_path = root / activation_value
activation_raw = activation_path.read_bytes()
activation = json.loads(activation_raw)
if activation.get("workspace_manifest_sha256") != hashlib.sha256(manifest_raw).hexdigest():
    raise SystemExit("activation receipt does not match WORKSPACE.json")
final_path = root / activation["validation_receipt_path"]
final_raw = final_path.read_bytes()
final = json.loads(final_raw)
if hashlib.sha256(final_raw).hexdigest() != activation.get("validation_receipt_sha256"):
    raise SystemExit("activation receipt does not match final receipt bytes")
if final.get("receipt_sha256") != activation.get("validation_record_sha256"):
    raise SystemExit("activation receipt does not match final receipt record")
if final.get("plan_sha256") != activation.get("migration_plan_sha256"):
    raise SystemExit("activation receipt does not match migration plan")
matches = [row for row in final.get("items", []) if row.get("source") == "lawrag"]
if len(matches) != 1:
    raise SystemExit("final receipt must bind exactly one lawrag target")
target = (root / matches[0]["target"]).resolve()
if root / "02_BACKEND" not in target.parents or target.name != "lawrag":
    raise SystemExit("receipt-bound lawrag target escaped 02_BACKEND")
print(target.parent)
PY
)"

# The package-level verifier performs no-follow publication checks and verifies
# the complete target fingerprint before uvicorn imports the application.
PYTHONPATH="$backend_app_dir${PYTHONPATH:+:$PYTHONPATH}" \
  "$workspace_root/.venv/bin/python" -c \
  'from lawrag.platform.workspace import load_layout; load_layout().migration_target("lawrag")'

workspace_data_root="$(
  PYTHONPATH="$backend_app_dir${PYTHONPATH:+:$PYTHONPATH}" \
    "$workspace_root/.venv/bin/python" -c \
    'from lawrag.platform.workspace import load_layout; print(load_layout().path("data"))'
)"

export CORS_ORIGINS="${CORS_ORIGINS:-*}"
export MAX_UPLOAD_MB="${MAX_UPLOAD_MB:-40}"
export STRUCTURE_RENDER_SCALE="${STRUCTURE_RENDER_SCALE:-2.0}"
export STRUCTURE_STORE="${STRUCTURE_STORE:-$workspace_data_root/structure}"
export STRUCTURE_CUSTOM_DIR="${STRUCTURE_CUSTOM_DIR:-$workspace_data_root/custom}"
export GLOSSARY_STORE="${GLOSSARY_STORE:-$workspace_data_root/glossary.json}"
export RAG_LINKS_STORE="${RAG_LINKS_STORE:-$workspace_data_root/links.json}"
export RAG_LOG_DIR="${RAG_LOG_DIR:-$workspace_data_root/rag}"
export RAG_RULES_DIR="${RAG_RULES_DIR:-$workspace_data_root/rules}"
export RAG_VECTOR_STORE="${RAG_VECTOR_STORE:-$workspace_data_root/embeddings/sections}"
export RAG_DELEGATION_STORE="${RAG_DELEGATION_STORE:-$workspace_data_root/delegation.json}"
export RAG_LAW_INDEX_STORE="${RAG_LAW_INDEX_STORE:-$workspace_data_root/law_index.json}"
export CORPUS_DIR="${CORPUS_DIR:-$workspace_data_root/corpus}"
export WIKI_STORE="${WIKI_STORE:-$workspace_data_root/wiki}"
export EXPC_STORE="${EXPC_STORE:-$workspace_data_root/expc}"
export REVIEW_STORE="${REVIEW_STORE:-$workspace_data_root/review}"
export LEGAL_GRAPH_STORE="${LEGAL_GRAPH_STORE:-$workspace_data_root/legal_graph}"
export DOMAIN_GRAPH_DB="${DOMAIN_GRAPH_DB:-$workspace_data_root/domain_graph/graph.sqlite}"
export OPS_DIR="${OPS_DIR:-$workspace_data_root/ops}"
export PIPELINE_DIR="${PIPELINE_DIR:-$workspace_data_root/pipeline}"
export PIPELINE_INBOX="${PIPELINE_INBOX:-$workspace_data_root/inbox}"

if [[ -n "${LAWRAG_RELEASE_STORE:-}" ]]; then
  exec "$workspace_root/.venv/bin/uvicorn" --app-dir "$backend_app_dir" \
    service:_app --factory --host "${HOST:-0.0.0.0}" --port "${PORT:-5566}"
fi

exec "$workspace_root/.venv/bin/uvicorn" --app-dir "$backend_app_dir" \
  lawrag.api.structure_app:app \
  --host "${HOST:-0.0.0.0}" --port "${PORT:-5566}"
