"""Post-hoc trace observations only; no quality regrade or product calls."""
import json,sqlite3
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0503-gemma-obligations-bound-paired-probe'
def read(p):return json.loads(p.read_text())
def main():
 products=read(A/'artifacts/run-001/results.json');cases=[]
 for cid,arms in products['cases'].items():
  for arm,row in arms.items():
   root=A/'artifacts/run-001'/cid/arm;calls=[]
   with sqlite3.connect('file:'+str(root/'journal.sqlite')+'?mode=ro',uri=True) as db:
    phases=[dict(zip(['phase','status'],x)) for x in db.execute('SELECT phase,status FROM model_view JOIN model_attempt USING(view_id)')]
   for p in sorted((root/'calls').glob('call-*')):
    if not (p/'response.json').exists():continue
    raw=read(p/'response.json')
    try:output=json.loads(raw['choices'][0]['message']['content'])
    except (KeyError,IndexError,TypeError,ValueError):continue
    entry={'call':p.name,'provider':raw.get('provider'),'model':raw.get('model')}
    if output.get('question_plan'):
     entry['plan']=output['question_plan'];entry['requirement_lengths']=[len(x['requirement']) for x in output['question_plan']['demands']]
    if 'paragraphs' in output:entry['draft']={'paragraphs':output['paragraphs'],'other_fields':{k:v for k,v in output.items() if k!='paragraphs'}}
    if 'obligation_checks' in output:entry['obligation_checks']=output['obligation_checks']
    if 'checks' in output:entry['checks']=output['checks'];entry['question']=output.get('question')
    calls.append(entry)
   trace=read(root/'trace.json');plans=[c for c in calls if 'plan' in c];requirements=[n for c in plans for n in c['requirement_lengths']]
   cases.append({'case_id':cid,'arm':arm,'final_result_available':bool(row.get('result')),'technical_error':row['error'],'phases':phases,'plans_emitted':len(plans),'requirement_lengths':requirements,'all_requirements_one_character':bool(requirements) and all(n==1 for n in requirements),'semantic_errors':trace.get('errors',[]),'calls':calls})
 result={'kind':'post_hoc_descriptive_trace_audit','no_new_calls':True,'not_a_regrade':True,'scope':'Observed plans, drafts and checks, including before an incomplete run; not final-answer quality claims','by_case':cases,'candidate_cases_with_plan':sum(x['arm']=='obligations' and x['plans_emitted']>0 for x in cases),'candidate_cases_all_requirements_one_character':sum(x['arm']=='obligations' and x['all_requirements_one_character'] for x in cases)}
 (A/'artifacts/trace-diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='by_case'},ensure_ascii=False))
if __name__=='__main__':main()
