"""Synthetic contracts only; no model or external-network calls."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib,importlib.util,itertools,json,time
import httpx,pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import wire_schema as ws,read_judgment_final as final
from semantic_runtime.ontology_work import profile_schema as ps,authoring_model
from test_domain_profile_workflow import env,normalized_output,add_observation
from test_genos_urllib_transport import server,local_network_only
ROOT=Path(__file__).resolve().parents[3]

def packed(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def expand(schema):
 defs=schema.get('$defs',{})
 def visit(n,seen=()):
  if isinstance(n,dict):
   if set(n)=={'$ref'}:
    ref=n['$ref'];assert ref.startswith('#/$defs/') and ref not in seen
    return visit(defs[ref[8:]],seen+(ref,))
   return {k:visit(v,seen) for k,v in n.items() if k!='$defs'}
  if isinstance(n,list):return [visit(v,seen) for v in n]
  return n
 return visit(schema)

def repeated():
 unit={'type':'object','additionalProperties':False,'required':['value','quote'],
       'properties':{'value':{'type':'string','minLength':1,'maxLength':120},'quote':{'type':'string','minLength':1,'maxLength':120}}}
 return {'type':'object','properties':{str(i):deepcopy(unit) for i in range(6)},'required':['0'],'additionalProperties':False}

def request(schema):
 return {'model':'synthetic','messages':[{'role':'system','content':'unchanged'},{'role':'user','content':'정확한 원문\n'}],
         'response_format':{'type':'json_schema','json_schema':{'name':'test','strict':True,'schema':schema}}}

@pytest.mark.parametrize('maker,limit',[(ps.observation_schema,.30),(ps.accumulation_schema,.50)])
def test_domain_shape_exact_and_smaller(maker,limit):
 # ROOT is rebound by the runner to the exact selected candidate.
 profile=json.loads((ROOT/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json').read_text());s=maker(profile);before=deepcopy(s)
 wire=ws.factor_schema(s)
 assert s==before and expand(wire)==s
 assert len(packed(wire))<len(packed(s))*limit
 assert all(len(n)<=4 for n in wire['$defs'])
 Draft202012Validator.check_schema(wire)
 assert ws.factor_schema(wire)==wire

@pytest.mark.parametrize('special',[{'$id':'urn:local'}, {'$ref':'#/$defs/source','$defs':{'source':{'type':'string'}}}, {'definitions':{'a':{'type':'string'}}}, {'const':{'$ref':'literal-data-not-schema'}}, {'enum':[{'$id':'data'}]}])
def test_existing_reference_scope_and_literal_guards(special):
 value={**repeated(),**special};assert ws.factor_schema(value)==value

@pytest.mark.parametrize('payload',[{}, {'0':{'value':'x','quote':'q'}}, {'0':{'value':'','quote':'q'}}, {'0':{'value':'x','quote':'q','extra':1}}, {'0':{'value':5,'quote':'q'}}, {'7':{'value':'x','quote':'q'}}, {'0':None}])
def test_factored_validator_acceptance_equals_original(payload):
 original=repeated();wire=ws.factor_schema(original)
 assert Draft202012Validator(wire).is_valid(payload)==Draft202012Validator(original).is_valid(payload)

def test_request_copy_receipt_and_non_schema_requests():
 body=request(repeated());old=deepcopy(body);wire,r=ws.project_request(body)
 assert body==old and wire['messages']==body['messages'] and wire['response_format']['json_schema']['strict'] is True
 assert expand(wire['response_format']['json_schema']['schema'])==body['response_format']['json_schema']['schema']
 assert r['validation_schema_sha256']==hashlib.sha256(packed(repeated()).encode()).hexdigest()
 assert r['wire_schema_chars']<r['validation_schema_chars'] and r['changed']
 for other in [{'model':'m'}, {'response_format':{'type':'json_object'}}]:assert ws.project_request(other)==(other,None)

@pytest.mark.parametrize('stream',[False,True])
def test_actual_genos_http_receives_projected_schema_once(stream):
 with server(mode='stream' if stream else 'json') as (_,transport,state):
  if stream:state['release'].set()
  body=request(repeated());prior=deepcopy(body)
  result=(transport.send_stream_once(body=body,ticket={'remaining_seconds':2},on_content=lambda _:None) if stream else transport.send_once(body=body,ticket={'remaining_seconds':2}))
  assert body==prior and len(state['calls'])==1
  sent=state['calls'][0]['body'];assert expand(sent['response_format']['json_schema']['schema'])==repeated()
  assert '$defs' in sent['response_format']['json_schema']['schema']
  assert result['schema_projection']['changed'] and result['status_code']==200

def test_genos_failure_keeps_projection_and_does_not_retry():
 from semantic_runtime.legal_agent.errors import TransportError
 with server(mode='slow-headers') as (_,transport,state):
  with pytest.raises(TransportError) as e:transport.send_once(body=request(repeated()),ticket={'remaining_seconds':.05})
  assert e.value.unknown and e.value.response['schema_projection']['changed']
  assert len(state['calls'])==1

@pytest.mark.parametrize('failure',['none','repair','twice','unknown','http'])
def test_authoring_actual_wire_and_existing_repair_owner(env,monkeypatch,failure):
 from semantic_runtime import genos
 from lawrag.core import request_deadline
 endpoint=SimpleNamespace(headers={},url=lambda p:'https://synthetic.invalid'+p)
 monkeypatch.setattr(genos,'from_env',lambda kind:(endpoint,'synthetic'))
 monkeypatch.setattr(genos,'advertised_model',lambda *a:'synthetic')
 sent=[]
 def post(url,**kw):
  body=kw['json_body'];sent.append(deepcopy(body));context=json.loads(body['messages'][1]['content'])
  if failure=='unknown':raise RuntimeError('injected unknown')
  if failure=='http':return httpx.Response(429,text='synthetic refusal')
  out=normalized_output(context)
  if failure=='twice' or failure=='repair' and len(sent)==1:out['observations'][0]['statement']['locators'][0]['quote']='원문과 다른 인용'
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(out,ensure_ascii=False)}}]})
 monkeypatch.setattr(request_deadline,'post_json',post)
 def generate(prompt,context,schema):return authoring_model.generate(env.w.store,prompt,context,schema)
 env.w.generate=generate
 if failure in ('twice','unknown','http'):
  with pytest.raises(Exception):add_observation(env)
 else:
  row=add_observation(env);assert env.w.load(row['bundle_id'])['normalized']['proposal']['observations']
 assert len(sent)==(2 if failure in ('repair','twice') else 1)
 p=env.w.selected_profile(env.profile_id,env.profile_work_hash)
 for body in sent:
  schema=body['response_format']['json_schema']['schema'];assert expand(schema)==p['output_schema']
  assert '$defs' in schema and body['response_format']['json_schema']['strict'] is True
  assert not {'max_tokens','max_output_tokens','max_completion_tokens'}&body.keys()
 if len(sent)==2:assert 'repair' in json.loads(sent[1]['messages'][1]['content'])

@pytest.mark.parametrize('enforce',[False,True])
@pytest.mark.parametrize('purposes',[False,True])
def test_final_review_exhaustive_branch_acceptance(enforce,purposes):
 # Load only the old generator; its other imported contracts did not change.
 workspace=Path(__file__).resolve().parents[3]
 b=json.loads((workspace/'04_EXPERIMENTS/ADR/ADR-1210-strict-schema-factor-main/artifacts/design/baseline.json').read_text())
 path=workspace/b['manifest']['code_root']/'02_BACKEND/semantic_runtime/legal_agent/read_judgment_final.py'
 spec=importlib.util.spec_from_file_location('semantic_runtime.legal_agent._schema_baseline',path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 ctx={'judgments':[{'id':'J1','review_purposes':[{'id':'P'}] if purposes else []},{'id':'J2','review_purposes':[]}], 'needs':[],'conflicts':[],'change_review':True}
 a=Draft202012Validator(old.review_schema(ctx,[{'id':'B1'}],enforce_claim_shape=enforce));b=Draft202012Validator(final.review_schema(ctx,[{'id':'B1'}],enforce_claim_shape=enforce))
 count=0
 for ident,disposition,claims,change in itertools.product(['J1','J2','fake'],['USE','CONDITIONAL','UNRESOLVED','NOT_USED','FAKE'],[[],['C1'],['C1','C2']],[None,{}, {'prior_version':1,'prior_finding_quote':'x','purpose_reviews':[]}]):
  row={'id':ident,'disposition':disposition,'claim_refs':claims,'basis_refs':['B1'],'reason':'확인'}
  if change is not None:row['change_review']=change
  value={'judgments':[deepcopy(row),deepcopy(row)],'needs':[],'conflicts':[]}
  assert a.is_valid(value)==b.is_valid(value),(ident,disposition,claims,change)
  count+=1
 assert count==135
 if purposes:assert len(final.review_schema(ctx,[{'id':'B1'}],enforce_claim_shape=enforce)['properties']['judgments']['items']['anyOf'])==4
