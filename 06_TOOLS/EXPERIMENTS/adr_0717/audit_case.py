"""Inspect one finished request before the next; no product or evaluator calls."""
from pathlib import Path
from collections import Counter
import argparse,gzip,hashlib,json,sqlite3,tarfile,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0717-main50-cm51-sequential-profile';D=A/'artifacts/design';ARM='measured-main50'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):
 if p.suffix=='.gz':
  with gzip.open(p,'wt',encoding='utf-8') as f:f.write(canon(v)+'\n')
 else:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ro(p):
 db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
p=argparse.ArgumentParser();p.add_argument('--case',required=True);args=p.parse_args();O=A/'artifacts/run-001'/args.case
assert not (O/'diagnostic.json').exists();r=read(O/'result.json');f=read(D/'freeze.json');base=read(D/'baseline.json');m=read(A/'실험/manifest.json')
allowed=set(read(R/f['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
nav=ro(R/f['source_generation']/'navigation/navigation.sqlite')
meta={x[0]:{'doc_id':x[1],'node':int(x[2])} for x in nav.execute("select id,json_extract(json,'$.document_id'),json_extract(json,'$.unit_id') from source")};nav.close()
def identities(ids):return [json.loads(x) for x in sorted({canon(meta[s]) for s in ids if s in meta})]
events=[];stages=[];acquired_ids=set();j=list((O/'runtime').rglob('journal.sqlite'))
if j:
 assert len(j)==1;db=ro(j[0]);events=[{'seq':x['seq'],'kind':x['kind'],'payload':json.loads(x['payload_json'])} for x in db.execute('select * from event order by seq')];stages=[{'stage':x['entity_id'],'created_seq':x['created_seq'],'payload':json.loads(x['payload_json'])} for x in db.execute("select * from entity_version where kind='case_stage' order by created_seq")];acquired_ids={x[0] for x in db.execute('select distinct source_id from evidence_unit')};db.close()
latest={x['stage']:x['payload'] for x in stages};selected=latest.get('case:SELECT',{});orig={x['source_id']:x for x in selected.get('selected_originals',[])}
offered_ids=set();calls=[]
def scan(v):
 if isinstance(v,dict):
  if v.get('source_id') in meta and isinstance(v.get('text'),str) and v['text']:offered_ids.add(v['source_id'])
  for x in v.values():scan(x)
 elif isinstance(v,list):
  for x in v:scan(x)
for call in sorted((O/'provider').glob('call-*')):
 req=read(call/'request.json');body=req.get('body',req);view=json.loads(body['messages'][1]['content'])['view'];scan(view);decision=None
 if (call/'response.json').exists():
  try:decision=json.loads(read(call/'response.json')['choices'][0]['message']['content'])
  except (KeyError,ValueError,TypeError):pass
 calls.append({'call':call.name,'phase':view.get('source_stage',view.get('phase')),'next_action':decision.get('next_action') if isinstance(decision,dict) else None,'disposition':decision.get('disposition') if isinstance(decision,dict) else None,'queries':decision.get('queries') if isinstance(decision,dict) else None,'reason':decision.get('reason') if isinstance(decision,dict) else None,'request_sha256':sha(call/'request.json'),'response_sha256':sha(call/'response.json') if (call/'response.json').exists() else None})
quotes=[]
for c in latest.get('case:ASSESS',{}).get('claims',[]):
 for e in ([{'source_id':c['source_id'],'quote':c['quote']}] if 'source_id' in c and 'quote' in c else [])+c.get('evidence',[]):
  sid=e['source_id'];quotes.append(sid in orig and sid in selected.get('final_ids',[]) and bool(e.get('quote','').strip()) and e['quote'] in orig[sid]['text'])
checks={'physical_accounting':len(calls)==r['model_calls']==len(r['attempts']),'main_unchanged':r['active_pointer_before']==r['active_pointer_after']==base['pointer_sha256'],'profile_matches_MAIN50_service':r['profile_sha256']==read(R/'04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context/artifacts/main-smoke.json')['execution_binding']['effective_profile_sha256'],'public_scope_valid':all(meta[s]['doc_id'] in allowed for s in offered_ids),'quotes_valid_when_present':all(quotes)}
checks['execution_binding_matches']=latest.get('case:READ',{}).get('binding')==r.get('expected_binding') if latest.get('case:READ') else None
accepted_errors=[]
for e in events:
 if e['kind']=='CASE_JUDGMENT_ACCEPTED':
  ev=e['payload'];matching=[x for x in stages if x['created_seq']==ev.get('validated_seq')]
  if not matching or ev.get('payload_hash')!=hashlib.sha256(canon(matching[0]['payload']).encode()).hexdigest():accepted_errors.append(e['seq'])
checks['approved_judgment_hashes_valid']=not accepted_errors
ats=r['attempts'];assessment=[x for x in ats if x['phase'].startswith('memory-assess')];investigation=[x for x in ats if not x['phase'].startswith('memory-assess')]
terminal_start=len(ats)
while terminal_start>0 and ats[terminal_start-1]['phase'].startswith('memory-assess'):terminal_start-=1
counts=Counter(x['kind'] for x in events);steps=[x['payload'] for x in events if x['kind']=='INVESTIGATION_CHAIN_STEP'];acts=Counter(x.get('action') for x in steps)
rejected=[{'phase':x['payload'].get('phase'),'error':x['payload'].get('error',x['payload'].get('diagnostics',{}).get('error_message')),'decision':{k:x['payload'].get('decision',{}).get(k) for k in ('next_action','queries','reason')}} for x in events if x['kind']=='LAW_DECISION_REJECTED']
trace=[{k:x.get(k) for k in ('number','action','status','reason','queries','structure_filter','outcome','progress')} for x in steps]
gold=next(x for x in read(D/'gold.json')['cases'] if x['case_id']==args.case);gs={x['source_id'] for x in gold['references']};main_gs={x['source_id'] for x in gold['references'] if x['evidence_role']=='MAIN'}
output=r.get('output',{});answer=output.get('answer',{}).get('text','') if isinstance(output.get('answer'),dict) else output.get('text','');(O/'answer.txt').write_text(answer+'\n')
out={'case_id':args.case,'http_status':r['http_status'],'answer_status':output.get('answer_status',output.get('assembly',{}).get('term_agent',{}).get('status')),'all_model_calls':r['model_calls'],'all_model_seconds':sum(x['seconds'] for x in ats),'investigation_calls':len(investigation),'investigation_seconds':sum(x['seconds'] for x in investigation),'assessment_calls':len(assessment),'assessment_seconds':sum(x['seconds'] for x in assessment),'before_terminal_assessment_calls':terminal_start,'before_terminal_assessment_seconds':sum(x['seconds'] for x in ats[:terminal_start]),'entry_calls':sum('request-entry' in x['phase'] for x in ats),'repair_calls':sum('repair' in x['phase'] for x in ats),'assessment_reentries':counts['ASSESSMENT_GAP_REENTRY_PLANNED'],'research':acts['RESEARCH'],'returns':acts['RETURN_TO'],'read_choices':sum(v for k,v in acts.items() if isinstance(k,str) and k.startswith('READ')),'fulltext_global':counts['LAW_FULLTEXT_DIRECTORY'],'fulltext_scoped':counts['LAW_SCOPED_FULLTEXT'],'structure_search':counts['LAW_STRUCTURE_DIRECTORY'],'actions':dict(acts),'event_counts':dict(counts),'acquired_ids':sorted(acquired_ids),'presented_ids':sorted(offered_ids),'adopted_ids':selected.get('final_ids',[]),'gold_total':len(gs),'gold_presented':len(gs&offered_ids),'main_gold_total':len(main_gs),'main_gold_presented':len(main_gs&offered_ids),'gold_missing':sorted(gs-offered_ids),'quote_count':len(quotes),'has_supported_claims':bool(quotes) and all(quotes),'checks':checks,'rejected':rejected,'trace':trace,'calls':calls,'usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd')},'semantic_correctness':'not_independently_scored','request_seconds_secondary':r.get('request_seconds'),'physical_attempts':ats}
put(O/'diagnostic.json',out)
recalls=[x['payload'] for x in stages if x['stage']=='case:RECALL'];corpus_ids={s for x in recalls for s in x.get('corpus_ids',[])} or {s for s,v in meta.items() if v['doc_id'] in allowed};corpus=identities(corpus_ids);acquired=identities(acquired_ids);presented=identities(offered_ids);gids=identities(gs);gkeys={canon(x) for x in gids};before=[];ledger=[]
for i,after in enumerate((corpus,acquired,presented)):
 plan=m['design']['retrieval_stage_plan']['stages_by_arm'][ARM][i];bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())];gb=[bm[k] for k in sorted(bm.keys()&gkeys)];ga=[am[k] for k in sorted(am.keys()&gkeys)];gain=[x for x in added if canon(x) in gkeys];loss=[x for x in discarded if canon(x) in gkeys];reason=['Bound catalogue metadata','Not acquired in this request','Original absent from physical provider input'][i]
 ledger.append({**plan,'executed':True,'skip_reason':None,'before':before,'after':after,'added':added,'discarded':discarded,'before_count':len(before),'after_count':len(after),'added_count':len(added),'discarded_count':len(discarded),'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':len(gids),'golden_recall':len(ga)/len(gids) if gids else None,'gold_before':len(gb),'gold_added':len(gain),'gold_discarded':len(loss),'gold_after':len(ga),'gold_before_identities':gb,'gold_added_identities':gain,'discarded_gold':[{'identity':x,'reason':reason} for x in loss],'gold_after_identities':ga});before=after
