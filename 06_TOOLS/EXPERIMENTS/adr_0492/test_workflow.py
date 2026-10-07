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

def test_review_card_and_view_specific_enum(tmp_path,generation):
 with session(tmp_path,generation) as s:
  read(s);v=s.view('investigate');delivered(s,v);s.commit_selection(v,choice(v));s.select({'retrieval':s.retrieval()})
  v=s.view('compose',required=s.packed['evidence_ids']);delivered(s,v)
  p={'text':'승인 조건','evidence':s.packed['evidence_ids'],'question_refs':[q['id'] for q in s.context.pieces],'fact_dependencies':[],'relation_dependencies':[]}
  s.commit_draft(v,{'paragraphs':[p],'limitations':[]});heads=s.work.heads('claim',current=True)
  v=s.view('review',required=s.packed['evidence_ids'],extra={'claims':heads})
  assert v['claims']==[{'claim':heads[0]['entity_id'],**p}]
  schema=s.gateway.request('review',v,'ReviewDecision')['response_format']['json_schema']['schema']
  assert schema['properties']['checks']['items']['properties']['claim']['enum']==[heads[0]['entity_id']]
  delivered(s,v)
  bad={'checks':[{'claim':'wrong','verdict':'SUPPORTED','evidence':p['evidence'],'issue':'없음','reason':'확인','actions':[],'relation_checks':[]}], 'question':{'status':'RESOLVED','question_refs':p['question_refs'],'reason':'확인'}}
  with pytest.raises(ProposalError):s.commit_review(v,bad)
  assert s.build_bundle()['sources'];assert not s.work.heads('review')

def test_schema_error_identifies_exact_field():
 bad={'checks':[{'claim':'x'*200,'verdict':'SUPPORTED','evidence':['E1'],'issue':'없음','reason':'확인','actions':[],'relation_checks':[]}], 'question':{'status':'RESOLVED','question_refs':['Q1'],'reason':'확인'}}
 with pytest.raises(ProposalError,match='/checks/0/claim'):protocol.validate('ReviewDecision',bad)

def test_packing_boundary_and_distinct_cursor_reservations(tmp_path,generation):
 from semantic_runtime.legal_agent.errors import BudgetExhausted
 with session(tmp_path,generation,{**PROFILE,'max_read_chars':600}) as s:
  read(s);read(s,'모의승인규정 제2조','r2')
  original=s.work.save_view
  # Capture the complete body exactly at the packing boundary, before repository envelopes.
  s.work.save_view=lambda phase,body,evidence:body
  successes=0
  for limit in range(3000,8500,19):
   s.profile['max_context_chars']=limit
   try:v=s.view('investigate')
   except BudgetExhausted as exc:
    assert 'before' in str(exc) or 'question and protocol' in str(exc),str(exc)
    continue
   successes+=1;assert len(encoded(v))+512<=limit
   assert 'relation_details' in v
   cursors=[c['action']['args']['cursor'] for c in v['continuations']]
   assert len(cursors)==len(set(cursors))
   assert all(c in v['offered_handles'] for c in cursors)
  assert successes>100
  s.work.save_view=original

def test_document_article_repair_then_actual_read(tmp_path,generation):
 with session(tmp_path,generation) as s:
  s.sources.execute(tool('search',target=s.sources.root,query='모의승인규정',mode='title',cursor=None),'search',actor='MODEL')
  v=s.view('investigate');delivered(s,v)
  target=next(h for h in v['offered_handles'] if h.startswith('D'))
  bad=turn(v,[tool('read',target=target,extent='article',cursor=None)])
  with pytest.raises(ProposalError,match='preserved'):s.apply_turn(v,bad)
  record=next(e for e in reversed(s.errors) if e['code']=='OPERATION_REJECTED');fix=record['errors'][0]['corrective_actions'][0]
  assert fix['args']['extent']=='subtree'
  assert not s.work.evidence()
  v=s.view('investigate');delivered(s,v);s.apply_turn(v,dict(turn(v,[fix]),intent='CONTINUE'))
  assert s.work.evidence()

def test_error_observation_enters_repair_preserving_selection(tmp_path,generation):
 with session(tmp_path,generation) as s:
  read(s);v=s.view('investigate');delivered(s,v);ident=v['exact_evidence'][0]['evidence']
  # E + article passes old syntactic validation but returns an ERROR observation at execution.
  with pytest.raises(ProposalError,match='preserved'):s.apply_turn(v,turn(v,[tool('read',target=ident,extent='article',cursor=None)]))
  record=next(e for e in reversed(s.errors) if e['code']=='OPERATION_REJECTED');e=record['errors'][0]
  assert e['observation_id'];assert 'exact extent' in e['message'];assert s.build_bundle()['sources']
  fix=e['corrective_actions'][0];assert fix['args']['extent']=='exact'
  v=s.view('investigate');delivered(s,v);s.apply_turn(v,dict(turn(v,[fix]),intent='CONTINUE'))
  assert any(o['status']=='REUSED' for o in s.work.observations(20))
  assert s.build_bundle()['sources']

