#!/bin/bash
# After the WSL host restart: finish ADR-1482 with one worker and its reruns, then ADR-1481's cm-049/cm-051.
PY=/home/jin/8-AGENT/.venv/bin/python
A2=$(ls -d /home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1482-*)/artifacts
A1=$(ls -d /home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1481-*)/artifacts
cd /home/jin/8-AGENT/06_TOOLS/EXPERIMENTS/adr_1482
$PY resume_after_restart.py > $A2/resume-after-restart.stdout 2>&1; echo "1482 resume exit $?"
$PY rerun_external.py > $A2/rerun-external.stdout 2>&1; echo "1482 rerun external exit $?"
$PY progress.py > /dev/null
echo "1482 done" > $A2/rest-done.txt
cd /home/jin/8-AGENT/06_TOOLS/EXPERIMENTS/adr_1481
$PY resume_after_restart.py > $A1/resume-after-restart.stdout 2>&1; echo "1481 resume exit $?"
$PY progress.py > /dev/null
echo "1481 cm-049/051 done" > $A1/resume-done.txt
