"""Post-run trace and retrieval accounting only. Never sends model requests."""
import json,hashlib,sqlite3,statistics,importlib.util
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0505-gemma-numbered-three-case-probe'
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 product=read(A/'product-cases.json');gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']};res=read(A/'artifacts/run-001/results.json');m=read(A/'실험/manifest.json')
 spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
 with sqlite3.connect('file:'+str(R/product['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
  coords={s:{'doc_id':d,'node':int(u)} for s,d,u in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if str(u).isdigit()}
 corpus=len({h.key(v) for v in coords.values() if v['doc_id'] in product['public_scope_document_ids']});cases=[];summary=[]
 for case in product['cases']:
  cid=case['case_id'];row=res['cases'][cid]['numbered'];base=A/'artifacts/run-001'/cid/'numbered';g=h.ordered(coords[x] for x in gold[cid]['decisive_source_ids']);stages=[];prev=[]
  for st in m['design']['retrieval_stage_plan']['stages_by_arm']['numbered']:
   after=h.ordered(coords[x] for x in row.get('stages',{}).get(st['stage_id'],[]) if x in coords);bk={h.key(x) for x in prev};ak={h.key(x) for x in after};added=[x for x in after if h.key(x) not in bk];discarded=[x for x in prev if h.key(x) not in ak]
   stage=h.stage(st['stage_id'],st['kind'],st['parent_stage_ids'],prev,added,discarded,{h.key(x):'not_carried_to_'+st['stage_id'] for x in discarded},g);stages.append(stage);prev=stage['after']
  cases.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':'numbered','case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':stages})
  calls=[]
  for p in sorted((base/'calls').glob('*/response.json')):
   raw=read(p)
   try:value=json.loads(raw['choices'][0]['message']['content'])
   except (KeyError,IndexError,TypeError,ValueError):value=None
   request=read(p.with_name('request.json'));view=json.loads(request['messages'][1]['content'])['view']
   calls.append({'call':str(p.parent.relative_to(A)),'phase':view['phase'],'model':raw.get('model'),'provider':raw.get('provider'),'output':value,'finish_reason':raw.get('choices',[{}])[0].get('finish_reason'),'error':raw.get('error')})
  with sqlite3.connect('file:'+str(base/'journal.sqlite')+'?mode=ro',uri=True) as db:
   db.row_factory=sqlite3.Row
   schema=list(db.execute('PRAGMA table_info(event)'));columns=[x['name'] for x in schema]
   events=[dict(x) for x in db.execute('SELECT * FROM event')]
   invalid=[x for x in events if 'OUTPUT_SCHEMA_INVALID' in x.values()]
   maps=[x for x in events if 'NUMBERED_REFERENCES' in x.values()]
  plans=[c['output']['question_plan'] for c in calls if c['output'] and c['output'].get('question_plan')]
  trace=read(base/'trace.json')
  summary.append({'case_id':cid,'question':case['question'],'reference_answer':gold[cid]['reference_answer'],'answer':row.get('result',{}).get('answer',{}),'calls':row['physical_calls'],'usage':{k:sum(u.get(k) or 0 for u in row['usage']) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']},'seconds':row['seconds'],'controller_seconds':row.get('controller_seconds'),'error':row['error'],'gold_presented':stages[2]['gold_after'],'gold_total':len(g),'requirements':[d['requirement'] for p in plans for d in p['demands']],'invalid_output_events':invalid,'numbered_map_count':len(maps),'semantic_errors':trace.get('errors',[]),'outputs':calls})
 counts=[c['stages'][-1]['after_count'] for c in cases];ga=sum(c['stages'][-1]['gold_after'] for c in cases);gt=sum(c['gold_total'] for c in cases)
 ledger={'schema_version':h.SCHEMA,'adr_id':'ADR-0505','experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':'numbered','declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm']['numbered']],'cases':cases,'aggregate':{'presented_total':sum(counts),'gold_after':ga,'gold_total':gt}}]}],'audit':{'corpus_total':corpus,'final_stage':'Sources in final answer claims, not publication; baseline is reference only and not executed','product_sha256':sha(A/'artifacts/run-001/results.json')}};ledger['artifact_sha256']=h._canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
 metrics={'before_filter':sum(c['stages'][0]['after_count'] for c in cases),'after_filter':sum(c['stages'][1]['after_count'] for c in cases),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':ga/gt if gt else None,'selectivity':statistics.mean(counts)/corpus}
 m['retrieval_accounting'].update(corpus_total=corpus,**{k:{'numbered':v} for k,v in metrics.items()});m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'artifacts/retrieval-stage-ledger.json')
 total={'physical_calls':sum(x['calls'] for x in summary),'cost_usd':sum(x['usage']['cost_usd'] for x in summary),'input_tokens':sum(x['usage']['input_tokens'] for x in summary),'output_tokens':sum(x['usage']['output_tokens'] for x in summary),'wall_p50':statistics.median(x['seconds'] for x in summary),'wall_p95':max(x['seconds'] for x in summary),'model_ids':sorted({c['model'] for x in summary for c in x['outputs'] if c['model']}),'providers':sorted({c['provider'] for x in summary for c in x['outputs'] if c['provider']})}
 write(A/'artifacts/trace-summary.json',{'by_case':summary,'totals':total,'assessment':'Observed traces only; qualitative findings in CASE_REVIEW.md; no automated judge score'})
 m['runs'][0].update(status='complete',artifact_path=str((A/'artifacts/run-001/results.json').relative_to(R)),sha256=sha(A/'artifacts/run-001/results.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'reference_only'},'numbered':{'status':'complete','total':3,'qualitative_assessment':'CASE_REVIEW.md'}},comparisons=[],judge_disagreements=None,usage=total,latency={'wall_p50':total['wall_p50'],'wall_p95':total['wall_p95']},error_taxonomy=[]);m['gemma_binding']['live_calls']=total['physical_calls'];write(A/'실험/manifest.json',m)
 print(json.dumps({'cases':[{k:x[k] for k in ['case_id','calls','requirements','gold_presented','gold_total','error','answer']} for x in summary],'totals':total},ensure_ascii=False))
if __name__=='__main__':main()
