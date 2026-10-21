"""Trace audit of durable declared gaps; source relevance is separately reviewed."""
from pathlib import Path
import hashlib,json,sqlite3,collections
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0936-durable-research-review-patch'
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
for P in sorted((A/'artifacts/run-001/fixed').glob('*')):
    if not (P/'audit.json').exists():continue
    journal=next((P/'runtime/workflows').glob('*/journal.sqlite'))
    with sqlite3.connect('file:'+str(journal)+'?mode=ro',uri=True) as db:
        state=json.loads(db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0]);board=state['task_board']
        needs=board.get('research_needs',{});tasks=board['tasks'];checks=[];normalizations=[]
        for inp,out in db.execute("SELECT input_json,result_json FROM workflow_call WHERE kind='model' AND status='COMPLETE' ORDER BY rowid"):
            data=json.loads(inp);value=json.loads(out)
            if data['stage']!='ITEMS':continue
            issue=data['data']['issue']['id']
            for item in value['items']:
                for side in ('internal','external'):
                    row=item.get(side)
                    if not row or not row['missing'].strip():continue
                    ident=digest([issue,item['field'],side]);need=needs.get(ident)
                    checks.append({'issue_id':issue,'field':item['field'],'side':side,'missing':row['missing'],
                        'durable_history':bool(need and any(h.get('missing')==row['missing'] for h in need['history'])),
                        'has_plan_receipt':bool(need and need['task_ids'] and all(i in tasks for i in need['task_ids']))})
        for ident,row in tasks.items():
            receipt=row.get('planning_receipt')
            if not receipt:continue
            normalizations.append({'task_id':ident,'rule':receipt['rule'],
                'exact_declared_gap':any(h.get('missing')==receipt['missing'] for h in needs[receipt['need_id']]['history']),
                'submitted_query_exact':row['task']['missing_target']==receipt['submitted_query'],
                'bounded_search':len(receipt['submitted_query'])<=500 and row['task']['operation']=='search_text' and row['task']['target_locator'] is None,
                'meaning_inferred':receipt['meaning_inferred'],'query_shortened':receipt['query_shortened']})
    body=json.loads((P/'response.json').read_text())['body'];delivered=body.get('research_needs',[])
    states=collections.Counter(n['execution_state'] for n in delivered)
    resolved=[]
    for ident,need in needs.items():
        if need['status']=='RESOLVED':
            event=need['resolution'];resolved.append({'need_id':ident,'has_citation':bool(event['citations']),'history_retained':any(h.get('missing') for h in need['history'])})
    result={'case_id':P.name,'declared_gap_checks':checks,'fallback_plan_checks':normalizations,'resolved_checks':resolved,
        'needs':len(needs),'delivered_needs':len(delivered),'execution_states':dict(states),'task_statuses':dict(collections.Counter(t['status'] for t in tasks.values())),
        'acquisitions_used':board['round'],'within_existing_budget':board['round']<=2,
        'all_declared_gaps_preserved':all(c['durable_history'] and c['has_plan_receipt'] for c in checks),
        'all_fallbacks_mechanical':all(c['exact_declared_gap'] and c['submitted_query_exact'] and c['bounded_search'] and not c['meaning_inferred'] for c in normalizations),
        'all_resolutions_cited':all(c['has_citation'] and c['history_retained'] for c in resolved),
        'no_implicit_plan_cancellation':not any(t['status']=='SUPERSEDED' for t in tasks.values()),
        'all_needs_visible':{n['need_id'] for n in delivered}==set(needs),
        'no_unaccounted_open_need':not states.get('NO_TASK',0),
        'limitation':'Explicit model-declared gaps only. A task receipt is not proof that the source exists, applies, or was found; source-selection and legal applicability remain separate.'}
    (P/'needs-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(P.name,'needs',len(needs),'all_gaps_preserved',result['all_declared_gaps_preserved'],'execution',dict(states))
