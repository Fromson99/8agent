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
 def canonical(n):
  if isinstance(n,dict):return {k:(ws.REF_PATTERN if k=='pattern' and v==ws.PORTABLE_REF_PATTERN else canonical(v)) for k,v in n.items()}
  if isinstance(n,list):return [canonical(v) for v in n]
  return n
 return canonical(visit(schema))

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


def test_exact_pattern_language_symbolic_and_boundaries():
 import re
 # A{0,a}A{0,b} = A{0,a+b}; all symbols/anchors remain identical.
 chunks=re.findall(r'\{0,(\d+)\}',ws.PORTABLE_REF_PATTERN)
 assert chunks==['32','32','32','32','31']
 attainable={0}
 for upper in map(int,chunks):attainable={a+b for a in attainable for b in range(upper+1)}
 assert attainable==set(range(160))
 assert ws.PORTABLE_REF_PATTERN=='^[A-Za-z]'+'[A-Za-z0-9_:-]{0,32}'*4+'[A-Za-z0-9_:-]{0,31}$'
 old,new=re.compile(ws.REF_PATTERN),re.compile(ws.PORTABLE_REF_PATTERN)
 for length in (0,1,2,31,32,33,64,96,128,159,160,161):
  value=('A'+'z'*(length-1)) if length else ''
  assert bool(old.search(value))==bool(new.search(value))
 for value in ['A_:-09','1A','가','A x','A.z','A\n','A'+'z'*159+'\n','A\r\n']:
  assert bool(old.search(value))==bool(new.search(value))

@pytest.mark.parametrize('location',['properties','patternProperties','dependentSchemas','$defs','definitions','items','contains','anyOf','oneOf','allOf','prefixItems'])
def test_known_pattern_locations_only_and_idempotence(location):
 unit={'type':'string','pattern':ws.REF_PATTERN}
 if location in ws.MAPS+('$defs','definitions'):s={location:{'x':unit}}
 elif location in ws.ARRAYS:s={location:[unit]}
 else:s={location:unit}
 prior=deepcopy(s);out,count=ws.portable_patterns(s)
 assert s==prior and count==1 and out!=s
 assert ws.portable_patterns(out)==(out,0)

@pytest.mark.parametrize('key',['enum','const','default','examples','description'])
def test_pattern_literal_data_and_unknown_patterns_untouched(key):
 s={key:{'pattern':ws.REF_PATTERN},'type':'string','pattern':'^[0-9a-f]{64}$'}
 assert ws.portable_patterns(s)==(s,0)

@pytest.mark.parametrize('finish,content',[('error',None),('error','{"ok":true}'),('length','{"ok":true}'),('tool_calls','{"ok":true}'),('unknown-finish','{"ok":true}'),('content_filter',None)])
def test_authoring_finish_error_kept_no_semantic_repair(env,monkeypatch,finish,content):
 from semantic_runtime import genos
 from lawrag.core import request_deadline
 endpoint=SimpleNamespace(headers={},url=lambda p:'https://synthetic.invalid'+p)
 monkeypatch.setattr(genos,'from_env',lambda kind:(endpoint,'synthetic'))
 monkeypatch.setattr(genos,'advertised_model',lambda *a:'synthetic')
 response={'choices':[{'finish_reason':finish,'message':{'content':content}}]};calls=[]
 def post(url,**kw):calls.append(kw);return httpx.Response(200,json=response)
 monkeypatch.setattr(request_deadline,'post_json',post)
 env.w.generate=lambda prompt,context,schema:authoring_model.generate(env.w.store,prompt,context,schema)
 with pytest.raises(authoring_model.AuthoringFailure) as error:add_observation(env)
 assert error.value.status=='INCOMPLETE_RESPONSE' and len(calls)==1
 assert error.value.receipt['finish_reason']==finish
 saved=env.w.store.get(error.value.receipt['store_hash']);assert saved['response']==response

@pytest.mark.parametrize('variant',['top_error','choice_error','refusal','message_wrong_type'])
def test_error_envelopes_never_accepted(env,monkeypatch,variant):
 from semantic_runtime import genos
 from lawrag.core import request_deadline
 endpoint=SimpleNamespace(headers={},url=lambda p:'https://synthetic.invalid'+p)
 monkeypatch.setattr(genos,'from_env',lambda kind:(endpoint,'synthetic'));monkeypatch.setattr(genos,'advertised_model',lambda *a:'synthetic')
 r={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
 if variant=='top_error':r['error']={'message':'synthetic'}
 elif variant=='choice_error':r['choices'][0]['error']={'message':'synthetic'}
 elif variant=='refusal':r['choices'][0]['message']['refusal']='synthetic'
 else:r['choices'][0]['message']='malformed'
 calls=[]
 def post(url,**kw):calls.append(kw);return httpx.Response(200,json=r)
 monkeypatch.setattr(request_deadline,'post_json',post)
 with pytest.raises(authoring_model.AuthoringFailure) as e:authoring_model.generate(env.w.store,'prompt',{'call_budget':{'absolute_deadline':time.time()+180}}, {})
 assert len(calls)==1 and e.value.status==('INVALID_RESPONSE' if variant=='message_wrong_type' else 'INCOMPLETE_RESPONSE')
