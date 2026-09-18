import json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parent))
import fixtures
from run_probe import load,A
M,ROOT=load(False)
@pytest.fixture
def session():
 store,matcher,g=fixtures.build(A/'dataset/synthetic-sources.json');s=M['structured_navigation'].StructuredSession(matcher,matcher.tools,g,'직원 성과급',['mock-staff','mock-customers','mock-travel']);s.issues={'Q1':'지급 기준'}
 yield s
 store.db.close()
def discover(s,sid='article:mock-staff'):s.source_card(sid);return sid
def deliver(s):s.delivered.update(s.active)
def test_catalogue_requires_delivered_pages(session):
 p=session.execute('CATALOG',{});assert p['total']==3 and not session.delivered
 with pytest.raises(ValueError):session.execute('STOP',{'status':'catalogue','unresolved':[]})
 session.catalogue_delivered.add(0);assert session.execute('STOP',{'status':'catalogue','unresolved':[]})['status']=='catalogue'
def test_literal_metadata_and_scope(session):
 p=session.execute('GREP',{'query':'휴직'});assert p['total']==1 and 'text' not in p['items'][0]
 assert not session.delivered
 with pytest.raises(ValueError):session.search('직원',document_id='private')
def test_fulltext_and_unavailable(session):
 assert session.search('원격 출장',mode='fulltext')['total']==1
 p=session.search('원격',mode='embedding');assert p['status']=='UNAVAILABLE' and p['matches'] is None
 assert session.search('없는말')['status']=='EMPTY'
def test_graph_and_reverse_term(session):
 session.term_card('incentive');p=session.graph('incentive',1,0);assert p['items'][0]['to_term']=='performance'
 sid=discover(session);p=session.execute('SOURCE_TERMS',{'source_id':sid});assert p['items'][0]['id']=='performance'
def test_complete_article_no_slicing(session):
 sid=discover(session);s=session.read(sid);assert len(s['text'])>2400 and s['text']==session.t.sources[sid]['text'] and '휴직' in s['text']
 assert s['kind']=='WHOLE_ARTICLE' and s['complete_article']
def test_large_article_metadata_whole_block_and_unread_guard(session):
 sid=discover(session);session.limits['active_chars']=1200;p=session.read(sid);assert p['status']=='CHOOSE_STRUCTURAL_UNIT' and not session.read_segments
 s=session.read(sid,unit_id='0');deliver(session);session.judge(s['id'],'adopted','Q1',s['text'],'지급 조건')
 with pytest.raises(ValueError,match='UNREAD_ARTICLE_BLOCKS'):session.execute('STOP',{'status':'sufficient','unresolved':[]})
 p=session.read(sid,unit_id='1');assert p['status']=='INDIVISIBLE_UNIT_TOO_LARGE' and not p['silent_truncation']
def test_undelivered_and_fabricated_quote_rejected(session):
 sid=discover(session);s=session.read(sid)
 with pytest.raises(ValueError):session.judge(s['id'],'adopted','Q1',s['text'],'조건')
 deliver(session)
 with pytest.raises(ValueError):session.judge(s['id'],'adopted','Q1','조작된 문장','조건')
def test_back_reopen_preserves_judgment(session):
 sid=discover(session);s=session.read(sid);deliver(session);session.execute('CHECKPOINT',{'name':'staff'});session.judge(s['id'],'adopted','Q1',s['text'],'조건')
 session.execute('BACK',{'name':'staff'});assert s['id'] in session.active and len(session.judgments)==1
 session.execute('RELEASE',{'segment_id':s['id']});assert not session.active
 assert session.execute('REOPEN',{'segment_id':s['id']})['text']==s['text']
