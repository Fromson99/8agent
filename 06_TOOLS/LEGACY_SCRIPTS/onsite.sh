#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# 폐쇄망에서 Hugging Face/Transformers가 누락 모델을 인터넷에서 받으려 하지 않게 한다.
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export EMBED_LOCAL_FILES_ONLY="${EMBED_LOCAL_FILES_ONLY:-1}"
export STRUCTURE_STORE="${STRUCTURE_STORE:-$PWD/data/structure}"
export PIPELINE_DIR="${PIPELINE_DIR:-$PWD/data/pipeline}"
export PIPELINE_INBOX="${PIPELINE_INBOX:-$PWD/data/inbox}"

exec .venv/bin/python -m lawrag.pipeline.onsite "$@"
