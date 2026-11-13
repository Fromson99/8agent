#!/bin/bash
# Light status of the ADR-1509 run (reads small JSON files only).
A=/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1518-main219-risk-ext-edge-v2/artifacts
N=${1:-0}; T=${2:-560}
timeout $T bash -c "until [ \$(ls $A/live/*/worker-exit.json 2>/dev/null | wc -l) -ge $N ] || grep -q ALL_DONE $A/driver.log 2>/dev/null; do sleep 20; done"
/home/jin/8-AGENT/.venv/bin/python - <<PY
import json,glob,collections,os
A='$A';rows=[]
for p in sorted(glob.glob(A+'/live/*/worker-exit.json')):
    r=json.load(open(p))
    if 'raw_json' in r: continue
    rows.append(r)
c=collections.Counter((r['kind'],r['http_status']) for r in rows)
print('done',len(rows),dict(c),'unknown',sum(r['unknown'] for r in rows),'calls',sum(r['physical_calls'] for r in rows))
for r in rows[-6:]:print(' ',r['case_id'],r['http_status'],round(r['seconds'] or 0),'s calls',r['physical_calls'],'unk' if r['unknown'] else '','claims',r['claims'])
stops=glob.glob(A+'/live/*/resource-stop.json');print('resource stops',[s.split('/')[-2] for s in stops])
cost=0
for p in glob.glob(A+'/live/*/calls.json'):
    v=json.load(open(p))
    if isinstance(v,dict): continue
    cost+=sum(((c.get('usage') or {}).get('cost') or 0) for c in v)
print('cost',round(cost,3))
PY
ls $A/live | tail -2; free -h | sed -n 2,3p; df -h / /mnt/c | tail -2 | awk '{print $6,$4}'; du -sh $A/live | cut -f1; tail -1 $A/driver.log 2>/dev/null
