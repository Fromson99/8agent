#!/bin/bash
# ADR-1525: 문서 대사 = ordinary 대사 per reading group. Runs after other sessions' experiments: before the first cell it
# waits until no live.py/batch.py/run_all.sh/rerun.py/start_now.sh of another 06_TOOLS/EXPERIMENTS/adr_* folder has run
# for 2 minutes (user rule: real-model cells alone; 2 hours at most). A cell starts only with >=5GiB free RAM; the
# resource guard inside the cell stops it under pressure. Frozen order: doc-liquidity; doc-model-code only if
# doc-liquidity answered HTTP 200; then collect.py.
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
A=$($PY -c "from common import ART;print(ART)")
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
GIB=1048576  # KiB
avail() { awk '/MemAvailable/{print $2}' /proc/meminfo; }
log() { echo "$*" >> $A/driver.log; }
cell() {
  local c=$1 waited=0
  [ -f $A/STOP_ALL.json ] && return 1
  while [ $(avail) -lt $((5*GIB)) ] && [ $waited -lt 1800 ]; do sleep 15; waited=$((waited+15)); done
  if [ $(avail) -lt $((5*GIB)) ]; then log "=== $c not started: free RAM below 5GiB for 30 minutes $(date '+%T')"; return 1; fi
  log "=== $c candidate $(date '+%H:%M:%S') waited $waited free_KiB $(avail)"
  $PY live.py $c candidate > $A/log-candidate-$c.txt 2>&1
  local rc=$?; log "exit $rc $(date +%H:%M:%S)"; return $rc
}
others() {
  for p in $(pgrep -f "live.py|start_now.sh|run_all.sh|batch.py|rerun.py"); do
    d=$(readlink /proc/$p/cwd 2>/dev/null) || continue
    case $d in */EXPERIMENTS/adr_1525) ;; */EXPERIMENTS/adr_*) echo $p;; esac
  done
}
quiet=0; waited=0
while [ $quiet -lt 120 ] && [ $waited -lt 7200 ]; do
  if [ -z "$(others)" ]; then quiet=$((quiet+15)); else quiet=0; fi
  sleep 15; waited=$((waited+15))
done
if [ $quiet -lt 120 ]; then log "not started: another experiment still running after 2 hours $(date '+%F %T')"; exit 0; fi
log "other experiments quiet for 2 minutes after ${waited}s $(date '+%T')"
for c in doc-liquidity doc-model-code; do
  $PY live.py $c candidate --preflight > $A/log-preflight-$c.txt 2>&1 && grep -q PREFLIGHT_READY $A/log-preflight-$c.txt \
    || { log "preflight failed $c $(date '+%F %T')"; exit 1; }
done
log "now start $(date '+%F %T') pid $$"
cell doc-liquidity
if $PY -c "from common import *;import sys;sys.exit(0 if read(ART/'live/candidate/doc-liquidity/turn-1/result.json')['http_status']==200 else 1)" 2>/dev/null; then
  cell doc-model-code
else
  log "doc-model-code not started: doc-liquidity did not answer HTTP 200 $(date '+%T')"
fi
$PY collect.py > $A/collect.stdout 2>&1; log "collect exit $?"
log ALL_DONE
