"""Offline trace audit; never imported by a product runner."""
from pathlib import Path
import json,gzip,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0931-general-research-evidence-update';O=A/'artifacts/run-001'
for p in sorted(O.glob('*/*')):
 if not (p/'audit.json').exists():continue
 target=p/'policy-audit.json'
 if target.exists() and json.loads(target.read_text()).get('audit_version')==2:continue
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
  new=v.get('new_evidence_ids',[]);updates=out.get('evidence_updates',[])
  catalogue={c['citation_id']:s['evidence_id'] for s in v.get('sources',[]) for c in s.get('citation_options',[])}
  bound=[]
  for update in updates:
   ok=update['evidence_id'] in new
   if update['disposition']=='USED':
    for field in update['fields']:
     item=next((r for r in out['items'] if r['field']==field),{})
     ok=ok and any(catalogue.get(c.get('citation_id'))==update['evidence_id'] for side in ('internal','external') for c in item.get(side,{}).get('citations',[]))
   bound.append(ok)
  reviews.append({'number':int(f.name[:3]),'mode':v.get('review_mode','LEGACY'),'requested_fields':list(v.get('fields',{})),
   'returned_fields':[r['field'] for r in out.get('items',[])],'new_evidence_ids':new,'updates':updates,
   'new_ids_exactly_accounted':sorted(new)==sorted(r['evidence_id'] for r in updates),
   'used_update_citations_bound':all(bound),'sources':len(v.get('sources',[])),
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
 result={'audit_version':2,'arm':p.parent.name,'case_id':p.name,'intake':intake,'item_reviews':reviews,'failed_review_attempts':failed,
  'followup_execution':execution,'acquisitions_used':state.get('task_board',{}).get('round'),
  'saved_updates':body.get('evidence_updates',[]),'saved_priorities':body.get('research_priorities',{}),
  'item_validation_failures':body.get('item_validation_failures',[]),
  'all_new_ids_accounted':all(r['new_ids_exactly_accounted'] for r in reviews) and not any(r['new_evidence_ids'] for r in failed),
  'all_used_citations_bound':all(r['used_update_citations_bound'] for r in reviews),
  'incremental_opportunities':len({tuple(r['new_evidence_ids']) for r in reviews+failed if r['new_evidence_ids']}),
  'semantic_accuracy_certified':False}
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(p.parent.name,p.name,'reviews',len(reviews),'update_opportunities',result['incremental_opportunities'])
