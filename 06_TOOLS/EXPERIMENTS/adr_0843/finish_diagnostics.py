"""Post-run checkpoint audit, separate from all product inputs."""
from pathlib import Path
from collections import Counter
import json,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0843-main80-live-comparison';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
summary={}
for case in read(A/'artifacts/design/cases.json'):
 c=O/case['id'];assert (c/'result.json').exists() and (c/'audit.json').exists();p=next((c/'runtime').glob('workflows/*/journal.sqlite'))
 db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;r=db.execute('select status,checkpoint_json from workflow_state').fetchone();s=json.loads(r['checkpoint_json']);tasks=list(s.get('task_board',{}).get('tasks',{}).values());events=[]
 for e in db.execute("select seq,kind,payload_json from event where kind like '%REJECT%' or kind like '%FAIL%' or kind like '%ERROR%' order by seq"):
  events.append({**dict(e),'payload':json.loads(e['payload_json'])});events[-1].pop('payload_json')
 v={'case_id':case['id'],'workflow_status':r['status'],'last_stage':s['stage'],'last_rag_attempts':s.get('rag_attempts',{}),'research_round':s.get('task_board',{}).get('round'),'task_counts':dict(Counter(t['status'] for t in tasks)),'tasks':tasks,'completed_task_zero_new_evidence':sum(t['status']=='COMPLETE' and not t.get('new_evidence') for t in tasks),'new_evidence_total':sum(len(t.get('new_evidence',[])) for t in tasks),'item_rejected_proposals':s.get('task_board',{}).get('rejected_proposals',[]),'parent_failure_events':events,'comparison':s.get('comparison'),'basis':s.get('basis')}
 (c/'checkpoint-audit.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');db.close();summary[case['id']]={k:v[k] for k in ('workflow_status','last_stage','task_counts','completed_task_zero_new_evidence','new_evidence_total')}
print(json.dumps(summary,ensure_ascii=False,indent=2))
