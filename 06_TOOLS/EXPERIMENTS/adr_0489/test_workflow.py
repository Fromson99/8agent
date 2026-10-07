from conftest import term_glossary
import json
from copy import deepcopy
import pytest
from test_legal_agent_double_harness import generation
from test_source_tiers_v4 import session,PROFILE,app_for
from test_tool_exploration_v3 import read,delivered,tool
from semantic_runtime.legal_agent.errors import ProposalError,ContractError
from semantic_runtime.legal_agent import tiers_protocol as protocol
from semantic_runtime.legal_agent.repository import encoded

def choice(v):return {'choices':[{'source':e['evidence'],'decision':'KEEP_CORE','reason':'승인 조건 원문'} for e in v['exact_evidence']]}
def turn(v,actions=()):return dict(source_selection=choice(v),actions=list(actions),assessments=[],relation_assessments=[],intent='DRAFT',reason='관련 원문 선택')
def test_whole_delivered_source_and_server_status(tmp_path,generation):
 with session(tmp_path,generation) as s:
  read(s);v=s.view('investigate');delivered(s,v);s.commit_selection(v,choice(v));b=s.build_bundle()
  assert b['sources'];assert b['sources'][0]['interpretation_status']=='UNASSESSED'
  assert all(e['source']==e['evidence'] for e in v['exact_evidence'])
  assert not v['selectable_spans']
  c=b['sources'][0];e=s.work.evidence(c['evidence_id'])
  assert ''.join(p['text'] for p in c['spans'])==''.join(s.sources.store.source(e['document_id'],p['block_id'])['text'][p['start_cp']:p['end_cp']] for p in e['spans'])
def test_good_source_survives_bad_read_and_retry(tmp_path,generation):
 with session(tmp_path,generation) as s:
  read(s);v=s.view('investigate');delivered(s,v)
  d=turn(v,[tool('read',target=s.sources.root,extent='self',cursor=None)])
  with pytest.raises(ProposalError,match='preserved'):s.apply_turn(v,d)
  assert s.build_bundle()['sources']
  v2=s.view('investigate');assert any(e.get('code')=='OPERATION_REJECTED' for e in v2['errors'])
  delivered(s,v2);s.apply_turn(v2,turn(v2));assert len(s.build_bundle()['sources'])==1
  assert s.apply_turn(v2,turn(v2)) is False

def test_valid_source_survives_unknown_choice(tmp_path,generation):
 with session(tmp_path,generation) as s:
  read(s);v=s.view('investigate');delivered(s,v);d=choice(v)
  d['choices'].append({'source':'unseen','decision':'KEEP_CORE','reason':'bad'})
  with pytest.raises(ProposalError):s.commit_selection(v,d)
  assert s.build_bundle()['sources']

def test_discovery_changes_progress_and_no_read_cannot_finish(tmp_path,generation):
 with session(tmp_path,generation) as s:
  before=s.progress_key();s.sources.execute(tool('locate',target=s.sources.root,locator='모의승인규정 제1조',branch='any',cursor=None),'locate',actor='MODEL')
  assert s.progress_key()!=before;v=s.view('investigate');delivered(s,v)
  assert not s.work.evidence()
  with pytest.raises(ProposalError):s.apply_turn(v,turn(v))

def test_wire_envelope_preserves_valid_operations(tmp_path,generation):
 with session(tmp_path,generation) as s:
  read(s);v=s.view('investigate');delivered(s,v);d=turn(v,[{'bad':'action'}])
  protocol.validate_wire('TurnDecision',d)
  with pytest.raises(ProposalError):s.apply_turn(v,d)
  assert s.build_bundle()['sources']
  with pytest.raises(ProposalError):protocol.validate_wire('TurnDecision',{'actions':[]})

def test_final_payload_budget_and_exact_receipt(tmp_path,generation):
 with session(tmp_path,generation,{**PROFILE,'max_context_chars':6000,'max_read_chars':2000}) as s:
  read(s);v=s.view('investigate');delivered(s,v)
  assert len(encoded(v))<=6000
  assert v['exact_evidence']
  assert len(encoded(s.gateway.request('investigate',v,'TurnDecision')).encode())<=s.gateway.transport.binding['max_input_bytes']
  for e in v['exact_evidence']:assert e['text']==s.work.evidence(e['evidence'])['text']

def test_no_selection_is_not_absence(tmp_path,generation):
 with session(tmp_path,generation) as s:
  assert s.build_bundle()['status']=='NO_SELECTION'
  assert s.metadata()['source_workflow']['absence_confirmed'] is False

def test_unpresented_source_stays_rejected(tmp_path,generation):
 with session(tmp_path,generation) as s:
  read(s);v=s.view('investigate')
  with pytest.raises(ProposalError):s.commit_selection(v,choice(v))
  assert not s.work.heads('source_selection')

