#!/bin/bash
# ADR-1511 start: starts nothing (not even the model-free preflight) while a driver, batch or live process of another
# experiment runs (ADR-1509 of another session was running at freeze time). When none has run for 10 minutes in a
# row: the model-free preflight of two cases (both generations), then run_all.sh (3 cells, rerun, collect).
# The operator stop file stops the wait. Every check is logged to artifacts/start.log.
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
A=$($PY -c "from common import ART;print(ART)")
others() {  # pids of other experiments' drivers/batches/live cells (by working folder or command line)
  for pid in $(pgrep -f 'run_all.sh|batch.py|live.py|rerun.py'); do
    cwd=$(readlink /proc/$pid/cwd 2>/dev/null); cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
    case "$cwd $cmd" in *adr_1511*) continue;; esac
    case "$cwd $cmd" in *06_TOOLS/EXPERIMENTS/adr_*) echo -n "$pid ";; esac
  done
}
echo "start $(date '+%F %T') pid $$" >> $A/start.log
quiet=0; last=""
while [ $quiet -lt 600 ]; do
  [ -f $A/STOP_ALL.json ] && { echo "operator stop $(date '+%F %T')" >> $A/start.log; exit 0; }
  busy=$(others)
  if [ -n "$busy" ]; then
    quiet=0; [ "$busy" != "$last" ] && echo "waiting $(date '+%F %T') other experiment pids: $busy" >> $A/start.log; last=$busy
  else
    quiet=$((quiet+30))
  fi
  sleep 30
done
echo "no other experiment for 10 minutes $(date '+%F %T'); preflight" >> $A/start.log
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
for c in cmp-liquidity cmp-riskcommittee; do
  $PY live.py $c candidate --preflight > $A/log-preflight-$c.txt 2>&1 || { echo "preflight failed $c $(date '+%F %T')" >> $A/start.log; exit 1; }
  grep -q PREFLIGHT_READY $A/log-preflight-$c.txt || { echo "preflight not ready $c" >> $A/start.log; exit 1; }
done
unset LD_PRELOAD
echo "preflight ready $(date '+%F %T'); run_all.sh" >> $A/start.log
bash run_all.sh
echo "run_all exit $? $(date '+%F %T')" >> $A/start.log
