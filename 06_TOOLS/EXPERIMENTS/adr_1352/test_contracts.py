from copy import deepcopy
from pathlib import Path
import importlib.util,json,gzip
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.contracts import digest
from semantic_runtime.ontology_work import wiki_contracts as wc
from semantic_runtime.ontology_work.observations import envelope
from semantic_runtime.legal_agent import need_continuity as nc, judgment_changes as jc, output_contract as oc
from semantic_runtime.legal_agent import read_judgment_final as final, assessment_links as links
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from test_wiki_workspace import env,ws
from conftest import term_glossary
ROOT=Path(__file__).resolve().parents[3]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
prior=module('scope_prior_1352','06_TOOLS/EXPERIMENTS/adr_1326/test_scope_recovery.py')

def selections(options,choose):
 return {'selections':{key:dict(disposition='CONTENT' if choose(row) else 'CONTROL',source_refs=[],reason='입력 내용과 처리 정보 구분') for key,row in options.items()}}

@pytest.mark.parametrize('payload',[{'status':'사업 승인 대기','work_hash':'이것은 실제 업무 내용','index':['배정 완료']},'실제 원문😀', [42,True,None]])
def test_content_keeps_business_keys_and_exact_literals_once(env,ws,payload):
 raw=ws.import_payload(payload,event_id='finite',run_id='test');before=deepcopy(ws.load(raw['bundle_id']));seen=[]
 def generate(prompt,context,schema):
  assert 'raw_records' not in context and context['proposal_contract']==wc.CONTENT_VERSION
  assert context['raw_record_bindings'][raw['bundle_id']]['work_hash']==before['work_hash']
  options=context['material_options'];out=selections(options,lambda r:True);Draft202012Validator(schema).validate(out)
  seen.append(deepcopy(context));return out,{}
 ws.generate=generate;args=dict(change_id='finite',raw_ids=[raw['bundle_id']]);p=ws.propose(**args)
 assert ws.propose(**args)==p and len(seen)==1 and ws.list_items()['items']==[]
 assert [o['value']['text'] for o in p['operations']]==[r['text'] for r in before['raw']['index']]
 ws.apply(**p);assert ws.apply(**p)['reused'] and ws.load(raw['bundle_id'])==before

@pytest.mark.parametrize('fault',['free_text','invented_material','foreign_source','duplicate_source','unselected_source','duplicate_literal','empty'])
def test_selection_cannot_synthesize_or_adopt_unoffered_metadata(env,ws,fault):
 raw=ws.import_payload(['실제 내용','실제 내용'],event_id=fault,run_id='test')
 s,expand,options=wc.content_selection_contract({raw['bundle_id']:ws.load(raw['bundle_id'])},[env.source])
 value=selections(options,lambda r:r['pointer']=='/0')
 if fault=='free_text':value['selections']['M1']['text']='revision을 지식으로 만들기'
 if fault=='invented_material':value['selections']['M404']=value['selections']['M1']
 if fault=='foreign_source':value['selections']['M1']['source_refs']=['foreign']
 if fault=='duplicate_source':value['selections']['M1']['source_refs']=[env.source['id']]*2
 if fault=='unselected_source':value['selections']['M2']['source_refs']=[env.source['id']]
 if fault=='duplicate_literal':value['selections']['M2']['disposition']='CONTENT'
 if fault=='empty':value['selections']['M1']['disposition']='UNCERTAIN'
 with pytest.raises(Exception):expand(value)
 assert ws.list_items()['items']==[]

def test_one_repair_original_retained_no_duplicate_and_changed_revision_blocks(env,ws,monkeypatch):
 raw=ws.import_payload(env.source['text'],event_id='repair',run_id='test');calls=[]
 def generate(prompt,context,schema):
  calls.append(deepcopy(context));v=selections(context['material_options'],lambda r:bool(r['raw_id']))
  if len(calls)==1:v['selections']['M1']['source_refs']=['foreign']
  return v,{}
 ws.generate=generate;p=ws.propose(change_id='repair',raw_ids=[raw['bundle_id']],originals=[env.source]);assert len(calls)==2
 assert calls[1]['repair']['previous']['response']['selections']['M1']['source_refs']==['foreign']
 ws.apply(**p);assert ws.apply(**p)['reused']
 raw2=ws.import_payload('보존',event_id='drift',run_id='test');load=ws.load;drift=[False]
 def changed(bid):
  row=load(bid)
  if bid==raw2['bundle_id'] and drift[0]:row=deepcopy(row);row['revision']+=1
  return row
 monkeypatch.setattr(ws,'load',changed)
 def change(*args):drift[0]=True;return {},{}
 ws.generate=change
 with pytest.raises(ContractError,match='raw record changed'):ws.propose(change_id='drift',raw_ids=[raw2['bundle_id']])

def test_repeated_invalid_and_unknown_remain_terminal(env,ws):
 raw=ws.import_payload('보존',event_id='stop',run_id='test');calls=[]
 def invalid(*a):calls.append(1);return {'selections':{}},{}
 ws.generate=invalid;args=dict(change_id='invalid',raw_ids=[raw['bundle_id']])
 with pytest.raises(Exception):ws.propose(**args)
 with pytest.raises(ContractError,match='INVALID'):ws.propose(**args)
 assert len(calls)==2
 def unknown(*a):calls.append(1);raise TimeoutError('unknown')
 ws.generate=unknown;args['change_id']='unknown'
 with pytest.raises(TimeoutError):ws.propose(**args)
 with pytest.raises(ContractError,match='UNKNOWN'):ws.propose(**args)
 assert len(calls)==3 and ws.list_items()['items']==[]

