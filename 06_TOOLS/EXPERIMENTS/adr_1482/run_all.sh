#!/bin/bash
# ADR-1482 driver: two workers on one queue, then the frozen single rerun of resource-stopped questions.
set -u
A=/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1482-main187-r5-fixes-answer-r8-cm50-qwen-run2/artifacts
PY=/home/jin/8-AGENT/.venv/bin/python
cd "$(dirname "$0")"
ADR_WORKER=1 $PY batch.py > $A/batch-W1.stdout 2>&1 &
W1=$!
python3 -c "import time;time.sleep(20)"
ADR_WORKER=2 $PY batch.py > $A/batch-W2.stdout 2>&1 &
W2=$!
wait $W1; echo "W1 exit $?"
wait $W2; echo "W2 exit $?"
$PY rerun.py > $A/rerun.stdout 2>&1; echo "rerun exit $?"
$PY rerun_external.py > $A/rerun-external.stdout 2>&1; echo "rerun external exit $?"
$PY progress.py
