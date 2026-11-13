#!/bin/bash
# ADR-1511: the cmp-liquidity rerun after start_now.sh (its first try at 15:56 was refused by the frozen live.py rule
# "a rerun follows STOP_EXTERNAL"; the yield is now recorded there as an operator stop). Same admission/yield as start_now.
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
A=$($PY -c "from common import ART;print(ART)")
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
GIB=1048576
avail() { awk '/MemAvailable/{print $2}' /proc/meminfo; }
log() { echo "$*" >> $A/driver.log; }
until grep -q '^ALL_DONE' $A/driver.log; do sleep 20; done
[ -f $A/STOP_ALL.json ] && exit 0
n=$($PY -c "
from common import *
print(sum(len(read(p)) for p in (ART/'live/candidate').glob('*/calls.json')))")
if [ $n -gt $((200-64)) ]; then log "cmp-liquidity --rerun skipped: $n physical calls (limit 200)"; else
  waited=0; while [ $(avail) -lt $((5*GIB)) ] && [ $waited -lt 1800 ]; do sleep 15; waited=$((waited+15)); done
  log "=== cmp-liquidity candidate --rerun $(date '+%H:%M:%S') waited $waited free_KiB $(avail) (beside ADR-1509 single lane)"
  $PY live.py cmp-liquidity candidate --rerun > $A/log-candidate-cmp-liquidity-rerun.txt 2>&1 &
  pid=$! low=0
  while kill -0 $pid 2>/dev/null; do
    if [ $(avail) -lt $((34*GIB/10)) ]; then low=$((low+1)); else low=0; fi
    if [ $low -ge 2 ]; then kill $pid; sleep 2; kill -9 $pid 2>/dev/null
      printf '{"case":"cmp-liquidity","rerun":"--rerun","reason":"free RAM below 3.4GiB twice; our cell yields","at":"%s","provider_outcome_unknown":true}\n' "$(date -Is)" > $A/yield-cmp-liquidity-rerun.json
      log "yield-stop cmp-liquidity --rerun $(date '+%H:%M:%S')"; break; fi
    sleep 5
  done
  wait $pid 2>/dev/null; log "exit $? $(date +%H:%M:%S)"
fi
$PY collect.py > $A/collect.stdout 2>&1; log "collect exit $? (after liquidity rerun)"
log ALL_DONE_FINAL
echo "run_all exit 0 $(date '+%F %T') (final)" >> $A/start.log
