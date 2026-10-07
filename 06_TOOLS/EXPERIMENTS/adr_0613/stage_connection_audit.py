"""Additional post-run connection diagnosis. Does not regrade or modify product outputs."""
import json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0613-cm-memory-current-state-authority';RUN=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def main():
 gold=read(A/'artifacts/design/gold.json');result={}
 for arm in ['BASELINE','REPAIRED']:
  p=read(RUN/arm/'product-result.json');db=sqlite3.connect('file:'+str(RUN/arm/'memory.sqlite')+'?mode=ro',uri=True);nodes={i:json.loads(v) for i,v in db.execute('SELECT id,payload FROM node')};db.close();rows=[]
  for c in p['products']:
   for t in c['turns']:
    o=t['output'];g=next((g for g in t['db']['goal'] if g['id']==o.get('goal_id')),None)
    if g is None:g=next((g for g in reversed(t['db']['goal']) if g['session']==t['input']['session_id']),None)
    parts={h['stage']:nodes[h['node']] for h in t['db']['head'] if g and h['goal']==g['id']}
    read_ids={s['source_id'] for s in parts.get('READ',{}).get('originals',[])};selected=set(parts.get('SELECT',{}).get('final_ids',[]));gs=set(gold[c['case_id']]['decisive_source_ids'])
    folders=[f for f in sorted((RUN/arm/'provider').glob('call-*')) if t['provider_attempt_start']<=int(f.name.split('-')[1])<=t['provider_attempt_end']]
    rows.append({'case_id':c['case_id'],'turn':t['turn'],'status':o.get('status'),'method':o.get('method_id'),'error':o.get('error') or o.get('reason') or o.get('body'),'goal':g['id'] if g else None,'pending':g.get('pending') if g else None,'scope_count':len(g['state']['document_ids']) if g else None,'read_count':len(read_ids),'decisive_read':sorted(read_ids&gs),'decisive_missing':sorted(gs-read_ids),'recall_mode':parts.get('RECALL',{}).get('discovery',{}).get('discovery_mode'),'selector_requested_more':parts.get('SELECT',{}).get('needs_fulltext',False),'selected_count':len(selected),'decisive_selected':sorted(selected&gs),'physical_calls':len(folders),'assessment_repair_calls':[f.name for f in folders if 'memory-assess-repair' in f.name],'format_repair_calls':[f.name for f in folders if 'format-repair' in f.name]})
  result[arm]=rows
 out={'type':'post_run_diagnosis_not_new_grade','gold_visible_to_product':False,'note':'Stage heads after each turn, including last prior successful checkpoints on failed turns; not a claim that those stages ran in that turn.','arms':result}
 (RUN/'connection-diagnosis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
