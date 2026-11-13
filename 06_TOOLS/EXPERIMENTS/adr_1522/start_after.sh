#!/bin/bash
# ADR-1522 launcher: start only when no other experiment folder has a running process for 2 minutes
# (another session's ADR-1521 is running), then the embedding server, a CM preflight, and the run (2 workers).
set -u
cd "$(dirname "$0")"
ROOT=/home/jin/8-AGENT
A=$ROOT/04_EXPERIMENTS/ADR/ADR-1522-candidate-cm51-edge20-accuracy/artifacts
PY=$ROOT/.venv/bin/python
others() {
  for p in $(pgrep -f "live.py|start_now.sh|run_all.sh|batch.py|rerun.py"); do
    d=$(readlink /proc/$p/cwd 2>/dev/null) || continue
    case $d in */EXPERIMENTS/adr_1522) ;; */EXPERIMENTS/adr_*) echo $p;; esac
  done
}
echo "waiting $(date +%T)" >> $A/launcher.log
quiet=0; w=0
while [ $quiet -lt 120 ] && [ $w -lt 14400 ]; do
  if [ -z "$(others)" ]; then quiet=$((quiet+20)); else quiet=0; fi
  sleep 20; w=$((w+20))
done
[ $quiet -lt 120 ] && { echo "gave up waiting $(date +%T)" >> $A/launcher.log; exit 0; }
[ -f $A/STOP_ALL.json ] && { echo "stop file" >> $A/launcher.log; exit 0; }
S=$ROOT/09_ARTIFACTS/AUDITS/20261112-main219-cm-all
# MAIN reflection evidence first, while nothing else runs (user 2026-11-12: 실모델 돌려봐 그리고 메인반영 후 삼성으로)
echo "release test $(date +%T)" >> $A/launcher.log
(cd $ROOT && $PY 06_TOOLS/maintenance/main_release.py test --out $S/stage-final --files-from $S/stage-final/regression-files.txt > $S/stage-final/regression.log 2>&1); echo "release test exit $? $(date +%T)" >> $A/launcher.log
(cd $ROOT && $PY 06_TOOLS/maintenance/oracle_scale_guard/run.py --code-root $S/stage-final/staged --out $S/pytest-guard-final > $S/pytest-guard-final.log 2>&1); echo "oracle guard exit $? $(date +%T)" >> $A/launcher.log
mkdir -p $A/embed
cp $ROOT/04_EXPERIMENTS/ADR/ADR-1509-main219-cm-financial-risk-all/artifacts/embed/profile-files.json $A/embed/
(cd $ROOT && setsid nohup $PY 06_TOOLS/EXPERIMENTS/adr_1504/embed_server.py --port 8765 --profile-files $A/embed/profile-files.json --log $A/embed > $A/embed/server.stdout 2>&1 &)
for i in $(seq 1 30); do curl -s 127.0.0.1:8765/health >/dev/null && break; sleep 5; done
echo "embed $(curl -s 127.0.0.1:8765/health) $(date +%T) avail $(awk '/MemAvailable/{print $2}' /proc/meminfo)KiB" >> $A/launcher.log
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
ADR_TARGET=1522 $PY live.py cm-001 --preflight > $A/preflight-cm.log 2>&1 && grep -q PREFLIGHT_READY $A/preflight-cm.log || { echo "cm preflight failed" >> $A/launcher.log; exit 1; }
echo "start $(date +%T)" >> $A/launcher.log
ADR_TARGET=1522 bash run_all.sh > $A/run_all.stdout 2>&1
echo "run_all exit $? $(date +%T)" >> $A/launcher.log
