"""Audit system relation reads against actual successful wire presentation receipts."""
import json,sqlite3,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0497-gemma4-fp8-source-workflow-cm51-fsc10'
def main():
 rows=[]
 for case in json.loads((A/'product-cases.json').read_text())['cases']:
  p=A/'artifacts/run-001'/case['case_id']/'gemma';t=json.loads((p/'trace.json').read_text());ev={e['evidence_id']:e for e in t['evidence']}
  actions={a['action_id']:{**a,'request':json.loads(a['proposed_json']),'result':json.loads(a['result_json']) if a['result_json'] else {}} for a in t['actions']}
  with sqlite3.connect('file:'+str(p/'journal.sqlite')+'?mode=ro',uri=True) as db:
   db.row_factory=sqlite3.Row
   shown={r[0] for r in db.execute("SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'")}
   tasks=[dict(x) for x in db.execute('SELECT * FROM system_task ORDER BY created_seq')]
   views=[json.loads(r[0]) for r in db.execute("SELECT v.body_json FROM model_view v JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'")]
  groups=[]
  for task in tasks:
   op=json.loads(task['operation_json'])
   if op['tool']!='prefetch_decision':continue
   summary=json.loads(task['result_json']) if task['result_json'] else {}
   child_ids={child['task_id'] for child in tasks if child['parent_action_id']==task['parent_action_id'] and child['evidence_id']==task['evidence_id'] and json.loads(child['operation_json'])['tool']=='read'}
   children=[a for ident,a in actions.items() if ident in child_ids]
   eids={e for a in children for e in a['result'].get('evidence_ids',[])}
   groups.append({'anchor':task['evidence_id'],'parent_action':actions[task['parent_action_id']]['request'],
    'decision_status':task['status'],'decision':summary,
    'automatic_read_actions':len(children),'automatic_read_errors':[a['result'] for a in children if a['result']['status'] in ('ERROR','NOT_EXECUTED')],
    'automatic_evidence_count':len(eids),'automatic_evidence_presented':len(eids&shown),'unpresented_automatic_evidence':sorted(eids-shown),
    'automatic_sources':[{'evidence':e,'source_id':ev[e]['source_id'],'heading':ev[e]['metadata'].get('heading'),'chars':len(ev[e]['text']),'presented':e in shown} for e in sorted(eids)]})
  auto=[a for a in actions.values() if a['actor']=='SYSTEM_POLICY' and a['request']['tool']=='read'];auto_ids={a['action_id'] for a in auto}
  recursive=[a['action_id'] for a in actions.values() if a['request']['tool']=='follow_relations' and a['parent_action_id'] in auto_ids]
  rows.append({'case_id':case['case_id'],'groups':groups,'auto_read_count':len(auto),'recursive_auto_scans':recursive,
    'relation_delivery_views':sum(bool(v.get('relation_delivery')) for v in views),'relation_menu_views':sum(bool(v.get('relation_menu')) for v in views),
    'system_continuations_offered':sum(any(n['tool']=='follow_relations' for n in v.get('next_actions',[])) for v in views),
    'all_read_count':len(ev),'all_presented_count':len(set(ev)&shown),'unpresented_evidence':sorted(set(ev)-shown)})
 out={'rows':rows,'note':'Automatic queued/read/presented statuses are distinct. Large/incomplete sets remain selection, not absence. Legal correctness is scored separately.'}
 (A/'artifacts/relations-delivery-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps([{k:x[k] for k in ['case_id','auto_read_count','recursive_auto_scans','relation_delivery_views','all_read_count','all_presented_count']} for x in rows],ensure_ascii=False))
if __name__=='__main__':main()