@pytest.fixture
def article_generation(tmp_path,term_glossary):
 import sqlite3
 from test_document_release import source
 from lawrag.pipeline.term_generation import build_generation
 texts=['제1조(승인)','①승인은 이사회가 결정한다. 다만 소액은 제외한다.','②신청서와 확인서를 제출한다.','제2조 다른 조의 원문']
 raw=source(tmp_path/'article.sqlite',[('d','모의규정',texts)])
 with sqlite3.connect(raw) as db:
  for uid,parent,unit in [('0',None,{'family':'kr_article','surface':'제1조','span':[0,3]}),('1','0',{'family':'kr_paragraph','surface':'제1항','span':[1,2]}),('2','0',{'family':'kr_paragraph','surface':'제2항','span':[2,3]}),('3',None,{'family':'kr_article','surface':'제2조','span':[3,4]})]:
   db.execute('UPDATE source_unit SET parent_id=?,json=? WHERE document_id=? AND unit_id=?',(parent,json.dumps(unit),'d',uid))
 build_generation(raw,term_glossary,tmp_path/'article-g',serving=True)
 return tmp_path/'article-g/generation'

@pytest.mark.parametrize('narrow',[True,False])
def test_article_read_expands_paragraph_and_excludes_neighbour(tmp_path,article_generation,narrow):
 with session(tmp_path,article_generation) as s:
  sid=s.sources.matcher._unit_sources('d','2')[0]
  n={'document_id':'d','unit_id':'2','source_id':sid}
  if narrow:n['block_ids']=['2']
  target=s.sources.handle('P',n)
  r=s.sources.execute(tool('read',target=target,extent='article',cursor=None),'article',actor='MODEL')
  assert r['coverage']['complete'] and r['next_cursor'] is None
  spans=[p for e in r['evidence_ids'] for p in s.work.evidence(e)['spans']]
  assert {p['block_id'] for p in spans}=={'0','1','2'}
  assert '다만 소액' in ''.join(p['text'] for p in spans)
  assert '다른 조' not in ''.join(p['text'] for p in spans)
  v=s.view('investigate');delivered(s,v);s.commit_selection(v,choice(v))
  assert '①승인' in s.build_bundle()['sources'][0]['excerpt']

def test_article_coverage_waits_for_all_pages(tmp_path,article_generation):
 with session(tmp_path,article_generation,{**PROFILE,'max_read_chars':12}) as s:
  sid=s.sources.matcher._unit_sources('d','2')[0]
  target=s.sources.handle('P',{'document_id':'d','unit_id':'2','source_id':sid,'block_ids':['2']})
  cursor=None;keys=set();texts=[]
  for i in range(20):
   r=s.sources.execute(tool('read',target=target,extent='article',cursor=cursor),'page'+str(i),actor='MODEL')
   keys.add(r['coverage_key']);texts.extend(p['text'] for e in r['evidence_ids'] for p in s.work.evidence(e)['spans'])
   cursor=r['next_cursor']
   if cursor is None:
    assert r['coverage']['complete'];break
   assert not r['coverage']['complete'] and r['status']=='PARTIAL'
  else:pytest.fail('article pagination never completed')
  assert len(keys)==1 and i>1 and '다만 소액은 제외한다.' in ''.join(texts)

def test_narrow_subtree_stays_narrow_then_article_widens(tmp_path,article_generation):
 with session(tmp_path,article_generation) as s:
  sid=s.sources.matcher._unit_sources('d','2')[0]
  target=s.sources.handle('P',{'document_id':'d','unit_id':'2','source_id':sid,'block_ids':['2']})
  narrow=s.sources.execute(tool('read',target=target,extent='subtree',cursor=None),'narrow',actor='MODEL')
  assert {p['block_id'] for e in narrow['evidence_ids'] for p in s.work.evidence(e)['spans']}=={'2'}
  whole=s.sources.execute(tool('read',target=target,extent='article',cursor=None),'whole',actor='MODEL')
  assert whole['coverage_key']!=narrow['coverage_key']
  assert {p['block_id'] for e in whole['evidence_ids'] for p in s.work.evidence(e)['spans']}=={'0','1','2'}
