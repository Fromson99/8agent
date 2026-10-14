"""Physical attempts are authoritative; upstream errors have no token usage receipt."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0707-grounded-law-title-entry';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());rows=[]
for p in sorted(O.glob('*/*/result.json')):
 v=read(p);usage={u['call']:u for u in v['usage']};calls=[]
 for a in v['attempts']:
  u=usage.get(a['call']);calls.append({**a,'usage':u,'usage_available':u is not None})
 assert len(calls)==v['model_calls']
 rows.append({'arm':v['arm'],'case_id':v['case_id'],'llm_calls':len(calls),'model_seconds':sum(a['seconds'] for a in calls),
   'successful_usage_receipts':len(usage),'failed_attempts':sum(a['status']=='failed' for a in calls),'calls':calls})
v={'contract':'physical-attempt-accounting-v1','cases':rows,'total_calls':sum(r['llm_calls'] for r in rows),
   'failed_attempts':sum(r['failed_attempts'] for r in rows),
   'note':'Frozen initial analyzer counts usage receipts for phase totals; error attempts have no usage receipt. Use this ledger for all physical phase counts/times. Missing error token/cost usage is unknown, not zero. E2E/model_calls in results remain original.'}
(O/'physical-call-ledger.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=A/'실험/manifest.json';m=read(p);m['results']['physical_call_accounting']={'path':str((O/'physical-call-ledger.json').relative_to(R)),'total_calls':v['total_calls'],'failed_attempts':v['failed_attempts'],'all_physical_counts_verified':True,'upstream_error_usage':'unavailable'};p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
print(v['total_calls'],v['failed_attempts'])
