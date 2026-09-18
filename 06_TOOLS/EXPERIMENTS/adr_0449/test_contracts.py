import sys,json,os
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from runtime import load,A
import fixtures
@pytest.fixture
def factory():
 mod,base,mods,root=load(bool(os.getenv("ADR449_TEST_FROZEN")));resources=[]
 def make(q='직원 성과급과 휴직',scope=None):
  store,m,g=fixtures.build(A/'dataset');resources.append(store);m=mod.bind_structure(m,store);s=mod.MultiSession(m,m.tools,g,q,scope or list(m.documents),{'max_calls':32,'context_chars':60000});return mod,s,store,m,g,mods,root
 yield make
 for store in resources:store.db.close()
def show(s):
 r=s.execute('CANDIDATES',{'offset':0});s.shown.update(x['id'] for x in r['items']);s.response_schema();return r
def test_two_independent_entries_union(factory):
 _,s,*_=factory();assert {x['label'] for x in s.entries}=={'성과급','휴직'};assert len(s.initial_pool_ids)==6;assert {'article:pay-base','article:leave-exception'}<=set(s.pool)
 assert not s.read_segments and not s.judgments
 opts=s.response_schema()['properties']['actions']['items']['anyOf'];assert {x['properties']['tool']['enum'][0] for x in opts}=={'CANDIDATES','STOP'}
def test_empty_direct_entry_uses_registered_relation(factory):
 _,s,*_=factory('인센티브와 휴직');assert len(s.entries)==2;assert 'article:pay-base' in s.pool
 eid=next(e['id'] for e in s.entries if e['label']=='인센티브');route=s.pool['article:pay-base'][eid]['routes'];assert route[0]['edge_ids']==['incentive-performance']
def test_overlap_deduplicates_preserves_paths(factory):
 _,s,*_=factory('성과급 인센티브');assert len(s.pool)==4;assert {'entry:1','entry:2'}<=set(s.pool['article:pay-base'])
def test_early_finish_blocked(factory):
 _,s,*_=factory();s.issues={'I':'지급'};s.judgments[('x','I')]={'source_id':'article:pay-base','status':'adopted','issue_id':'I'}
 with pytest.raises(ValueError,match='UNREVIEWED'):s.execute('STOP',{'status':'sufficient','unresolved':[]})
def test_metadata_dismissal_requires_shown_handle(factory):
 _,s,*_=factory();r=s.candidates();s.response_schema();h=r['items'][0]['read_handle']
 with pytest.raises(ValueError,match='delivered'):s.execute('DISMISS',{'read_handles':[h],'reason':'문서 대상 차이'})
 s.shown.add(r['items'][0]['id']);s.execute('DISMISS',{'read_handles':[h],'reason':'문서 대상 차이'});assert len(s.pending_candidates())==5
 with pytest.raises(ValueError):s.execute('DISMISS',{'read_handles':['RH999'],'reason':'없음'})
def test_read_judge_required_and_reference_expands(factory):
 _,s,*_=factory();r=show(s);item=next(x for x in r['items'] if x['id']=='article:leave-exception');out=s.execute('READ',item['read_action']['args']);s.delivered.add(out['id']);s.issues={'I':'휴직'}
 assert item['id'] in s.pending_candidates()
 s.execute('JUDGE',{'segment_id':out['id'],'status':'adopted','issue_id':'I','quote_ref':out['quote_refs'][0]['id'],'claim':'휴직 예외는 승인 필요'})
 assert item['id'] not in s.pending_candidates();assert 'article:approval-rule' in s.pending_candidates();assert 'reference:ref-leave-approval' in s.pool['article:approval-rule']
def test_reference_scope_not_expanded(factory):
 _,s,*_=factory(scope=['leave']);r=show(s);item=next(x for x in r['items'] if x['id']=='article:leave-exception');out=s.execute('READ',item['read_action']['args']);s.delivered.add(out['id']);s.issues={'I':'휴직'};s.execute('JUDGE',{'segment_id':out['id'],'status':'adopted','issue_id':'I','quote_ref':out['quote_refs'][0]['id'],'claim':'예외'});assert 'article:approval-rule' not in s.pool
 # An unresolved/out-of-scope reference must not be claimed as read.
 assert set(s.pool)=={'article:leave-exception','article:leave-form'}
