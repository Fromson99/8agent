"""Read-only post-selection accounting; no evaluator input reaches product."""
from pathlib import Path
import json,hashlib,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0806-host-owned-generation-fields'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def coords(rows):
 d={canon({'doc_id':did,'node':int(uid)}):{'doc_id':did,'node':int(uid)} for did,uid in rows if uid is not None}
 return [d[k] for k in sorted(d)]

def extract(adr):
 O=adr/'artifacts/live';result=read(O/'result.json')
 root=R/result['journal_root'] if result.get('journal_root') else next((O/'runtime/workflows').iterdir())
 if (O/'response.json').exists():v=read(O/'response.json')['body']
 else:
  with sqlite3.connect('file:'+str(root/'journal.sqlite')+'?mode=ro',uri=True) as db:
   state=json.loads(db.execute('select checkpoint_json from workflow_state').fetchone()[0])
  v={'status':'stopped_known_defect','error_code':'WIRE_REQUIRED_FIELD_OMISSION','rag_results':state.get('rag_results',{}),
     'report':{'rows':[]},'evidence_refs':[],'unresolved':['Stopped repeated known wire defect; no final response was published.']}

 with sqlite3.connect('file:'+str(root/'journal.sqlite')+'?mode=ro',uri=True) as db:
  parent={e:(d,u) for e,d,u in db.execute('select evidence_id,document_id,unit_id from evidence_unit')}
  events=[(k,json.loads(p)) for k,p in db.execute('select kind,payload_json from event order by seq')]
 allrows=[];seed=[];child=[]
 for p in root.glob('children/*/legal-agent/**/journal.sqlite'):
  with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
   rows=db.execute('select document_id,unit_id from evidence_unit').fetchall();allrows.extend(rows)
   ev=[(k,json.loads(j)) for k,j in db.execute('select kind,payload_json from event order by seq')]
   for k,j in ev:
    if k=='UNIT_READ_CHOICE' and j.get('reason','').startswith('시스템: 질문의 정의 원문'):
     seed.append((j['document_id'],j['offer']['unit_id']))
   child.append({'path':str(p.relative_to(R)),'read_units':len(coords(rows)),
    'system_seed_events':sum(k=='SYSTEM_DEFINITION_ORIGINALS_ACQUIRED' for k,_ in ev),
    'composition_model_calls':[j.get('model_call') for k,j in ev if k=='COMPOSITION_RENDERED'],
    'navigation_projections':sum(k=='NAVIGATION_MECHANICAL_PROJECTION' for k,_ in ev)})
 adopted=[i for r in v.get('rag_results',{}).values() for i in r.get('evidence_ids',[])]
 sets=[coords(seed),coords(allrows),coords(parent[i] for i in adopted),coords(parent[i] for i in v.get('evidence_refs',[]))]
 calls=[]
 for p in sorted((O/'raw').glob('call-*/response.json')):
  x=read(p);calls.append({'call':p.parent.name,'model':x.get('model'),'provider':x.get('provider'),'finish':x.get('choices',[{}])[0].get('finish_reason')})
 summary={'status':v.get('status'),'error_code':v.get('error_code'),'model_calls':result['model_calls'],
   'seconds':result['elapsed_seconds'],'rows':v.get('report',{}).get('rows',[]),
   'evidence_summary':v.get('evidence_summary'),'unresolved':v.get('unresolved'),
   'children':child,'system_comparison_gates':sum(k=='WORKFLOW_COMPARISON_GATE' for k,_ in events),
   'workflow_citation_projections':sum(k=='WORKFLOW_MECHANICAL_PROJECTION' for k,_ in events),
   'physical_calls':calls,'coordinates':sets,'both_child_statuses':{k:r['status'] for k,r in v.get('rag_results',{}).items()},
   'quality_certified':False,'genos_changed':False}
 return sets,summary

m=read(A/'실험/manifest.json');plans=m['design']['retrieval_stage_plan']['stages_by_arm']
measure={a:extract(adr) for a,adr in [('baseline',R/'04_EXPERIMENTS/ADR/ADR-0805-mechanical-wire-coverage'),('connected',A)]}
corpus=len({canon(x) for sets,_ in measure.values() for x in sets[1]});arms=[];metrics={k:{} for k in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')}
for arm,(sets,summary) in measure.items():
 before=[];stages=[]
 for i,after in enumerate(sets):
  bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discard=[bm[k] for k in sorted(bm.keys()-am.keys())]
  reason=['Verified definition-source read not yet acquired','Not among successful actual acquisitions','Not adopted by the committed current child judgments','Not cited in final verified comparison rows'][i]
  stages.append({**plans[arm][i],'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discard,'after':after,
    'before_count':len(before),'added_count':len(added),'discarded_count':len(discard),'after_count':len(after),
    'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
    'discard_receipts':[{'identity':x,'reason':reason} for x in discard],'discard_reason_counts':{reason:len(discard)} if discard else {},
    'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,
    'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]});before=after
 case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
   'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':'K01','gold_total':0,'gold_identities':[],'stages':stages}
 arms.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in plans[arm]],'cases':[case],
              'aggregate':{'cases':1,'presented_total':len(sets[-1]),'gold_total':0}})
 metrics['before_filter'][arm]=len(sets[1]);metrics['after_filter'][arm]=len(sets[2])
 for k in ('presented_total','presented_mean','presented_p50','presented_p95'):metrics[k][arm]=len(sets[-1])
 metrics['golden_recall'][arm]=None;metrics['selectivity'][arm]=len(sets[-1])/corpus
 put(A/('artifacts/'+arm+'-observation.json'),summary)
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
 'accounting_unit':case['accounting_unit'],'computed_post_selection':True,'gold_visible_to_product':False,
 'runs':[{'run_id':'run-001','arms':arms}],
 'audit':{'scope':'System seed -> successful reads -> current adopted -> final report; detailed native search navigation in immutable model inputs and child journals',
 'denominator':'Union of actually acquired coordinates in archived and new observed runs, not full corpus','legal_gold_approved':False,'causal_quality_or_latency_comparison':False}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();p=A/'artifacts/run-001/retrieval-ledger.json';put(p,ledger)
m['retrieval_accounting'].update(changed=True,corpus_total=corpus,not_applicable_reason=None,**metrics)
m['retrieval_accounting']['stage_ledger']['sha256']=sha(p);put(A/'실험/manifest.json',m)
print(json.dumps({'observations':{a:{k:s[k] for k in ('status','model_calls','seconds','evidence_summary','system_comparison_gates')} for a,(_,s) in measure.items()},'counts':metrics},ensure_ascii=False))
