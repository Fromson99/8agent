from common import *
from copy import deepcopy
x=read(ART/'live/execution.json');f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root']
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.wire_schema import REF_PATTERN,PORTABLE_REF_PATTERN
from semantic_runtime.ontology_work import observations as obs, recorded_fields as roles, authoring_semantics as sem
from semantic_runtime.ontology_work.profile import compile_profile
from semantic_runtime.ontology_work.assembly_compiler import verify_package
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
rows=[];source_inputs=[];repairs=[]
for i,stage in enumerate(x['stage_receipts'],1):
 original=read(ART/f'live/input-{i:03d}.json')
 if 'repair' in original['context']:repairs.append({'phase':stage['phase'],'error':original['context']['repair']['previous']['error']})
 if stage['phase'].startswith('source-'):
  context=original['context'];allowed={'operation','originals','profile_hash','call_budget','repair'}
  assert set(context)<=allowed
  source_inputs.append({'phase':stage['phase'],'context_keys':list(context),'independent':True,'originals':len(context['originals'])})
 if stage['physical_after']==stage['physical_before']:continue
 wire=read(ART/f'live/wire-{i:03d}.json')
 for call in range(stage['physical_before']+1,stage['physical_after']+1):
  d=next((ART/'live/calls').glob(f'call-{call:03d}-*'));request=read(d/'request.json');response=read(d/'response.json') if (d/'response.json').exists() else {}
  normalized=deepcopy(request)
  for key in ('provider','reasoning','usage'):normalized.pop(key,None)
  assert normalized==wire
  schema=request['response_format']['json_schema']['schema'];assert expand(schema)==original['schema']
  assert request['messages'][0]['content']==original['prompt'] and json.loads(request['messages'][1]['content'])==original['context']
  assert request['response_format']['json_schema']['strict'] and not {'max_tokens','max_completion_tokens','max_output_tokens'}&request.keys()
  choice=(response.get('choices') or [{}])[0];content=(choice.get('message') or {}).get('content')
  rows.append({'call':call,'phase':stage['phase'],'finish_reason':choice.get('finish_reason'),'content_null':content is None,'error':response.get('error'),'provider':response.get('provider'),'usage':response.get('usage'),'wire_schema_chars':len(packed(schema)),'request_chars':len(packed(request)),'messages_exact':True,'schema_equivalent':True})
profile=compile_profile(read(C/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json'),read(C/'00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json'))
normalizations=[];previews=[]
for j,row in enumerate(x['results']):
 case=row['case_id'];suffix='a' if j==0 else 'b'
 if row['normalization']=='REUSED_VERIFIED':
  n=read(ART/f'live/{case}-normalized.json')['normalized'];raw_event=read(ART/'live/objects/objects'/f"{n['raw_event_ref']}.json")
  obs.validate_observations(n['proposal'],raw_event,profile,n['glossary_candidates'])
  prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1228-source-first-authoring-live/artifacts/live'
  previous=read(prior/f'{case}-normalized.json')['normalized'];assert previous==n
  canonical=n['proposal'];receipt=n['model_receipt']['normalization_assembly']
  normalizations.append({'case':case,'coverage':len(canonical['coverage']),'locators':receipt['assembled_locators'],'observations':len(canonical['observations']),'absent_roles':all(o[k]['state']=='NOT_RECORDED' for o in canonical['observations'] for k in ('reason','purpose')),'original_validation':True,'assembly_exact':True})
 if row['accumulation']=='DRAFT_SAVED':
  k=read(ART/f'live/{case}-knowledge.json');package=read(ART/f'live/{case}-preview.json');verify_package(package,recompile=True)
  attempts=[i for i,s in enumerate(x['stage_receipts'],1) if s['phase']=='accumulate-'+suffix and s['status']=='RESPONSE_RECEIVED'];i=attempts[-1]
  inp=read(ART/f'live/input-{i:03d}.json');analysis=inp['context']['source_analysis'];originals=k['originals']
  sem.validate_source(analysis,sem.source_schema(profile,originals),originals)
  canonical,receipt=sem.restore(read(ART/f'live/output-{i:03d}.json'),inp['schema'],analysis,originals)
  assert canonical==k['proposal'] and receipt==k['model_receipt']['semantic_assembly'] and analysis==k['model_receipt']['source_analysis']
  previews.append({'case':case,'revision':k['revision'],'nodes':len(package['graph']['nodes']),'edges':len(package['graph']['edges']),'paths':[{'id':p['id'],'status':p['status'],'unresolved':p['unresolved']} for p in package['paths']],'history':len(k['comparison_history']),'observations':len(k['observation_ledger']),'diff':k['diff'],'recompiled_exact':True,'semantic_assembly_exact':True})
resources=[read(ART/'live/resource-baseline.json')]
with gzip.open(ART/'live/resource-samples.jsonl.gz','rt') as stream:resources += [json.loads(line) for line in stream if line.strip()]
checks={'candidate490_exact':len(f['files'])==490 and all(sha(C/n)==h for n,h in f['files'].items()),'working487_baseline':all(sha(ROOT/n)==h for n,h in b['release']['files'].items()),'frozen_inputs':all(sha(ROOT/n)==h for n,h in f['inputs'].items()),'frozen_scripts':all(sha(ROOT/n)==h for n,h in f['scripts'].items()),'main122_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],'data_unchanged':sha(ROOT/b['data_path']/'manifest.json')==b['generation_manifest_sha256'],'no_import_leaks':not x['imports_outside_candidate'],'no_approval_publication':not x['published'] and not x['knowledge_approved'],'source_independence':all(r['independent'] for r in source_inputs),'within_budget':x['calls']<=4 and read(DES/'continuation.json')['previous_physical_calls']+x['calls']<=9, 'prior_unchanged':all(sha(ROOT/n)==h for n,h in read(DES/'continuation.json')['files'].items()),'no_resource_stop':not x['resource_stop']}
assert all(checks.values()),checks
result={'checks':checks,'wire_calls':rows,'calls':x['calls'],'seconds':x['seconds'],'reported_cost_usd':sum(u.get('cost_usd') or 0 for u in x['usage']),'unknown':sum(s['status']=='UNKNOWN' for s in x['stage_receipts']),'error_null_count':sum(r['finish_reason']=='error' and r['content_null'] for r in rows),'complete_responses':sum(r['finish_reason']=='stop' and not r['content_null'] for r in rows),'source_inputs':source_inputs,'normalization_audit':normalizations,'previews':previews,'repair_errors':repairs,'resource':{'min_available_GiB':min(r['available'] for r in resources)/1024**3,'peak_rss_MiB':max(r['rss'] for r in resources)/1024**2,'max_swap_growth_MiB':max(r['swap_used']-resources[0]['swap_used'] for r in resources)/1024**2},'case_statuses':[{k:v for k,v in r.items() if k not in ('observation','knowledge')} for r in x['results']]}
put(ART/'audit.json',result);print({k:v for k,v in result.items() if k not in ('wire_calls','checks','previews','repair_errors')})
