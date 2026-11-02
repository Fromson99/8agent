"""Actual read-only candidate surface check against archived1259 candidate bodies."""
from common import *
gold,C,F=frozen_gold();output=A/'artifacts/oracle-literal-check';output.mkdir(exist_ok=False)
rows=[];start=time.monotonic()
with gold.open_store(documents=['7bbe815ff43b6635'],seconds=300,max_calls=1000) as (store,request,transport):
 g=store.gold_ports.glossary_binding()
 try:
  for n in (3,4):
   old=json.loads(gzip.decompress((R/f'04_EXPERIMENTS/ADR/ADR-1259-wiki-typed-proposal-oracle-live/artifacts/run-001/live/authoring/{n:03d}-input.json.gz').read_bytes()))['context']['glossary_candidates']
   before=request.sql.calls;t=time.monotonic();now=g.candidates([p['label'] for p in old['queries']],exact_only=True)
   old_by_id={c['concept_id']:c for c in old['candidates']}
   assert now['candidates'] and all(c==old_by_id[c['concept_id']] for c in now['candidates'])
   response=json.loads(gzip.decompress((R/f'04_EXPERIMENTS/ADR/ADR-1259-wiki-typed-proposal-oracle-live/artifacts/run-001/live/authoring/{n:03d}-output.json.gz').read_bytes()))
   refs={r['concept_id'] for o in response['observations'] for r in o['glossary_refs']}
   assert refs <= {c['concept_id'] for c in now['candidates']}
   raw(output/f'case-{n}.json.gz',now)
   rows.append({'case':n,'historical_full_candidates':len(old['candidates']),'current_exact_candidates':len(now['candidates']),'retained_body_equal':True,'previous_model_referenced_ids_preserved':True,'unsearched_preserved':now['unsearched'],'sql_calls':request.sql.calls-before,'seconds':time.monotonic()-t})
  put(output/'result.json',{'passed':True,'cases':rows,'source_sql_calls':request.sql.calls,'seconds':time.monotonic()-start,'models':0,'DDL':0,'DML':0,'comparison':'Retained exact source card equality only; historical whole-run time is not a comparable baseline'})
  raw(output/'sql.json.gz',transport.statements);print(json.dumps(rows,ensure_ascii=False))
 finally:g.reader.close()
