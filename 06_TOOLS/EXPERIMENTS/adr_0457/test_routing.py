from pathlib import Path
import sys,os,pytest,json
sys.path.insert(0,str(Path(__file__).parent))
from runtime import *

@pytest.fixture
def env(tmp_path):
 mod,old,multi,mods,root,binding=load(bool(os.getenv('ADR457_FROZEN')));store,m,g=build(multi)
 class Provider:
  def __init__(self):self.requests=[];self.decide=lambda d:decision(d)
  def call(self,role,system,data,schema):self.requests.append((role,system,data,schema));return self.decide(data),{'kind':'scripted'}
  def record_local(self,v):return {'kind':'local'}
 p=mods['pipeline'].Pipeline(root,store,Provider());c=mod.Conversation(p,mod.MappedAgent(p,g,None,m,ledger=tmp_path/'ledger.sqlite',actor='test'),list(m.documents))
 yield mod,m,store,g,c
 store.db.close()
def cards(d):return d['scope_menu']['items']+d['keyword_types']['items']
def decision(d,identity='internal',intent='catalogue',scope=None,title='',expression=None):
 h=next((x['handle'] for x in cards(d) if x['identity']==identity),None)
 return {'action':{'tool':'INTERPRET_QUERY','args':{'intent':intent,'scope':scope if scope is not None else [h],'bindings':[{'expression':expression,'handle':h}] if expression else [],'title_query':title,'clarification':'표현 의미를 확인해 주세요.' if intent=='clarify' else ''},'reason':'desired output and stored scope'}}
def state(c,q):return c.run(q)['retrieval']['term_agent']
def ids(s):return sorted(d['id'] for d in s['catalogue']['documents'])

def test_all_includes_unclassified_without_folder_enumeration(env):
 mod,m,store,g,c=env;c.pipeline.provider.decide=lambda d:decision(d,scope='all')
 s=state(c,'우리 DB에 있는 전체 문서 목록 알려줘');assert ids(s)==sorted(m.documents) and 'unknown' in ids(s)
 assert s['interpretation']['scope_handles']==[] and not s['failure']

@pytest.mark.parametrize('bad',[{'kind':'all','handles':['E1']},[],['all','E1']])
def test_exclusive_scope_rejects_mixed_or_empty_scope(env,bad):
 *_,c=env;c.pipeline.provider.decide=lambda d:decision(d,scope=bad,expression='내문')
 s=state(c,'내문 목록');assert s['failure'] and not c.list_mappings()

@pytest.mark.parametrize('scope',['all','current'])
def test_unknown_scope_never_widens(env,scope):
 *_,c=env;c.pipeline.provider.decide=lambda d:decision(d,scope=scope)
 s=state(c,'알수없는약어 목록');assert s['failure'] and not ids(s)

@pytest.mark.parametrize('handle',['E999','KHb88e58c751d576f5f49e'])
def test_wire_invented_or_raw_id_rejected(env,handle):
 *_,c=env;c.pipeline.provider.decide=lambda d:decision(d,scope=[handle],expression='내문')
 assert state(c,'내문 목록')['failure'] and not c.list_mappings()

@pytest.mark.parametrize('title,expected',[('ESG채권',['customer']),('우주탐사',[])])
def test_title_only_excludes_body_decoy_and_empty_does_not_fallback(env,title,expected):
 *_,c=env;c.pipeline.provider.decide=lambda d:decision(d,identity='external/kofia',title=title)
 s=state(c,'kofia의 '+title+' 관련 문서 목록');assert ids(s)==expected and not s['read_source_ids'] and s['catalogue']['complete']
 assert not s['failure'] and len(c.pipeline.provider.requests)==1

def test_generic_title(env):
 *_,c=env;c.pipeline.provider.decide=lambda d:decision(d,title='안전')
 assert ids(state(c,'내규 제목에서 안전 문서'))==['safety']

def test_exact_handles_roundtrip_and_prompt_stage(env):
 *_,c=env;c.pipeline.provider.decide=lambda d:decision(d,expression='내문')
 s=state(c,'내문 목록');assert not s['failure'];req=c.pipeline.provider.requests[0]
 assert all(x['handle'].startswith('E') for x in cards(req[2]));assert s['interpretation']['scope_handles'][0].startswith('KH')
 assert 'available_tools' not in json.dumps(req[2]) and 'ESG' not in req[1] and 'kofia' not in req[1]
 assert c.list_mappings()[0]['status']=='PROPOSED'
 ident=s['mapping_proposal_ids'][0];c.review_mapping(ident,'APPROVED','확인')
 assert ident in state(c,'내문 목록')['approved_mapping_ids']