def test_long_source_not_rejected_by_display_cap(tmp_path,term_glossary):
 from test_document_release import source
 from lawrag.pipeline.term_generation import build_generation
 raw=source(tmp_path/'source.sqlite',[('d','모의규정',['승인 조건을 검토한다. '*180])])
 build_generation(raw,term_glossary,tmp_path/'g',serving=True)
 with session(tmp_path,tmp_path/'g/generation') as s:
  read(s,'모의규정 제1조');v=s.view('investigate');delivered(s,v);s.commit_selection(v,choice(v));b=s.build_bundle()
  assert len(b['sources'][0]['excerpt'])>1600
  assert b['sources'][0]['coverage']=='PARTIAL'

def test_selected_source_reaches_draft_and_independent_review(tmp_path,generation):
 with session(tmp_path,generation) as s:
  read(s);v=s.view('investigate');delivered(s,v);s.commit_selection(v,choice(v))
  s.select({'retrieval':s.retrieval()});assert s.packed['support'];assert not s.work.heads('assessment')
  v=s.view('compose',required=s.packed['evidence_ids']);delivered(s,v)
  p={'text':'모의 승인 조건','evidence':s.packed['evidence_ids'],'question_refs':[q['id'] for q in s.context.pieces],'fact_dependencies':[],'relation_dependencies':[]}
  s.commit_draft(v,{'paragraphs':[p],'limitations':[]})
  assert s.work.heads('claim');assert not s.work.heads('review')
  v=s.view('review',required=s.packed['evidence_ids']);delivered(s,v)
  c=s.work.heads('claim')[0]['entity_id']
  review={'checks':[{'claim':c,'verdict':'UNCERTAIN','evidence':p['evidence'],'issue':'조건 미확인','reason':'추가 사실 필요','actions':[],'relation_checks':[]}],
          'question':{'status':'UNRESOLVED','question_refs':p['question_refs'],'reason':'조건 미확인'}}
  s.commit_review(v,review);assert s.work.head('review',c)['payload']['verdict']=='UNCERTAIN'

def test_http_error_repair_source_publication_and_open(tmp_path,generation):
 from fastapi.testclient import TestClient
 from test_legal_agent_double_harness import BINDING,wire
 class Transport:
  binding=BINDING
  def __init__(self):self.calls=[];self.bad=False
  def validate_model(self):return {'verified':True,'synthetic':True}
  def send_once(self,*,body,ticket):
   self.calls.append(body);v=json.loads(body['messages'][1]['content'])['view']
   if v['phase']=='select_sources':return wire(choice(v))
   if v['phase']=='compose':return wire({'paragraphs':[],'limitations':['모의 작성 실패']})
   if not v['last_action_results']:return wire(dict(turn(v),source_selection=None,actions=[tool('locate',locator='모의승인규정 제1조',target=v['corpus_root'],branch='any',cursor=None)],intent='CONTINUE'))
   if not v['exact_evidence']:
    target=next(o['items'][0]['target'] for o in v['last_action_results'] if o['tool']=='locate')
    return wire(dict(turn(v),source_selection=None,actions=[tool('read',target=target,extent='subtree',cursor=None)],intent='CONTINUE'))
   if not self.bad:
    self.bad=True;return wire(turn(v,[tool('read',target=v['corpus_root'],extent='subtree',cursor=None)]))
   assert any(e.get('code')=='OPERATION_REJECTED' for e in v['errors'])
   return wire(turn(v))
 t=Transport();app=app_for(tmp_path,generation,t)
 with TestClient(app) as client:
  r=client.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']});assert r.status_code==200,r.text
  b=r.json()['assembly']['term_agent']['source_bundle'];assert b['sources']
  assert not r.json()['answer']['claims']
  assert client.get(b['sources'][0]['open_url']).status_code==200
  assert len(t.calls)<=PROFILE['max_model_attempts']
  assert any(json.loads(c['messages'][1]['content'])['view']['phase']=='compose' for c in t.calls)

@pytest.mark.parametrize('field,value',[('model','wrong'),('destination','https://wrong.invalid'),('scope_document_ids',[]),('source_authorization_sha256','0'*64),('private_documents_allowed',True)])
def test_scoped_export_grant_rejects_drift(field,value):
 from pathlib import Path
 from semantic_runtime.legal_agent.source_bundle import validate_export_authorization
 import hashlib
 R=Path('/home/jin/8-AGENT');g=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0488-qwen-source-tiers-v4-paired/artifacts/export-rebinding.json').read_text())
 b={'export_authorization':deepcopy(g),'generation_id':g['generation_id'],'store_sha256':g['source_store_sha256'],'source_export_allowed':g['source_manifest_export_allowed'],
    'scope':{'document_version_ids':g['scope_document_ids']},'model':{'model':g['model'],'endpoint_identity':hashlib.sha256(g['destination'].encode()).hexdigest()}}
 validate_export_authorization(b)
 b['export_authorization'][field]=value
 with pytest.raises(ContractError):validate_export_authorization(b)
