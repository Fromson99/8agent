from pathlib import Path
import json,sqlite3,gzip
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0915-answer-first-followup-provenance';S=A/'artifacts/run-001/retained/cm-001'
read=lambda p:json.loads(p.read_text())
a=read(S/'cm-001/response.json')['body'];b=read(S/'cm-001-followup/response.json')['body']
counts={};reused=[];new=[];prior=[]
for name,body in [('first',a),('followup',b)]:
 paths=list((S/'runtime/legal-agent/runs').glob('*/'+body.get('run_id','NO_RUN')+'/journal.sqlite'))
 assert len(paths)==1,paths
 with sqlite3.connect(paths[0].resolve().as_uri()+'?mode=ro',uri=True) as db:
  db.execute('PRAGMA cache_size=-1024');db.execute('PRAGMA mmap_size=0')
  for ident,tool in db.execute('SELECT observation_id,tool FROM observation ORDER BY created_seq'):
   counts[name+':'+tool]=counts.get(name+':'+tool,0)+1
   rows=[{'source_id':sid,'text_hash':h} for sid,h in db.execute('SELECT source_id,text_hash FROM evidence_unit JOIN observation_evidence USING(evidence_id) WHERE observation_id=?',(ident,))]
   if name=='first':prior.extend(rows)
   elif tool=='case_evidence_rebind' and counts[name+':'+tool]==1:reused.extend(rows)
   elif tool.startswith('read'):new.extend(rows)
keys=lambda xs:{(v['source_id'],v['text_hash']) for v in xs}
with gzip.open(S/'cm-001-followup/canonical/002-output.json.gz','rt') as f:command=json.load(f)
out={'same_goal_and_prior_evidence':bool(a.get('goal_id')==b.get('goal_id') and a.get('goal_id') and reused and keys(reused)<=keys(prior)),
 'initial_goal':a.get('goal_id'),'followup_goal':b.get('goal_id'),'command_method':command.get('method_id'),'observation_counts':counts,
 'reused_prior_source_fragments':len(keys(reused)),'new_source_fragments':len(keys(new)-keys(prior)),
 'reused_fragments':sorted(keys(reused)),'new_fragments':sorted(keys(new)-keys(prior)),
 'reuse_basis':'First verified rebind before any follow-up reads; later reentry also rebinds newly acquired current-turn evidence and is not counted as prior-turn reuse.',
 'model_calls_extra_evaluator':0,'source_exactness':'Per-turn observe.py audit independently checks original source hash/span.'}
(A/'artifacts/followup-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('reused_fragments','new_fragments')},ensure_ascii=False))
