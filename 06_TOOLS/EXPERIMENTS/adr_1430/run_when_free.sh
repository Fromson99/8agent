#!/bin/bash
# ADR-1430: start only when no other live cell / test run is active and memory has recovered.
# Then: MAIN165-based contract re-check -> freeze -> preflight -> live 3 turns -> read-choice audit.
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1430
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1430-guided-forced-reads-qwen-r3/artifacts; mkdir -p "$ART"; LOG=$ART/run-when-free.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
calm() {
  pgrep -f "[l]ive[.]py" >/dev/null && return 1
  pgrep -f "[b]atch[.]py" >/dev/null && return 1
  pgrep -f "[p]ytest" >/dev/null && return 1
  pgrep -f "[c]heck[0-9]*[.]py" >/dev/null && return 1
  pgrep -f "[p]robe[.]py" >/dev/null && return 1
  local avail sfree
  avail=$(awk '/MemAvailable/{print $2}' /proc/meminfo); sfree=$(awk '/SwapFree/{print $2}' /proc/meminfo)
  [ "$avail" -gt $((6*1024*1024)) ] && [ "$sfree" -gt $((1638*1024)) ]
}
wait_calm() { local ok=0; while [ $ok -lt 4 ]; do if calm; then ok=$((ok+1)); else ok=0; fi; sleep 15; done; }
say "waiting for a free machine"; wait_calm; say "machine free: $(free -m | awk '/Mem:/{print "avail="$7"MB"} /Swap:/{print "swapfree="$4"MB"}' | tr '\n' ' ')"
# 1. Contract re-check on the current selected release (MAIN165) with the work code.
ISO=/tmp/a8-followup-iso165; rm -rf "$ISO"; rsync -a --exclude __pycache__ /tmp/a8-followup-iso164/ "$ISO"/
REL=$($PY -c "import json;p=json.load(open('$ROOT/01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'));print(json.load(open('$ROOT/'+p['manifest_path']))['code_root'])")
cp -a "$ROOT/$REL/." "$ISO"/; find "$ISO" -name __pycache__ -type d -prune -exec rm -rf {} +
for f in 02_BACKEND/semantic_runtime/legal_agent/{guided_navigation,law_navigation,decision_projection,memory_rag,corrected_memory,memory_methods,guided_answer,completion_execution,law_candidates,connection_scope}.py \
         00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json 05_TESTS/CONTRACTS/test_guided_followup_reads.py 05_TESTS/CONTRACTS/test_guided_continue_bounds.py; do cp "$ROOT/$f" "$ISO/$f"; done
$PY -I /tmp/a8-followup-tools/repin.py "$ISO" >> "$LOG" 2>&1
( cd "$ISO" && timeout 900 $PY -m pytest -q -p no:cacheprovider 05_TESTS/CONTRACTS/test_guided_followup_reads.py 05_TESTS/CONTRACTS/test_guided_continue_bounds.py \
    05_TESTS/CONTRACTS/test_guided_answer.py 05_TESTS/CONTRACTS/test_multiturn_dialogue_api.py 05_TESTS/CONTRACTS/test_multiturn_dialogue.py ) > "$ART/contract-recheck.log" 2>&1
tail -1 "$ART/contract-recheck.log" | tee -a "$LOG"
if ! tail -1 "$ART/contract-recheck.log" | grep -q " passed" || tail -1 "$ART/contract-recheck.log" | grep -q "failed"; then say "STOP: contract re-check failed"; exit 3; fi
# 2. Freeze (no model call).
( cd "$HERE" && $PY setup.py design ) >> "$LOG" 2>&1 || { say "STOP: freeze failed"; exit 4; }
say "frozen"; wait_calm
# 3. Preflight and live cell, alone.
( cd "$HERE" && timeout 900 $PY live.py shareholder-resolution-3turn candidate --preflight ) > "$ART/preflight.log" 2>&1 || { say "STOP: preflight failed"; exit 5; }
say "preflight ready"; wait_calm; say "live start"
( cd "$HERE" && timeout 3000 $PY live.py shareholder-resolution-3turn candidate ) > "$ART/live-run.log" 2>&1; rc=$?
say "live exit $rc"; grep -E "^LIVE_RESULT|^RESOURCE_STOP" "$ART/live-run.log" | cut -c1-400 | tee -a "$LOG"
# 4. Read-choice audit (no model call).
$PY "$HERE/audit.py" "$ART/public-live/shareholder-resolution-3turn-candidate" 2>&1 | tail -1 | tee -a "$LOG"
say "done"
