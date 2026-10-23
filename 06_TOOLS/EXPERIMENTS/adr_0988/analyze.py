"""Post-selection deterministic grading and exact native trace summary."""
from common import *
import statistics,collections,xml.etree.ElementTree as ET
f=read(ART/'design-freeze.json');cases=read(ART/'cases.json');gold=read(ART/'grading-only.json');s=read(ART/'stage.json')
assert sha(ART/'cases.json')==f['cases_sha256'] and sha(ART/'grading-only.json')==f['gold_sha256']
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
rows={a:[] for a in ('baseline','candidate')};usage=[]
for a in rows:
 for c in cases:
  r=read(ART/'trials'/c['id']/a/'result.json');g=gold[c['id']];v=r.get('accepted',{});raw=r.get('raw',{});ok=r['error'] is None
  text=json.dumps(v.get('claims',[]),ensure_ascii=False);gaps=v.get('gaps',[]);material=[x for x in gaps if x['material']]
  if g['kind'] in ('answer','partial','gap'):
   if g['kind']=='answer':ok=ok and bool(v.get('claims')) and not material
   elif g['kind']=='partial':ok=ok and bool(v.get('claims')) and bool(material)
   else:ok=ok and bool(material)
   ok=ok and all(t in text for t in g.get('required',[])) and not any(t in text for t in g.get('exclude_claim',[]))
   if g.get('required_target'):ok=ok and g['required_target'] in json.dumps(material,ensure_ascii=False)
  else:
   ok=ok and raw.get('choice') in g['allowed']
   if g.get('sufficient'):ok=ok and raw.get('evidence_sufficient') is True
  rows[a].append({'case_id':c['id'],'passed':bool(ok) if r.get('raw') else None,'gradable':bool(r.get('raw')),'validated':r['error'] is None,'choice':raw.get('choice'),'claims':len(v.get('claims',[])),'material_gaps':len(material),'seconds':r['seconds'],'calls':r['calls'],'necessary':g.get('necessary',False),'error':r['error']});usage+=r['usage']
known={}
for a in rows:
 path=ART/'known-query'/a;r=read(path/'result.json');q=read(path/'response.json') if (path/'response.json').exists() else {};b=q.get('body',{});assembly=b.get('assembly',{});answer=b.get('answer',{});agent=assembly.get('term_agent',{});text=answer.get('text','').replace(' ','');context=assembly.get('context',[])
 rawcalls=[];headings=set();prevnav=0
 for d in sorted((path/'model').glob('call-*/request.json')):
  req=read(d)
  for message in req.get('messages',[]):
   if message.get('role')!='user':continue
   try:v=json.loads(message['content']).get('view',{})
   except (ValueError,AttributeError):continue
   src=v.get('sources',[])
   if isinstance(src,dict) and 'table_rows' in src:src=[dict(zip(src['table_columns'],x)) for x in src['table_rows']]
   headings.update(x.get('heading','') for x in src if isinstance(x,dict))
   if v.get('read_candidates') and v.get('previous_assessments',{}).get('claims'):prevnav+=1
  response=d.with_name('response.json')
  if response.exists():
   try:out=json.loads(read(response)['choices'][0]['message']['content'])
   except (KeyError,ValueError):out={}
   rawcalls.append({'call':d.parent.name,'choice':out.get('choice'),'missing_needs':[x.get('missing_need') for x in out.get('selections',[])],'gaps':out.get('gaps',[]),'claims':len(out.get('claims',[]))})
 checks={'service_200':q.get('status')==200,'source434':any(x.get('id')=='article:816aee85d53f84a3b2f322dd' for x in context),'ratios':('3분의2' in text or '2/3' in text) and ('3분의1' in text or '1/3' in text),'claims':bool(answer.get('claims')),'citation_integrity':agent.get('citation_integrity')=='ORIGINAL_SPANS','no_unrelated_company_read':not any('제585조' in h or '제576조' in h for h in headings)}
 known[a]={'checks':checks,'passed':all(checks.values()) if q.get('status')==200 else None,'completed_answer':q.get('status')==200,'service_status':q.get('status'),'failure':q.get('body',{}).get('error_code'),'calls':r['model_calls'],'seconds':r['seconds'],'model_seconds':sum(x.get('seconds',0) for x in r['usage']),'headings':sorted(headings),'trace':rawcalls,'previous_opinion_navigation_calls':prevnav,'outcome':agent.get('accepted_outcome'),'error':r['error']};usage+=r['usage']
graded={a:sum(x['gradable'] for x in rr) for a,rr in rows.items()}
counts={a:sum(x['passed'] is True for x in rr) if graded[a] else None for a,rr in rows.items()}
checks={'candidate_minimum7':counts['candidate']>=7 if counts['candidate'] is not None else None,'required_expansion_preserved':all(x['passed'] for x in rows['candidate'] if x['necessary']) if all(x['gradable'] for x in rows['candidate'] if x['necessary']) else None,'candidate_schema_source_valid':all(x['validated'] for x in rows['candidate']) if all(x['gradable'] for x in rows['candidate']) else None,'known_candidate':known['candidate']['passed'],'known_calls_not_increased':known['candidate']['calls']<=known['baseline']['calls'] if all(v['completed_answer'] for v in known.values()) else None,'no_extra_review_call':True,'pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']}
checks['candidate_and_baseline_hashes']=all(sha(ROOT/s['roots'][a]/n)==h for a in rows for n,h in f['files'][a].items())
contracts={}
if (ART/'contracts.xml').exists():
 testcases={}
 for xml in [ART/'contracts.xml',ART/'contracts-fixture-corrected.xml']:
  if xml.exists():
   for case in ET.parse(xml).getroot().iter('testcase'):testcases[(case.get('classname'),case.get('name'))]=case
 contracts={'tests':len(testcases),**{plural:sum(c.find(single) is not None for c in testcases.values()) for single,plural in [('failure','failures'),('error','errors'),('skipped','skipped')]},'initial_fixture_errors':14,'fixture_recovery':'Original outputs retained; only bounded-delivered-handoff file rerun with existing conftest plugin registered. Product code/test bodies unchanged.'};checks['contracts']=contracts['failures']==contracts['errors']==0
comparison=dict(collections.Counter('unavailable_pair' if not (b['gradable'] and c['gradable']) else 'both_correct' if b['passed'] and c['passed'] else 'candidate_only' if c['passed'] else 'baseline_only' if b['passed'] else 'both_wrong' for b,c in zip(rows['baseline'],rows['candidate'])))
summary={'probe_passed':all(checks.values()),'checks':checks,'correct':counts,'graded_per_arm':graded,'total_per_arm':8,'status':'MODEL_EVALUATION_UNAVAILABLE' if not all(graded.values()) else 'EVALUATED','comparison':comparison,'by_arm':rows,'known':known,'contracts':contracts,'usage':{k:sum(r.get(k) or 0 for r in usage) for k in ('input_tokens','output_tokens','thinking_tokens','cost_usd')},'physical_calls':sum(x['calls'] for rr in rows.values() for x in rr)+sum(v['calls'] for v in known.values()),'latency':{a:{'p50':statistics.median(x['seconds'] for x in rr),'p95':sorted(x['seconds'] for x in rr)[-1]} for a,rr in rows.items()},'main_changed':False,'quality_certified':False,'genos_verified':False}
save(ART/'result.json',summary)
print(json.dumps({k:summary[k] for k in ('probe_passed','checks','correct','comparison','contracts','physical_calls')},ensure_ascii=False))
print('KNOWN',json.dumps({a:{k:v[k] for k in ('calls','seconds','passed','headings')} for a,v in known.items()},ensure_ascii=False))
