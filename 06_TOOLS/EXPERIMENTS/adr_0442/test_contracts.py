from pathlib import Path
import hashlib,json,sys
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from run_probe import load,read,A,Provider,downstream
@pytest.fixture
def env():
 mods,root=load();corpus=read(A/'dataset/corpus.json');m,t,g=mods['fixture'].build(corpus,mods['navigation_match']);cls=mods['candidate'].session_class(mods['navigation_loop']);s=cls(m,t,g,'공동운용 가상투자규정 제2조',['invest','deposit']);s.issues={'Q1':'검토'}
 yield s,mods,root,corpus
 t.db.close()

def test_empty_scope(env):
 s,mods,root,c=env;cls=mods['candidate'].session_class(mods['navigation_loop']);empty=cls(s.m,s.t,s.g,'질문',[])
 assert empty.catalog()['total']==0 and empty.search('비공개')['total']==0 and not empty.metadata
 empty.searchdb.close()
def test_scope_counts_and_hidden_body(env):
 s,*_=env;assert s.catalog()['total']==2
 assert s.search('비공개')['total']==0
 with pytest.raises(ValueError):s.search('예탁금',document_id='private')
 with pytest.raises(ValueError):s.read('secret')
def test_unknown_scope(env):
 s,*_=env
 with pytest.raises(ValueError):s.t.validate_scope(['unknown'])
def test_fulltext_and_literal(env):
 s,*_=env;assert s.search('반환 지연')['items'][0]['id']=='s4'
 assert s.search('복구 승인','fulltext')['items'][0]['id']=='s6'
 assert s.search('투자금 반환','fulltext')['total']==1
 assert not s.search('복구 승인','semantic')['not_found']
def test_fts_escaped_and_empty_query(env):
 s,*_=env;assert s.search('" OR *','fulltext')['total']==0
 with pytest.raises(ValueError):s.search('')
def test_catalog_delivery_gate(env):
 s,*_=env;s.catalog()
 with pytest.raises(ValueError):s.execute('FINISH_CATALOG',{})
def test_catalog_all_pages_and_v2_render(env):
 s,mods,root,c=env;scope=[d for d in c['documents'] if d!='private'];cls=mods['candidate'].session_class(mods['navigation_loop']);x=cls(s.m,s.t,s.g,'모든 문서',scope)
 class P:
  def __init__(self):self.n=0
  def call(self,*args):
   self.n+=1;tool='CATALOG' if self.n<3 else 'FINISH_CATALOG';a={'offset':(self.n-1)*8} if self.n<3 else {}
   return {'issues':[],'actions':[{'tool':tool,'args':json.dumps(a),'reason':'전체 페이지 조회'}]},{}
 p=P();out=x.run(p);assert len(out['catalogue'])==11 and out['status']=='FINISH'
 provider=Provider(None);answer=downstream(mods,root,x,out,{'id':'test','question':'모든 문서','scope_document_ids':scope},provider)['answer'];assert answer['kind']=='CATALOGUE' and '11개' in answer['text']
def test_structure_whole_and_parent_trailing(env):
 s,_,_,c=env;r=s.read('structure:invest:2');assert r['text']==c['sources']['s2']['text'];assert r['complete_extent']
 assert r['block_ids']==['s2b0','s2b1','s2b2'] and r['text'].endswith('공휴일을 제외한다.')
 assert hashlib.sha256(r['text'].encode()).hexdigest()==r['extent_sha256']
def test_structural_own_coverage_blocks_finish(env):
 s,*_=env;r=s.read('structure:invest:2',extent='OWN');assert '다만' not in r['text'] and '공휴일' in r['text'];s.delivered.add(r['id']);s.judge(r['id'],'adopted','Q1','공휴일을 제외한다.','공휴일 제외')
 with pytest.raises(ValueError):s.execute('STOP',{'status':'sufficient','unresolved':[]})
