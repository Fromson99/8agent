from common import *
from copy import deepcopy
x=read(ART/'live/execution.json');f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root']
packed=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def expand(s):
 defs=s.get('$defs',{})
 def walk(v,stack=()):
  if isinstance(v,dict):
   if set(v)=={'$ref'}:
    r=v['$ref'];assert r.startswith('#/$defs/') and r not in stack
    return walk(defs[r[8:]],stack+(r,))
   return {k:walk(c,stack) for k,c in v.items() if k!='$defs'}
  if isinstance(v,list):return [walk(c,stack) for c in v]
  return v
 return walk(s)
rows=[]
for i,d in enumerate(sorted((ART/'live/calls').glob('call-*')),1):
 request=read(d/'request.json');response=read(d/'response.json');original=read(ART/f'live/input-{i:03d}.json');wire=read(ART/f'live/wire-{i:03d}.json')
 s=request['response_format']['json_schema']['schema'];normalized=deepcopy(request)
 for key in ('provider','reasoning','usage'):normalized.pop(key)
 assert normalized==wire
 assert expand(s)==original['schema']
 assert request['messages'][0]['content']==original['prompt']
 assert json.loads(request['messages'][1]['content'])==original['context']
 assert request['response_format']['type']=='json_schema' and request['response_format']['json_schema']['strict'] is True
 assert not {'max_tokens','max_completion_tokens','max_output_tokens'}&request.keys()
 choice=response['choices'][0];row={'call':i,'phase':original['phase'],'request':{'path':str((d/'request.json.gz').relative_to(ROOT)),'sha256':sha(d/'request.json.gz')},'response':{'path':str((d/'response.json.gz').relative_to(ROOT)),'sha256':sha(d/'response.json.gz')},'requested_provider':request['provider'],'actual_provider':response['provider'],'model':response['model'],'finish_reason':choice['finish_reason'],'content':choice['message']['content'],'usage':response.get('usage'),'original_schema_chars':len(packed(original['schema'])),'wire_schema_chars':len(packed(s)),'original_schema_sha256':hashlib.sha256(packed(original['schema']).encode()).hexdigest(),'wire_schema_sha256':hashlib.sha256(packed(s).encode()).hexdigest(),'request_chars':len(packed(request)),'system_chars':len(request['messages'][0]['content']),'user_chars':len(request['messages'][1]['content']),'schema_exact_expansion':True,'messages_exact':True,'strict':True,'output_cap_fields':[]}
 rows.append(row)
assert len(rows)==2 and x['calls']==2 and len(x['stage_receipts'])==2
jobs=[];sent=[];kinds={}
for p in (ART/'live/objects').rglob('*.json'):
 v=read(p)
 if not isinstance(v,dict):continue
 if v.get('kind'):kinds[v['kind']]=kinds.get(v['kind'],0)+1
 if v.get('kind')=='JOB' and v.get('phase')=='INCOMPLETE_RESPONSE':
  jobs.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'stage':v['stage'],'phase':v['phase'],'status_code':v['receipt']['response']['status_code'],'attempt':v['attempt']})
 if v.get('status')=='SENT_ONCE' and 'schema_projection' in v:sent.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'projection':v['schema_projection']})
assert len(jobs)==2 and all(j['status_code']==200 for j in jobs)
assert len(sent)==2 and all(r['projection']['wire_schema_chars']==10136 for r in sent)
resource=[read(ART/'live/resource-baseline.json')]
with gzip.open(ART/'live/resource-samples.jsonl.gz','rt') as stream:resource += [json.loads(line) for line in stream if line.strip()]
checks={'frozen488_equal':len(f['files'])==488 and all(sha(C/n)==h for n,h in f['files'].items()),'serving487_working_selected_equal':all(sha(ROOT/n)==h and sha(ROOT/b['release']['code_root']/n)==h for n,h in b['release']['files'].items()),'frozen_inputs':all(sha(ROOT/n)==h for n,h in f['inputs'].items()),'frozen_runner':all(sha(ROOT/n)==h for n,h in f['scripts'].items()),'no_import_leaks':not x['imports_outside_candidate'],'main120_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],'data_manifest_unchanged':sha(ROOT/b['data_path']/'manifest.json')==b['generation_manifest_sha256'],'published_false':not x['published'] and x['head']=={'publication_id':None,'sequence':0},'no_knowledge_approval':not x['knowledge_approved'],'resource_not_stopped':not x['resource_stop'],'two_exact_wire_schema':all(r['schema_exact_expansion'] and r['messages_exact'] for r in rows),'two_failed_jobs_preserved':len(jobs)==2,'actual_authoring_projection_receipts':len(sent)==2}
assert all(checks.values()),checks
result={'checks':checks,'wire_calls':rows,'failed_jobs':jobs,'authoring_projection_receipts':sent,'resource':{'samples':len(resource),'min_available_bytes':min(r['available'] for r in resource),'peak_worker_rss_bytes':max(r['rss'] for r in resource),'max_swap_growth_bytes':max(r['swap_used']-resource[0]['swap_used'] for r in resource),'resource_stop':x['resource_stop']},'calls':x['calls'],'provider_switches':x['provider_switches'],'seconds_from_dispatch':x['seconds'],'historical_comparison':'ADR1206:3physical/429+NearAI2 finish_error, original159226 chars; current2physical/Parasail2 finish_error, wire10136 chars. Same failure category across different provider/time/current cumulative code; not a causal paired test.','unknown':sum(r['status']=='UNKNOWN' for r in x['stage_receipts']),'vendor_internal_cause':None}
put(ART/'audit.json',result)
print('Audit PASS; two actual strict wire10136 exact; HTTP200/error/null2; originals/jobs/receipts preserved; MAIN120 unchanged')
print('resources',result['resource'])
print('request sizes',[(r['request_chars'],r['system_chars'],r['user_chars']) for r in rows])
