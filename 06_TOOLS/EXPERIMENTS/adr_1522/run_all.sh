#!/bin/bash
# ADR-1518 driver: two workers on one queue, then the rerun pass alone, then collect.
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
A=$($PY -c "from common import ART;print(ART)")
ADR_WORKER=1 $PY batch.py > $A/batch-W1.stdout 2>&1 &
W1=$!; echo "W1 $W1 $(date +%T)" >> $A/driver.log; sleep 40
ADR_WORKER=2 $PY batch.py > $A/batch-W2.stdout 2>&1 &
W2=$!; echo "W2 $W2 $(date +%T)" >> $A/driver.log
wait $W1; wait $W2; echo "workers done $(date +%T)" >> $A/driver.log
$PY rerun.py > $A/rerun.stdout 2>&1; echo "rerun exit $?" >> $A/driver.log
$PY collect.py --quiet > $A/collect.stdout 2>&1; echo "collect exit $?" >> $A/driver.log
echo ALL_DONE >> $A/driver.log