def test_typed_args_and_failure_feedback(session):
 class P:
  def __init__(self):self.n=0
  def call(self,role,system,data,schema):
   self.n+=1
   if self.n==1:a={'tool':'READ','args':{'source_id':'INVALID'},'reason':'검증'}
   elif self.n==2:
    assert data['last_results'][0]['status']=='REJECTED';a={'tool':'GREP','args':{'query':'휴직'},'reason':'복구'}
   else:a={'tool':'STOP','args':{'status':'incomplete','unresolved':['원문 미검토']},'reason':'미확인 보존'}
   return {'issues':[],'actions':[a]},{}
 result=session.run(P());assert result['calls']==3 and result['trace'][1]['status']=='OK' and not result['failure']
def test_pipeline_catalogue_downstream():
 store,matcher,g=fixtures.build(A/'dataset/synthetic-sources.json')
 class P:
  def call(self,role,system,data,schema):
   a={'tool':'STOP','args':{'status':'catalogue','unresolved':[]},'reason':'전체 문서 확인'} if data['last_results'] else {'tool':'CATALOG','args':{},'reason':'문서 목록 확인'}
   return {'issues':[],'actions':[a]},{}
  def record_local(self,v):return {'kind':'local-contract','data':v}
 p=M['pipeline'].Pipeline(ROOT,store,P());p.term_agent=M['structured_navigation'].StructuredAgent(p,g,None,matcher)
 result=p.run('보유 문서를 전부 알려줘',list(matcher.documents));assert '보유 문서 3개' in result['answer']['text'];assert not result['answer']['claims'] and not result['answer']['unresolved'];store.db.close()
def test_bounded_history_not_erased(session):
 session.history=[{'tool':'GREP','args':{'query':str(i)},'reason':'조회','status':'OK','result':{}} for i in range(40)]
 c=session.context();assert c['history']['total']==40 and len(session.execute('HISTORY',{'offset':32})['items'])==8
 assert 'history_summary' not in c and len(session.history)==40
def test_explicit_empty_scope():
 store,m,g=fixtures.build(A/'dataset/synthetic-sources.json')
 with pytest.raises(ValueError):M['structured_navigation'].StructuredSession(m,m.tools,g,'질문',[])
 store.db.close()

def options(s):return {x['properties']['tool']['enum'][0]:x['properties']['args'] for x in s.response_schema()['properties']['actions']['items']['anyOf']}
def test_schema_prevents_unread_judgment_and_guessed_source(session):
    opts=options(session);assert 'JUDGE' not in opts and 'READ' not in opts
    sid=discover(session);opts=options(session);allowed=opts['READ']['properties']['source_id']['enum'];assert any(x.startswith('A') for x in allowed) and not any(x.startswith('D') for x in allowed)
    assert 'unit_id' not in opts['READ']['properties']
def test_judge_schema_requires_exact_fields_and_single_action(session):
    from jsonschema import Draft202012Validator,ValidationError
    sid=discover(session);s=session.read(sid);args=options(session)['JUDGE'];assert set(args['required'])=={'segment_id','status','issue_id','quote','claim'}
    with pytest.raises(ValidationError):Draft202012Validator(args).validate({'segment_id':'E1','status':'adopted','unresolved':['Q1']})
    assert session.response_schema()['properties']['actions']['maxItems']==1
    assert options(session)['STOP']['properties']['status']['enum']==['incomplete']
def test_read_handle_and_structure_ancestry(session):
    c=session.source_card('article:mock-staff');assert c['read_action']['args']=={'source_id':'article:mock-staff'}
    c=session.structure_card('structure:mock-staff:1');assert c['ancestry'][0]['surface']=='제1조'
def test_catalogue_multi_page_completion(session):
    for i in range(9):session.scope.add('extra'+str(i));session.m.documents['extra'+str(i)]='모의 추가 문서'+str(i)
    p=session.catalogue();assert p['total']==12 and p['next_offset']==8
    session.catalogue_delivered.add(0)
    with pytest.raises(ValueError,match='unseen pages'):session.execute('STOP',{'status':'catalogue','unresolved':[]})
    session.catalogue(8);session.catalogue_delivered.add(8);assert session.execute('STOP',{'status':'catalogue','unresolved':[]})['status']=='catalogue'