def test_unread_and_fabricated_quote(env):
 s,*_=env;r=s.read('structure:invest:2')
 with pytest.raises(ValueError):s.judge(r['id'],'adopted','Q1','공휴일을 제외한다.','주장')
 s.delivered.add(r['id'])
 with pytest.raises(ValueError):s.judge(r['id'],'adopted','Q1','무조건 100퍼센트 보장','주장')
def test_refocus_invalidates_claims(env):
 s,*_=env;r=s.read('structure:invest:2');s.delivered.add(r['id']);s.judge(r['id'],'adopted','Q1','공휴일을 제외한다.','공휴일 제외');s.execute('REFOCUS',{'reason':'잘못된 범위'})
 assert not s.judgments and s.invalidated
 with pytest.raises(ValueError):s.judge(r['id'],'adopted','Q1','공휴일을 제외한다.','주장')
def test_relationship_and_reference_preserved(env):
 s,*_=env;r=s.graph('fund',1,0);assert r['items'][0]['edge']['code']=='RELATED_TO' and r['items'][0]['edge']['source']=='fund'
 s.listing(['manager']);segment=s.read('s3');s.delivered.add(segment['id']);assert s.references('s3',0)['items'][0]['resolution']=='RESOLVED'
def test_invalid_tool_error_visible_next_turn(env):
 s,*_=env
 class P:
  def __init__(self):self.n=0
  def call(self,role,system,data,schema):
   self.n+=1
   if self.n==1:a={'tool':'READ','args':'{"source_id":"bad-id"}','reason':'오선택'}
   else:
    assert data['last_results'][0]['status']=='REJECTED' and data['last_results'][0]['error'];a={'tool':'STOP','args':'{"status":"incomplete","unresolved":["원문 미확인"]}','reason':'한계 명시'}
   return {'issues':[],'actions':[a]},{}
 assert s.run(P())['calls']==2

def test_large_atomic_block_blocked_no_truncate(env):
 s,*_=env;s.t.sources['s2']['blocks'][0]['text']='가'*19000
 r=s.read('structure:invest:2');assert r['status']=='BLOCKED' and not s.read_segments

def test_full_payload_budget_stops_before_model(env):
 s,*_=env;s.limits['context_chars']=10
 class P:
  def call(self,*a):raise AssertionError('must not invoke')
 r=s.run(P());assert r['status']=='STOP' and r['calls']==0

def test_actual_owner_adapter_retains_parent_blocks(env):
 import sqlite3
 from types import SimpleNamespace
 s,mods,*_=env;db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.execute('create table source_block(document_id,unit_id,block_id)');db.executemany('insert into source_block values (?,?,?)',[('invest','2','1'),('invest','2.2','2'),('invest','2','3')])
 bound=mods['candidate'].bind_source_structure(s.m,SimpleNamespace(db=db,manifest={'generation_id':'v1'}));assert bound.units[('invest','2')]['blocks']==['1','3'];assert bound.units[('invest','2.2')]['blocks']==['2'];db.close()

def test_paged_history_preserves_full_record(env):
 s,*_=env
 for i in range(20):s.history.append({'tool':'GREP','args':{},'reason':'조회','status':'OK','result':{'n':i}})
 assert len(s.context()['history_summary'])==8 and s.execute('HISTORY',{'offset':16})['total']==20

def test_legal_findings_original_downstream(env):
 s,mods,root,c=env;s.source_card('s1');seg=s.read('s1');s.delivered.add(seg['id']);s.judge(seg['id'],'adopted','Q1',seg['text'],'공동운용은 여러 사람의 투자금을 모아 운용한다.')
 state={'adopted':list(s.judgments.values()),'read_source_ids':['s1'],'status':'FINISH','stop':{'status':'sufficient','unresolved':[]},'provider_receipts':[]}
 out=downstream(mods,root,s,state,{'id':'wiring','question':'정의','scope_document_ids':['invest']},Provider(None));assert out['answer']['claims'][0]['source_ids']==['s1'] and out['answer']['schema_version']=='term-runtime-v1'
