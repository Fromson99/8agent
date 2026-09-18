from pathlib import Path
import os,sys,json
import pytest
sys.path.insert(0,str(Path(__file__).parent));from runtime import load,R
sys.path.append(str(R/'06_TOOLS/EXPERIMENTS/adr_0449'));import fixtures

@pytest.fixture
def env(tmp_path):
 mod,typed,multi,mods,root=load(bool(os.getenv('ADR451_TEST_FROZEN')));store,m,g=fixtures.build(R/'04_EXPERIMENTS/ADR/ADR-0449-multi-entry-catalogue-navigation/artifacts/dataset')
 projection={**store.manifest,'documents':{d:{'document_id':d,'status':'verified','raw_relative_path':('internal/hr/'+m.documents[d]+'.html' if d in ('pay','leave') else 'kofia/규정/'+m.documents[d]+'.html')} for d in m.documents}}
 m=multi.bind_structure(m,store,projection);m.navigation_store=store
 class Provider:
  def __init__(self):self.requests=[];self.decide=lambda data:decision(data)
  def call(self,role,system,data,schema):
   self.requests.append((role,system,data,schema));return self.decide(data),{'kind':'scripted'}
  def record_local(self,v):return {'kind':'local-contract'}
 p=mods['pipeline'].Pipeline(root,store,Provider());agent=mod.MappedAgent(p,g,None,m,ledger=tmp_path/'review.sqlite',actor='test-user');c=mod.Conversation(p,agent,list(m.documents))
 yield mod,m,store,g,c,mods,root
 store.db.close()

def cards(data):return data['scope_menu']['items']+data['keyword_types']['items']+[x for r in data.get('last_results',[]) for x in r.get('result',{}).get('items',[])]
def decision(data,scope='internal',intent='catalogue',expression='내문',mode='selected',title='',bindings=None):
 card=next(x for x in cards(data) if x['identity']==scope) if scope else None
 return {'action':{'tool':'INTERPRET_QUERY','args':{'intent':intent,'scope_mode':mode,'scope_handles':[card['handle']] if card else [],'bindings':bindings if bindings is not None else ([{'expression':expression,'handle':card['handle']}] if expression else []),'title_query':title,'clarification':'뜻을 확인해 주세요.' if intent=='clarify' else ''},'reason':'질문의 표현과 실제 타입 후보로 범위 해석'}}
def state(out):return out['retrieval']['term_agent']

def test_first_call_unknown_alias_real_folder_scope_and_result(env):
 mod,m,store,g,c,mods,root=env;out=c.run('내문 어떤게 있지');s=state(out)
 assert s['failure'] is None and s['calls']==1 and {d['id'] for d in s['catalogue']['documents']}=={'pay','leave'}
 assert s['trace'][0]['tool']=='INTERPRET_QUERY' and s['mapping_proposal_ids']
 assert c.list_mappings()[0]['status']=='PROPOSED'
 c.pipeline.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result')
 assert not s['read_source_ids']

def test_proposal_requires_review_then_reuses_across_sessions(env):
 mod,m,store,g,c,mods,root=env;s=state(c.run('내문 어떤게 있지'));ident=s['mapping_proposal_ids'][0]
 assert not c.mapping_store().active(list(m.documents))
 c.review_mapping(ident,'APPROVED','내부문서의 사용자 약어 확인')
 other=mod.Conversation(c.pipeline,mod.MappedAgent(c.pipeline,g,None,m,ledger=c.agent.ledger,actor='test-user'),list(m.documents));out=other.run('내문 어떤게 있지')
 assert ident in state(out)['approved_mapping_ids'] and not state(out)['mapping_proposal_ids']
 assert any(x['type']=='folder' and x['identity']=='internal' for x in c.pipeline.provider.requests[-1][2]['keyword_types']['items'])
 other.review_mapping(ident,'REVOKED','약어 변경');assert not other.mapping_store().active(list(m.documents))

def test_user_add_is_active_and_target_type_preserved(env):
 mod,m,store,g,c,mods,root=env;ident=c.add_mapping('내문',{'type':'folder','identity':'internal'});assert c.list_mappings()[0]['status']=='APPROVED'
 out=c.run('내문 어떤게 있지');assert ident in state(out)['approved_mapping_ids']
 with pytest.raises(ValueError):c.add_mapping('잘못',{'type':'document','identity':'internal'})

def test_unknown_alias_cannot_expand_to_all_or_current_catalogue(env):
 mod,m,store,g,c,mods,root=env
 for mode in ('all','current'):
  c.pipeline.provider.decide=lambda d:decision(d,scope=None,mode=mode,expression=None)
  s=state(c.run('내문 어떤게 있지'));assert s['navigation_output']['kind']=='NEEDS_SELECTION' and not s['catalogue']['complete'] and not s['catalogue']['documents']
  assert c.context is None

def test_model_error_no_global_fallback(env):
 mod,m,store,g,c,mods,root=env;c.pipeline.provider.decide=lambda d:(_ for _ in ()).throw(RuntimeError('mock backend unavailable'))
 s=state(c.run('내문 어떤게 있지'));assert s['failure']['type']=='RuntimeError' and s['navigation_output']['kind']=='NEEDS_SELECTION'