def shape():
 c,o,v,s,w,expand=prior.shape();v=prior.singles(v)
 t=deepcopy(c['need_continuity']['targets'][0]);t['id']='duplicate-purpose';c['need_continuity']['targets'].append(t)
 c['need_continuity']['scope_input_hash']=digest([c['need_continuity']['targets'],o])
 base={'type':'object','properties':{k:{} for k in ('claims','gaps','issue_assessments')},'required':['claims','gaps','issue_assessments'],'additionalProperties':False}
 s=links.attach(final.attach(base,c,o),o,direct=True);w,e=links.projection(s)
 w=nc.generation_schema(w,c);w,j=nc.scope_claim_projection(w);w,u=nc.original_review_projection(w,c)
 raw=nc.scope_claim_model_copy(v);rows=raw['read_judgment_review'].pop('scope_reviews');by={g['basis_refs'][0]:g for r in rows for g in r['groups']}
 raw['read_judgment_review']['original_reviews']={f'R{i+1}':by[ref] for i,ref in enumerate(dict.fromkeys(ref for t in c['need_continuity']['targets'] for ref in t['available_evidence_refs']))}
 return c,o,raw,w,lambda raw:e(j(u(raw)))

def test_same_original_once_shared_across_different_targets_without_semantic_change():
 c,o,raw,w,e=shape();before=deepcopy(raw);v=e(raw);final.validate_review(v,c,o)
 scopes=v['read_judgment_review']['scope_reviews'];assert scopes[0]['groups']==scopes[2]['groups']
 assert len(raw['read_judgment_review']['original_reviews'])==6 and sum(len(r['groups']) for r in scopes)==9
 assert raw==before and v['claims']==raw['claims']

@pytest.mark.parametrize('fault',['exclude_adopted','unsupported_use','wrong_issue','missing','foreign','open_without_gap'])
def test_unique_review_does_not_fix_bad_semantics(fault):
 c,o,raw,w,e=shape();rows=raw['read_judgment_review']['original_reviews']
 if fault=='exclude_adopted':rows['R2']['disposition']='EXCLUDE'
 if fault=='unsupported_use':rows['R1']['disposition']='USE'
 if fault=='wrong_issue':rows['R2']['issue_refs']=['Q2']
 if fault=='missing':del rows['R1']
 if fault=='foreign':rows['R2']['basis_refs']=['S404']
 if fault=='open_without_gap':rows['R2']['disposition']='OPEN'
 with pytest.raises(ProposalError):final.validate_review(e(raw),c,o)

@pytest.mark.parametrize('status',['COVERED_ELSEWHERE','ROLE_ONLY','REINTERPRETED','UNRESOLVED'])
def test_purpose_join_only_same_selected_original_and_issue(status):
 ctx={'change_review':True,'judgments':[{'id':'J','review_purposes':[{'id':'P','issue_refs':['Q1']}]}]}
 schema={'type':'object','properties':{'claims':{},'read_judgment_review':{'type':'object','properties':{'judgments':{'type':'array','items':{'type':'object','properties':{'change_review':jc.schema(ctx,[{'id':'S'}])}}}}}}}
 w,e=jc.claim_projection(schema,ctx)
 claims=[{'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':['S']},{'claim_id':'C2','issue_refs':['Q2'],'evidence_refs':['S']},{'claim_id':'C3','issue_refs':['Q1'],'evidence_refs':['OTHER']}]
 p={'purpose_id':'P','source_quote':'old','status':status,'basis_refs':['S'],'gap_indices':[],'reason':'검토'}
 raw={'claims':claims,'read_judgment_review':{'judgments':[{'id':'J','change_review':{'prior_version':1,'prior_finding_quote':'old','purpose_reviews':[p]}}]}}
 v=e(raw);result=v['read_judgment_review']['judgments'][0]['change_review']['purpose_reviews'][0]
 assert result['claim_refs']==(['C1'] if status=='COVERED_ELSEWHERE' else [])
 assert {k:x for k,x in result.items() if k!='claim_refs'}==p and v['claims']==claims

# Actual native API harness: adapt synthetic replies to the product's new wire;
# normal API validation, review repair, publication and duplicate guards remain.
@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice'])
def test_actual_api_new_review_and_bounded_repair(tmp_path,term_glossary,monkeypatch,fault):
 import test_legal_agent_double_harness as harness
 from need_continuity_fixture import run_api
 prior.per_original_wire.__wrapped__(monkeypatch)
 old=harness.wire
 def wire(value):
  v=nc.scope_claim_model_copy(value);r=v.get('read_judgment_review',{});rows=r.pop('scope_reviews',None)
  if rows is not None:
   refs={}
   for row in rows:
    for g in row['groups']:refs.setdefault(g['basis_refs'][0],g)
   r['original_reviews']={f'R{i+1}':g for i,g in enumerate(refs.values())}
  for row in r.get('judgments',[]):
   for p in (row.get('change_review') or {}).get('purpose_reviews',[]):p.pop('claim_refs',None)
  return old(v)
 monkeypatch.setattr(harness,'wire',wire)
 result=run_api(tmp_path,term_glossary,'goal_control',monkeypatch,coverage_fault=fault)
 if fault=='scope_twice':assert result is None
 else:
  response,calls,reviews=result;assert len([p for p in calls if p.startswith('memory-assess')])==(2 if fault else 1)
