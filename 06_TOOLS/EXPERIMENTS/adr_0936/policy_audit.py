"""Offline trace audit; never imported by a product runner."""
from pathlib import Path
import json,gzip,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0936-durable-research-review-patch';O=A/'artifacts/run-001'
def grouped_items(items):
 # Audit wire representation independently of the product normalizer.
 grouped={}
 for raw in items:
  row=dict(raw)
  if 'side' in row:
   side=row.pop('side');body={k:row.pop(k) for k in ('status','text','assessment','finding','citations','missing') if k in row}
   row[side]=body
  field=row['field'];target=grouped.setdefault(field,{'field':field})
  for k,v in row.items():
   if k in ('internal','external'):assert k not in target
   target[k]=v
 return list(grouped.values())
for p in sorted(O.glob('*/*')):
 if p.parent.name!='fixed':continue
 if not (p/'audit.json').exists():continue
 target=p/'policy-audit.json'
 if target.exists() and json.loads(target.read_text()).get('audit_version')==3:continue
 if target.exists():target.rename(p/'policy-audit-v1.json')
 reviews=[];failed=[];intake=None
 for f in sorted((p/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  v=json.load(gzip.open(f,'rt'))['view'];output=f.with_name(f.name.replace('.json.gz','-output.json.gz'))
  stage=v.get('source_stage')
  if not output.exists():
   if stage=='workflow-items':failed.append({'number':int(f.name[:3]),'mode':v.get('review_mode','LEGACY'),'new_evidence_ids':v.get('new_evidence_ids',[]),'repair':v.get('repair')})
   continue
  out=json.load(gzip.open(output,'rt'))
  if stage=='workflow-intake':intake=out
  if stage!='workflow-items':continue
  out['items']=grouped_items(out['items'])
  new=v.get('new_evidence_ids',[]);updates=out.get('evidence_updates',[])
  catalogue={c['citation_id']:s['evidence_id'] for s in v.get('sources',[]) for c in s.get('citation_options',[])}
  bound=[];host_fields={}
  for update in updates:
   ok=update['evidence_id'] in new
   fields=[item['field'] for item in out['items'] if any(catalogue.get((c if isinstance(c,str) else c.get('citation_id')))==update['evidence_id'] for side in ('internal','external') for c in item.get(side,{}).get('citations',[]))]
   host_fields[update['evidence_id']]=fields
   if update['disposition']=='USED':
    for field in fields:
     item=next((r for r in out['items'] if r['field']==field),{})
     ok=ok and any(catalogue.get((c if isinstance(c,str) else c.get('citation_id')))==update['evidence_id'] for side in ('internal','external') for c in item.get(side,{}).get('citations',[]))
   bound.append(ok)
  reviews.append({'number':int(f.name[:3]),'mode':v.get('review_mode','LEGACY'),'requested_fields':list(v.get('fields',{})),
   'returned_fields':[r['field'] for r in out.get('items',[])],'new_evidence_ids':new,'updates':updates,
   'new_ids_exactly_accounted':sorted(new)==sorted(r['evidence_id'] for r in updates),
   'used_update_citations_bound':all(bound),'sources':len(v.get('sources',[])),
   'host_expected_fields':host_fields,
   'host_fields_absent_from_wire':all(not {'fields','declared_disposition','binding_note'} & set(u) for u in updates),
   'next_tasks':[t for r in out.get('items',[]) for t in r.get('next_tasks',[])]})
 body=json.loads((p/'response.json').read_text()).get('body',{}) if (p/'response.json').exists() else {}
 journal=next((p/'runtime/workflows').glob('*/journal.sqlite'))
 with sqlite3.connect('file:'+str(journal)+'?mode=ro',uri=True) as db:
  state=json.loads(db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0]);tasks=state.get('task_board',{}).get('tasks',{})
  execution=[]
  for raw, in db.execute("SELECT input_json FROM workflow_call WHERE kind='rag' ORDER BY rowid"):
   action=json.loads(raw);task=action.get('args',{}).get('task',{}).get('research_task')
   if task:execution.append({'task_id':task['task_id'],'side':task['target_side'],'fields':task['requested_fields'],
     'priority':tasks.get(task['task_id'],{}).get('priority'),'priority_reason':tasks.get(task['task_id'],{}).get('priority_reason'),
     'target':task.get('target_locator'),'query':task['missing_target']})
 receipts=[]
 for review in reviews:
  for update in review['updates']:
   expected=review['host_expected_fields'][update['evidence_id']]
   matches=[u for u in body.get('evidence_updates',[]) if u['evidence_id']==update['evidence_id'] and u.get('origin')!='SYSTEM_FAILURE']
   normalized=update['disposition']=='USED' and not expected
   ok=any(u['fields']==expected and u['reason']==update['reason'] and u['disposition']==('UNRESOLVED' if normalized else update['disposition']) and (not normalized or u.get('declared_disposition')=='USED' and u.get('binding_note')) for u in matches)
   receipts.append({'call':review['number'],'evidence_id':update['evidence_id'],'host_fields_match':bool(ok),'uncited_used_preserved':normalized})
 delivered={i for r in reviews+failed for i in r['new_evidence_ids']}
 result={'audit_version':3,'arm':p.parent.name,'case_id':p.name,'intake':intake,'item_reviews':reviews,'failed_review_attempts':failed,
  'followup_execution':execution,'acquisitions_used':state.get('task_board',{}).get('round'),
  'saved_updates':body.get('evidence_updates',[]),'saved_priorities':body.get('research_priorities',{}),
  'item_validation_failures':body.get('item_validation_failures',[]),
  'all_new_ids_accounted':all(r['new_ids_exactly_accounted'] for r in reviews) and not any(r['new_evidence_ids'] for r in failed),
  'all_used_citations_bound':all(r['used_update_citations_bound'] for r in reviews),
  'host_receipt_checks':receipts,'all_host_receipts_match':all(r['host_fields_match'] for r in receipts),
  'all_delivered_ids_have_terminal_receipt':delivered<={r['evidence_id'] for r in body.get('evidence_updates',[])},
  'incremental_opportunities':len({tuple(r['new_evidence_ids']) for r in reviews+failed if r['new_evidence_ids']}),
  'semantic_accuracy_certified':False}
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(p.parent.name,p.name,'reviews',len(reviews),'update_opportunities',result['incremental_opportunities'])
