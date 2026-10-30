from common import *
from copy import deepcopy
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path']);assert active['generation']==120
assert all(sha(ROOT/n)==h for n,h in release['files'].items())
put(DES/'baseline.json',{'active':active,'release':release,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
saved=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1211-main120-domain-schema-live/artifacts/live/calls/call-001-normalize-a/request.json');schema=saved['response_format']['json_schema']['schema']
original=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1211-main120-domain-schema-live/artifacts/live/input-001.json')['schema']
expected={'observations':[],'coverage':[{'pointer':'','state':'NON_JUDGMENT','observation_ids':[],'reason':'synthetic'}],'unresolved':[]}
from jsonschema import Draft202012Validator
assert Draft202012Validator(original).is_valid(expected)
mini={'type':'object','additionalProperties':False,'required':list(expected),'properties':{'observations':{'type':'array','items':{'type':'string'}},'coverage':{'type':'array','items':{'type':'object','additionalProperties':False,'required':list(expected['coverage'][0]),'properties':{'pointer':{'type':'string'},'state':{'type':'string'},'observation_ids':{'type':'array','items':{'type':'string'}},'reason':{'type':'string'}}}},'unresolved':{'type':'array','items':{'type':'string'}}}}
def strip(s,keys):
 if isinstance(s,dict):return {k:strip(v,keys) for k,v in s.items() if k not in keys}
 if isinstance(s,list):return [strip(v,keys) for v in s]
 return s
def replace_pattern(s,old,new):
 if isinstance(s,dict):return {k:(new if k=='pattern' and v==old else replace_pattern(v,old,new)) for k,v in s.items()}
 if isinstance(s,list):return [replace_pattern(v,old,new) for v in s]
 return s
ref='^[A-Za-z][A-Za-z0-9_:-]{0,159}$';hashpat='^[0-9a-f]{64}$'
def remove_one(s,pat):
 if isinstance(s,dict):return {k:remove_one(v,pat) for k,v in s.items() if not(k=='pattern' and v==pat)}
 if isinstance(s,list):return [remove_one(v,pat) for v in s]
 return s
star=replace_pattern(schema,ref,'^[A-Za-z][A-Za-z0-9_:-]*$')
def bound(s):
 if isinstance(s,dict):
  v={k:bound(v) for k,v in s.items()}
  if v.get('pattern')=='^[A-Za-z][A-Za-z0-9_:-]*$':v['maxLength']=160
  return v
 if isinstance(s,list):return [bound(v) for v in s]
 return s
mini['properties']['observations']['items']={'type':'string','pattern':ref}
variants=[('full_ref_star_bound',bound(star),True),('full_ref_count32',replace_pattern(schema,ref,'^[A-Za-z][A-Za-z0-9_:-]{0,32}$'),True),('minimal_ref_original',mini,True),('full_ref_star',star,True)]
requests=[]
for name,s,template in variants:
 Draft202012Validator.check_schema(s);assert Draft202012Validator(s).is_valid(expected),name
 body={'model':saved['model'],'messages':[{'role':'system','content':'This is a synthetic JSON grammar diagnostic. Return exactly the supplied JSON object, with no extra text.'},{'role':'user','content':json.dumps(expected,ensure_ascii=False)}],'temperature':0,'stream':False,'response_format':{'type':'json_schema','json_schema':{'name':'domain_profile','strict':True,'schema':s}}}
 if template:body['chat_template_kwargs']={'enable_thinking':False}
 requests.append({'id':name,'request':body})
raw(DES/'requests.json',requests)
criteria={'scope':'Diagnosis only; none of the relaxed wire variants is a product proposal','hypothesis':'REF bounded repetition may trigger grammar compilation failure; compare star plus separate length bound, lower count32, minimal original REF, and star-only.','success':['Full versus category-specific removals and equivalent REF regex rewrites identify a reproducible failure trigger; original schema validates the expected empty JSON','Retain every request/response and reject/UNKNOWN, no success-shaped substitutions','No product/Main edits; actual schema and model/provider policy hashes bound'],'failure':'If controls are inconsistent or no one-variable contrast distinguishes the failure, mark cause unresolved and do not claim a compiler cause.','order':[r['id'] for r in requests],'budget':{'physical_max':5,'logical':4,'per_call_seconds':180,'batch_seconds':1800,'same_provider_retry':0,'switch_only_http429':1},'plan':'Run each predeclared variant once in order. Stop all remaining variants on UNKNOWN/resource/integrity failure. Same approved provider policy; record actual provider for attribution. No source texts or judgments in diagnostic prompts.','resource':{'startup_available_GiB':5,'running_available_GiB':3,'rss_GiB':4,'swap_growth_MiB':128,'address_space_GiB':6,'disk_GiB':20}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Completed synthetic control versus error/null per frozen schema variant; no legal quality metric',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':['ADR-1215-experiment-v1/diagnostic'],'changes':'Historical failed request schema, not historical model output replay','controls':'No modification to MAIN120'},{'id':'diagnostic','role':'candidate','derived_from':['baseline'],'changes':'4 predeclared REF quantifier requests','controls':'Same model/provider policy, synthetic prompt, no semantic scoring or product writes'}]);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['runs'][0].update(arm_ids=['diagnostic'],selection_rule='All4frozen REF variants once',artifact_path=str((RUN/'result.json').relative_to(ROOT)));m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}];m['dataset'].update(name='Synthetic valid empty observation for schema diagnosis',version='v1',frozen_source=str((DES/'requests.json').relative_to(ROOT)),sha256=sha(DES/'requests.json'));m['retrieval_accounting']['not_applicable_reason']='Synthetic schema diagnostics only, no retrieval';m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='No legal retrieval or gold.'
(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
files=sorted(set(release['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'})
c=ac.snapshot(ADR,'diagnostic',files,experiment_id=m['experiment_id'],arm_id='diagnostic',run_ids=['run-001']);ac.freeze(c);assert not ac.validate(c)
v=read(c/'candidate.json')['revisions'][-1];C=c/'revisions'/v['revision_id']/'snapshot';binding={'manifest_path':str((c/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(c/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(DES/'candidate.json',{'code_root':str(C.relative_to(ROOT)),'files':{n:sha(C/n) for n in files},'candidate_revision':binding})
print('Prepared8synthetic variants; no actual calls yet')
