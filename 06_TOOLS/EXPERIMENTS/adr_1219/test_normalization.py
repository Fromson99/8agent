"""Independent synthetic inputs. No external model or archived answers."""
from copy import deepcopy
import json,time
from pathlib import Path
from types import SimpleNamespace
import pytest,httpx
from jsonschema import Draft202012Validator
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.ontology_work import observations as o,authoring_model
from test_domain_profile_workflow import env,normalized_output,add_observation,proposal,save
ROOT=Path(__file__).resolve().parents[3]

def compact(value, raw):
 p=deepcopy(value)
 p['coverage']={r['pointer']:{k:v for k,v in r.items() if k!='pointer'} for r in p['coverage']}
 def visit(v):
  if isinstance(v,dict):
   if set(v)=={'payload_hash','pointer','start','end','quote'}:
    text=next(r['text'] for r in raw['index'] if r['pointer']==v['pointer']);positions=[];at=-1
    while True:
     at=text.find(v['quote'],at+1)
     if at<0:break
     positions.append(at)
    return {'pointer':v['pointer'],'quote':v['quote'],'occurrence':positions.index(v['start'])}
   return {k:visit(x) for k,x in v.items()}
  if isinstance(v,list):return [visit(x) for x in v]
  return v
 return visit(p)

def raw_profile(e,payload):
 r=e.w.import_payload(payload,event_id='raw-test',run_id='test')
 raw=e.w.load(r['bundle_id'])['raw'];p=e.w.selected_profile(e.profile_id,e.profile_work_hash)
 return r,raw,p

@pytest.mark.parametrize('payload',[{'opinion':'의견😀'}, {'nested':[{'a/b~':'보존'}]}, ['내용',None,3],{},[], '원문 원문'])
def test_exact_coverage_keys_and_locator_roundtrip(env,payload):
 _,raw,p=raw_profile(env,payload);before=deepcopy(p);canonical=normalized_output({'raw':raw});wire=compact(canonical,raw)
 schema=o.normalization_schema(raw,p);Draft202012Validator.check_schema(schema)
 assert Draft202012Validator(schema).is_valid(wire)
 assert schema['properties']['coverage']['required']==[r['pointer'] for r in raw['index']]
 restored,receipt=o.restore_normalization(wire,raw)
 assert restored==canonical and wire==compact(canonical,raw) and p==before
 assert receipt['canonical_sha256']==digest(canonical) and receipt['proposal_sha256']==digest(wire)
 assert receipt['assembled_locators']==1

@pytest.mark.parametrize('state,refs,valid',[('USED',['O1'],True),('USED',[],False),('NON_JUDGMENT',[],True),('NON_JUDGMENT',['O1'],False),('NEEDS_CONTEXT',[],True),('NEEDS_CONTEXT',['O1'],False)])
def test_schema_encodes_state_reference_both_directions(env,state,refs,valid):
 _,raw,p=raw_profile(env,'인용');wire=compact(normalized_output({'raw':raw}),raw)
 wire['coverage'][''].update(state=state,observation_ids=refs)
 assert Draft202012Validator(o.normalization_schema(raw,p)).is_valid(wire) is valid

@pytest.mark.parametrize('fault',['missing','extra','nested-origin','duplicate-canonical'])
def test_missing_extra_and_external_paths_are_not_repaired(env,fault):
 _,raw,p=raw_profile(env,{'a':'의견','b':'다른문구'});wire=compact(normalized_output({'raw':raw}),raw)
 if fault=='missing':del wire['coverage']['/b']
 elif fault=='extra':wire['coverage']['/x']=deepcopy(wire['coverage']['/a'])
 elif fault=='nested-origin':wire['coverage']={'/old/archive/path':deepcopy(wire['coverage']['/a'])}
 else:
  wire=normalized_output({'raw':raw});wire['coverage'].append(deepcopy(wire['coverage'][0]))
 with pytest.raises(ContractError):
  value,_=o.restore_normalization(wire,raw);o.validate_observations(value,raw,p,{'candidates':[]})

@pytest.mark.parametrize('pointer,quote,occurrence',[('/archive','인용',0),('', '없는문구',0),('','',0),('','인용',-1),('','인용',True),('','인용',10**9)])
def test_locator_invalid_values_rejected(env,pointer,quote,occurrence):
 _,raw,p=raw_profile(env,'인용')
 wire=compact(normalized_output({'raw':raw}),raw)
 wire['observations'][0]['statement']['locators'][0].update(pointer=pointer,quote=quote,occurrence=occurrence)
 with pytest.raises(ContractError):o.restore_normalization(wire,raw)

@pytest.mark.parametrize('occurrence,start',[(0,0),(1,3),(2,6)])
def test_repeated_quote_exact_occurrence(env,occurrence,start):
 _,raw,p=raw_profile(env,'반복 반복 반복');wire=compact(normalized_output({'raw':raw}),raw)
 field=wire['observations'][0]['statement'];field.update(value='반복',locators=[{'pointer':'','quote':'반복','occurrence':occurrence}])
 value,_=o.restore_normalization(wire,raw);o.validate_observations(value,raw,p,{'candidates':[]})
 assert value['observations'][0]['statement']['locators'][0]['start']==start


