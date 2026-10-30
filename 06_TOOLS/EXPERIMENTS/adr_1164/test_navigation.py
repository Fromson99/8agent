from test_unit_fulltext_adaptive_read import tree,session
from test_law_grouped_navigation import enable,decide,reader
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent import law_navigation as ln
from semantic_runtime.initial_vector import VectorUnavailable
import pytest

class Vector:
 def __init__(self,s):self.s=s;self.calls=0
 def search(self,q,docs):
  self.calls+=1
  src=next(v for v in self.s.tools.sources.values() if v['document_id']=='d')
  return {'rows':[{'SOURCE_ID':src['id'],'DOC_ID':'d','DISTANCE':0.1}],'publication_id':'a'*64,'truncated':False,'embedding_calls':1}

def test_vector_real_navigation_read(session,monkeypatch):
 monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH','vector')
 native,_=session;s=native.sources;enable(s);v=Vector(s);s.matcher.initial_vector=v
 rec=SourceRecall(s).prepare();assert rec['law_navigation']['search_policy']=='vector-initial-v1'
 inv=ln.Investigation(s,'긴급 승인 예외',rec,reader,120,None,None)
 data,actions=inv.view();row=data['initial_vector_candidates'][0];target=row['read_action']
 assert actions[target]['action']=='READ_ARTICLES'
 value=decide(data,'READ_ARTICLES',target)
 inv.validate(value,data,actions);inv.execute(value,data,actions)
 assert inv.read_records() and v.calls==1
 nextdata,_=inv.view();assert nextdata['basis']

def test_empty_vector_returns_keyword(session,monkeypatch):
 monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH','vector');native,_=session;s=native.sources;enable(s)
 class Empty:
  def search(self,*a):return {'rows':[],'publication_id':'a'*64}
 s.matcher.initial_vector=Empty();rec=SourceRecall(s).prepare();assert rec['law_navigation']['search_policy']!='vector-initial-v1'

def test_timeout_vector_returns_keyword(session,monkeypatch):
 monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH','vector');native,_=session;s=native.sources;enable(s)
 class Timeout:
  def search(self,*a):raise VectorUnavailable('TIMEOUT')
 s.matcher.initial_vector=Timeout();rec=SourceRecall(s).prepare();assert rec['law_navigation']['search_policy']!='vector-initial-v1'

def test_keyword_switch_never_calls_embedding(session,monkeypatch):
 monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH','keyword');native,_=session;s=native.sources;enable(s);v=Vector(s);s.matcher.initial_vector=v
 rec=SourceRecall(s).prepare();assert v.calls==0
