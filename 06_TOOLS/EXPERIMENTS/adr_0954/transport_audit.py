"""Post-run diagnostics only; no imports or inputs into product execution."""
from pathlib import Path
from collections import Counter,defaultdict
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0954-risk-photo-forced-graph'
out={}
for p in sorted((A/'artifacts/run-001').glob('*/*/calls.json')):
    rows=json.loads(p.read_text());groups=defaultdict(list)
    for r in rows:groups[r['generation']].append(r)
    receipts=[]
    for number,rs in groups.items():
        rejected=[r['call'] for r in rs if r.get('http_status')==429]
        if not rejected:continue
        success=[r['call'] for r in rs if r.get('http_status')==200]
        receipts.append({'generation':number,'stage':rs[0]['phase'],'rejected_calls':rejected,'received_calls':success,
            'received_after_429':any(s>min(rejected) for s in success),
            'physical_call_numbers':[r['call'] for r in rs]})
    provider_reasons=Counter()
    for f in p.parent.glob('raw/call-*/response.json'):
        d=json.loads(f.read_text());error=d.get('error') or {}
        if error.get('code')==429:
            meta=error.get('metadata') or {};provider_reasons[(meta.get('provider_name'),meta.get('limit_source'))]+=1
    out['/'.join(p.parent.parts[-2:])]={'calls':len(rows),'known_rejected_429':sum(r.get('http_status')==429 for r in rows),
        'received':sum(r.get('http_status')==200 for r in rows),'unknown':sum(r.get('outcome') in (None,'UNKNOWN') for r in rows),
        'retry_generations':receipts,'provider_reasons':[{'provider':k[0],'limit_source':k[1],'count':v} for k,v in provider_reasons.items()]}
(A/'artifacts/transport-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:{n:v[n] for n in ('calls','known_rejected_429','received','unknown')} for k,v in out.items()}))
