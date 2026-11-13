#!/bin/bash
# ADR-1525 deviation 1: doc-model-code again from the start with the fixed runner, then collect.py.
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
A=$($PY -c "from common import ART;print(ART)")
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
echo "=== doc-model-code (rerun after deviation 1) $(date '+%H:%M:%S') free_KiB $(awk '/MemAvailable/{print $2}' /proc/meminfo)" >> $A/driver.log
$PY live.py doc-model-code candidate > $A/log-candidate-doc-model-code.txt 2>&1
echo "exit $? $(date +%H:%M:%S)" >> $A/driver.log
$PY collect.py > $A/collect.stdout 2>&1; echo "collect exit $?" >> $A/driver.log
echo ALL_DONE >> $A/driver.log
