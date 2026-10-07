"""Preserved article paging/direct-reference contracts from the completed workflow candidate."""
from contextlib import contextmanager
from copy import deepcopy
import json
import pytest
from conftest import term_glossary
from test_legal_agent_v5 import session as v5_session, PROFILE, plan, decision
from test_tool_exploration_v3 import read, delivered, tool
from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.legal_agent.repository import encoded
@contextmanager
def session(tmp_path,generation,profile=None):
    with v5_session(tmp_path,generation,profile=profile) as s:yield s

def choice(v):
    return {'choices':[{'source':e['evidence'],'decision':'KEEP_CORE','reason':'승인 조건 원문'} for e in v['exact_evidence']]}

def turn(v, actions=()):
    return decision(plan(),source_selection=choice(v),actions=list(actions),intent='CONTINUE' if actions else 'DRAFT')

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

def test_bound_next_action_preserves_target_extent_and_page(tmp_path,article_generation):
 with session(tmp_path,article_generation,{**PROFILE,'max_read_chars':12}) as s:
  sid=s.sources.matcher._unit_sources('d','2')[0]
  target=s.sources.handle('P',{'document_id':'d','unit_id':'2','source_id':sid,'block_ids':['2']})
  r=s.sources.execute(tool('read',target=target,extent='article',cursor=None),'first',actor='MODEL')
  v=s.view('investigate');n=v['next_actions'][0]
  assert n['args']=={'target':target,'extent':'article','cursor':r['next_cursor']}
  assert target in v['offered_handles'] and r['next_cursor'] in v['offered_handles']
  s.sources.validate_action(n,set(v['offered_handles']))
  later=s.sources.execute(n,'next',actor='MODEL')
  assert later['evidence_ids']!=r['evidence_ids']

def test_cursor_as_target_repair_actually_continues_and_preserves_selection(tmp_path,article_generation):
 with session(tmp_path,article_generation,{**PROFILE,'max_read_chars':12}) as s:
  sid=s.sources.matcher._unit_sources('d','2')[0]
  target=s.sources.handle('P',{'document_id':'d','unit_id':'2','source_id':sid,'block_ids':['2']})
  r=s.sources.execute(tool('read',target=target,extent='article',cursor=None),'first',actor='MODEL')
  v=s.view('investigate');delivered(s,v)
  bad=tool('read',target=r['next_cursor'],extent='subtree',cursor=None)
  with pytest.raises(ProposalError):s.apply_turn(v,dict(turn(v,[bad]),intent='CONTINUE'))
  assert s.build_bundle()['sources']
  record=next(e for e in reversed(s.errors) if e['code']=='OPERATION_REJECTED')
  fix=record['errors'][0]['corrective_actions'][0]
  assert fix['args']['target']==target and fix['args']['cursor']==r['next_cursor']
  v=s.view('investigate');delivered(s,v);before=len(s.work.evidence())
  s.apply_turn(v,dict(turn(v,[fix]),intent='CONTINUE'))
  assert len(s.work.evidence())>before and s.build_bundle()['sources']

def test_unknown_or_retargeted_cursor_stays_rejected(tmp_path,article_generation):
 with session(tmp_path,article_generation,{**PROFILE,'max_read_chars':12}) as s:
  sid=s.sources.matcher._unit_sources('d','2')[0]
  target=s.sources.handle('P',{'document_id':'d','unit_id':'2','source_id':sid,'block_ids':['2']})
  s.sources.execute(tool('read',target=target,extent='article',cursor=None),'first',actor='MODEL')
  v=s.view('investigate');n=deepcopy(v['next_actions'][0])
  assert s.corrective_actions(v,tool('read',target='Punknown',extent='subtree',cursor=None))==[]
  other=s.sources.handle('U',{'document_id':'d','unit_id':'3'})
  n['args']['target']=other
  with pytest.raises(ProposalError):s.sources.validate_action(n)
  n['args']['cursor']='Punknown'
  with pytest.raises(ProposalError):s.sources.validate_action(n)

from test_document_release import source
from lawrag.pipeline.term_generation import build_generation

def relation_fixture(tmp_path,term_glossary,texts):
 raw=source(tmp_path/'relation.sqlite',[('d','모의규정',texts)])
 build_generation(raw,term_glossary,tmp_path/'relation-g',serving=True)
 return tmp_path/'relation-g/generation'

