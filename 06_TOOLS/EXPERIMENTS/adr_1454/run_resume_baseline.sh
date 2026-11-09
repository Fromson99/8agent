#!/bin/bash
# ADR-1454 resume: baseline s3..s8 only (candidate and baseline s1, s2 already done). One cell at a time.
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1454
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1454-multiturn-branch-scenarios-r12-qwen/artifacts; LOG=$ART/run.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
cd "$HERE"
ARM=baseline
for CASE in s3-article-number-only s4-continue-controls s5-compare s6-mentioned-article s7-guidance-unanswered s8-ask-when-unclear; do
  if stopped; then say "skip $ARM $CASE: earlier UNKNOWN or resource stop"; continue; fi
  timeout 900 $PY live.py $CASE $ARM --preflight > "$ART/preflight-$ARM-$CASE.log" 2>&1 || { say "STOP: preflight failed $ARM $CASE"; exit 3; }
  say "live start $ARM $CASE"
  timeout 3000 $PY live.py $CASE $ARM > "$ART/live-$ARM-$CASE.log" 2>&1; say "live exit $ARM $CASE $?"
done
say done
