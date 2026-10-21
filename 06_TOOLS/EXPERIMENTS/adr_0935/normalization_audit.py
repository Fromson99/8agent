"""Offline audit of host normalization receipts; not a legal evaluator."""
from pathlib import Path
import json,sqlite3,collections
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0935-lossless-review-wire'
for P in sorted((A/'artifacts/run-001/fixed').glob('*')):
    if not (P/'audit.json').exists():continue
    target=P/'normalization-audit.json'
    if target.exists():continue
    journal=next((P/'runtime/workflows').glob('*/journal.sqlite'))
    checks=[];counts=collections.Counter();calls=[]
    with sqlite3.connect('file:'+str(journal)+'?mode=ro',uri=True) as db:
        for raw, in db.execute("SELECT payload_json FROM event WHERE kind='WORKFLOW_MECHANICAL_PROJECTION' ORDER BY seq"):
            event=json.loads(raw)
            if event.get('stage')!='ITEMS':continue
            calls.append({'call_id':event['call_id'],'version':event['version'],'normalizations':len(event.get('normalizations',[]))})
            for note in event.get('normalizations',[]):
                rule=note['rule'];counts[rule]+=1
                if rule=='explanation-lines-v1':ok=all(isinstance(s,str) for s in note['original']) and '\n'.join(note['original'])==note['canonical']
                elif rule=='packet-citation-choice-v1':ok=note['canonical_choice']=={'citation_id':note['original']}
                elif rule=='partial-review-patch-v1':ok=set(note['omitted'])<={'content_status','difference','next_tasks'} and note['comparison_if_omitted']=='UNKNOWN' and note['task_plan_if_omitted']=='PRESERVE'
                else:ok=False
                checks.append({'call_id':event['call_id'],'rule':rule,'path':note['path'],'allowed_mechanical_conversion':bool(ok)})
    result={'case_id':P.name,'accepted_review_calls':calls,'rule_counts':dict(counts),'checks':checks,
        'all_conversions_allowed':all(c['allowed_mechanical_conversion'] for c in checks),
        'meaning':'Original representations remain in received model records. Exact original/side/scope checks are separate audit.json and scope receipts. No legal meaning certified.'}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(P.name,dict(counts),'allowed',result['all_conversions_allowed'])