def test_state_errors_and_missing_pointers_are_precise(env):
 _,raw,p=raw_profile(env,{'a':'의견','b':'다른문구'});v=normalized_output({'raw':raw})
 v['coverage'][0]['state']='NON_JUDGMENT';v['coverage']=v['coverage'][:1]
 with pytest.raises(ContractError) as e:o.validate_observations(v,raw,p,{'candidates':[]})
 assert 'missing=' in str(e.value) and '/b' in str(e.value) and 'NON_JUDGMENT requires empty' in str(e.value)


def test_canonical_legacy_and_approved_profile_unchanged(env):
 _,raw,p=raw_profile(env,{'a':'과거의견'});v=normalized_output({'raw':raw})
 restored,r=o.restore_normalization(v,raw);o.validate_observations(restored,raw,p,{'candidates':[]})
 assert restored==v and r['assembled_locators']==0 and r['coverage_map'] is False
 b=json.loads((Path(__file__).parent/'../../../04_EXPERIMENTS/ADR/ADR-1219-normalization-coverage-contract/artifacts/design/baseline.json').resolve().read_text())
 import hashlib
 for name in ('profile.py','profile_schema.py','assembly_ir.py','assembly_compiler.py'):
  n='02_BACKEND/semantic_runtime/ontology_work/'+name
  assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==b['manifest']['files'][n]

@pytest.mark.parametrize('fault',['none','repair','twice','unknown','bad_quote','tamper'])
def test_real_authoring_boundary_repair_jobs_and_canonical_storage(env,monkeypatch,fault):
 from semantic_runtime import genos
 from lawrag.core import request_deadline
 endpoint=SimpleNamespace(headers={},url=lambda p:'https://synthetic.invalid'+p)
 monkeypatch.setattr(genos,'from_env',lambda kind:(endpoint,'synthetic'));monkeypatch.setattr(genos,'advertised_model',lambda *a:'synthetic')
 calls=[];raw_outputs=[]
 def post(url,**kw):
  body=kw['json_body'];calls.append(deepcopy(body));context=json.loads(body['messages'][1]['content'])
  assert body['response_format']['json_schema']['strict'] is True
  assert 'payload_hash' not in json.dumps(body['response_format']['json_schema']['schema'])
  if fault=='unknown':raise RuntimeError('injected unknown')
  value=compact(normalized_output(context),context['raw'])
  if fault=='twice' or fault=='repair' and len(calls)==1:del value['coverage'][next(iter(value['coverage']))]
  if fault=='bad_quote':value['observations'][0]['statement']['locators'][0]['quote']='다른 인용'
  if fault=='tamper':env.glossary.reader.changed=True
  raw_outputs.append(deepcopy(value));return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value,ensure_ascii=False)}}]})
 monkeypatch.setattr(request_deadline,'post_json',post)
 env.w.generate=lambda prompt,context,schema:authoring_model.generate(env.w.store,prompt,context,schema)
 if fault in ('twice','unknown','bad_quote','tamper'):
  with pytest.raises(Exception):add_observation(env)
 else:
  row=add_observation(env);saved=env.w.load(row['bundle_id'])['normalized'];receipt=saved['model_receipt']['normalization_assembly']
  assert isinstance(saved['proposal']['coverage'],list) and receipt['coverage_map']
  assert receipt['proposal_sha256']==digest(raw_outputs[-1])
  again=add_observation(env);assert again['work_hash']==row['work_hash']
 assert len(calls)==(2 if fault in ('repair','twice','bad_quote') else 1)
 jobs=[env.w.load(r['bundle_id']) for r in env.repo.list(prefix='job-')]
 assert len(jobs)==1
 if raw_outputs:assert jobs[0]['response']==raw_outputs[-1]
 if fault in ('twice','bad_quote'):assert jobs[0]['phase']=='INVALID' and len(jobs[0]['attempts'])==2
 if fault=='unknown':assert jobs[0]['phase']=='UNKNOWN'


def test_normalization_two_records_accumulate_preview_and_duplicate(env):
 calls=[]
 def generate(prompt,context,schema):
  calls.append(context)
  assert schema['properties']['coverage']['type']=='object'
  return compact(normalized_output(context),context['raw']),{'physical_calls':1}
 env.w.generate=generate
 a=add_observation(env);first=save(env,a,proposal(env,a))
 b=add_observation(env,'B','앞선 가상 판단을 보완한다.')
 second=save(env,b,proposal(env,b,base=env.w.load(first['bundle_id'])['proposal']['graph'],exception=True,relation='COMPLEMENT'),1)
 result=env.w.preview(second['bundle_id']);assert result['paths'] and len(result['graph']['nodes'])==2
 assert len(env.w.load(second['bundle_id'])['observation_ledger'])==2 and len(calls)==2
 assert env.repo.head(second['bundle_id'])['publication_id'] is None
