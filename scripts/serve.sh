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

export STRUCTURE_STORE="${STRUCTURE_STORE:-$PWD/data/structure}"
export STRUCTURE_CUSTOM_DIR="${STRUCTURE_CUSTOM_DIR:-$PWD/data/custom}"
export GLOSSARY_STORE="${GLOSSARY_STORE:-$PWD/data/glossary.json}"
export RAG_LINKS_STORE="${RAG_LINKS_STORE:-$PWD/data/links.json}"
export CORS_ORIGINS="${CORS_ORIGINS:-*}"
export MAX_UPLOAD_MB="${MAX_UPLOAD_MB:-40}"
export STRUCTURE_RENDER_SCALE="${STRUCTURE_RENDER_SCALE:-2.0}"

exec .venv/bin/uvicorn lawrag.api.structure_app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-5566}"
