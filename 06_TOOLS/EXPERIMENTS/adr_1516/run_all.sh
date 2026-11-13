#!/bin/bash
# ADR-1516 driver: worker 1 now (beside another session's ADR-1515 cells); worker 2 joins once no other session's
# experiment process has run for 2 minutes (ADR-1515 finished). Then the rerun pass alone, then collect.
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
A=$($PY -c "from common import ART;print(ART)")
others() {  # processes of another experiment folder (cwd under 06_TOOLS/EXPERIMENTS/adr_*, not ours)
  for p in $(pgrep -f "live.py|start_now.sh|run_all.sh|batch.py"); do
    d=$(readlink /proc/$p/cwd 2>/dev/null) || continue
    case $d in */EXPERIMENTS/adr_1516) ;; */EXPERIMENTS/adr_*) echo $p;; esac
  done
}
ADR_WORKER=1 $PY batch.py > $A/batch-W1.stdout 2>&1 &
W1=$!; echo "W1 $W1 $(date +%T)" >> $A/driver.log
quiet=0; W2=""
while kill -0 $W1 2>/dev/null; do
  if [ -z "$(others)" ]; then quiet=$((quiet+30)); else quiet=0; fi
  if [ $quiet -ge 120 ]; then
    ADR_WORKER=2 $PY batch.py > $A/batch-W2.stdout 2>&1 &
    W2=$!; echo "W2 $W2 $(date +%T) (no other experiment for 2 minutes)" >> $A/driver.log; break
  fi
  sleep 30
done
wait $W1; [ -n "$W2" ] && wait $W2
echo "workers done $(date +%T)" >> $A/driver.log
$PY rerun.py > $A/rerun.stdout 2>&1; echo "rerun exit $?" >> $A/driver.log
$PY collect.py --quiet > $A/collect.stdout 2>&1; echo "collect exit $?" >> $A/driver.log
echo ALL_DONE >> $A/driver.log