def test_forged_handle_and_nonquestion_mapping_rejected(env):
 mod,m,store,g,c,mods,root=env
 def bad(d):
  out=decision(d);out['action']['args']['scope_handles']=['KHforged'];return out
 c.pipeline.provider.decide=bad;assert state(c.run('내문 어떤게 있지'))['failure']
 c.pipeline.provider.decide=lambda d:decision(d,expression='질문에없는표현');assert state(c.run('내문 어떤게 있지'))['failure']
 assert not c.list_mappings()

def test_scope_empty_remains_empty(env):
 mod,m,store,g,c,mods,root=env
 for d in m.document_catalogue.values():d['category']='external';d['navigation_folder']='external/kofia'
 s=state(c.run('내문 어떤게 있지'));assert s['catalogue']['total']==0 and s['effective_document_ids']==[]
 assert c.run('어떤 문서든 알려줘')['status']=='EMPTY_SCOPE'

def test_approved_conflict_and_cross_user_isolation(env):
 mod,m,store,g,c,mods,root=env;c.add_mapping('내문',{'type':'folder','identity':'internal'})
 with pytest.raises(ValueError,match='conflict'):c.add_mapping('내문',{'type':'folder','identity':'external'})
 other=mod.MappingStore(c.agent.ledger,m,store.manifest,list(m.documents),'different-user');assert other.list()==[]

def test_generation_and_scope_binding(env):
 mod,m,store,g,c,mods,root=env;c.add_mapping('내문',{'type':'folder','identity':'internal'});s=c.mapping_store()
 stale=mod.MappingStore(s.path,m,{**store.manifest,'generation_id':'new-generation'},list(m.documents),'test-user');assert stale.active(list(m.documents))==[]
 narrower=mod.MappingStore(s.path,m,store.manifest,['pay'],'test-user');assert not narrower.list()  # no fragments from wider scope

def test_legacy_learning_queue_and_publish_compatible(env,tmp_path):
 mod,m,store,g,c,mods,root=env;c.add_mapping('내문',{'type':'folder','identity':'internal'})
 from importlib import import_module
 base=import_module(mod.__package__+'.mapping_base_store');ident=base.propose(c.agent.ledger,'expression',{'generation_id':store.manifest['generation_id'],'source_store_sha256':store.manifest['store_sha256'],'expression':'휴직급여','document_version_ids':list(m.documents),'run_sha256':'a'*64})
 tid=next(iter(m.tools.terms));base.review(c.agent.ledger,ident,'APPROVED','tester','모의 검토',tid)
 assert len(base.candidates(c.agent.ledger))==1 and len(c.list_mappings())==1
 out=base.publish(c.agent.ledger,tmp_path/'bundle.json',store.manifest['generation_id'],'a'*64,store.manifest['store_sha256'],m.tools.terms,m.documents);assert out['expressions']==1 and out['recipes']==0

def test_title_only_filter_after_interpretation(env):
 mod,m,store,g,c,mods,root=env;c.pipeline.provider.decide=lambda d:decision(d,title='휴직')
 out=c.run('내문 중 휴직 문서 어떤게 있지');assert state(out)['catalogue']['total']==1
 assert state(out)['catalogue']['documents'][0]['id']=='leave'

def test_explicit_overall_catalogue(env):
 mod,m,store,g,c,mods,root=env;c.pipeline.provider.decide=lambda d:decision(d,scope=None,mode='all',expression=None)
 assert state(c.run('전체 문서 목록 알려줘'))['catalogue']['total']==len(m.documents)

def test_saved_folder_mapping_cannot_be_ignored(env):
 mod,m,store,g,c,mods,root=env;c.add_mapping('내문',{'type':'folder','identity':'internal'})
 c.pipeline.provider.decide=lambda d:decision(d,scope=None,mode='all',expression=None)
 assert state(c.run('내문 전체 목록 알려줘'))['navigation_output']['kind']=='NEEDS_SELECTION'

def test_content_binding_preserves_multiple_entry_union(env):
 mod,m,store,g,c,mods,root=env
 terms=list(m.tools.terms);assert len(terms)>=2
 c.add_mapping('표현A',{'type':'term','identity':terms[0]});c.add_mapping('표현B',{'type':'term','identity':terms[1]})
 def respond(d):
  if 'scope_menu' in d:return decision(d,scope=None,mode='current',intent='content',expression=None)
  return {'issues':[],'actions':[{'tool':'STOP','args':{'status':'incomplete','unresolved':['모의 계약 검사 종료']},'reason':'원문 판단 성능 검사가 아님'}]}
 c.pipeline.provider.decide=respond;s=state(c.run('표현A와 표현B의 조건은?'))
 assert s['failure'] is None and s['calls']==2
 assert set(terms[:2])<={x['term_id'] for x in s['entry_paths'] if x['kind']=='term'}
 assert s['pending_source_ids'] and not s['adopted']

