from copy import deepcopy
from pathlib import Path
import importlib.util,json,gzip
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import need_continuity as nc, read_judgment_final as final, memory_methods as mm, output_contract as oc
from semantic_runtime.legal_agent.errors import ProposalError
from test_memory_runtime_v2 import memory,command
from conftest import term_glossary
ROOT=Path(__file__).resolve().parents[3]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);return v
prior=module('repeat_scope_prior','06_TOOLS/EXPERIMENTS/adr_1326/test_scope_recovery.py')

def shape():
 c,o,v,s,w,expand=prior.shape();w,join=nc.scope_claim_projection(w)
 return c,o,prior.singles(v),w,lambda raw:expand(join(raw))

def test_scope_exact_join_preserves_all_model_choices_and_legacy():
 c,o,v,w,expand=shape();raw=nc.scope_claim_model_copy(v);before=deepcopy(raw)
 out=expand(raw);final.validate_review(out,c,o)
 assert out['read_judgment_review']==v['read_judgment_review']
 assert out['claims']==v['claims'] and out['gaps']==v['gaps'] and raw==before
 assert 'claim_refs' not in json.dumps(w['properties']['read_judgment_review']['properties']['scope_reviews'])
 final.validate_review(v,c,o)
 assert nc.scope_claim_model_copy(out)['claims']==v['claims']

@pytest.mark.parametrize('fault',['unused_use','excluded_adopted','other_issue','unadopted','open_without_gap','duplicate','foreign'])
def test_join_cannot_invent_support_or_change_disposition(fault):
 c,o,v,w,expand=shape();g=v['read_judgment_review']['scope_reviews'][0]['groups']
 if fault=='unused_use':g[0]['disposition']='USE'
 if fault=='excluded_adopted':g[1]['disposition']='EXCLUDE'
 if fault=='other_issue':g[1]['issue_refs']=['Q2']
 if fault=='unadopted':v['read_judgment_review']['judgments'][0]['basis_refs']=['S3']
 if fault=='open_without_gap':g[1]['disposition']='OPEN'
 if fault=='duplicate':g[0]['basis_refs']=['S2']
 if fault=='foreign':g[0]['basis_refs']=['S6']
 raw=nc.scope_claim_model_copy(v);before=deepcopy(raw)
 with pytest.raises(ProposalError):final.validate_review(expand(raw),c,o)
 assert raw==before

@pytest.mark.parametrize('n',[27,44])
def test_recorded_failed_scope_join_is_derived_without_changing_legal_decisions(n):
 b=ROOT/'04_EXPERIMENTS/ADR/ADR-1327-scope-recovery-live-multiturn/artifacts/public-live/repeat-integrated/canonical'
 with gzip.open(b/f'{n:03}.json.gz','rt') as f:data=json.load(f)
 value=data['view']['repair_feedback']['rejected_assessment'];ctx=data['view']['read_judgments'];opts=data['view']['evidence_options']
 with pytest.raises(ProposalError):final.validate_review(value,ctx,opts)
 raw=nc.scope_claim_model_copy(value)
 # Real failed values, unchanged claims/evidence/issues/statuses; only the redundant join is removed.
 schema={'type':'object','properties':{'read_judgment_review':{'type':'object','properties':{'scope_reviews':{'type':'array'}}}}}
 w,join=nc.scope_claim_projection(schema);out=join(raw)
 assert out['claims']==value['claims'] and out['gaps']==value['gaps']
 for old,new in zip(value['read_judgment_review']['scope_reviews'],out['read_judgment_review']['scope_reviews']):
  for a,b in zip(old['groups'],new['groups']):assert {k:v for k,v in a.items() if k!='claim_refs'}=={k:v for k,v in b.items() if k!='claim_refs'}
 final.validate_review(out,ctx,opts)

@pytest.mark.parametrize('fault',[None,'changed_question','changed_task','changed_scope','acl','pending','stale_route','changed_state','other_latest','scenario'])
def test_literal_repeat_is_exact_identity_only(fault):
 state={'task':'일반 요청','facts':[],'document_ids':['d'],'queries':['요청']}
 event={'id':1,'utterance':'일반 요청','after':deepcopy(state)}
 goal={'id':'g','state':state,'status':'READY','pending':None,'command_ready':True,'events':[event]}
 ctx={'utterance':'일반 요청','goals':[goal]};body={'question':'일반 요청','document_ids':['d']};p={'document_ids':['d']}
 if fault=='changed_question':ctx['utterance']=body['question']='일반 요청을 다시 조사해줘'
 if fault=='changed_task':state['task']='다른 목적'
 if fault=='changed_scope':body['document_ids']=['d','e'];p['document_ids']=['d','e']
 if fault=='acl':p['document_ids']=[]
 if fault=='pending':goal['status']='PENDING';goal['pending']='ASSESS'
 if fault=='stale_route':goal['command_ready']=False
 if fault=='changed_state':state['facts']=[{'name':'상태','value':'변경'}]
 if fault=='other_latest':ctx['goals'].append({**deepcopy(goal),'id':'other','events':[dict(event,id=2,utterance='별도 질문')]})
 if fault=='scenario':state['scenario_context']={'id':'hypothetical'}
 assert mm.literal_repeat_target(ctx,body,p)==('g' if fault is None else None)

