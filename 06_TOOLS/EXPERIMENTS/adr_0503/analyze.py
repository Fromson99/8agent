"""Aggregate frozen outcomes and exact observed source stages; no model calls."""
import json,hashlib,sqlite3,statistics,math,importlib.util,sys
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0503-gemma-obligations-bound-paired-probe';ARMS=['baseline','obligations']
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 product=read(A/'product-cases.json');gold={x['case_id']:x for x in read(A/'gold-cases.json')['cases']};res=read(A/'artifacts/run-001/results.json');jud=read(A/'artifacts/run-001/judgment/results.json');m=read(A/'실험/manifest.json')
 spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
 with sqlite3.connect('file:'+str(R/product['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
  coords={s:{'doc_id':d,'node':int(u)} for s,d,u in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if str(u).isdigit()}
 corpus=len({h.key(v) for v in coords.values() if v['doc_id'] in product['public_scope_document_ids']});larms=[];flat=[];ret={k:{} for k in ['before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']}
 for arm in ARMS:
  cases=[]
  for case in product['cases']:
   cid=case['case_id'];r=res['cases'][cid][arm];g=h.ordered(coords[x] for x in gold[cid]['decisive_source_ids']);prev=[];stages=[]
   for st in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
    after=h.ordered(coords[x] for x in r.get('stages',{}).get(st['stage_id'],[]) if x in coords);bk={h.key(x) for x in prev};ak={h.key(x) for x in after};added=[x for x in after if h.key(x) not in bk];discarded=[x for x in prev if h.key(x) not in ak]
    reasons={h.key(x):'not_carried_to_'+st['stage_id'] for x in discarded};stage=h.stage(st['stage_id'],st['kind'],st['parent_stage_ids'],prev,added,discarded,reasons,g);stages.append(stage);prev=stage['after']
   cases.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':stages})
   vv=[x.get('by_arm',{}).get(arm) for x in jud['cases'][cid]['assessments']];valid=[x for x in vv if x]
   verdict=None if r['error'] or len(valid)!=2 or valid[0]['correct']!=valid[1]['correct'] else valid[0]['correct']
   dims={}
   for dim in ['demand_coverage','rule_scope','conditions_exceptions','appropriate_abstention','self_review']:
    vals=[x['dimensions'][dim]['status'] for x in valid];dims[dim]=vals[0] if len(vals)==2 and vals[0]==vals[1] and not r['error'] else 'unresolved'
   usage={k:sum(u.get(k) or 0 for u in r['usage']) for k in ['input_tokens','output_tokens','thinking_tokens','total_tokens','cost_usd']}
   flat.append({'case_id':cid,'arm':arm,'correct':verdict,'judge_votes':[x['correct'] if x else None for x in vv],'dimensions':dims,'technical_error':r['error'],'answer':r.get('result',{}).get('answer',{}).get('text',''),'claims':len(r.get('result',{}).get('answer',{}).get('claims',[])),'calls':r['physical_calls'],'usage_receipts':len(r['usage']),'usage':usage,'seconds':r['seconds'],'controller_seconds':r.get('controller_seconds'),'gold_read':stages[1]['gold_after'],'gold_presented':stages[2]['gold_after'],'gold_answer':stages[-1]['gold_after'],'gold_total':len(g),'limitations':r.get('limitations',[]),'judge_reasons':[x['reason'] if x else None for x in vv]})
  counts=[c['stages'][-1]['after_count'] for c in cases];ga=sum(c['stages'][-1]['gold_after'] for c in cases);gt=sum(c['gold_total'] for c in cases)
  larms.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':cases,'aggregate':{'presented_total':sum(counts),'gold_after':ga,'gold_total':gt}})
  metrics={'before_filter':sum(c['stages'][0]['after_count'] for c in cases),'after_filter':sum(c['stages'][1]['after_count'] for c in cases),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':sorted(counts)[round((len(counts)-1)*.95)],'golden_recall':ga/gt if gt else None,'selectivity':statistics.mean(counts)/corpus}
  for k,v in metrics.items():ret[k][arm]=v
 ledger={'schema_version':h.SCHEMA,'adr_id':'ADR-0503','experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':larms}],'audit':{'corpus_total':corpus,'final_stage':'Sources in answer claims, not publication. Stages measure aggregate observed identities; no latent per-action retrieval reconstruction.','product_sha256':sha(A/'artifacts/run-001/results.json')}};ledger['artifact_sha256']=h._canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
 by={}
 for arm in ARMS:
  rr=[r for r in flat if r['arm']==arm]
  by[arm]={'confirmed_correct':sum(x['correct'] is True for x in rr),'confirmed_incorrect':sum(x['correct'] is False for x in rr),'unresolved':sum(x['correct'] is None for x in rr),'technical_unevaluable':sum(bool(x['technical_error']) for x in rr),'total':len(rr),'with_reviewed_claims':sum(x['claims']>0 for x in rr),'product_calls':sum(x['calls'] for x in rr),'usage_receipts':sum(x['usage_receipts'] for x in rr),'usage_unreported_calls':sum(x['calls']-x['usage_receipts'] for x in rr),'usage':{k:sum(x['usage'][k] for x in rr) for k in rr[0]['usage']},'wall_p50_seconds':statistics.median(x['seconds'] for x in rr),'wall_p95_seconds':sorted(x['seconds'] for x in rr)[math.ceil(.95*len(rr))-1],'controller_max_seconds':max(x['controller_seconds'] or 0 for x in rr),'dimensions':{d:dict(Counter(x['dimensions'][d] for x in rr)) for d in rr[0]['dimensions']}}
 pairs=Counter()
 for case in product['cases']:
  rows={x['arm']:x for x in flat if x['case_id']==case['case_id']};b=rows['baseline']['correct'];o=rows['obligations']['correct']
  label='unresolved' if b is None or o is None else ('both_correct' if b and o else 'candidate_only' if o else 'baseline_only' if b else 'both_incorrect');pairs[label]+=1
 cost_ratio=by['obligations']['usage']['cost_usd']/by['baseline']['usage']['cost_usd'] if by['baseline']['usage']['cost_usd'] else None
 call_ratio=by['obligations']['product_calls']/by['baseline']['product_calls'] if by['baseline']['product_calls'] else None
 criteria={'net_new_correct_min1':pairs['candidate_only']-pairs['baseline_only']>=1,'zero_regressions':pairs['baseline_only']==0,'all_pairs_evaluable':pairs['unresolved']==0,'demand_omissions_not_increased':by['obligations']['dimensions']['demand_coverage'].get('fail',0)<=by['baseline']['dimensions']['demand_coverage'].get('fail',0),'calls_ratio_max1_5':call_ratio is not None and call_ratio<=1.5,'cost_ratio_max1_5':cost_ratio is not None and cost_ratio<=1.5 and all(x['usage_unreported_calls']==0 for x in by.values()),'controller_max300':all(x['controller_seconds'] is not None and x['controller_seconds']<=300 for x in flat)}
 judge_usage={k:sum(u.get(k) or 0 for c in jud['cases'].values() for u in c['usage']) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']}
 summary={'by_arm':by,'paired_outcomes':dict(pairs),'by_case':flat,'criteria':criteria,'criteria_met':all(criteria.values()),'cost_ratio':cost_ratio,'call_ratio':call_ratio,'judge_usage':judge_usage,'judge_calls':sum(len(c['assessments']) for c in jud['cases'].values()),'interpretation':'Stored-reference agreement, not certified current legal correctness. Two votes must agree; disagreement is unresolved. No technical failure counted as model reasoning error. In-sample single-attempt probe.'};write(A/'artifacts/metrics.json',summary)
 m['retrieval_accounting'].update(corpus_total=corpus,**ret);m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'artifacts/retrieval-stage-ledger.json');m['runs'][0].update(status='complete',artifact_path=str((A/'artifacts/run-001/results.json').relative_to(R)),sha256=sha(A/'artifacts/run-001/results.json'));m['results'].update(status='complete',by_arm=by,comparisons=[{'paired_outcomes':dict(pairs),'path':str((A/'artifacts/metrics.json').relative_to(R)),'sha256':sha(A/'artifacts/metrics.json')}],judge_disagreements=sum(x['correct'] is None and not x['technical_error'] for x in flat),usage={'product':{a:by[a]['usage'] for a in ARMS},'judge':judge_usage},latency={a:{k:v for k,v in by[a].items() if 'seconds' in k} for a in ARMS},error_taxonomy=[]);write(A/'실험/manifest.json',m)
 print(json.dumps({'by_arm':by,'paired':dict(pairs),'criteria':criteria,'judge_usage':judge_usage},ensure_ascii=False))
if __name__=='__main__':main()
