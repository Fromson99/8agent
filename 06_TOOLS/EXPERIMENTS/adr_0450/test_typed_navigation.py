from pathlib import Path
from types import SimpleNamespace
import json,sys,os
import pytest
sys.path.insert(0,str(Path(__file__).parent));from runtime import load,R
sys.path.append(str(R/'06_TOOLS/EXPERIMENTS/adr_0449'));import fixtures

@pytest.fixture
def env():
 mod,parent,mods,root=load(bool(os.getenv('ADR450_TEST_FROZEN')));store,m,g=fixtures.build(R/'04_EXPERIMENTS/ADR/ADR-0449-multi-entry-catalogue-navigation/artifacts/dataset')
 projection={**store.manifest,'documents':{d:{'document_id':d,'status':'verified','raw_relative_path':('kofia/규정/ESG/'+m.documents[d]+'.html' if d in ('pay','leave') else 'krx/규정/'+m.documents[d]+'.html')} for d in m.documents}}
 m=parent.bind_structure(m,store,projection);m.navigation_store=store
 class NoModel:
  def call(self,*a):raise AssertionError('metadata request should not invoke LLM')
  def record_local(self,x):return {'kind':'local-contract'}
 p=mods['pipeline'].Pipeline(root,store,NoModel());agent=mod.TypedAgent(p,g,None,m);c=mod.Conversation(p,agent,list(m.documents))
 yield mod,m,store,g,c
 store.db.close()

def test_folder_type_has_grounded_guidance(env):
 mod,m,store,g,c=env;r=mod.TypeRegistry(m,list(m.documents),'kofia에 있는 문서 알려줘');out=r.matches('kofia에 있는 문서 알려줘');card=next(x for x in out['items'] if x['type']=='folder')
 assert card['identity']=='external/kofia' and card['document_count']==2 and card['child_folder_count']==1
 assert '원문 근거가 아닙니다' in card['meaning'] and set(card['available_tools'])=={'OPEN_FOLDER','FOLDER_TREE','DOCUMENT_TITLES'}
 assert card['question_spans'][0]=={'text':'kofia','start':0,'end':5}

def test_kofia_natural_list_zero_models(env):
 mod,m,store,g,c=env;out=c.run('kofia에 있는 문서 알려줘');state=out['retrieval']['term_agent'];assert state['calls']==0
 assert {x['id'] for x in state['catalogue']['documents']}=={'pay','leave'}
 assert state['trace'][0]['tool']=='KEYWORD_TYPES'
 c.pipeline.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result')
 assert not state['read_source_ids']

def test_case_alias_and_lexical_boundaries(env):
 mod,m,store,g,c=env
 for question in ['KOFIA 문서 알려줘','금융투자협회에 있는 문서 알려줘']:
  r=mod.TypeRegistry(m,list(m.documents),question).matches(question);assert any(x['type']=='folder' and x['identity']=='external/kofia' for x in r['items'])
 r=mod.TypeRegistry(m,list(m.documents),'akofiax').matches('akofiax');assert not r['items']

def test_folder_and_term_same_name_remain_distinct(env):
 mod,m,store,g,c=env;m.tools.terms['kofia-term']={'id':'kofia-term','label':'kofia'}
 r=mod.TypeRegistry(m,list(m.documents),'kofia');matches=r.matches('kofia');assert {x['type'] for x in matches['items']}=={'folder','term'}
 term=next(x for x in matches['items'] if x['type']=='term')
 with pytest.raises(ValueError,match='type'):r.open_folder(term['handle'])

def test_tree_preserves_hierarchy(env):
 mod,m,store,g,c=env;r=mod.TypeRegistry(m,list(m.documents),'kofia');h=r.matches('kofia')['items'][0]['handle'];opened=r.open_folder(h);assert [x['identity'] for x in opened['items']]==['external/kofia/규정']
 tree=r.open_folder(h,tree=True);assert any(x['identity']=='external/kofia/규정/ESG' for x in tree['items'])
 assert sum(x['type']=='document' for x in tree['items'])==2
 out=c.run('kofia 폴더를 트리로 보여줘');assert out['retrieval']['term_agent']['navigation_output']['kind']=='FOLDER_TREE'
 assert 'external/kofia/규정/ESG' in out['answer']['text']

def test_title_search_does_not_read_body(env):
 mod,m,store,g,c=env;r=mod.TypeRegistry(m,list(m.documents),'kofia');h=r.matches('kofia')['items'][0]['handle']
 m.tools.sources['article:pay-base']['text']+=' HIDDEN-BODY-KEY'
 assert r.titles(h,'HIDDEN-BODY-KEY')['total']==0
 hit=r.titles(h,'휴직');assert hit['total']==1 and hit['items'][0]['document_id']=='leave'

