"""Post-execution accounting only; never imported by the product."""
from pathlib import Path
import gzip, hashlib, json, sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0795-main72-workflow-comparison'
O=A/'artifacts/live-v2';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(O/'result.json');response=read(O/'response.json');value=response.get('body',{})
p=R/r['journal_root']/'journal.sqlite'
with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    state=json.loads(db.execute('select checkpoint_json from workflow_state').fetchone()[0])
    views=[json.loads(x[0]) for x in db.execute('select body_json from model_view order by created_seq')]
    calls=[dict(x) for x in db.execute('select * from workflow_call')]
    events=[dict(x) for x in db.execute('select kind,payload_json from event order by seq')]
    evidence=[dict(x) for x in db.execute('select evidence_id,source_id,document_id,unit_id from evidence_unit')]
    attempts=[dict(x) for x in db.execute('select a.status,v.body_json from model_attempt a join model_view v using(view_id) order by a.created_seq')]
    budget=dict(db.execute('select * from budget').fetchone())
basis_views=[v for v in views if v.get('source_stage')=='workflow-basis']
compare_views=[v for v in views if v.get('source_stage')=='workflow-compare']
native=value.get('rag_results',{})
checks=dict(r.get('checks',{}))
checks.update(http_ok=response.get('status')==200,
    both_rag_outputs_returned=all(k in native for k in ('internal','external')),
    both_rag_answers_returned=all(native.get(k,{}).get('answer') is not None for k in ('internal','external')),
    both_rag_evidence_returned=all(native.get(k,{}).get('evidence_ids') for k in ('internal','external')),
    both_rag_records_returned=all(native.get(k,{}).get('records') for k in ('internal','external')),
    basis_called=bool(basis_views),compare_called=bool(compare_views),
    compare_model_accepted=any(json.loads(c['input_json']).get('stage')=='COMPARE' and c['status']=='COMPLETE' for c in calls if c['kind']=='model'),
    compare_received_both_exact_outputs=bool(compare_views) and all(compare_views[-1].get('rag_results',{}).get(k)==native.get(k) for k in ('internal','external')),
    nonempty_validated_report_rows=bool(value.get('report',{}).get('rows')),
    reached_normal_report=any(e['kind']=='WORKFLOW_CHECKPOINT' and json.loads(e['payload_json']).get('stage')=='REPORT' for e in events),
    saved_terminal_result=state.get('stage')=='END' and bool(value.get('answer')),
    pointer_and_frozen_code_unchanged=all(sha(R/n)==h for n,h in read(D/'freeze-v2.json')['files'].items()))
rows=value.get('report',{}).get('rows',[]);pairs=value.get('report',{}).get('basis',{}).get('pairs',[])
stages=[dict(stage=json.loads(c['input_json']).get('stage'),status=c['status'],error=json.loads(c['error_json'] or 'null')) for c in calls if c['kind']=='model']
diagnostic={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'run_id':value.get('run_id'),'workflow_status':value.get('status'),'final_stage':state.get('stage'),'error_code':value.get('error_code'),'model_calls':r['model_calls'],'elapsed_seconds':r['elapsed_seconds'],'model_stages':stages,'rag_results':{k:{x:v.get(x) for x in ('status','run_id','assessment','unresolved')}|{'evidence_count':len(v.get('evidence_ids',[])),'record_count':len(v.get('records',[]))} for k,v in native.items()},'basis_pairs':pairs,'comparison_rows':rows,'unresolved':value.get('unresolved'),
    'workflow_stops':[json.loads(e['payload_json']) for e in events if e['kind']=='WORKFLOW_STOPPED'],
    'recoveries':state.get('recovery_count'),'history':state.get('history'),'usage':r['usage'],'budget':budget,
    'consumer_result':r,'source_counts':{s:sum(x.get('side')==s for x in value.get('assembly',{}).get('term_agent',{}).get('source_bundle',{}).get('sources',[])) for s in ('internal','external')},
    'limitations':['One previously observed question, no correctness/generalization certification','Substantive verdicts require original applicability/provenance; deferred rows are not conformance','Actual WSL local selected release only; GENOS not accessed or deployed']}
put(O/'diagnostic.json',diagnostic)

# Frozen stage plan measures delivery to the workflow, not all native search pruning.
m=read(A/'실험/manifest.json');baseline=read(D/'baseline.json');G=R/baseline['manifest']['data_path']
scope=value.get('binding',{}).get('document_ids',[])
with sqlite3.connect('file:'+str(G/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
    data=db.execute('select id,document_id,json_extract(json,\'$.unit_id\') from source where document_id in ('+','.join('?' for _ in scope)+')',scope).fetchall()
source_map={sid:{'doc_id':did,'node':int(uid)} for sid,did,uid in data}
def ids(source_ids):
    values={canon(source_map[s]):source_map[s] for s in source_ids if s in source_map}
    return [values[k] for k in sorted(values)]
eidmap={e['evidence_id']:e['source_id'] for e in evidence}
sets=[ids(source_map),ids(e['source_id'] for e in evidence),ids(eidmap[s['evidence_id']] for v in compare_views for s in v.get('sources',[]) if s['evidence_id'] in eidmap)]
plan=m['design']['retrieval_stage_plan']['stages_by_arm']['baseline'];before=[];stages=[]
for i,after in enumerate(sets):
    bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discard=[bm[k] for k in sorted(bm.keys()-am.keys())]
    reason=['Initial authorized catalogue','Not returned as acquired evidence to parent workflow','Not presented to actual comparison model'][i]
    stages.append({**plan[i],'executed':True,'skip_reason':None, 'before':before,'added':added,'discarded':discard,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discard),'after_count':len(after),'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reason} for x in discard],'discard_reason_counts':{reason:len(discard)} if discard else {},'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]});before=after
case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':'baseline','case_id':'W01','gold_total':0,'gold_identities':[],'stages':stages}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':case['accounting_unit'],'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':'baseline','declared_stage_ids':[s['stage_id'] for s in plan],'cases':[case],'aggregate':{'cases':1,'presented_total':len(sets[-1]),'gold_total':0}}]}],'audit':{'scope':'Observed delivery of authorized article roots to parent workflow and actual comparison model; unchanged native RAG intermediate navigation remains in raw inputs/journals','known_case':True,'semantic_gold_approved':False,'outside_canonical_source_ids':[e['source_id'] for e in evidence if e['source_id'] not in source_map]}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest()
with gzip.open(A/'artifacts/retrieval-ledger.json.gz','wt',encoding='utf-8') as stream:json.dump(ledger,stream,ensure_ascii=False)
put(O/'retrieval-summary.json',{'corpus_total':len(sets[0]),'workflow_acquired':len(sets[1]),'comparison_presented':len(sets[2])})
print(json.dumps({k:diagnostic[k] for k in ('status','checks','workflow_status','final_stage','model_calls','elapsed_seconds')},ensure_ascii=False))
