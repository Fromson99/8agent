"""Offline accounting after the single frozen request. No model calls."""
from pathlib import Path
from collections import Counter, defaultdict
import gzip, hashlib, json, sqlite3

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0705-cm-max-call-bottleneck-probe'
D=A/'artifacts/design'; O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):
    if p.suffix=='.gz':
        with gzip.open(p,'wt',encoding='utf-8') as out:out.write(canon(v)+'\n')
    else:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ro(p):
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    return db

assert (O/'provider').is_dir() and (O/'runtime').is_dir(), 'Raw records were archived; inspect the saved diagnostic or restore into a separate audit workspace.'
r=read(O/'result.json');m=read(A/'실험/manifest.json');f=read(D/'freeze.json')
spans=read(O/'timing-spans.json');functions=read(O/'function-profile.json') if (O/'function-profile.json').exists() else []
children=defaultdict(float)
for x in spans:
    if x['parent'] is not None:children[x['parent']]+=x['seconds']
timers=defaultdict(lambda:{'calls':0,'inclusive_seconds':0,'exclusive_seconds':0})
for x in spans:
    label=x['name']+(':'+x['stage'] if 'stage' in x else '')
    v=timers[label];v['calls']+=1;v['inclusive_seconds']+=x['seconds'];v['exclusive_seconds']+=max(0,x['seconds']-children[x['id']])
groups=defaultdict(lambda:{'calls':0,'seconds':0,'input_tokens':0,'output_tokens':0,'cost_usd':0})
for u in r['usage']:
    phase=u['phase']
    if 'source-law-navigation' in phase:group='navigation'
    elif 'memory-assess' in phase:group='assessment'
    elif any(x in phase for x in ('source-request-route','memory-resolve','memory-command-check','memory-intent')):group='request_interpretation'
    else:group='other_model'
    g=groups[group];g['calls']+=1
    for k in ('seconds','input_tokens','output_tokens','cost_usd'):g[k]+=u.get(k,0) or 0

logs=[]
for line in (A/'artifacts/run-console.log').read_text().splitlines():
    try:logs.append(json.loads(line))
    except ValueError:pass
prepare=[x for x in logs if x.get('event')=='session.prepare.timings']
events=[];stages=[];acquired_ids=set()
journals=list((O/'runtime').rglob('journal.sqlite'))
if journals:
    assert len(journals)==1
    db=ro(journals[0])
    events=[{'seq':x['seq'],'kind':x['kind'],'payload':json.loads(x['payload_json'])} for x in db.execute('SELECT * FROM event ORDER BY seq')]
    stages=[{'stage':x['entity_id'],'payload':json.loads(x['payload_json'])} for x in db.execute("SELECT * FROM entity_version WHERE kind='case_stage' ORDER BY created_seq")]
    acquired_ids={x[0] for x in db.execute('SELECT DISTINCT source_id FROM evidence_unit')}
    db.close()
