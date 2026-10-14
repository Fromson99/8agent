"""Post-run accounting only; never calls a model or changes frozen inputs."""
from pathlib import Path
from collections import Counter,defaultdict
import gzip,hashlib,json,sqlite3,statistics
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0708-grounded-title-body-retest';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):
 if p.suffix=='.gz':
  with gzip.open(p,'wt',encoding='utf-8') as out:out.write(canon(v)+'\n')
 else:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ro(p):
 db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
f=read(D/'freeze.json');m=read(A/'실험/manifest.json');dataset=read(D/'dataset.json')
allowed=set(read(R/f['codes']['body-retest']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
nav=ro(R/f['source_generation']/'navigation/navigation.sqlite');sources={}
for row in nav.execute('SELECT id,json FROM source'):
 v=json.loads(row['json'])
 if v.get('document_id') in allowed:sources[row['id']]=v
nav.close()
def identities(ids):return [json.loads(x) for x in sorted({canon({'doc_id':sources[s]['document_id'],'node':int(sources[s]['unit_id'])}) for s in ids if s in sources and str(sources[s]['unit_id']).isdigit()})]
corpus=identities(sources);summaries=[];ledger_arms=[]
for arm in ('body-retest',):
 ledger_cases=[]
 for case in dataset['cases']:
  out=O/arm/case['case_id'];r=read(out/'result.json');events=[];stages=[];acquired_ids=set()
  journals=list((out/'runtime').rglob('journal.sqlite'));assert len(journals)==1
  db=ro(journals[0]);events=[{'kind':x['kind'],'payload':json.loads(x['payload_json'])} for x in db.execute('SELECT * FROM event ORDER BY seq')]
  stages=[{'stage':x['entity_id'],'payload':json.loads(x['payload_json'])} for x in db.execute("SELECT * FROM entity_version WHERE kind='case_stage' ORDER BY created_seq")]
  acquired_ids={x[0] for x in db.execute('SELECT DISTINCT source_id FROM evidence_unit')};db.close()
  offered_ids=set();front_outputs=[]
  def offered(v):
   if isinstance(v,dict):
    if v.get('source_id') in sources and isinstance(v.get('text'),str) and v['text']:offered_ids.add(v['source_id'])
    for x in v.values():offered(x)
   elif isinstance(v,list):
    for x in v:offered(x)
  for p in sorted((out/'provider').glob('call-*')):
   req=read(p/'request.json');view={}
   for msg in req.get('messages',[]):
    try:offered(json.loads(msg.get('content','')))
    except (TypeError,ValueError):pass
   try:view=json.loads(req['messages'][1]['content']).get('view',{})
   except (ValueError,KeyError):pass
   phase=view.get('source_stage',view.get('phase',''))
   if any(k in phase for k in ('request-entry','source-request-route','memory-resolve','memory-command-check','memory-intent')):
    response=p/'response.json';value=None
    if response.exists():
     try:value=json.loads(read(response)['choices'][0]['message']['content'])
     except (KeyError,ValueError,TypeError):pass
    front_outputs.append({'phase':phase,'output':value,'raw_path':str(p.relative_to(R))})
  acquired=identities(acquired_ids);presented=identities(offered_ids);before=[];ledger_stages=[]
  for i,after in enumerate((corpus,acquired,presented)):
   plan=m['design']['retrieval_stage_plan']['stages_by_arm'][arm][i]
   bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
   reason=('Authorized catalogue','Not acquired in this request','Not present as source text in physical model input')[i]
   item={**plan,'executed':True,'skip_reason':None,'before':before,'after':after,'added':added,'discarded':discarded,
    'before_count':len(before),'after_count':len(after),'added_count':len(added),'discarded_count':len(discarded),
    'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
    'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':0,'golden_recall':None}
   for k in ('gold_before','gold_added','gold_discarded','gold_after'):item[k]=0
   for k in ('gold_before_identities','gold_added_identities','discarded_gold','gold_after_identities'):item[k]=[]
   ledger_stages.append(item);before=after
  ledger_cases.append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
   'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':case['case_id'],
   'gold_total':0,'gold_identities':[],'gold_not_applicable_reason':'No approved required-evidence gold used; engineering E2E probe only','stages':ledger_stages})
  latest={x['stage']:x['payload'] for x in stages};selection=latest.get('case:SELECT',{});groups=defaultdict(lambda:{'calls':0,'seconds':0.,'input_tokens':0,'output_tokens':0,'cost_usd':0.})
  usage={u['call']:u for u in r['usage']}
  for attempt in r['attempts']:
   u={**usage.get(attempt['call'],{}),'seconds':attempt['seconds']};phase=attempt['phase'];group='front' if any(k in phase for k in ('request-entry','source-request-route','memory-resolve','memory-command-check','memory-intent')) else 'assessment' if 'memory-assess' in phase else 'navigation' if 'source-law-navigation' in phase else 'other'
   g=groups[group];g['calls']+=1
   for k in ('seconds','input_tokens','output_tokens','cost_usd'):g[k]+=u.get(k,0) or 0
  prepare=[]
  for line in (A/'artifacts'/('console-'+arm+'-'+case['case_id']+'.log')).read_text().splitlines():
   try:log=json.loads(line)
   except ValueError:continue
   if log.get('event')=='session.prepare.timings':prepare.append(log)
  summary={k:r.get(k) for k in ('case_id','arm','http_status','model_calls','request_seconds','app_setup_seconds','profile_sha256')}
  output=r.get('output',{});public_stats=output.get('execution_stats',{})
  summary.update(answer_completed=r['http_status']==200 and bool(output.get('answer',{}).get('claims')),
   model_seconds=sum(u['seconds'] for u in r['attempts']),groups=dict(groups),stages=list(latest),
   acquired_article_roots=len(acquired),presented_article_roots=len(presented),adopted_source_ids=selection.get('final_ids',[]),
   acquired_unmapped_source_ids=sorted(acquired_ids-set(sources)),event_counts=dict(Counter(x['kind'] for x in events)),
   front_outputs=front_outputs,intent=latest.get('case:INTENT'),preparation=prepare,
   attempt_count_matches=len(r['attempts'])==r['model_calls'] and len(r['usage'])==sum(a['status']=='completed' for a in r['attempts']),
   response_metrics=public_stats,
   response_metrics_match=public_stats.get('llm_calls')==r['model_calls'] and len(public_stats.get('calls',[]))==r['model_calls'] and public_stats.get('timing_complete') is True,
   main_unchanged=r['active_pointer_before']==r['active_pointer_after'],
   result_path=str((out/'result.json').relative_to(R)),result_sha256=sha(out/'result.json'))
  summary['non_model_seconds']=summary['request_seconds']-summary['model_seconds'];summaries.append(summary)
  put(out/'diagnostic.json',summary)
 ledger_arms.append({'arm_id':arm,'declared_stage_ids':['catalogue','acquired','presented'],'cases':ledger_cases,
   'aggregate':{'cases':len(ledger_cases),'presented_total':sum(c['stages'][-1]['after_count'] for c in ledger_cases),'gold_total':0}})
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
 'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
 'runs':[{'run_id':'run-001','arms':ledger_arms}],
 'audit':{'no_quality_grade':True,'adoption_reported_separately':True,'physical_provider_inputs_only':True}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json.gz',ledger)