@pytest.mark.parametrize('first_bad',[False,True])
def test_actual_memory_repeat_cannot_reset_goal_and_preserves_originals(memory,first_bad):
 mem,f,w,send,p=memory;first=send(command('CASE_START',task='모의 요청',facts=[]));gid=first['goal_id'];before=mem.parts(gid);seen=[]
 def invoke(system,data,schema,phase):
  seen.append(phase)
  if phase.startswith('memory-resolve'):
   assert data['literal_repeat_target']==gid and 'CASE_START' not in data['offered_methods']
   if first_bad and phase=='memory-resolve':return command('CASE_START',task='모의 요청',facts=[])
   return command('ANSWER_PRESENT',target=gid)
  return {'valid':True,'reason':'같은 요청과 범위의 재표현'}
 mem.invoke=invoke;body={'question':'모의 요청','session_id':'s','request_id':'repeat'}
 result=mem.execute(body,p)
 assert result['goal_id']==gid and result['executed']==['COMPOSE']
 assert mem.parts(gid)['READ']==before['READ'] and mem.parts(gid)['SELECT']==before['SELECT']
 assert mem.execute(body,p)==result
 assert len(seen)==(3 if first_bad else 2)
 assert mem.db.execute('SELECT count(*) FROM goal').fetchone()[0]==1

@pytest.mark.parametrize('disposition',['USE','EXCLUDE','OPEN'])
def test_numbered_provider_projection_keeps_derived_join(disposition):
 from semantic_runtime.legal_agent.navigation_input import NavigationReferences
 from semantic_runtime.legal_agent.minimal_output import Projection
 c,o,v,w,expand=shape();row=v['read_judgment_review']['scope_reviews'][0]['groups'][1]
 row.update(disposition=disposition,gap_indices=[1] if disposition=='OPEN' else [])
 raw=nc.scope_claim_model_copy(v);refs=NavigationReferences({'read_judgments':c,'evidence_options':o,'source_stage':'memory-assess'})
 encoded=refs.view(raw);schema=refs.schema(w);projection=Projection(schema);wire=projection.project(encoded)
 oc.validate_shape(wire,projection.wire)
 restored=refs.decode(projection.expand(wire),schema)
 assert restored==raw
 assert 'claim_refs' not in restored['read_judgment_review']['scope_reviews'][0]['groups'][1]

@pytest.fixture
def current_wire(monkeypatch):
 observed=prior.per_original_wire.__wrapped__(monkeypatch)
 import test_legal_agent_double_harness as harness
 old=harness.wire
 monkeypatch.setattr(harness,'wire',lambda value:old(nc.scope_claim_model_copy(value)))
 from semantic_runtime.legal_agent.bounded_source_session import _Gateway
 from semantic_runtime.legal_agent import answer_progress
 gateway_request=_Gateway.request;navigation=[]
 def request(self,*args,**kw):
  result=gateway_request(self,*args,**kw)
  if '-read-choice' in args[1].get('source_stage',''):
   system=result['messages'][0]['content'];assert answer_progress.SCOPE_GUIDANCE in system;navigation.append(system)
  return result
 monkeypatch.setattr(_Gateway,'request',request)
 return observed,navigation

@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice','need_first','need_twice','open'])
def test_api_join_repair_stop_and_actual_navigation_wire(tmp_path,term_glossary,monkeypatch,current_wire,fault):
 from need_continuity_fixture import run_api
 result=run_api(tmp_path,term_glossary,'goal_control',monkeypatch,coverage_fault=fault)
 observed,navigation=current_wire
 assert observed and navigation
 if fault in ('scope_twice','need_twice'):assert result is None;return
 response,calls,reviews=result
 assert len([p for p in calls if p.startswith('memory-assess')])==(2 if fault in ('scope_first','need_first') else 1)
