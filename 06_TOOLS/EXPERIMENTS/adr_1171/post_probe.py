"""Offline audit of actual responses; no retries or generated legal conclusions."""
from common import *
from types import SimpleNamespace as NS
import jsonschema,copy
f=read(DES/'freeze.json');C=ROOT/f['code_root'];sys.path[:0]=[str(C/'02_BACKEND')]
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent.source_goal_control import validate
from semantic_runtime.legal_agent.errors import ContractError
from resource_guard import self_test,sample
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
rows=[];usage=[]
for src in read(DES/'probe-inputs.json'):
 canonical=read(ROOT/src['canonical']);body=read(ROOT/src['body']);wv=json.loads(body['messages'][1]['content'])['view']
 assert sha(ROOT/src['body'])==src['body_sha256'] and sha(ROOT/src['canonical'])==src['canonical_sha256']
 for n in (1,2):
  out=ART/'model-probe/genos122'/src['case_id']/str(n);result=read(out/'result.json');raw=read(next((out/'raw').glob('call-*/response.json')));value=json.loads(raw['choices'][0]['message']['content'])
  errors=list(jsonschema.Draft202012Validator(body['response_format']['json_schema']['schema']).iter_errors(value));assert errors and result['status']=='invalid_output'
  native=NavigationReferences(canonical['view']).restore(value)
  row={'case_id':src['case_id'],'repeat':n,'schema_rejected':True,'response_sha256':sha(next((out/'raw').glob('call-*/response.json'))),'new_model_calls':0,'source_targets':value.get('source_targets'),'raw_next_action':value.get('next_action',value.get('action'))}
  if src['case_id']=='cm-007':
   assert value['source_targets'][0]['lookup_target']=='T136'
   table=wv['tool_options']['BROWSE_STRUCTURE'];columns=table['table_columns'];items=[dict(zip(columns,r)) for r in table['table_rows']]
   actual=next(r for r in items if r['target']=='T136');assert actual['document']=='D4'
   assert {'lookup_target':'T44','document':'D5'} in wv['source_target_options']
   inv=NS(policy={'source_goal_control':True,'supervisor_mode':'enforce'},p={'binding':'saved-audit'},s=NS(scope=set(read(DES/'corpus.json')['document_ids'])))
   try:validate(native,inv,canonical['data'],canonical['actions'])
   except ContractError as exc:row.update(server_target_rejected=True,server_error=str(exc))
   else:raise AssertionError('Actual wrong tool target must not dispatch')
   row.update(described_document='D5/유가증권시장 상장규정',actual_target=actual,required_lookup={'lookup_target':'T44','document':'D5'},finding='Goal prose D5 but T136 belongs to D4 BROWSE_STRUCTURE; also action.kind is not action.choice and supervisor fields omitted')
  else:
   row['finding']='No executable source goal. Required choice/source_goal_exclusions and compact response contract not followed. Repeat1 premature FINISH; repeat2 describes missing 시행세칙23 but requests unsupported READ_SCOPE.'
  rows.append(row);usage.extend(result['usage'])
cap=[]
for p in (ART/'model-probe').rglob('request.json'):
 d=read(p);assert d['provider']['allow_fallbacks'] is False
 for k in ('max_tokens','max_output_tokens','max_completion_tokens'):
  if k in d:cap.append([str(p.relative_to(ROOT)),k])
assert not cap
r={'status':'complete','actual_response_replays':4,'schema_rejections_reproduced':4,'actual_wrong_document_tool_rejected':2,'new_model_calls':0,'physical_requests':len(list((ART/'model-probe').rglob('request.json'))),'generated_responses':4,'rate_limited_requests':1,'unexecuted_planned_cells':3,'tokens':{'input':sum(x['input_tokens'] for x in usage),'output':sum(x['output_tokens'] for x in usage),'thinking':sum(x['thinking_tokens'] for x in usage)},'reported_cost_usd':sum(x['cost_usd'] for x in usage),'reported_provider_seconds':sum(x['seconds'] for x in usage),'output_cap_fields':cap,'fallback':False,'rows':rows,'resource_guard_checks':self_test(),'resource_observation':sample(),'full_cm_runs':0,'gate':'no eligible4/4 model; full run not started','model_quality_comparison':'unavailable; Qwen38 HTTP429, no comparative quality conclusion','MAIN112_unchanged':True}
put(ART/'post-probe-audit.json',r)
print('4 actual responses rejected; 2 actual wrong tool targets blocked; resource checks8; newmodel0; totalrequests5')