def test_free_text_not_decoded(env):
 import importlib
 mod,*_=env;codec=importlib.import_module(mod.__package__+'.compact_handles')
 v={'expression':'E1','question':'E1','handle':'E1','scope':['E1']};x=codec.transform(v,{'E1':'KHoriginal'})
 assert x['expression']==x['question']=='E1' and x['handle']=='KHoriginal' and x['scope']==['KHoriginal']

def test_bounds_and_offered_ids_preserved_in_wire_schema(env):
 *_,c=env
 def too_many(d):
  out=decision(d);out['action']['args']['bindings']=[{'expression':'내문','handle':out['action']['args']['scope'][0]}]*17;return out
 c.pipeline.provider.decide=too_many;assert state(c,'내문 목록')['failure'] and not c.list_mappings()

def test_content_title_scope_applied_before_session(env,monkeypatch):
 mod,m,store,g,c=env;seen=[]
 class Session:
  def __init__(self,matcher,tools,glossary,q,scope,limits,**kwargs):seen.append(scope);self.t=tools
  def run(self,provider):return {'synthesis':{'findings':[]},'adopted':[],'stop':{'unresolved':[]},'status':'FINISH','read_source_ids':[],'calls':0,'provider_receipts':[],'trace':[],'failure':None}
 monkeypatch.setattr(mod,'WorkSession',Session)
 c.pipeline.provider.decide=lambda d:decision(d,identity='external/kofia',intent='content',title='ESG채권')
 plan={'question':'kofia에서 제목에 ESG채권이 있는 문서의 내용을 알려줘','scope':{'document_version_ids':list(m.documents)},'generation_id':store.manifest['generation_id']}
 c.agent.retrieve(plan);assert seen==[['customer']]

def test_transport_failure_no_identical_retry_or_raw_error_in_answer(env):
 *_,c=env
 def fail(d):raise RuntimeError('HTTP400 raw diagnostic message')
 c.pipeline.provider.decide=fail;out=c.run('내문 목록')
 assert len(c.pipeline.provider.requests)==1 and 'HTTP400' not in out['answer']['text']
 assert 'HTTP400' in out['retrieval']['term_agent']['failure']['message']

def test_repeated_empty_lookup_is_clarification_not_backend_failure(env):
 *_,c=env;c.pipeline.provider.decide=lambda d:{'action':{'tool':'LOOKUP_ENTITIES','args':{'type':'term','query':'뽀문'},'reason':'find entity'}}
 s=state(c,'뽀문 어떤게 있지?');assert not s['failure'] and s['navigation_output']['kind']=='NEEDS_SELECTION'
 assert len(c.pipeline.provider.requests)==2 and s['metadata_lookup_count']==1 and not ids(s)

def test_distinct_empty_lookups_have_bound(env):
 *_,c=env
 def lookup(d):return {'action':{'tool':'LOOKUP_ENTITIES','args':{'type':['folder','document','term'][len(c.pipeline.provider.requests)-1],'query':'없는표현'},'reason':'find entity'}}
 c.pipeline.provider.decide=lookup;s=state(c,'없는표현 문서 목록');assert not s['failure'] and s['metadata_lookup_count']==3 and s['calls']==3

def test_mapping_target_not_subject_to_search_scope_filter(env):
 *_,c=env;c.pipeline.provider.decide=lambda d:decision(d,intent='mapping',scope='current',expression='내문')
 s=state(c,'내문을 내부문서에 연결하는 표현 매핑을 제안해줘');assert not s['failure'] and s['navigation_output']['kind']=='MAPPING_PROPOSALS'
 assert c.list_mappings()[0]['payload']['target']=={'type':'folder','identity':'internal'} and c.list_mappings()[0]['status']=='PROPOSED'

def test_one_semantic_repair_precedes_ledger_mutation(env):
 *_,c=env
 def choose(d):
  if len(c.pipeline.provider.requests)==1:return decision(d,scope='all',expression='내문')
  assert not c.list_mappings() and d['last_results'][0]['status']=='REJECTED'
  return decision(d,expression='내문')
 c.pipeline.provider.decide=choose;s=state(c,'내문 목록');assert s['interpretation_repairs']==1 and not s['failure'] and ids(s)==['approval','leave','pay','privacy','safety','travel']
 assert len(c.list_mappings())==1

def test_semantic_repair_is_bounded(env):
 *_,c=env;c.pipeline.provider.decide=lambda d:decision(d,scope='all',expression='내문')
 s=state(c,'내문 목록');assert s['failure'] and len(c.pipeline.provider.requests)==2 and not c.list_mappings()