case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':ARM,'case_id':args.case,'gold_total':len(gids),'gold_identities':gids,'stages':ledger};put(O/'ledger-case.json.gz',case)
# Raw generated records are only removed after byte-for-byte archive verification.
roots=[p for p in (O/'provider',O/'runtime',O/'binding-runtime') if p.exists()];files=[p for root in roots for p in sorted(root.rglob('*')) if p.is_file()];assert all(not p.is_symlink() for p in files)
rows=[{'path':str(p.relative_to(O)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files];archive=O/'raw.tar.gz';assert not archive.exists()
with tarfile.open(archive,'w:gz',compresslevel=6) as t:
 for p in files:t.add(p,arcname=str(p.relative_to(O)),recursive=False)
expected={x['path']:x for x in rows}
with tarfile.open(archive,'r:gz') as t:
 assert len(t.getmembers())==len(rows)
 for member in t:
  rr=expected[member.name];assert member.size==rr['bytes'] and hashlib.file_digest(t.extractfile(member),'sha256').hexdigest()==rr['sha256']
for row in rows:assert sha(O/row['path'])==row['sha256']
put(O/'raw-archive.json',{'archive':str(archive.relative_to(R)),'sha256':sha(archive),'archive_bytes':archive.stat().st_size,'original_bytes':sum(x['bytes'] for x in rows),'files':rows,'verified':True,'restore':'Extract into a new empty directory; verify every member SHA/bytes. Never overwrite an existing case.','removed_only_verified_duplicate_raw_directories':[str(p.relative_to(O)) for p in roots]})
for root in roots:shutil.rmtree(root)
print(json.dumps({k:out[k] for k in ('case_id','http_status','investigation_calls','investigation_seconds','assessment_calls','assessment_seconds','research','returns','read_choices','assessment_reentries','main_gold_presented','main_gold_total','checks')},ensure_ascii=False),flush=True)
if any(v is False for v in checks.values()):raise SystemExit('Integrity check failed; stop before next request')
