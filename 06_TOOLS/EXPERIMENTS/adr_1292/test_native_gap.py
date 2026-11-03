"""Real native API/storage/publication with a deterministic mock model."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from conftest import term_glossary
from test_domain_profile_workflow import env
from test_review_explanation_actions import current_normalizer_wire
from semantic_runtime.legal_agent import assessment_input as ai, scenario_application as app, assessment_links as links
from semantic_runtime.legal_agent.errors import ContractError
from fixtures import share
from semantic_runtime.legal_agent import scenario_computation as calc
ROOT=Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('fault,missing_plan',[('repair_success',True)])
def test_native_computed_id_repair_preserves_raw_and_replay(env,tmp_path,term_glossary,monkeypatch,fault,missing_plan):
 monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
 import api_fixture_integrated as fixture
 decode=fixture.decode;seen=[];last={};wire_views=[]
 def read(value):
  result=decode(ai.restore(value) if ai.META in value else value)
  last.clear();last.update(deepcopy(result));return result
 monkeypatch.setattr(fixture,'decode',read)
 import test_legal_agent_double_harness as harness
 original=harness.wire
 def response(value):
  if 'scenario_review' in value and last.get('hypothetical_scenario'):
   value=deepcopy(value);c=last['hypothetical_scenario'];v=value['scenario_review']
   if fault=='rule_success':
    value['claims'][0]['explanation']='가정 한도245만 원을 적용하면 비용150만원은 가정 금액 조건을 충족하고, 서면 승인은 미확인이다.'
   if fault=='repair_success' and last['source_stage'].endswith('-repair'):
    value['claims'][0]['rule']=None
    value['claims'][0]['explanation']='가정 비용50만원으로 금액 조건을 검토했으며 서면 승인은 미확인이다.'
   v['version']=app.SERVER_VERSION;v.pop('application_links',None)
   if fault in ('repair_success','rule_success') and missing_plan:
    offered=last['computed_gap_options'][0]
    chosen=False
    for index,gap in enumerate(value['gaps']):
     if gap['kind']=='MISSING_FACT':
      value['gaps'][index]={'computed_gap_ref':offered['computed_gap_ref'],'issue_id':gap['issue_id']}
      seen.append(deepcopy(value['gaps'][index]));chosen=True;break
    if not chosen:
     row={'computed_gap_ref':offered['computed_gap_ref'],'issue_id':last['issues'][0]['id']}
     value['gaps'].append(row);seen.append(deepcopy(row))
    value['issue_assessments'][0].update(status='PARTIAL',reason='서면 승인 입력을 확인해야 합니다.')
   if missing_plan and not last['source_stage'].endswith('-repair'):
    for index,gap in enumerate(value['gaps']):
     if 'computed_gap_ref' in gap:
      value['gaps'][index]={'kind':'MISSING_FACT','material':True,
       'reason':'미확인 '+gap['computed_gap_ref']+' 확인','issue_id':gap['issue_id'],
       'material_id':None,'missing_target':'','suggested_action':'REQUEST_FACT'}
      break
   value=share(value)
   if fault=='repair_success' and not last['source_stage'].endswith('-repair'):
    from semantic_runtime.legal_agent.scenario_review import results
    value['scenario_review']['condition_results']=results(c)
    # This test injects the offered ID in prose instead of a link failure.
  elif last.get('hypothetical_scenario') and 'requirement_review' in value and fault=='missing_receipt':value=share(value)
  return original(value)
 monkeypatch.setattr(harness,'wire',response)
 from semantic_runtime.legal_agent import minimal_output
 prepare=minimal_output.prepare_request
 def capture(*args,**kwargs):
  body,p=prepare(*args,**kwargs);view=json.loads(body['messages'][1]['content'])['view']
  if ai.META in view:wire_views.append(deepcopy(body))
  return body,p
 monkeypatch.setattr(minimal_output,'prepare_request',capture)
 from starlette.testclient import TestClient
 post=TestClient.post;responses=[]
 def capture_post(self,*args,**kwargs):
  response=post(self,*args,**kwargs)
  if response.status_code==200:
   body=response.json()
   if body.get('assembly',{}).get('term_agent',{}).get('scenario_context'):
    responses.append(body)
  return response
 monkeypatch.setattr(TestClient,'post',capture_post)
 import test_review_explanation_actions as prior
 if missing_plan:
  original_spec=prior.spec;original_proposal=prior.proposal
  def with_approval_spec():
   spec=original_spec()
   spec['fields']['approval']={'kind':'FACT','type':'boolean','unit':'','concept':'서면 승인','period':'건별','as_of':'2026-11-03','baseline':None}
   spec['rules'].append({'node_id':'N2','expression':{'field':'approval'},'source_ids':['S1'],'rounding':'EXACT_ONLY'})
   return spec
  def with_approval_node(*args,**kwargs):
   value=original_proposal(*args,**kwargs);graph=value['graph'];node=deepcopy(graph['nodes'][0]);node['id']='N2'
   node['text']='별도 승인 확인';node['slots']['statement']['value']=node['text'];graph['nodes'].append(node)
   graph['purposes'].append({'id':'P2','purpose':'required-action','roots':['N2'],'title':'합성 승인 확인'})
   return value
  monkeypatch.setattr(prior,'spec',with_approval_spec);monkeypatch.setattr(prior,'proposal',with_approval_node)
 prior.test_native_typed_scenario_and_explicit_ontology_use(env,tmp_path,term_glossary,monkeypatch,fault)
 assert responses
 for body in responses:
  t=body['assembly']['term_agent'];r=t['review_explanation']['scenario_calculation']
  assert calc.build(t['scenario_context'])==r
  assert '가정의 계산 결과' in json.dumps(body['answer'],ensure_ascii=False)
 assert wire_views
 for body in wire_views:
  schema=body['response_format']['json_schema']['schema']
  assert 'review_links' in schema['properties']
  assert 'application_links' not in schema['properties']['scenario_review']['properties']
  assert 'condition_results' not in schema['properties']['scenario_review']['properties']
  assert calc.PROMPT in body['messages'][0]['content']
  restored=ai.restore(json.loads(body['messages'][1]['content'])['view'])
  assert 'calculation_catalog' not in restored['hypothetical_scenario']
  assert 'application_values' not in restored['hypothetical_scenario']
  def no_pair(node):
   if isinstance(node,dict):
    assert not {'claim_refs','basis_refs'}<=node.get('properties',{}).keys()
    for child in node.values():no_pair(child)
   elif isinstance(node,list):
    for child in node:no_pair(child)
  for field in links.REVIEWS:
   if field in schema['properties']:no_pair(schema['properties'][field])
  assert links.PROMPT in body['messages'][0]['content']
 from semantic_runtime.legal_agent import journal_storage,scenario_review
 saved=[]
 for journal in tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/*/journal.sqlite'):
  with journal_storage.connect(journal) as db:
   saved.extend(json.loads(row[0])['assessment'] for row in db.execute("SELECT payload_json FROM event WHERE kind='ASSESSMENT_VALIDATED'") if links.FIELD in json.loads(row[0])['assessment'])
 if fault in ('repair_success','rule_success'):
  assert saved
  for assessment in saved:
   links.verify_saved(assessment)
   assert assessment['scenario_calculation']['legal_conclusion_confirmed'] is False
   if missing_plan:assert assessment['scenario_calculation']['missing_fields']==['approval']
   forged=deepcopy(assessment);forged['review_links']['links'][0]['basis_refs']=['foreign']
   with pytest.raises(ContractError):links.verify_saved(forged)
   if fault=='rule_success':
    display=calc.render(assessment['scenario_calculation'])
    assert '2450000원' in display and '1000000원' in display
    assert '245만 원' in assessment['claims'][0]['answer_content']['explanation']
  if missing_plan:
   assert seen, 'native fixture must explicitly choose a computed missing-input reference'
   assert any('서면 승인 입력이 미확인' in g['reason'] for a in saved for g in a['gaps'])


 import sqlite3
 dumps=[]
 for path in tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/*/journal.sqlite'):
  with sqlite3.connect(path) as db:dumps.extend(db.iterdump())
 assert any('COMPUTED_GAP_IN_REASON' in text for text in dumps)
 assert any('미확인 computed-gap:' in text or '\\ubbf8\\ud655\\uc778 computed-gap:' in text for text in dumps)