def test_deferred_does_not_close_candidate(factory):
 _,s,*_=factory();r=show(s);item=r['items'][0];out=s.execute('READ',item['read_action']['args']);s.delivered.add(out['id']);s.issues={'I':'확인'};s.execute('JUDGE',{'segment_id':out['id'],'status':'deferred','issue_id':'I','quote_ref':out['quote_refs'][0]['id'],'claim':''});assert item['id'] in s.pending_candidates()
def test_first_page_delivery_no_duplicate_forced_scan(factory):
 _,s,*_=factory();r=s.candidates();s.last=[{'tool':'CANDIDATES','args':{},'status':'OK','result':r}];s.context();opts=s.response_schema()['properties']['actions']['items']['anyOf'];assert 'READ' in {x['properties']['tool']['enum'][0] for x in opts}
def test_pagination_not_top8_cut(factory):
 _,s,*_=factory('성과급 휴직 승인 혜택 특별 출장 안전 개인정보');assert len(s.pool)==12;r=show(s);assert len(r['items'])==8 and r['next_offset']==8;assert len(s.pool)==12
 opts=s.response_schema()['properties']['actions']['items']['anyOf'];assert {x['properties']['tool']['enum'][0] for x in opts}=={'CANDIDATES','STOP'}
def test_catalogue_uses_classification_not_name(factory):
 mod,s,store,m,*_=factory();all_=mod.document_listing(m,list(m.documents),'all');internal=mod.document_listing(m,list(m.documents),'internal');assert all_['total']==10;assert internal['total']==6;assert internal['unknown_category_count']==1;assert 'unknown' not in {d['id'] for d in internal['documents']};assert 'vendor' not in {d['id'] for d in internal['documents']}
def test_catalogue_respects_scope_unknown_is_not_absence(factory):
 mod,s,store,m,*_=factory();r=mod.document_listing(m,['unknown'],'internal');assert r['total']==0 and r['unknown_category_count']==1 and not r['classification_complete']
def test_catalogue_routing_does_not_swallow_content_question(factory):
 mod,*_=factory();assert mod.catalogue_request('우리 db에 있는 문서 알려줘')=='all';assert mod.catalogue_request('내규들은 어떤 게 있어?')=='internal';assert mod.catalogue_request('내규의 성과급 지급기준 내용을 알려줘') is None
def test_catalogue_pipeline_zero_model_calls(factory):
 mod,s,store,m,g,mods,root=factory()
 class Provider:
  def call(self,*a):raise AssertionError('catalogue should use database')
  def record_local(self,x):return {'kind':'catalogue-test','data':x}
 p=mods['pipeline'].Pipeline(root,store,Provider());p.term_agent=mod.MultiAgent(p,g,None,m);out=p.run('우리 내규들은 어떤 게 있어?',list(m.documents),True);p.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result');state=out['retrieval']['term_agent'];assert state['calls']==0 and len(state['catalogue']['documents'])==6;assert '분류 미확인 문서 1개' in out['answer']['text']
def test_catalogue_empty_unknown_wording(factory):
 mod,s,store,m,g,mods,root=factory()
 class Provider:
  def call(self,*a):raise AssertionError('no model')
  def record_local(self,x):return {'kind':'test'}
 p=mods['pipeline'].Pipeline(root,store,Provider());p.term_agent=mod.MultiAgent(p,g,None,m);out=p.run('내규들은 어떤 게 있어?',['unknown'],True);assert '없다고 단정할 수 없습니다' in out['answer']['text'];assert out['retrieval']['term_agent']['catalogue']['unknown_category_count']==1

def test_adopted_out_of_scope_reference_blocks_completion(factory):
 _,s,*_=factory(scope=['leave']);page=show(s);item=next(x for x in page['items'] if x['id']=='article:leave-exception');out=s.execute('READ',item['read_action']['args']);s.delivered.add(out['id']);s.issues={'I':'휴직 예외'}
 s.execute('JUDGE',{'segment_id':out['id'],'status':'adopted','issue_id':'I','quote_ref':out['quote_refs'][0]['id'],'claim':'별도 승인 확인 필요'})
 assert s.unresolved_references()
 with pytest.raises(ValueError,match='REFERENCE'):s.execute('STOP',{'status':'sufficient','unresolved':[]})