def test_unknown_handle_and_foreign_scope_rejected(env):
 mod,m,store,g,c=env;r=mod.TypeRegistry(m,['pay'],'kofia')
 with pytest.raises(ValueError):r.open_folder('guessed')
 r.matches('kofia');h=r.folder_handle('external/kofia');assert r.entities[h]['document_ids']==['pay']
 assert r.titles(h)['total']==1

def test_llm_receives_types_and_per_type_schema(env):
 mod,m,store,g,c=env;s=mod.TypedSession(m,m.tools,g,'kofia 살펴봐',list(m.documents));context=s.context();assert any(x['type']=='folder' for x in context['keyword_types']['items'])
 options=s.response_schema()['properties']['actions']['items']['anyOf'];open_=next(x for x in options if x['properties']['tool']['enum']==['OPEN_FOLDER'])
 assert open_['properties']['args']['properties']['handle']['enum']==[context['keyword_types']['items'][0]['handle']]

def test_scripted_tool_loop_consumes_folder_card(env):
 mod,m,store,g,c=env
 class Provider:
  def __init__(self):self.n=0
  def call(self,role,system,data,schema):
   self.n+=1
   if self.n==1:
    card=next(x for x in data['keyword_types']['items'] if x['type']=='folder');action={'tool':'OPEN_FOLDER','args':{'handle':card['handle']},'reason':'폴더 타입을 따라 하위 목록 조회'}
   else:action={'tool':'STOP','args':{'status':'incomplete','unresolved':['단위 검사 종료']},'reason':'scripted contract end'}
   return {'issues':[],'actions':[action]},{'kind':'scripted'}
  def record_local(self,x):return {'kind':'local'}
 c.pipeline.provider=Provider();out=c.run('kofia 살펴봐');state=out['retrieval']['term_agent']
 assert state['trace'][0]['tool']=='OPEN_FOLDER' and state['trace'][0]['status']=='OK'
 assert state['trace'][0]['result']['items'][0]['type']=='folder'
 assert state['failure'] is None

def test_document_selection_narrows_all_followup_tools(env):
 mod,m,store,g,c=env;s=mod.TypedSession(m,m.tools,g,'kofia',list(m.documents));card=s.type_page['items'][0];listing=s.execute('DOCUMENT_TITLES',{'handle':card['handle'],'query':'보수'});doc=listing['items'][0]
 s.execute('SELECT_DOCUMENT',{'handle':doc['handle']});assert s.scope=={'pay'} and all(v['document_id']=='pay' for v in s.metadata.values())
 h=s.registry.folder_handle('external/kofia');s.registry.card(h);assert s.execute('DOCUMENT_TITLES',{'handle':h})['total']==1
 r=s.execute('DOCUMENT_OUTLINE',{'handle':doc['handle']});assert r['document_id']=='pay'

def test_coordinate_type_uses_saved_structure(env):
 mod,m,store,g,c=env;s=mod.TypedSession(m,m.tools,g,'제1조', ['pay']);cards=s.type_page['items'];assert any(x['type']=='coordinate' and x['coordinate_key']=='body:제1조' for x in cards)
 assert not any(x['type']=='coordinate' and x['document_id']!='pay' for x in cards)

def test_duplicate_folder_leaf_names_require_path_selection(env):
 mod,m,store,g,c=env;out=c.run('규정에 있는 문서 알려줘');assert out['retrieval']['term_agent']['navigation_output']['kind']=='FOLDER_SELECTION'
 assert '여러 개' in out['answer']['text']

def test_keyword_paging_preserves_all_matches(env):
 mod,m,store,g,c=env
 for i in range(20):m.tools.terms['amb'+str(i)]={'id':'amb'+str(i),'label':'kofia'}
 r=mod.TypeRegistry(m,list(m.documents),'kofia');a=r.matches('kofia');b=r.matches('kofia',offset=a['next_offset']);assert a['total']==21 and len(a['items'])+len(b['items'])==21

def test_content_request_not_swallowed_by_folder_listing(env):
 mod,m,store,g,c=env
 class Stop:
  def call(self,*args):return {'issues':[],'actions':[{'tool':'STOP','args':{'status':'incomplete','unresolved':['contract only']},'reason':'content query'}]},{'kind':'scripted'}
  def record_local(self,x):return {'kind':'test'}
 c.pipeline.provider=Stop();out=c.run('kofia 문서의 지급요건 내용을 알려줘');state=out['retrieval']['term_agent'];assert state['calls']==1 and not state['catalogue']['complete']

def test_negative_metadata_page_rejected(env):
 mod,m,store,g,c=env;r=mod.TypeRegistry(m,list(m.documents),'kofia')
 with pytest.raises(ValueError):r.matches('kofia',offset=-1)

def test_tree_only_offers_displayed_page_handles(env):
 mod,m,store,g,c=env;r=mod.TypeRegistry(m,list(m.documents),'kofia');h=r.matches('kofia')['items'][0]['handle'];before=set(r.offered);page=r.open_folder(h,tree=True,limit=1)
 assert r.offered-before=={page['items'][0]['handle']}