pairs=[]
by_arm={}
for arm in ('body-retest',):
 rows=[s for s in summaries if s['arm']==arm]
 by_arm[arm]={'status':'complete','requests':len(rows),'completed_answers':sum(s['answer_completed'] for s in rows),
   'model_calls':sum(s['model_calls'] for s in rows),'request_seconds':sum(s['request_seconds'] for s in rows),
   'front_calls':sum(s['groups'].get('front',{}).get('calls',0) for s in rows),
   'front_seconds':sum(s['groups'].get('front',{}).get('seconds',0) for s in rows),'quality_certified':False}
summary={'by_arm':by_arm,'pairs':pairs,'cases':summaries,'frozen_files_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),
 'main_unchanged':all(s['main_unchanged'] for s in summaries),'count_accounting_complete':all(s['attempt_count_matches'] for s in summaries),
 'limitations':['One frozen identical-code retry after upstream429; no speed comparison or accuracy claim','Fresh processes, OS cache not flushed','No GENOS execution or independent legal grading','Existing-session corrections/restores/resumes retain legacy front']}
put(O/'summary.json',summary)
m['runs'][0].update(status='complete',sha256=sha(O/'summary.json'));m['results'].update(status='complete',by_arm=by_arm,comparisons=pairs,
 usage={arm:{k:sum(g[k] for s in summaries if s['arm']==arm for g in s['groups'].values()) for k in ('input_tokens','output_tokens','cost_usd','seconds')} for arm in by_arm},
 latency={arm:{'total_request_seconds':v['request_seconds'],'p50':None,'p95':None,'reason':'One public question, one observation; failed usage unknown'} for arm,v in by_arm.items()})
ra=m['retrieval_accounting'];ra['corpus_total']=len(corpus)
for key,field in [('before_filter',None),('after_filter','acquired_article_roots'),('presented_total','presented_article_roots')]:
 ra[key]={arm:sum(s[field] if field else len(corpus) for s in summaries if s['arm']==arm) for arm in by_arm}
for key in ('presented_mean','presented_p50','presented_p95'):
 ra[key]={arm:(statistics.mean if key=='presented_mean' else statistics.median if key=='presented_p50' else max)([s['presented_article_roots'] for s in summaries if s['arm']==arm]) for arm in by_arm}
ra['golden_recall']={arm:None for arm in by_arm};ra['selectivity']={arm:ra['presented_total'][arm]/ra['before_filter'][arm] for arm in by_arm}
ra['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json.gz');put(A/'실험/manifest.json',m)
print(json.dumps({'by_arm':by_arm,'pairs':pairs},ensure_ascii=False,indent=2))
