"""Candidate publication/tool contracts with synthetic transport, no model eval."""
import importlib.util, json, sys
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')]
from test_legal_agent_double_harness import generation, wire
from conftest import term_glossary
from test_bounded_source_main import Transport, settings
from test_legal_agent_v5 import app_for
C=R/'02_BACKEND/lawrag/research/candidates/adr_0555/catalogue-router/revisions/rev-002/snapshot/02_BACKEND/semantic_runtime/legal_agent'

def load(name, path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

@pytest.fixture
def candidate(monkeypatch):
 from semantic_runtime.legal_agent import bounded_source_session as existing
 module=load('semantic_runtime.legal_agent._catalogue555',C/'bounded_source_session.py')
 module.source_query_planning=load('semantic_runtime.legal_agent._route555',C/'source_query_planning.py')
 monkeypatch.setattr(existing,'BoundedSourceSession',module.BoundedSourceSession)
 return module

class Routed(Transport):
 def __init__(self,mode,inspect=False):super().__init__();self.mode=mode;self.inspect=inspect
 def send_once(self,*,body,ticket):
  self.calls.append(body);v=json.loads(body['messages'][1]['content'])['view'];phase=v['source_stage']
  if phase=='source-query-plan':
   return wire({'mode':self.mode,'reason':'합성 계약 판단','answer':'안녕하세요. 법령검색 에이전트입니다.' if self.mode=='DIRECT' else '법률 관련 자료를 다루므로 해당 질문은 서비스 범위 밖입니다.' if self.mode=='OUT_OF_DOMAIN' else '',
    'law_names':[],'queries':[],'document_category':'all','browse_view':'documents','title_query':'','inspect_documents':self.inspect})
  if phase=='catalogue-document-choice':return wire({'targets':[v['catalogue'][0]['target']],'reason':'실제 목록의 문서'})
  if phase=='catalogue-next-step':
   outline=v['observed_outlines'][0];return wire({'search_required':False,'answer':outline['document']['name']+'의 조회한 목차에서 읽을 곳을 확인하세요.','law_names':[],'queries':[]})
  raise AssertionError(phase)

@pytest.mark.parametrize('mode,inspect,calls',[('DIRECT',False,1),('OUT_OF_DOMAIN',False,1),('BROWSE',False,1),('BROWSE',True,3)])
def test_candidate_commits_route_and_publishes_observed_metadata(candidate,tmp_path,generation,mode,inspect,calls):
 transport=Routed(mode,inspect);app=app_for(tmp_path,generation,transport,settings())
 try:
  ask=next(r.endpoint for r in app.routes if r.path=='/v1/rag/ask')
  result=ask({'question':'어떤 자료를 읽으면 좋을까요?' if inspect else '현재 문서는?' if mode=='BROWSE' else '안녕' if mode=='DIRECT' else '김치찌개 레시피줘','document_ids':['d']})
  assert result['answer']['text'].strip()
  assert result['answer']['claims']==[]
  assert result['assembly']['term_agent']['request_routing']['mode']==mode
  assert len(transport.calls)==calls
  assert result['assembly']['term_agent']['source_bundle']['sources']==[]
  if mode=='BROWSE':assert '모의승인규정' in result['answer']['text']
 finally:app.state.pipeline.store.close()

def test_candidate_search_keeps_original_acquisition_and_publication(candidate,tmp_path,generation):
 class Search(Transport):
  def send_once(self,*,body,ticket):
   view=json.loads(body['messages'][1]['content'])['view']
   if view.get('source_stage')=='source-query-plan':
    self.calls.append(body)
    return wire({'mode':'SEARCH','reason':'법률 내용 질문','answer':'',
     'law_names':['모의승인규정'],'queries':['모의승인규정 제1조','모의승인규정 제2조'],
     'document_category':'all','browse_view':'documents','title_query':'','inspect_documents':False})
   return super().send_once(body=body,ticket=ticket)
 transport=Search();app=app_for(tmp_path,generation,transport,settings())
 try:
  ask=next(r.endpoint for r in app.routes if r.path=='/v1/rag/ask')
  result=ask({'question':'안녕, 모의승인규정의 승인 대상과 예외는?','document_ids':['d']})
  assert result['assembly']['term_agent']['request_routing']['mode']=='SEARCH'
  assert result['answer']['claims']
  assert len(result['assembly']['term_agent']['source_bundle']['sources'])==2
 finally:app.state.pipeline.store.close()
