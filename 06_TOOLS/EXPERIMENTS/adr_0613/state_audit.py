"""Explain state restoration separately from frozen answer-completion scores."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0613-cm-memory-current-state-authority';run=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def main():
 gold=read(A/'artifacts/design/gold.json');rows=[]
 for arm in ('BASELINE','REPAIRED'):
  for case in read(run/arm/'products.json'):
   for target,origin in gold[case['case_id']]['restore_pairs']:
    t=case['turns'][target-1];before=case['turns'][origin-1]
    def state(row):
     session=row['input']['session_id'];goals=[g for g in row['db']['goal'] if g['session']==session]
     return goals[-1]['state'] if goals else None
    x,y=state(before),state(t)
    rows.append({'arm':arm,'case_id':case['case_id'],'target':target,'origin':origin,'origin_has_goal':x is not None,'target_has_goal':y is not None,'facts_equal':x is not None and y is not None and x['facts']==y['facts'],'origin_answer_status':before['output'].get('status'),'target_answer_status':t['output'].get('status'),'origin_facts':x['facts'] if x else None,'target_facts':y['facts'] if y else None})
 out={'type':'post_run_readonly_state_diagnosis','not_a_regrade':True,'note':'Compares DB goal facts at frozen restore pairs; does not substitute this result for answer completion or predeclared state-in-response metric.','restorations':rows};(run/'state-diagnosis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
