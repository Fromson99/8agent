"""Append-only, post-output diagnosis; never read by the product/evaluator."""
from pathlib import Path
import json,time,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization/artifacts';out=A/'GENERALIZATION_DIAGNOSTICS.jsonl';cases={c['case_id']:c for c in json.loads((A/'design/dataset.json').read_text())['cases']}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
seen={json.loads(l)['case_id'] for l in out.read_text().splitlines()} if out.exists() else set()
while True:
 all_results=list(A.glob('run-001/integrated/*/result.json'))
 for p in all_results:
  cid=p.parent.name;g=p.parent/'grade.json'
  if cid in seen or not g.exists():continue
  r=json.loads(p.read_text());grade=json.loads(g.read_text());seen.add(cid)
  if grade['correct']:continue
  row={'case_id':cid,'type':cases[cid]['kind'],'question':cases[cid]['question'],'http_status':r['http_status'],'model_calls':r['model_calls'],'semantic_absolute_gate':False,'grading_reason':grade['reason'],'error':r.get('output',{}).get('code') or r.get('error'),'result':{'path':str(p.relative_to(R)),'sha256':sha(p)},'grade':{'path':str(g.relative_to(R)),'sha256':sha(g)},'product_output_unchanged':True,'next_candidate_requires_new_ADR':True}
  with out.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
  print('RECORDED',cid,row['error'] or row['grading_reason'],flush=True)
 if len(seen)==32:break
 time.sleep(20)