def test_lookup_metadata_enables_document_abbreviation(env):
 mod,m,store,g,c,mods,root=env
 def respond(d):
  if not d['last_results']:return {'action':{'tool':'LOOKUP_ENTITIES','args':{'type':'document','query':'보수'},'reason':'약어에 대응하는 실제 문서명 조회'}}
  doc=d['last_results'][0]['result']['items'][0];return decision(d,scope=doc['identity'],expression='보규')
 c.pipeline.provider.decide=respond;s=state(c.run('보규 어떤 문서야'))
 assert s['calls']==2 and s['effective_document_ids']==['pay'] and s['catalogue']['total']==1

def test_genos_existing_transport_receives_first_interpretation(env,tmp_path,monkeypatch):
 mod,m,store,g,c,mods,root=env
 from semantic_runtime.provider import Haiku
 from semantic_runtime import genos
 provider=Haiku(tmp_path,tmp_path/'receipts',backend='genos',trust_zone='internal');monkeypatch.setattr(provider,'_resolve_genos',lambda secrets:('mock-target','mock-internal-model'))
 requests=[]
 def request_json(endpoint,path,payload):
  assert endpoint=='mock-target' and path=='/chat/completions';requests.append(payload)
  d=json.loads(payload['messages'][1]['content'])['context'];return {'choices':[{'message':{'content':json.dumps(decision(d),ensure_ascii=False)}}],'usage':{'prompt_tokens':0,'completion_tokens':0}}
 monkeypatch.setattr(genos,'request_json',request_json);c.pipeline.provider=provider;s=state(c.run('내문 어떤게 있지'))
 assert s['failure'] is None and len(requests)==1 and s['calls']==1
 assert requests[0]['model']=='mock-internal-model' and requests[0]['response_format']['json_schema']['schema']['properties']['action']
 assert s['catalogue']['total']==2

def test_saved_mapping_reused_in_narrowed_conversation(env):
 mod,m,store,g,c,mods,root=env;ident=c.add_mapping('내문',{'type':'folder','identity':'internal'})
 c.run('내문 어떤게 있지');out=c.run('내문 어떤게 있지');assert ident in state(out)['approved_mapping_ids']

def test_interpretation_and_content_share_call_budget(env):
 mod,m,store,g,c,mods,root=env;c.agent.limits={'max_calls':1}
 c.pipeline.provider.decide=lambda d:decision(d,scope=None,mode='current',intent='content',expression=None)
 s=state(c.run('휴직 급여의 조건은?'));assert s['calls']==1 and len(c.pipeline.provider.requests)==1 and s['stop']['status']=='incomplete'

def test_operator_cli_same_ledger_add_list_revoke(env,monkeypatch,capsys):
 from contextlib import contextmanager
 from learn import main
 mod,m,store,g,c,mods,root=env
 if not os.getenv('ADR451_TEST_FROZEN'):monkeypatch.setenv('ADR451_TEST_MUTABLE','1')
 @contextmanager
 def context(args):yield c.mapping_store(),mod.EntityRegistry(m,list(m.documents),'',[])
 common=['--generation','explicit-generation','--authorized-documents','authorized.json','--actor','test-user']
 assert main(['--ledger',str(c.agent.ledger),'mapping-add',*common,'--expression','내문','--type','folder','--identity','internal','--reason','사용자 입력'],context)==0
 ident=json.loads(capsys.readouterr().out)['candidate_id']
 main(['mapping-list',*common],context);assert json.loads(capsys.readouterr().out)[0]['status']=='APPROVED'
 main(['mapping-review',*common,'--candidate',ident,'--status','REVOKED','--reason','잘못 입력'],context);assert json.loads(capsys.readouterr().out)['status']=='REVOKED'

def test_factory_entrypoint_connects_pipeline_to_mapping_agent(env):
 from runtime import create_conversation
 mod,m,store,g,c,mods,root=env
 projection={**store.manifest,'documents':{d:{'document_id':d,'status':'verified','raw_relative_path':('internal/hr/'+m.documents[d]+'.html' if d in ('pay','leave') else 'kofia/규정/'+m.documents[d]+'.html')} for d in m.documents}}
 other=create_conversation(c.pipeline,g,None,m,list(m.documents),projection,ledger=c.agent.ledger,actor='test-user',frozen=bool(os.getenv('ADR451_TEST_FROZEN')))
 assert other.pipeline.term_agent is other.agent
 other.add_mapping('내문',{'type':'folder','identity':'internal'});out=other.run('내문 어떤게 있지');assert state(out)['calls']==1 and state(out)['catalogue']['total']==2

def test_natural_mapping_assistance_stays_proposal(env):
 mod,m,store,g,c,mods,root=env;c.pipeline.provider.decide=lambda d:decision(d,intent='mapping')
 s=state(c.run('내문을 내부문서에 연결해서 등록하고 싶어'));assert s['navigation_output']['kind']=='MAPPING_PROPOSALS'
 assert s['mapping_proposal_ids'] and c.list_mappings()[0]['status']=='PROPOSED' and not s['read_source_ids']
