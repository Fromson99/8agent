from common import *
from copy import deepcopy
x=read(ART/'live/execution.json');f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root']
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.wire_schema import REF_PATTERN,PORTABLE_REF_PATTERN
packed=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def expand(s):
 defs=s.get('$defs',{})
 def walk(v,stack=()):
  if isinstance(v,dict):
   if set(v)=={'$ref'}:
    r=v['$ref'];assert r.startswith('#/$defs/') and r not in stack
    return walk(defs[r[8:]],stack+(r,))
   return {k:(REF_PATTERN if k=='pattern' and c==PORTABLE_REF_PATTERN else walk(c,stack)) for k,c in v.items() if k!='$defs'}
  if isinstance(v,list):return [walk(c,stack) for c in v]
  return v
 return walk(s)
rows=[]
for i,stage in enumerate(x['stage_receipts'],1):
 original=read(ART/f'live/input-{i:03d}.json');wire=read(ART/f'live/wire-{i:03d}.json')
 for call in range(stage['physical_before']+1,stage['physical_after']+1):
  d=next((ART/'live/calls').glob(f'call-{call:03d}-*'));request=read(d/'request.json');response=read(d/'response.json') if (d/'response.json').exists() else {}
  normalized=deepcopy(request)
  for key in ('provider','reasoning','usage'):normalized.pop(key)
  assert normalized==wire
  s=request['response_format']['json_schema']['schema'];assert expand(s)==original['schema']
  assert request['messages'][0]['content']==original['prompt'] and json.loads(request['messages'][1]['content'])==original['context']
  assert request['response_format']['json_schema']['strict'] is True
  assert not {'max_tokens','max_completion_tokens','max_output_tokens'}&request.keys()
  choice=(response.get('choices') or [{}])[0];content=(choice.get('message') or {}).get('content')
  rows.append({'call':call,'phase':stage['phase'],'finish_reason':choice.get('finish_reason'),'content_null':content is None,'content_chars':len(content or ''),'error':response.get('error'),'actual_provider':response.get('provider'),'usage':response.get('usage'),'original_schema_chars':len(packed(original['schema'])),'wire_schema_chars':len(packed(s)),'request_chars':len(packed(request)),'equivalent_schema':True,'messages_exact':True,'request':{'path':str((d/'request.json.gz').relative_to(ROOT)),'sha256':sha(d/'request.json.gz')},'response':{'path':str((d/'response.json').relative_to(ROOT)),'sha256':sha(d/'response.json')} if (d/'response.json').exists() else None})
resources=[read(ART/'live/resource-baseline.json')]
with gzip.open(ART/'live/resource-samples.jsonl.gz','rt') as stream:resources += [json.loads(line) for line in stream if line.strip()]
checks={'candidate488_exact':len(f['files'])==488 and all(sha(C/n)==h for n,h in f['files'].items()),'working487_baseline':all(sha(ROOT/n)==h for n,h in b['release']['files'].items()),'frozen_inputs':all(sha(ROOT/n)==h for n,h in f['inputs'].items()),'frozen_runner':all(sha(ROOT/n)==h for n,h in f['scripts'].items()),'no_import_leaks':not x['imports_outside_candidate'],'main121_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],'data_unchanged':sha(ROOT/b['data_path']/'manifest.json')==b['generation_manifest_sha256'],'not_published':not x['published'] and x['head']=={'publication_id':None,'sequence':0},'not_approved':not x['knowledge_approved'],'resource_not_stopped':not x['resource_stop'],'all_wire_checked':len(rows)==x['calls'] and all(r['equivalent_schema'] and r['messages_exact'] for r in rows)}
assert all(checks.values()),checks
result={'checks':checks,'wire_calls':rows,'calls':x['calls'],'seconds':x['seconds'],'error_null_count':sum(r['finish_reason']=='error' and r['content_null'] for r in rows),'complete_responses':sum(r['finish_reason']=='stop' and not r['content_null'] for r in rows),'unknown':sum(r['status']=='UNKNOWN' for r in x['stage_receipts']),'reported_cost_usd':sum(u.get('cost_usd') or 0 for u in x['usage']),'resource':{'min_available_GiB':min(r['available'] for r in resources)/1024**3,'peak_rss_MiB':max(r['rss'] for r in resources)/1024**2,'max_swap_growth_MiB':max(r['swap_used']-resources[0]['swap_used'] for r in resources)/1024**2},'provider_internal_logs_available':False}
from semantic_runtime.ontology_work import observations as obs
from semantic_runtime.ontology_work.profile import compile_profile
from semantic_runtime.contracts import digest
profile=compile_profile(read(C/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json'))
normalized=[]
for case,attempt in [('a',1),('b',4)]:
 n=read(ART/f'live/saved-007-{case}-normalized.json')['normalized']
 raw_event=read(ART/'live/objects/objects'/f"{n['raw_event_ref']}.json")
 obs.validate_observations(n['proposal'],raw_event,profile,n['glossary_candidates'])
 restored,receipt=obs.restore_normalization(read(ART/f'live/output-{attempt:03d}.json'),raw_event)
 assert restored==n['proposal'] and receipt==n['model_receipt']['normalization_assembly']
 normalized.append({'case':case,'coverage':len(restored['coverage']),'locators':receipt['assembled_locators'],'original_validator':True,'receipt_exact':True})
result['normalization_audit']=normalized
put(ART/'audit.json',result);print({k:v for k,v in result.items() if k not in ('wire_calls','checks')})
