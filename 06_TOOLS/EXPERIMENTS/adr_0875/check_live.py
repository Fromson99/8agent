from pathlib import Path
import json,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0875-bounded-followup-live';O=A/'artifacts/run-001/committee-comparison'
read=lambda p:json.loads(p.read_text());digest=lambda v:hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
a=read(O/'audit.json');run=read(O/'result.json');calls=read(O/'calls.json')
p=next((O/'runtime/workflows').glob('*/journal.sqlite'));db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
state=json.loads(db.execute('select checkpoint_json from workflow_state').fetchone()[0]);board=state['task_board'];rows=[];physical={}
for rec in board['tasks'].values():
 ident=rec.get('result_request_id');t=rec['task'];v={'task_id':t['task_id'],'side':t['target_side'],'operation':t['operation'],'query':t['missing_target'],'status':rec['status'],'request_id':ident,'new_evidence':rec.get('new_evidence',[]),'reused':rec.get('reused_acquisition',False)}
 if ident:
  call=db.execute('select result_json from workflow_call where call_id=?',(ident,)).fetchone();result=json.loads(call[0]);owner=rec.get('acquisition_task_id',t['task_id']);receipt=result.get('investigation_return',{}).get('research_tasks',{}).get(owner,{})
  v['receipt_status']=receipt.get('status');v['lookup_status']=(receipt.get('lookup') or {}).get('status');v['task_hash_bound']=receipt.get('task_hash')==digest(board['tasks'][owner]['task'])
  physical.setdefault(ident,rec)
 rows.append(v)
checks={'end_to_end_comparison':run['http_status']==200 and run['status'] in ('completed','partial') and a['rows']>=1 and state['stage']=='END',
 'both_source_sides_returned':all(a['children'].get(s,{}).get('returned_evidence_ids') for s in ('internal','external')),
 'original_spans_exact':bool(a['evidence_span_checks']) and all(x['exact_original_match'] for x in a['evidence_span_checks']),
 'saved_duplicate_without_new_calls':all(run['checks'].values()),
 'all_wire_schemas_valid':all(c['schemas_valid'] for c in calls),
 'complete_requires_exact_receipt':all(r.get('receipt_status')=='COMPLETE' and r.get('task_hash_bound') for r in rows if r['status']=='COMPLETE'),
 'existing_acquisition_cap':board['round']<=2 and len(physical)<=2,
 'partial_receipts_kept_partial':all(r['status']=='PARTIAL' for r in rows if r.get('receipt_status')=='PARTIAL'),
 'no_distinct_pending_starvation':not(board['round']<2 and any(r['status']=='PENDING' for r in rows) and any(r.get('receipt_status')=='PARTIAL' and not r['new_evidence'] for r in rows)),
 'active_MAIN83_unchanged':run['active_pointer_unchanged'],
 'within_combined_model_ceiling':8+run['model_calls']<=40}
value={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'acquisition_rounds':board['round'],'unique_acquisition_requests':len(physical),'task_receipts':rows,'physical_model_calls':run['model_calls'],'prior_model_calls':8,'combined_model_calls':8+run['model_calls'],'semantic_quality_certified':False,'genos_executed':False}
(A/'artifacts/live-contract-checks.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':value['status'],'checks':checks,'rounds':board['round'],'tasks':[{k:r.get(k) for k in ('side','status','receipt_status','lookup_status','reused')} for r in rows]},ensure_ascii=False))
assert all(checks.values()),checks
