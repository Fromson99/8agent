"""Offline audit of host normalization receipts; not a legal evaluator."""
from pathlib import Path
import json,sqlite3,collections,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0936-durable-research-review-patch'
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
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
            captured=db.execute("SELECT a.response_json,a.response_hash FROM model_attempt a JOIN model_view v USING(view_id) WHERE json_extract(v.body_json,'$.workflow_call_id')=? AND a.status='SUCCEEDED' ORDER BY a.created_seq DESC LIMIT 1",(event['call_id'],)).fetchone()
            response=json.loads(captured[0]);assert digest(response)==captured[1]
            original=json.loads(response['body_json']['choices'][0]['message']['content'])
            saved=db.execute('SELECT result_json,result_hash FROM workflow_call WHERE call_id=?',(event['call_id'],)).fetchone()
            value=json.loads(saved[0]);assert digest(value)==saved[1]
            calls.append({'call_id':event['call_id'],'version':event['version'],'normalizations':len(event.get('normalizations',[]))})
            for note in event.get('normalizations',[]):
                rule=note['rule'];counts[rule]+=1
                if rule=='explanation-lines-v1':ok=all(isinstance(s,str) for s in note['original']) and '\n'.join(note['original'])==note['canonical']
                elif rule=='packet-citation-choice-v1':ok=note['canonical_choice']=={'citation_id':note['original']}
                elif rule=='partial-review-patch-v1':ok=set(note['omitted'])<={'content_status','difference','next_tasks'} and note['comparison_if_omitted']=='UNKNOWN' and note['task_plan_if_omitted']=='PRESERVE'
                elif rule=='flat-side-patch-v1':
                    row=original['items'][int(note['path'].split('/')[2])]
                    normalized=next(r for r in value['items'] if r['field']==row['field'])[row['side']]
                    ok=(digest(row)==note['original_hash'] and row['field']==note['field'] and row['side']==note['side']
                        and normalized['status']==row.get('status',row.get('assessment')) and normalized['text']==row.get('text',row.get('finding'))
                        and normalized['missing']==('\n'.join(row['missing']) if isinstance(row['missing'],list) else row['missing']))
                elif rule=='judgment-key-alias-v1':
                    _,_,index,side=note['path'].split('/');row=original['items'][int(index)]
                    body=row if 'side' in row else row[side]
                    normalized=next(r for r in value['items'] if r['field']==row['field'])[side]
                    ok=note['renames']=={'assessment':'status','finding':'text'} and normalized['status']==body['assessment'] and normalized['text']==body['finding']
                else:ok=False
                checks.append({'call_id':event['call_id'],'rule':rule,'path':note['path'],'allowed_mechanical_conversion':bool(ok)})
    result={'case_id':P.name,'accepted_review_calls':calls,'rule_counts':dict(counts),'checks':checks,
        'all_conversions_allowed':all(c['allowed_mechanical_conversion'] for c in checks),
        'meaning':'Original representations remain in received model records. Exact original/side/scope checks are separate audit.json and scope receipts. No legal meaning certified.'}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(P.name,dict(counts),'allowed',result['all_conversions_allowed'])
