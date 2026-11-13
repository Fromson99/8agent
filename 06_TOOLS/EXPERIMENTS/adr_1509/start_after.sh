#!/bin/bash
# ADR-1509 launcher: wait for another session's live run (ADR-1510 run_all.sh, PID given) to end, so the two
# real-model runs never overlap on this RAM-limited host, then start this run (2 workers).
set -u
cd "$(dirname "$0")"
A=/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1509-main219-cm-financial-risk-all/artifacts
WAIT_PID=$1
echo "waiting for PID $WAIT_PID $(date +%H:%M:%S)" >> $A/launcher.log
while kill -0 $WAIT_PID 2>/dev/null; do sleep 20; done
# Any other experiment live.py still running (another session)? wait for it too (max 2 h).
w=0
while pgrep -f "EXPERIMENTS/adr_1[0-9]*|live.py" | grep -v -w $$ | xargs -r -I{} readlink /proc/{}/cwd 2>/dev/null | grep -v adr_1509 | grep -q EXPERIMENTS && [ $w -lt 7200 ]; do sleep 30; w=$((w+30)); done
echo "start $(date +%H:%M:%S) other-wait $w avail $(awk '/MemAvailable/{print $2}' /proc/meminfo)KiB" >> $A/launcher.log
[ -f $A/STOP_ALL.json ] && { echo "stop file, not started" >> $A/launcher.log; exit 0; }
ADR_TARGET=1509 ADR_WORKERS=2 bash run_all.sh > $A/run_all.stdout 2>&1
echo "run_all exit $? $(date +%H:%M:%S)" >> $A/launcher.log
