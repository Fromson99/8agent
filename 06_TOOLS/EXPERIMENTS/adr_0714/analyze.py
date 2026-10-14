"""Post-output physical-call, original-delivery and binding audit; no model calls."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,sqlite3,gzip
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0714-main50-cm018-call-retest';D=A/'artifacts/design';O=A/'artifacts/run-001';ARM='measured-main50'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):
 if p.suffix=='.gz':
  with gzip.open(p,'wt',encoding='utf-8') as f:f.write(canon(v)+'\n')
 else:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ro(p):
 db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
r=read(O/'result.json');f=read(D/'freeze.json');m=read(A/'실험/manifest.json');base=read(D/'baseline.json');g=read(D/'gold.json');gold=g['source'];code=R/f['code_root']
allowed=set(read(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
nav=ro(R/f['source_generation']/'navigation/navigation.sqlite');sources={x['id']:json.loads(x['json']) for x in nav.execute('select id,json from source')};nav.close()
def identities(ids):return [json.loads(s) for s in sorted({canon({'doc_id':sources[x]['document_id'],'node':int(sources[x]['unit_id'])}) for x in ids if x in sources})]
paths=list((O/'runtime').rglob('journal.sqlite'));events=[];stages=[];acquired_ids=set()
if paths:
 assert len(paths)==1;db=ro(paths[0]);events=[{'seq':x['seq'],'kind':x['kind'],'payload':json.loads(x['payload_json'])} for x in db.execute('select * from event order by seq')]
 stages=[{'stage':x['entity_id'],'created_seq':x['created_seq'],'payload':json.loads(x['payload_json'])} for x in db.execute("select * from entity_version where kind='case_stage' order by created_seq")]
 acquired_ids={x[0] for x in db.execute('select distinct source_id from evidence_unit')};db.close()
latest={x['stage']:x['payload'] for x in stages};selected=latest.get('case:SELECT',{});orig={x['source_id']:x for x in selected.get('selected_originals',[])}
offered_ids=set();source_texts=defaultdict(list);calls=[];refs=[]
def walk(v,strings):
 if isinstance(v,dict):
  if v.get('source_id') in sources and isinstance(v.get('text'),str) and v['text']:
   offered_ids.add(v['source_id']);source_texts[v['source_id']].append(v['text'])
  if isinstance(v.get('text_id'),str) and isinstance(v.get('text'),str):strings[v['text_id']]=v['text']
  for x in v.values():walk(x,strings)
 elif isinstance(v,list):
  for x in v:walk(x,strings)
def verify_refs(v,strings):
 if isinstance(v,dict):
  if isinstance(v.get('text_ref'),dict):
   ref=v['text_ref'];t=strings.get(ref.get('id'));start=ref.get('start');end=ref.get('end');refs.append(t is not None and type(start)==int and type(end)==int and 0<=start<=end<=len(t))
  for x in v.values():verify_refs(x,strings)
 elif isinstance(v,list):
  for x in v:verify_refs(x,strings)
for call in sorted((O/'provider').glob('call-*')):
 req=read(call/'request.json');body=req.get('body',req);view=json.loads(body['messages'][1]['content'])['view'];strings={};walk(view,strings);verify_refs(view,strings)
 response=read(call/'response.json') if (call/'response.json').exists() else None;decision=None
 if response:
  try:decision=json.loads(response['choices'][0]['message']['content'])
  except (KeyError,ValueError,TypeError):pass
 calls.append({'call':call.name,'phase':view.get('source_stage',view.get('phase')),'decision':decision,'request_sha256':sha(call/'request.json'),'response_sha256':sha(call/'response.json') if response else None,'request_bytes':(call/'request.json').stat().st_size})
recalls=[x['payload'] for x in stages if x['stage']=='case:RECALL'];corpus_ids={s for x in recalls for s in x.get('corpus_ids',[])} or {sid for sid,s in sources.items() if s['document_id'] in allowed}
corpus=identities(corpus_ids);acquired=identities(acquired_ids);presented=identities(offered_ids);gs=identities([gold['id']]);gkeys={canon(x) for x in gs};before=[];ledger=[]
for i,after in enumerate((corpus,acquired,presented)):
 plan=m['design']['retrieval_stage_plan']['stages_by_arm'][ARM][i];bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
 gb=[bm[k] for k in sorted(bm.keys()&gkeys)];ga=[am[k] for k in sorted(am.keys()&gkeys)];gain=[x for x in added if canon(x) in gkeys];loss=[x for x in discarded if canon(x) in gkeys]
 reason=['Bound authorized article catalogue','Not acquired by executed original reader','Original text absent from physical provider input'][i]
 ledger.append({**plan,'executed':True,'skip_reason':None,'before':before,'after':after,'added':added,'discarded':discarded,'before_count':len(before),'after_count':len(after),'added_count':len(added),'discarded_count':len(discarded),'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':1,'golden_recall':len(ga),'gold_before':len(gb),'gold_added':len(gain),'gold_discarded':len(loss),'gold_after':len(ga),'gold_before_identities':gb,'gold_added_identities':gain,'discarded_gold':[{'identity':x,'reason':reason} for x in loss],'gold_after_identities':ga});before=after
case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':ARM,'case_id':'cm-018','gold_total':1,'gold_identities':gs,'stages':ledger}
all_ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':case['accounting_unit'],'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':ARM,'declared_stage_ids':['catalogue','acquired','presented'],'cases':[case],'aggregate':{'cases':1,'presented_total':len(presented),'gold_total':1}}]}],'audit':{'adoption_separately_reported':True,'physical_provider_inputs_only':True,'full_paragraph_blocks_checked_separately':True}}
all_ledger['artifact_sha256']=hashlib.sha256(canon(all_ledger).encode()).hexdigest();put(O/'retrieval-ledger.json.gz',all_ledger)
blocks={x['block_id']:any(x['text'] in t for t in source_texts[gold['id']]) for x in gold['blocks'] if x['block_id'] in g['required_block_ids']}
claims=latest.get('case:ASSESS',{}).get('claims',[]);quotes=[]
for c in claims:
 for e in ([{'source_id':c['source_id'],'quote':c['quote']}] if 'source_id' in c and 'quote' in c else [])+c.get('evidence',[]):
  sid=e['source_id'];quotes.append(sid in orig and sid in selected.get('final_ids',[]) and bool(e.get('quote','').strip()) and e['quote'] in orig[sid]['text'])
commit_errors=[]
for ev in (x['payload'] for x in events if x['kind']=='CASE_JUDGMENT_ACCEPTED'):
 matching=[x for x in stages if x['created_seq']==ev.get('validated_seq')]
 if not matching or ev.get('payload_hash')!=hashlib.sha256(canon(matching[0]['payload']).encode()).hexdigest():commit_errors.append(ev)
checks={'physical_accounting':len(calls)==r['model_calls']==len(r['attempts']),'main_unchanged':r['active_pointer_before']==r['active_pointer_after']==base['pointer_sha256'],'frozen_files_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),'profile_matches_MAIN50_service':r['profile_sha256']==read(R/'04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context/artifacts/main-smoke.json')['execution_binding']['effective_profile_sha256'],'execution_binding_matches':latest.get('case:READ',{}).get('binding')==r.get('expected_binding'),'public_scope_valid':all(sources[s]['document_id'] in allowed for s in offered_ids),'citations_verified':bool(quotes) and all(quotes),'approved_judgment_hashes_valid':not commit_errors,'text_ref_bounds_valid':all(refs)}
output=r.get('output',{});text=output.get('answer',{}).get('text','')
if not text:text=output.get('text','')
(O/'answer.txt').write_text(text+'\n')
groups=defaultdict(lambda:{'calls':0,'seconds':0})
for a in r['attempts']:
 phase=a['phase'];name='request_entry' if 'request-entry' in phase else 'navigation' if 'source-law-navigation' in phase else 'assessment' if 'memory-assess' in phase else phase
 groups[name]['calls']+=1;groups[name]['seconds']+=a['seconds']
d={'case_id':'cm-018','http_status':r['http_status'],'model_calls':r['model_calls'],'llm_seconds':sum(x['seconds'] for x in r['attempts']),'groups':dict(groups),'attempts':r['attempts'],'usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd','seconds')},'checks':checks,'gold_presented':gold['id'] in offered_ids,'required_blocks_presented':blocks,'all_required_blocks_presented':bool(blocks) and all(blocks.values()),'corpus_roots':len(corpus),'acquired_roots':len(acquired),'presented_roots':len(presented),'adopted_ids':selected.get('final_ids',[]),'quote_count':len(quotes),'event_counts':dict(Counter(x['kind'] for x in events)),'quality_certified':False,'request_seconds_secondary':r.get('request_seconds'),'main_wiring':'unchanged','GENOS_execution':False}
put(O/'diagnostic.json',d);put(O/'model-decisions.json',calls)
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={ARM:{'status':'complete','requests':1,'http_status':r['http_status'],'model_calls':r['model_calls'],'llm_seconds':d['llm_seconds'],'accuracy':None,'semantic_review':'Separate original-bound final-output review follows'}},comparisons=[],usage={ARM:d['usage']},latency={ARM:{'llm_seconds':d['llm_seconds'],'p50':None,'p95':None,'reason':'One known request, no population latency estimate'}},error_taxonomy=[])
ra=m['retrieval_accounting'];ra['corpus_total']=len(corpus)
for k,v in [('before_filter',len(corpus)),('after_filter',len(acquired)),('presented_total',len(presented)),('presented_mean',len(presented)),('presented_p50',len(presented)),('presented_p95',len(presented)),('golden_recall',int(d['gold_presented'])),('selectivity',len(presented)/len(corpus))]:ra[k]={ARM:v}
ra['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json.gz');put(A/'실험/manifest.json',m)
print(json.dumps(d,ensure_ascii=False,indent=2))
