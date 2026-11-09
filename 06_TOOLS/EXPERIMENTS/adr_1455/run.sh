#!/bin/bash
# ADR-1455: candidate r13 only (8 chats), one cell at a time. Baseline = ADR-1454 MAIN176 cells.
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1455
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1455-multiturn-branch-scenarios-r13-qwen/artifacts; LOG=$ART/run.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
cd "$HERE"
CASES="s1-same-law-other-article s2-other-law-field s3-article-number-only s4-continue-controls s5-compare s6-mentioned-article s7-guidance-unanswered s8-ask-when-unclear"
for ARM in candidate; do
  for CASE in $CASES; do
    if stopped; then say "skip $ARM $CASE: earlier UNKNOWN or resource stop"; continue; fi
    timeout 900 $PY live.py $CASE $ARM --preflight > "$ART/preflight-$ARM-$CASE.log" 2>&1 || { say "STOP: preflight failed $ARM $CASE"; exit 3; }
    say "live start $ARM $CASE"
    timeout 3000 $PY live.py $CASE $ARM > "$ART/live-$ARM-$CASE.log" 2>&1; say "live exit $ARM $CASE $?"
  done
done
say done
