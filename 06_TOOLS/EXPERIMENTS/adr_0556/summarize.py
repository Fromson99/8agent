"""Offline article-coordinate accounting. Never imported by product worker."""
from pathlib import Path
import json,hashlib,sqlite3,statistics,math,gzip,sys,importlib.util,collections
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0556-pecab-qwen-authorized-routing'
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
from adr_structure import _canonical_value_sha256,ADR_HEADINGS,QUESTION_HEADINGS_V4
spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def read(p):return json.loads(p.read_text())
def sha(p):
 d=hashlib.sha256()
 with p.open('rb') as f:
  while c:=f.read(8388608):d.update(c)
 return d.hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def enrich(summary, prod, gold, index, frozen):
 """Offline utility checks require correct routing and successful final output.

 Greeting must describe legal-service role. Recipe must refuse the requested
 content. Catalogue must have actual browse/search receipts, no article claims.
 Internal absence must be scope-qualified. Recommendations require observed
 document outlines; a title inventory alone never counts as a full-text read.
 Manual content review remains necessary and is recorded separately.
 """
 utility=[];historical=[]
 for c in prod['cases']:
  cid=c['case_id']
  for arm in ('baseline','catalogue-router'):
   path=R/index['cases'][cid][arm]['path'];row=read(path)
   answer=row.get('result',{}).get('answer',{});text=answer.get('text','')
   route=row.get('request_route') or {}
   mode=route.get('mode') or ('DIRECT' if route.get('agent_required') is False else
       'SEARCH' if route.get('agent_required') is True else 'BROWSE' if row.get('metadata_only') else None)
   if c['kind']=='utility':
    trace={}
    if (path.parent/'trace.json.gz').exists():
     with gzip.open(path.parent/'trace.json.gz','rt') as z:trace=json.load(z)
    observations=trace.get('observations',[])
    actual=[o for o in observations if o.get('status') in ('OK','EMPTY','PARTIAL','REUSED')]
    passed=not row.get('error') and bool(text.strip()) and mode==c['expected_route']
    if cid=='greeting':passed &= '법' in text and any(x in text for x in ('검색','도움','자료'))
    elif cid=='out-of-domain':passed &= any(x in text for x in ('관련','범위','법률')) and not all(x in text for x in ('김치','돼지고기','끓'))
    else:
     passed &= bool(actual) and not answer.get('claims')
     if cid=='catalogue-internal':passed &= any(x in text for x in ('허용','범위','요청'))
     if cid=='title-search':
      proposals=[json.loads(x['proposed_json']) for x in trace.get('actions',[]) if x.get('proposed_json')]
      passed &= any(x.get('tool')=='search' and x.get('args',{}).get('mode')=='title' and
          '내부회계' in x['args'].get('query','').replace(' ','') for x in proposals)
     if cid=='browse-uncertain':passed &= len(actual)>=2
    utility.append({'case_id':cid,'arm':arm,'mode':mode,'expected_route':c['expected_route'],
       'automatic_rubric_pass':bool(passed),'actual_tool_receipts':len(actual),'answer':text,
       'claims':answer.get('claims',[]),'error':row.get('error'),'needs_content_review':True})
   elif cid in frozen['historical_paths']:
    old=read(R/frozen['historical_paths'][cid]);required=set(gold[cid]['decisive_source_ids'])
    historical.append({'case_id':cid,'arm':arm,'question_identical':True,
      'old_model':'qwen/qwen3.5-122b-a10b','old_artifact':frozen['historical_paths'][cid],
      'old_delivered_gold':len(required&set(old.get('stages',{}).get('presented',[]))),
      'new_delivered_gold':len(required&set(row.get('stages',{}).get('presented',[]))),
      'gold_total':len(required),'old_physical_calls':old.get('physical_calls'),'new_physical_calls':row.get('physical_calls'),
      'comparable_conditions':False,'interpretation':'Historical question/source comparison only; model, tokenizer, workflow differ'})
 summary['utility_rubric']=utility;summary['historical_comparison']=historical
 totals=summary['totals'];by={(x['case_id'],x['arm']):x for x in summary['rows']}
 utility_counts={arm:sum(x['automatic_rubric_pass'] for x in utility if x['arm']==arm) for arm in totals}
 criteria={'utility_automatic_counts':utility_counts,
   'utility_target':utility_counts['catalogue-router']>=5 and utility_counts['catalogue-router']>utility_counts['baseline'],
   'core_per_case_nonregression':all(by[c['case_id'],'catalogue-router']['gold_by_stage'].get('presented',0)>=by[c['case_id'],'baseline']['gold_by_stage'].get('presented',0) for c in prod['cases'] if c['kind']=='legal'),
   'all_attempts_finalized':all(not x['error'] and (x.get('control') or {}).get('decision')=='FINAL' for x in summary['rows']),
   'mean_calls_limit':totals['catalogue-router']['physical_calls']/14<=totals['baseline']['physical_calls']/14+2,
   'median_seconds_limit':statistics.median(x['seconds'] or 360 for x in summary['rows'] if x['arm']=='catalogue-router')<=statistics.median(x['seconds'] or 360 for x in summary['rows'] if x['arm']=='baseline')*1.5+15,
   'content_review_required':True,'quality_certified':False}
 summary['frozen_criteria_outcomes']=criteria
