"""Read-only progress; no runtime mutation, model call or retries."""
from pathlib import Path
import json,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0840-comparison-source-handoff/artifacts/run-001'
for c in sorted(A.iterdir()):
 if not c.is_dir():continue
 raw=sorted((c/'raw').glob('call-*'));out={'case':c.name,'calls':len(raw),'last_call':raw[-1].name if raw else None,'journals':[]}
 if (c/'result.json').exists():
  v=json.loads((c/'result.json').read_text());out['result']={k:v.get(k) for k in ('http_status','status','model_calls','elapsed_seconds','error','message')}
 for p in (c/'runtime').rglob('journal.sqlite'):
  try:
   db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=1);db.row_factory=sqlite3.Row;row=db.execute('select status,phase from run').fetchone()
   x={'side':next((s for s in ('internal','external') if s in p.parts),'parent'),'state':dict(row) if row else None,'evidence':db.execute('select count(*) from evidence_unit').fetchone()[0]}
   x['last_event']=[dict(v) for v in db.execute('select kind from event order by seq desc limit 1')]
   out['journals'].append(x);db.close()
  except sqlite3.OperationalError:x={'unavailable':str(p)}
 print(json.dumps(out,ensure_ascii=False))
