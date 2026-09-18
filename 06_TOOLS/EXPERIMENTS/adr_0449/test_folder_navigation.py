import sys,json,os,hashlib
from pathlib import Path
from copy import deepcopy
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from runtime import load,A
import fixtures
from lawrag.core.structure import pipeline,recipe_template,recipe_regions,viewer,recipe_basic
from lawrag.core.structure.model import Block

@pytest.fixture
def nav():
 mod,base,mods,root=load(bool(os.getenv("ADR449_TEST_FROZEN")));store,m,g=fixtures.build(A/'dataset')
 # Ordinary synthetic structure contract, not an answer evaluation dataset.
 texts=['제1조(목적) 모의 ESG채권의 기준을 정한다.','① 첫 항은 등록한다.','② 둘째 항은 확인한다.','③ 셋째 항은 검토보고서를 제출한다.']
 template=recipe_basic.default_template();template=recipe_template.compile_recipe(template['heading_rules'],{k:{} for k in template['heading_rules']})
 recipe={'tag':recipe_regions.VERSION,'version':1,'source_block_count':len(texts),'regions':[{'start_block':0,'end_block':len(texts),'template_id':'base','label':'unit-test','reason':'synthetic parser contract'}],'templates':{'base':template}}
 tree=recipe_regions.build(pipeline,[Block(i,t) for i,t in enumerate(texts)],recipe);nodes=[];viewer._flat_tree(tree.tree,nodes);viewer.annotate_coordinate_scopes(nodes,document_kind='law')
 store.db.execute('DELETE FROM source_unit WHERE document_id="pay"')
 for n in nodes:store.db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',('pay',str(n['id']),n['parent'],json.dumps(n,ensure_ascii=False)))
 source=m.sources['article:pay-base'];text='\n'.join(texts);source.update(text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest(),blocks=[{'block_id':str(i),'text':t} for i,t in enumerate(texts)],heading='제1조(목적)',unit_id='0',document_name='모의 ESG채권 인증 가이드라인')
 # Replace the closure used by the synthetic fixture with current stored ancestry.
 def membership(d,u):
  while u is not None:
   found=[s['id'] for s in m.tools.sources.values() if s['document_id']==d and str(s['unit_id'])==u]
   if found:return found
   row=store.db.execute('SELECT parent_id FROM source_unit WHERE document_id=? AND unit_id=?',(d,u)).fetchone();u=str(row[0]) if row and row[0] is not None else None
  return []
 m._unit_sources=membership;m.sources.pop('article:pay-date');store.db.execute('DELETE FROM occurrence WHERE source_id="article:pay-date"');m.documents['pay']=source['document_name'];store.db.execute('UPDATE document SET name=? WHERE document_id="pay"',(source['document_name'],))
 # ESG appears ONLY in the unrelated document body: title-only search must exclude it.
 m.sources['article:vendor-pay']['text']+=' ESG채권'
 origins={d:{'status':'verified','document_id':d,'raw_relative_path':('external/kofia/채권/'+m.documents[d]+'.html' if d in ('pay','vendor') else 'internal/인사/휴직/'+m.documents[d]+'.pdf')} for d in m.documents if d!='unknown'}
 proj={**store.manifest,'documents':origins};m=mod.bind_structure(m,store,proj)
 class Provider:
  def call(self,*a):raise AssertionError('metadata or exact coordinate lookup must not call model')
  def record_local(self,value):return {'kind':'local-test','value':value}
 p=mods['pipeline'].Pipeline(root,store,Provider());agent=mod.MultiAgent(p,g,None,m);conv=mod.Conversation(p,agent,list(m.documents))
 yield mod,store,m,conv,proj
 store.db.close()

def test_folder_classification_overrides_old_category(nav):
 mod,store,m,c,_=nav
 assert m.document_catalogue['pay']['category']=='external' # previous stored category internal
 assert m.document_catalogue['leave']['tags']==['내규']
 assert m.document_catalogue['leave']['navigation_folder']=='internal/인사/휴직'
 assert mod.folders.classify_path('kofia/채권/a.html')['navigation_folder']=='external/kofia/채권'
 assert mod.folders.classify_path('internal/팀/하위/a.pdf')['folder']=='internal/팀/하위'
 assert mod.folders.classify_path('kofia/internal/a.html')['category']=='external'

def test_origin_and_context_generation_checks(nav):
 mod,store,m,c,proj=nav
 bad=deepcopy(proj);bad['store_sha256']='wrong'
 with pytest.raises(ValueError,match='stale'):mod.bind_structure(m,store,bad)
 with pytest.raises(ValueError):c.navigator.scope(c.authorized,'guessed-context')
 with pytest.raises(ValueError):mod.folders.classify_path('../internal/a.pdf')

def test_title_only_scope_chain(nav):
 _,store,m,c,_=nav
 a=c.catalogue(category='external');assert a['total']==2
 b=c.catalogue(provider='kofia',folder='external/kofia/채권');assert b['total']==2
 r=c.catalogue(title_query='ESG 채권');assert r['total']==1 and r['documents'][0]['id']=='pay'
 assert r['filters']['search_field']=='document.name' and not r['content_read']
 assert c.navigator.scope(['leave'],r['context'])==set()
 with pytest.raises(ValueError):c.select('leave')
 # No automatic expansion after an empty result.
 empty=c.catalogue(title_query='없는제목');assert empty['total']==0
 assert c.run('1조 3항 알려줘')['status']=='EMPTY_SCOPE'

