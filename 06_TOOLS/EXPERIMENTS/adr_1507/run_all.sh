#!/bin/bash
# ADR-1507 driver: the 6 cells one at a time (no other heavy work), then one rerun of each cell whose run
# had a provider failure (unknown/blank/5xx), then the offline collection.
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
# Local SQLite record files commit every row with FULL fsync; the field (DP=oracle) saves once per question.
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
A=$($PY -c "from common import ART;print(ART)")
LIM=$($PY -c "from common import *;l=read(DES/'criteria.json')['limits'];print(l['time_box_minutes'],int(l['ram_start_gib']*1024*1024),l['wait_seconds'])")
read BOX RAMKIB WAITMAX <<<"$LIM"
CELLS=$($PY -c "from common import *;print(' '.join(c['case']+':'+c['arm'] for c in read(DES/'cells.json')))")
start=$(date +%s); fails=0; stop=""
run_cell() {  # case arm [--rerun]
  local waited=0
  while [ $(awk '/MemAvailable/{print $2}' /proc/meminfo) -lt $RAMKIB ] && [ $waited -lt $WAITMAX ]; do sleep 15; waited=$((waited+15)); done
  echo "=== $1 $2 ${3:-} $(date +%H:%M:%S) waited $waited" >> $A/driver.log
  $PY live.py $1 $2 ${3:-} > $A/log-$2-$1${3:+-rerun}.txt 2>&1
  echo "exit $? $(date +%H:%M:%S)" >> $A/driver.log
}
for cell in $CELLS; do
  c=${cell%%:*}; arm=${cell##*:}
  [ -f $A/STOP_ALL.json ] && { stop="operator stop file"; break; }
  [ $(( $(date +%s) - start )) -ge $(( BOX * 60 )) ] && { stop="time box"; break; }
  run_cell $c $arm
  if [ -f $A/live/$arm/$c/turn-1/result.json ]; then fails=0; else fails=$((fails+1)); fi
  [ $fails -ge 2 ] && { stop="two consecutive runner/resource failures before an answer"; break; }
done
if [ -z "$stop" ]; then
  for cell in $CELLS; do
    c=${cell%%:*}; arm=${cell##*:}
    [ -f $A/STOP_ALL.json ] && { stop="operator stop file"; break; }
    [ $(( $(date +%s) - start )) -ge $(( BOX * 60 )) ] && { stop="time box"; break; }
    [ -f $A/live/$arm/$c/STOP_EXTERNAL.json ] && run_cell $c $arm --rerun
  done
fi
echo "STOP: ${stop:-none}" >> $A/driver.log
$PY collect.py > $A/collect.stdout 2>&1; echo "collect exit $?" >> $A/driver.log
echo ALL_DONE >> $A/driver.log
