#!/bin/bash
# After the session time limit: finish ADR-1481 reruns, then ADR-1482 (detached with nohup).
PY=/home/jin/8-AGENT/.venv/bin/python
A=$(ls -d /home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1481-*)/artifacts
cd /home/jin/8-AGENT/06_TOOLS/EXPERIMENTS/adr_1481
$PY rerun_continue.py '["cm-035","cm-047","cm-048"]' >> $A/rerun.stdout 2>&1
$PY rerun_external.py > $A/rerun-external.stdout 2>&1
$PY progress.py > /dev/null
echo "1481 reruns done" > $A/rest-done.txt
/home/jin/8-AGENT/06_TOOLS/EXPERIMENTS/adr_1482/run_all.sh > $(ls -d /home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1482-*)/artifacts/run_all.log 2>&1
echo "1482 done" > $(ls -d /home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1482-*)/artifacts/rest-done.txt