def test_natural_catalogue_and_followup_exact_paragraph(nav):
 _,store,m,c,_=nav
 out=c.run('외부 문서중에서 ESG채권 관련한 문서들 뭐가 있는지 알려줘')
 cat=out['retrieval']['term_agent']['catalogue'];assert cat['total']==1 and cat['documents'][0]['id']=='pay'
 out=c.run('ESG채권 조문에서 1조 3항 알려줘')
 state=out['retrieval']['term_agent'];assert state['calls']==0
 assert '셋째 항은 검토보고서를 제출한다' in out['answer']['text']
 assert '첫 항은 등록한다' not in out['answer']['text']
 read=state['navigation_output']['data'];assert [b['block_id'] for b in read['blocks']]==['3']
 assert out['answer']['claims'][0]['source_ids']==['article:pay-base']
 assert out['answer']['scope']['document_version_ids']==['pay']

def test_outline_comes_from_stored_nodes(nav):
 _,store,m,c,_=nav;c.catalogue(title_query='ESG채권')
 r=c.run('해당 조문 구조나 목차 알려줘');data=r['retrieval']['term_agent']['navigation_output']['data']
 assert [x['surface'] for x in data['items']]==['제1조','①','②','③']
 assert data['items'][3]['parent_id']=='0'
 assert '저장된 구조로 만든 목차' in r['answer']['text']
 assert '검토보고서' not in r['answer']['text']

def test_missing_coordinate_never_falls_back_to_article(nav):
 _,store,m,c,_=nav;c.catalogue(title_query='ESG채권')
 out=c.run('제1조 제9항 알려줘');assert '찾지 못했습니다' in out['answer']['text']
 assert not out['retrieval']['term_agent']['read_source_ids']

def test_ambiguous_document_requires_selection(nav):
 _,store,m,c,_=nav;c.catalogue(category='external')
 out=c.run('1조 3항 알려줘');assert '먼저 선택' in out['answer']['text']
 assert not out['retrieval']['term_agent']['read_source_ids']
 c.select('pay');out=c.run('목차 알려줘');assert out['answer']['scope']['document_version_ids']==['pay']

def test_outline_and_reads_cannot_escape_scope(nav):
 _,store,m,c,_=nav;c.catalogue(title_query='ESG채권')
 with pytest.raises(ValueError,match='outside'):c.navigator.outline(c.authorized,context=c.context,document_id='leave')
 with pytest.raises(ValueError,match='outside'):c.navigator.read_unit(c.authorized,context=c.context,document_id='leave',unit_id='0')
 r=c.navigator.outline(c.authorized,context=c.context,include_children=True,root_unit_id='3');assert len(r['items'])==1

def test_independent_conversations_no_scope_leak(nav):
 mod,store,m,c,_=nav;c.catalogue(title_query='ESG채권')
 other=mod.folders.FolderNavigator(m,store)
 with pytest.raises(ValueError):other.scope(list(m.documents),c.context)

def test_explicit_title_and_provider_parser(nav):
 mod,*_=nav
 assert mod.folders.request('외부 문서중에서 ESG채권 관련한 문서들 뭐가 있는지 알려줘')['title_query']=='ESG채권'
 assert mod.folders.request('kofia의 ESG채권 관련 문서들 알려줘')['provider']=='kofia'
 assert mod.folders.request('외부 문서 목록 알려줘')['title_query']==''

def test_structural_span_must_be_complete(nav):
 _,store,m,c,_=nav;c.catalogue(title_query='ESG채권')
 m.tools.sources['article:pay-base']['blocks'].pop()
 with pytest.raises(ValueError):c.navigator.read_unit(c.authorized,context=c.context,unit_id='3')


def test_subtree_search_uses_only_requested_field(nav):
 _,store,m,c,_=nav;c.catalogue(title_query='ESG채권')
 store.db.execute('CREATE TABLE source_block(document_id,block_id,unit_id,text)')
 store.db.executemany('INSERT INTO source_block VALUES (?,?,?,?)',[('pay',b['block_id'],b['block_id'],b['text']) for b in m.tools.sources['article:pay-base']['blocks']])
 assert c.search_structure(root_unit_id='0',query='목적')['total']==1
 assert c.search_structure(root_unit_id='3',query='등록',field='body')['total']==0
 assert c.search_structure(root_unit_id='3',query='검토보고서',field='body')['items'][0]['block_id']=='3'
 assert c.search_structure(root_unit_id='0',query='검토보고서',field='structure_title')['total']==0
 with pytest.raises(ValueError):c.search_structure(root_unit_id='missing',query='보고서',field='body')

def test_followup_model_search_remains_inside_selected_document(nav):
 mod,store,m,c,_=nav;c.catalogue(title_query='ESG채권')
 # Scripted controller stop verifies actual pipeline scope wiring; not an LLM evaluation.
 seen=[]
 class StopProvider:
  def call(self,role,system,data,schema):
   seen.append(data)
   return {'issues':[],'actions':[{'tool':'STOP','args':{'status':'incomplete','unresolved':['단위 테스트에서 모델 실행 생략']},'reason':'scope contract'}]},{'kind':'scripted-contract'}
  def record_local(self,x):return {'kind':'local'}
 c.pipeline.provider=StopProvider();result=c.run('등록과 검토 절차를 설명해줘')
 assert result['answer']['scope']['document_version_ids']==['pay'] and len(seen)==1
 assert all(v['document_id']=='pay' for v in mod.MultiSession(m,m.tools,c.agent.glossary,'등록', ['pay']).metadata.values())


def test_adapter_final_result_preserves_existing_contract(nav):
 _,store,m,c,_=nav
 out=c.run('외부 문서중에서 ESG채권 관련한 문서들 뭐가 있는지 알려줘')
 c.pipeline.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result')
 assert out['retrieval']['term_agent']['navigation_context']==c.context
 out=c.run('1조 3항 알려줘');c.pipeline.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result')
