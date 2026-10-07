"""Read-only inspection of server offered page actions and actual model use."""
import json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0493-source-continuation-repair'
def main():
 rows=[]
 for arm in ['baseline','repaired']:
  p=A/'artifacts/run-001/cm-018'/arm
  with sqlite3.connect('file:'+str(p/'journal.sqlite')+'?mode=ro',uri=True) as db:
   views={ident:json.loads(body) for ident,body in db.execute('SELECT view_id,body_json FROM model_view')}
   matched=[]
   for ident,v,a in db.execute("SELECT action_id,input_view_id,proposed_json FROM action_context WHERE actor='MODEL'"):
    actual=json.loads(a)
    if any(actual['tool']==n['tool'] and actual['args']==n['args'] for n in views.get(v,{}).get('next_actions',[])):
     matched.append(ident)
   errors=[json.loads(p) for (p,) in db.execute("SELECT payload_json FROM event WHERE kind='WORKFLOW_REPAIR'")]
   cursor_errors=[]
   for record in errors:
    for e in record.get('errors',[]):
     actual=e.get('actual',{});target=actual.get('args',{}).get('target','')
     if len(target)==29 and target.startswith('P'):
      cursor_errors.append({'message':e.get('message'),'corrective_actions':e.get('corrective_actions',[])})
  rows.append({'arm':arm,'views_with_bound_next_actions':sum(bool(v.get('next_actions')) for v in views.values()),'actions_matching_offered_continuation':matched,'cursor_as_target_errors':cursor_errors})
 out={'rows':rows,'note':'Matched action means model submitted the offered tool/args. Absence of an injected error in a live run does not prove live repair; synthetic tests explicitly inject and follow the repair.'}
 (A/'artifacts/continuation-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