def main():
 index=read(A/'artifacts/run-001/results.json');f=read(A/'artifacts/frozen-design.json');m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json')
 for p,v in f['file_hashes'].items():assert sha(R/p)==v,p
 for p,v in f['grader_only_hashes'].items():assert sha(R/p)==v,p
 gold={x['case_id']:x for x in read(A/'gold-cases.json')['cases']}
 db=sqlite3.connect('file:'+str(R/f['generations']['catalogue-router']/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
 coords={sid:{'doc_id':did,'node':int(uid)} for sid,did,uid in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if str(uid).isdigit()};db.close()
 corpus=sum(c['doc_id'] in prod['public_scope_document_ids'] for c in coords.values())
 rows=[];arms=[];totals={};traces={};all_usage=[]
 for arm in ('baseline','catalogue-router'):
  records=[];arows=[]
  for c in prod['cases']:
   cid=c['case_id'];path=R/index['cases'][cid][arm]['path'];row=read(path);out=path.parent
   stages=row.get('stages',{})
   if not stages and (out/'journal.sqlite').exists():
    j=sqlite3.connect('file:'+str(out/'journal.sqlite')+'?mode=ro',uri=True)
    ev={eid:sid for eid,sid in j.execute('SELECT evidence_id,source_id FROM evidence_unit')};read_ids=set(ev.values());discovered={json.loads(raw).get('source_id') for (raw,) in j.execute('SELECT identity_json FROM navigation_handle')}-{None};discovered|=read_ids
    delivered={ev[eid] for (eid,) in j.execute("SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'") if eid in ev}
    stages={'discovered':sorted(discovered),'read':sorted(read_ids),'presented':sorted(delivered)};j.close()
   trace={}
   if (out/'trace.json.gz').exists():
    with gzip.open(out/'trace.json.gz','rt') as z:trace=json.load(z)
   origins=collections.Counter();verbs=collections.Counter()
   for act in trace.get('actions',[]):
    result=json.loads(act['result_json']) if act.get('result_json') else {};origins[result.get('exploration_origin',{}).get('route_class','unspecified')]+=1
    for k in ('action_json','args_json'):
     if act.get(k):
      val=json.loads(act[k]);verbs[val.get('tool',val.get('verb','unknown'))]+=1
   required=set(gold.get(cid,{}).get('decisive_source_ids',[]));assert required<=set(coords)
   got={k:len(required&set(ids)) for k,ids in stages.items()}
   g=h.ordered(coords[s] for s in required);outputs={};ledger_stages=[]
   for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
    prev=h.ordered(x for parent in plan['parent_stage_ids'] for x in outputs[parent])
    after=h.ordered(coords[s] for s in stages.get(plan['stage_id'],[]) if s in coords);ak={h.key(x) for x in after};pk={h.key(x) for x in prev};drop=[x for x in prev if h.key(x) not in ak]
    st=h.stage(plan['stage_id'],plan['kind'],plan['parent_stage_ids'],prev,[x for x in after if h.key(x) not in pk],drop,{h.key(x):{'read':'not_fully_read','selected':'not_selected','presented':'no_successful_exact_evidence_presentation_receipt'}.get(plan['stage_id'],'not_observed') for x in drop},g);ledger_stages.append(st);outputs[plan['stage_id']]=st['after']
   records.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':ledger_stages})
   provider_errors=collections.Counter()
   for rp in (out/'calls').glob('call-*/response.json'):
    response=read(rp);err=response.get('error')
    if isinstance(err,dict):provider_errors[str(err.get('code','unknown'))]+=1
   usage=row.get('usage',[]);all_usage+=usage
   rr={'case_id':cid,'arm':arm,'error':row.get('error'),'provider_errors':dict(provider_errors),'gold_total':len(required),'gold_by_stage':got,'counts':{k:len(set(v)) for k,v in stages.items()},'missing_presented':sorted(required-set(stages.get('presented',[]))),'physical_calls':row['physical_calls'],'seconds':row['seconds'],'controller_seconds':row.get('controller_seconds'),'graph':row.get('graph_summary'),'cost_usd':sum(u.get('cost_usd') or 0 for u in usage),'unknown_usage':row.get('in_flight_usage_unknown',False),'limitations':row.get('limitations',[]),'gate':row.get('control'),'action_origins':dict(origins),'session_errors':trace.get('errors',[]),'artifacts':{'result':str(path.relative_to(R)),'result_sha256':sha(path),'trace':str((out/'trace.json.gz').relative_to(R)) if trace else None}}
   rows.append(rr);arows.append(rr);traces[cid,arm]=trace
   rr.update(kind=c['kind'], expected_route=c['expected_route'], route=row.get('request_route'), answer=row.get('result',{}).get('answer'), control=row.get('control'))
  counts=sorted(r['stages'][-1]['after_count'] for r in records);n=sum(r['gold_total'] for r in records);got=sum(r['stages'][-1]['gold_after'] for r in records)
  arms.append({'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':{'presented_total':sum(counts),'gold_after':got,'gold_total':n}})
  totals[arm]={'cases':len(records),'error_cases':sum(bool(x['error']) for x in arows),'bounded_cases':sum((x.get('gate') or {}).get('gate')=='BOUNDED' for x in arows),'no_read_cases':sum(not x['counts'].get('read') for x in arows),'provider_429_responses':sum(x['provider_errors'].get('429',0) for x in arows),'proposal_errors':sum(len(x['session_errors']) for x in arows),'gold_obtained':got,'gold_total':n,'golden_recall':got/n if n else None,'before_filter':sum(r['stages'][0]['after_count'] for r in records),'after_filter':sum(counts),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':counts[round((len(counts)-1)*.95)],'selectivity':statistics.mean(counts)/corpus,'physical_calls':sum(x['physical_calls'] for x in arows),'mean_seconds':statistics.mean([x['seconds'] for x in arows if x['seconds'] is not None]) if any(x['seconds'] is not None for x in arows) else None,'cost_usd':sum(x['cost_usd'] for x in arows),'partial_graphs':sum((x['graph'] or {}).get('status')=='PARTIAL' for x in arows),'gold_by_stage':{k:sum(x['gold_by_stage'].get(k,0) for x in arows) for k in ['discovered','read','presented','selected','answer','protected_originals']},'mean_counts':{k:statistics.mean(x['counts'].get(k,0) for x in arows) for k in ['discovered','read','presented','selected','answer','protected_originals']}}
 ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'presentation':'Evidence spans linked to model attempts with successful responses; article identity recall does not certify complete decisive provision delivery','protected_originals':'Local graph preservation is a separate count, never equated with delivered evidence','gold_join':'Only in this offline script after all product workers completed'}};ledger['artifact_sha256']=_canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
 summary={'totals':totals,'rows':rows,'active_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['file_hashes']['01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'],'quality_certified':False,'main_changed':False,'model':'qwen/qwen3.8-27b','provider':'OpenRouter / Parasail FP8','thinking':False,'usage':{'physical_calls':sum(t['physical_calls'] for t in totals.values()),'cost_missing_calls':sum(t['physical_calls'] for t in totals.values())-sum(u.get('cost_usd') is not None for u in all_usage),'input_tokens':sum(u.get('input_tokens') or 0 for u in all_usage),'output_tokens':sum(u.get('output_tokens') or 0 for u in all_usage),'cost_usd':sum(u.get('cost_usd') or 0 for u in all_usage)},'limitations':['Eight historically observed legal questions plus six utility questions; one run per arm; in-sample and not quality certification','Article-level gold recall does not certify exact paragraph/item coverage or answer correctness','Utility routing/tool receipts checked against the prespecified deterministic rubric; no independent semantic/legal correctness grade','External Qwen3.8 Parasail FP8 proxy; no GENOS model or internal-data measurement','Three workers overlap on one WSL host; latency describes this experiment only','Legacy90/90 retrieval union used a different acquisition workflow; not a comparable end-to-end baseline','Primary paired comparison uses identical PeCab data and model. ADR0496 historical comparison uses a different model, tokenizer and workflow and is descriptive only']}
 enrich(summary, prod, gold, index, f)
 write(A/'artifacts/summary.json',summary)
 decision='Deferred: paired in-sample probe; no MAIN promotion. Frozen criteria and reviewed utility outcomes are recorded separately. Preserve every error and source miss.'
 m['results'].update(status='complete',by_arm=totals,comparisons=[{'baseline':'baseline','candidate':'catalogue-router','interpretation':decision}],judge_disagreements=None,usage=summary['usage'],latency={'mean_seconds':{k:t['mean_seconds'] for k,t in totals.items()}},error_taxonomy=sorted({x['error']['type'] for x in rows if x['error']}))
 m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/results.json'))
 m['actual_model_binding']={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','thinking':'none','physical_calls':summary['usage']['physical_calls']}
 m['retrieval_accounting']={'changed':True,'corpus_total':corpus,'not_applicable_reason':None,'stage_ledger':{'mode':'measured','schema_version':h.SCHEMA,'accounting_unit':h.UNIT,'summary_run_id':'run-001','artifact_path':str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),'sha256':sha(A/'artifacts/retrieval-stage-ledger.json'),'not_applicable_reason':None},**{key:{arm:t[key] for arm,t in totals.items()} for key in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')}}
 m['questions']=[]
 for number,c in enumerate(prod['cases'],1):
  cid=c['case_id'];filename=f'질문-{number:03d}-{cid}.md';qp=A/'실험'/filename;goldrow=gold.get(cid,{'kind':'utility','expected_route':c['expected_route'],'grading':'Utility rubric and actual tool receipts; no article gold'});crows=[x for x in rows if x['case_id']==cid];raw=[]
  for arm in ('baseline','catalogue-router'):
   for p in sorted((A/'artifacts/run-001'/cid/arm/'calls').rglob('*.json')):
    raw.append(f'- {arm}: [{p.name}](../{p.relative_to(A)}) SHA256 `{sha(p)}`')
  blocks=[f'ADR0556 / run-001 / {cid}. Fresh paired Qwen3.8 execution. 원본 상태: exact.',c['question'],'```json\n'+json.dumps(goldrow,ensure_ascii=False,indent=2)+'\n```','Frozen product-cases.json, frozen-design.json and public export-rebinding.json. No gold read by product workers.','artifacts/retrieval-stage-ledger.json; article identity counts, gold joined after completion.','\n'.join(raw) or 'No physical model sends.','Planning/tool exploration/selection/compose/review and repairs are included in the raw call sequence above; no separate hidden model calls.','No evaluator model calls; deterministic source-coordinate and frozen utility-receipt rubric only; no independent semantic/legal quality certification.','```json\n'+json.dumps(crows,ensure_ascii=False,indent=2)+'\n```']
  qp.write_text('# '+cid+'\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(QUESTION_HEADINGS_V4,blocks))+'\n');m['questions'].append({'number':number,'case_id':cid,'file':filename,'sha256':sha(qp)})
 write(A/'실험/manifest.json',m)
 (A/'실험/README.md').write_text('# Fourteen paired Qwen3.8 cases\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
 original=(A/'README.md').read_text();front=original.split('---',2)[1]
 blocks=[decision,'Frozen catalogue-first candidate compared with the current working two-way router on the same public145 PeCab generation. Previous Kiwi design was abandoned with zero model sends. Public-only rebuild preserves original store, literal navigation and glossary assets.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],(A/'PLAN.md').read_text(),'Exact Qwen3.8 model/provider and all input/code/data/prompt/schema hashes in artifacts/frozen-design.json; public originals only.','```json\n'+json.dumps(totals,ensure_ascii=False,indent=2)+'\n```','Each question file links exact request, response, validation schema, binding, usage and SQLite journal; summary.json contains per-case errors.','```json\n'+json.dumps(summary['usage'],indent=2)+'\n```','Article-level recall measures source identity, not exact paragraph or legal correctness. Request routing and utility-task outcomes are separate measurements.','\n'.join('- '+x for x in summary['limitations']),'Router candidate and paired outputs remain isolated. No experimental MAIN promotion or GENOS deployment. PeCab maintenance migration is reported separately.','```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0556/run_probe.py --execute\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0556/summarize.py\n```\nCompleted run directories are immutable; any repeated model execution must reserve a new ADR.']
 (A/'README.md').write_text('---'+front+'---\n\n# ADR0556 Qwen3.8 paired experiment\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(ADR_HEADINGS,blocks))+'\n')
 print(json.dumps(summary['totals'],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
