#!/usr/bin/env bash
# 구조 해석 서버 — 호스트 직접 실행 (2026-08-11 사용자 결정: 컨테이너 안 씀).
#
#   scripts/serve.sh              # 포그라운드
#   nohup scripts/serve.sh >/tmp/structure-serve.log 2>&1 &   # 백그라운드
#
# env 는 예전 compose 가 주던 것을 호스트 경로로 그대로 옮긴
# 것이다. ANTHROPIC_API_KEY 는 .env 에서 lawrag.core.llm.load_env() 가 읽는다.
# 도클링 모델 캐시는 호스트 HF 기본 캐시(~/.cache/huggingface)를 쓴다 —
# 첫 재해석 때 모델을 새로 받을 수 있다(RAG·링크·디버깅 화면은 무관).
set -euo pipefail
cd "$(dirname "$0")/.."

# v2 is admitted only through the workspace activation receipt.  Keep the
# legacy import path untouched while bridge mode remains the default.
if [[ "${LAWRAG_LAYOUT_VERSION:-}" == "v2" ]]; then
  workspace_root="$PWD"
  (
    cd /tmp
    PYTHONPATH="$workspace_root/02_BACKEND${PYTHONPATH:+:$PYTHONPATH}" \
      "$workspace_root/.venv/bin/python" -c \
      'from lawrag.platform.workspace import load_layout; load_layout().path("backend")'
  )
  backend_app_dir="$workspace_root/02_BACKEND"
  workspace_data_root="$workspace_root/01_DATA"
else
  backend_app_dir=""
  workspace_data_root="$PWD/data"
fi

export CORS_ORIGINS="${CORS_ORIGINS:-*}"
export MAX_UPLOAD_MB="${MAX_UPLOAD_MB:-40}"
export STRUCTURE_RENDER_SCALE="${STRUCTURE_RENDER_SCALE:-2.0}"

if [[ -n "${LAWRAG_RELEASE_STORE:-}" ]]; then
  # service.py verifies and pins release/SourceSet/MAIN before importing any
  # application router.  --factory preserves that import order for host mode.
  exec .venv/bin/uvicorn service:_app --factory \
    --host "${HOST:-0.0.0.0}" --port "${PORT:-5566}"
fi

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

if [[ -n "$backend_app_dir" ]]; then
  exec .venv/bin/uvicorn --app-dir "$backend_app_dir" lawrag.api.structure_app:app \
    --host "${HOST:-0.0.0.0}" --port "${PORT:-5566}"
fi

exec .venv/bin/uvicorn lawrag.api.structure_app:app \
  --host "${HOST:-0.0.0.0}" --port "${PORT:-5566}"
