#!/bin/bash
# Full run driver: N workers on one queue, then the provider/resource rerun pass.
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
N=${ADR_WORKERS:-2}
# Local SQLite record files commit every row with FULL fsync; the field (DP=oracle) saves once per question.
# Remove that local-only cost so request time and CPU compare with the field path (ADR-1504 probe).
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
A=$($PY -c "from common import ART;print(ART)")
pids=()
for w in $(seq 1 $N); do
  ADR_WORKER=$w $PY batch.py > $A/batch-W$w.stdout 2>&1 &
  pids+=($!)
  sleep 40
done
for p in "${pids[@]}"; do wait $p; done
$PY rerun.py > $A/rerun.stdout 2>&1; echo "rerun exit $?"
$PY collect.py > $A/collect.stdout 2>&1; echo "collect exit $?"
echo ALL_DONE