def decisions(s):
 return [json.loads(r['result_json']) for r in s.work.db.execute("SELECT * FROM system_task WHERE operation_json LIKE '%prefetch_decision%' AND result_json IS NOT NULL")]

@pytest.mark.parametrize('incoming',[False,True])
def test_small_links_all_read_both_directions(tmp_path,term_glossary,incoming):
 texts=['기준 내용.','제1조에 따른다.','제1조에 따른다.'] if incoming else ['제2조에 따르고 제3조를 준용한다.','두 번째 내용.','세 번째 내용.']
 g=relation_fixture(tmp_path,term_glossary,texts)
 with session(tmp_path,g) as s:
  r=read(s,'모의규정 제1조')
  assert len(s.work.evidence())==3
  assert {n['direction'] for n in s.work.notices()}==({'incoming'} if incoming else {'outgoing'})
  assert decisions(s)[0]['pending_target_count']==2
  v=s.view('investigate');delivered(s,v)
  assert len(v['exact_evidence'])==3
  assert len(v['relation_menu'])==2
  assert all(n['target_labels'][0]['read_action'] for n in v['relation_menu'])
  assert v['relation_delivery'][0]['reason']=='ALL_RESOLVABLE_DIRECT_TARGETS_QUEUED'
  read(s,'모의규정 제1조','again');assert len(s.work.evidence())==3

def test_auto_read_cycle_stops_and_explicit_second_hop_expands(tmp_path,term_glossary):
 g=relation_fixture(tmp_path,term_glossary,['제2조를 준용한다.','제3조를 준용한다.','제1조를 준용한다.'])
 with session(tmp_path,g) as s:
  read(s,'모의규정 제1조');assert len(s.work.evidence())==3
  assert len(decisions(s))==1
  read(s,'모의규정 제2조','explicit');assert len(decisions(s))==2
  assert len(s.work.evidence())==3

def test_large_links_keep_actionable_menu_and_system_continuation(tmp_path,term_glossary):
 g=relation_fixture(tmp_path,term_glossary,['제2조에 따르고 제3조를 준용한다.','두 번째.','세 번째.'])
 with session(tmp_path,g,{**PROFILE,'relation_page_size':1}) as s:
  read(s,'모의규정 제1조');assert len(s.work.evidence())==1
  v=s.view('investigate');assert v['relation_delivery'][0]['status']=='SKIPPED_SELECTION'
  nxt=next(n for n in v['next_actions'] if n['tool']=='follow_relations')
  assert nxt['args']['cursor'];s.sources.validate_action(nxt)
  delivered(s,v)
  target=v['relation_menu'][0]['target_labels'][0]['read_action']
  s.sources.execute({**target,'question_refs':['Q1'],'expected_information':'선택 연결 원문','reason':'직접 선택'},'selected',actor='MODEL')
  assert len(s.work.evidence())>=2

def test_long_target_requires_selection_not_partial_auto_success(tmp_path,term_glossary):
 g=relation_fixture(tmp_path,term_glossary,['제2조를 준용한다.','긴 대상 원문. '*100])
 with session(tmp_path,g,{**PROFILE,'max_auto_reference_chars_per_request':50}) as s:
  read(s,'모의규정 제1조');assert len(s.work.evidence())==1
  assert decisions(s)[0]['reason']=='TARGET_TEXT_LIMIT'
  v=s.view('investigate');assert v['relation_menu'][0]['target_labels'][0]['read_action']

def test_small_set_above_old_four_card_cap_all_presented(tmp_path,term_glossary):
 g=relation_fixture(tmp_path,term_glossary,['기준 내용.']+['제1조에 따른다. '+str(i) for i in range(5)])
 with session(tmp_path,g) as s:
  read(s,'모의규정 제1조');assert len(s.work.evidence())==6
  v=s.view('investigate');delivered(s,v)
  assert len(v['exact_evidence'])==6
  assert len(encoded(v))<=s.profile['max_context_chars']

def test_unresolved_is_explicit_not_no_relation(tmp_path,term_glossary):
 g=relation_fixture(tmp_path,term_glossary,['「없는규정」 제99조를 준용한다.'])
 with session(tmp_path,g) as s:
  read(s,'모의규정 제1조');d=decisions(s)[0]
  assert d['unresolved_count']>0 and d['reason']=='UNRESOLVED_RELATIONS'
  assert len(s.work.evidence())==1
