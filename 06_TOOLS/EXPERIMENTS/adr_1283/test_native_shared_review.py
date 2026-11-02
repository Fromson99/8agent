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
ROOT=Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('fault',['missing_receipt','wrong_condition','stale_value','repair_success','rule_stale','rule_success'])
def test_native_generation_repair_publication_and_duplicate(env,tmp_path,term_glossary,monkeypatch,fault):
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
    value['claims'][0]['explanation']='변경 전 한도100만 원에서 가정 한도245만 원으로 바뀐다. 비용150만원은 가정 금액 조건을 충족하고, 서면 승인은 미확인이다.'
   if fault=='repair_success' and last['source_stage'].endswith('-repair'):
    value['claims'][0]['rule']=None
    value['claims'][0]['explanation']='가정 비용50만원으로 금액 조건을 검토했으며 서면 승인은 미확인이다.'
   v['version']=app.VERSION;v['application_links']=[]
   catalog=app.values(c)
   for claim in value['claims']:
    if not claim.get('explanation') and (claim.get('rule') or {}).get('kind')!='CASE_APPLICATION':continue
    from semantic_runtime.legal_agent.scenario_review import condition_options
    conditions=[k for k,r in condition_options(c).items() if r['changed_inputs']]
    fields={k for condition in conditions for k in condition_options(c)[condition]['changed_inputs']}
    v['application_links'].append({'claim_id':claim['claim_id'],'condition_ids':conditions,
     'applied_value_refs':[k for k,r in catalog.items() if r['role']=='CURRENT' and r['field'] in fields],
     'comparison_value_refs':[k for k,r in catalog.items() if r['role']=='HISTORICAL' and r['field'] in fields] if fault=='rule_success' else []})
   value=share(value)
   if fault=='repair_success' and not last['source_stage'].endswith('-repair'):
    from semantic_runtime.legal_agent.scenario_review import results
    value['scenario_review']['condition_results']=results(c)
    value['requirement_review'][0]['link_ref']='review-link:999'
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
 import test_review_explanation_actions as prior
 prior.test_native_typed_scenario_and_explicit_ontology_use(env,tmp_path,term_glossary,monkeypatch,fault)
 assert wire_views
 for body in wire_views:
  schema=body['response_format']['json_schema']['schema']
  assert 'review_links' in schema['properties']
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
   assert assessment['scenario_application_display']
   forged=deepcopy(assessment);forged['review_links']['links'][0]['basis_refs']=['foreign']
   with pytest.raises(ContractError):links.verify_saved(forged)
   if fault=='rule_success':
    assert '2450000원' in assessment['scenario_application_display'][0]['text']
    assert '1000000원' in assessment['scenario_application_display'][0]['text']
    assert '245만 원' in assessment['claims'][0]['answer_content']['explanation']


def test_general_api_keeps_full_gap_reason_and_duplicate(tmp_path,term_glossary,monkeypatch):
 monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
 monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1282'))
 from test_native_lossless import test_full_600_character_gap_survives_native_publication_and_duplicate
 test_full_600_character_gap_survives_native_publication_and_duplicate(tmp_path,term_glossary,monkeypatch,[])