code=R/f['code_root'];allowed=set(read(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
nav=ro(R/f['source_generation']/'navigation/navigation.sqlite')
sources={}
for row in nav.execute('SELECT id,json FROM source'):
    v=json.loads(row['json'])
    if v.get('document_id') in allowed:sources[row['id']]=v
nav.close()
def identities(ids):
    return [json.loads(x) for x in sorted({canon({'doc_id':sources[s]['document_id'],'node':int(sources[s]['unit_id'])}) for s in ids if s in sources and str(sources[s]['unit_id']).isdigit()})]
offered_ids=set();call_outputs=[];model_inputs=[]
def offered(v):
    if isinstance(v,dict):
        if v.get('source_id') in sources and isinstance(v.get('text'),str) and v['text']:offered_ids.add(v['source_id'])
        for x in v.values():offered(x)
    elif isinstance(v,list):
        for x in v:offered(x)
for p in sorted((O/'provider').glob('call-*')):
    req=read(p/'request.json');phase=p.name
    for msg in req.get('messages',[]):
        try:offered(json.loads(msg.get('content','')))
        except (TypeError,ValueError):pass
    view=json.loads(req['messages'][1]['content']).get('view',{})
    model_inputs.append({'call':phase,'view_keys':list(view),'request_bytes':(p/'request.json').stat().st_size})
    response=p/'response.json'
    if response.exists():
        raw=read(response)
        try:value=json.loads(raw['choices'][0]['message']['content'])
        except (KeyError,ValueError,TypeError):value=None
        call_outputs.append({'call':phase,'structured':value})
recalls=[x['payload'] for x in stages if x['stage']=='case:RECALL']
corpus_ids={s for x in recalls for s in x.get('corpus_ids',[])}
corpus=identities(corpus_ids or set(sources))
acquired=identities(acquired_ids);presented=identities(offered_ids)
latest={x['stage']:x['payload'] for x in stages}
selected=latest.get('case:SELECT',{})
state=selected.get('investigation_state') or {}
inventory={'corpus_article_roots':len(corpus),'acquired_article_roots':len(acquired),'presented_article_roots':len(presented),
           'adopted_source_ids':selected.get('final_ids',[]),'event_counts':dict(Counter(x['kind'] for x in events)),
           'gap_rounds':len(state.get('gap_rounds',[])), 'quality_scored':False}
ledger_stages=[];before=[]
for i,after in enumerate((corpus,acquired,presented)):
    plan=m['design']['retrieval_stage_plan']['stages_by_arm']['measured-main48'][i]
    bm={canon(x):x for x in before};am={canon(x):x for x in after}
    added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
    reason=('Authorized article catalogue','Not acquired during this request','No full-text source object in a physical model input')[i]
    item={**plan,'executed':True,'skip_reason':None,'before':before,'after':after,'added':added,'discarded':discarded,
          'before_count':len(before),'after_count':len(after),'added_count':len(added),'discarded_count':len(discarded),
          'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
          'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],
          'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':0,'golden_recall':None}
    for k in ('gold_before','gold_added','gold_discarded','gold_after'):item[k]=0
    for k in ('gold_before_identities','gold_added_identities','discarded_gold','gold_after_identities'):item[k]=[]
    ledger_stages.append(item);before=after
case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
      'accounting_unit':'case_id + canonical article-root coordinate','arm_id':'measured-main48','case_id':'cm-018',
      'gold_total':0,'gold_identities':[],'gold_not_applicable_reason':'Latency diagnosis only; no answer or required-evidence grading','stages':ledger_stages}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
        'accounting_unit':case['accounting_unit'],'computed_post_selection':True,'gold_visible_to_product':False,
        'runs':[{'run_id':'run-001','arms':[{'arm_id':'measured-main48','declared_stage_ids':['catalogue','acquired','presented'],
        'cases':[case],'aggregate':{'cases':1,'presented_total':len(presented),'gold_total':0}}]}],
        'audit':{'no_quality_grade':True,'adoption_reported_separately':True,'physical_provider_inputs_only':True}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json.gz',ledger)
summary={'case_id':'cm-018','http_status':r['http_status'],'model_calls':r['model_calls'],
         'request_seconds':r.get('request_seconds'),'setup_seconds':r.get('app_setup_seconds'),
         'model_seconds':sum(u['seconds'] for u in r['usage']), 'groups':dict(groups),
         'request_preparation':prepare,'timers':dict(timers),'inventory':inventory,
         'top_local_cumulative_functions':[x for x in functions if '/semantic_runtime/' in x['file']][:35],
         'top_self_functions':sorted(functions,key=lambda x:x['self_seconds'],reverse=True)[:25],
         'model_inputs':model_inputs,'model_decisions':call_outputs,
         'main_unchanged':r['active_pointer_before']==r['active_pointer_after'],
         'frozen_files_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),
         'profile_same_as_recorded_main48_service':r['profile_sha256']==read(R/'04_EXPERIMENTS/ADR/ADR-0704-compact-progress-call-metrics/artifacts/main-smoke.json')['execution_binding']['effective_profile_sha256'],
         'limitations':['Single profiled request; overhead unmeasured; not warm service SLA','Historical case used older code/data','No legal correctness or required-source grade','No GENOS execution']}
if summary['request_seconds'] is not None:summary['non_model_seconds']=summary['request_seconds']-summary['model_seconds']
put(O/'diagnostic.json',summary)
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'measured-main48':{'status':'complete','requests':1,'http_status':r['http_status'],'model_calls':r['model_calls'],'accuracy':None,'quality_not_measured':True}},comparisons=[],judge_disagreements=None,
                    usage={'measured-main48':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd','seconds')}},
                    latency={'measured-main48':{'request_seconds':r.get('request_seconds'),'p50':None,'p95':None,'reason':'One profiled request; no population quantiles'}},error_taxonomy=[])
ra=m['retrieval_accounting'];ra['corpus_total']=len(corpus)
for key,val in [('before_filter',len(corpus)),('after_filter',len(acquired)),('presented_total',len(presented)),('presented_mean',len(presented)),('presented_p50',len(presented)),('presented_p95',len(presented)),('golden_recall',None),('selectivity',len(presented)/len(corpus))]:ra[key]={'measured-main48':val}
ra['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json.gz');put(A/'실험/manifest.json',m)
print(json.dumps({k:v for k,v in summary.items() if k in ('http_status','model_calls','request_seconds','model_seconds','non_model_seconds','groups','main_unchanged','frozen_files_unchanged','profile_same_as_recorded_main48_service')},ensure_ascii=False,indent=2))
print('TOP SELF',json.dumps(summary['top_self_functions'][:10],ensure_ascii=False))
