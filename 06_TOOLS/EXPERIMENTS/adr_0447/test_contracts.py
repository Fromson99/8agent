import sys,json
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from run_probe import load,A
import fixtures
@pytest.fixture
def factory():
 mods,_=load(False);resources=[]
 def make(q='규정을 찾아줘',scope=None):
  store,m,g=fixtures.build(A/'dataset/synthetic-sources.json');resources.append(store);m=mods['bound'].bind_structure(m,store)
  s=mods['bound'].BoundSession(m,m.tools,g,q,scope or sorted(m.documents),{'max_calls':16,'active_chars':18000,'context_chars':60000});resources.append(s);return s
 yield make
 for r in resources:
  if getattr(r,'fts',None):r.fts.close()
  if hasattr(r,'db'):r.db.close()
def ids(r):return {i['id'] for i in r['items']}
def offer(s,sid):
 h=s.source_card(sid)['read_handle'];s.response_schema();return h
def test_actual_template_fields(factory):
 s=factory();r=s.find_article('제 6조의 2 제2항',branch='body');assert ids(r)=={'article:ko-article'}
 item=r['items'][0];raw=s.m.units[(item['document_id'],item['structure_match']['unit_id'])]['raw_structure']
 assert item['structure_match']['coordinate']==raw['legal_coordinate'];assert raw['family']=='circled';assert raw['ordinal']==[2]
 assert raw['coordinate_key']=='body:제6조의2제2항'
def test_heading_is_not_coordinate_authority(factory):
 s=factory();s.t.sources['article:ko-article']['heading']='제999조 (가짜 표제)'
 assert ids(s.find_article('제6조의2',branch='body'))=={'article:ko-article'}
 assert not ids(s.find_article('제999조'))
def test_omitted_prefix_shared_grammar(factory):
 s=factory();assert ids(s.find_article('6조의 2 제2항',branch='body'))=={'article:ko-article'}
 assert not ids(s.find_article('제6조',branch='body'));assert not ids(s.find_article('제6-2조'));assert not ids(s.find_article('제62조'))
def test_collision_keeps_stored_scope(factory):
 s=factory();assert ids(s.find_article('제6조의2',branch='appendix'))=={'article:ko-collision'}
 assert s.find_article('제6조의2')['status']=='NEEDS_SELECTION'
def test_missing_scope_unresolved(factory):
 s=factory()
 for (d,u),n in s.m.units.items():
  if d=='mock-legal-disclosure':n.pop('coordinate_scope',None)
 r=s.find_article('제6조의2');assert r['status']=='UNRESOLVED' and not r['items'] and r['unresolved']
def test_raw_structure_or_source_not_readable(factory):
 s=factory();offer(s,'article:ko-article')
 for bad in ['article:ko-article','D1','S1','A1','structure:mock-legal-disclosure:1','RH999']:
  with pytest.raises(ValueError,match='READ_HANDLE_REQUIRED'):s.execute('READ',{'source_id':bad})
def test_handle_roundtrip_and_quote(factory):
 s=factory();h=offer(s,'article:ko-article');out=s.execute('READ',{'source_id':h});assert out['source_id']=='article:ko-article';s.delivered.add(out['id']);s.issues={'I':'내용'}
 result=s.execute('JUDGE',{'segment_id':out['id'],'status':'adopted','issue_id':'I','quote_ref':out['quote_refs'][0]['id'],'claim':'모의 기준'})
 assert result['quote'] in s.t.sources['article:ko-article']['text']
def test_handle_not_offered_rejected(factory):
 s=factory();h=s.source_card('article:ko-article')['read_handle']
 with pytest.raises(ValueError,match='READ_HANDLE_REQUIRED'):s.execute('READ',{'source_id':h})
def test_stale_handle_rejected(factory):
 s=factory();h=offer(s,'article:ko-article');s.t.sources['article:ko-article']['text_sha256']='changed'
 with pytest.raises(ValueError,match='stale'):s.execute('READ',{'source_id':h})
def test_scope_enforced(factory):
 s=factory(scope=['mock-staff']);assert not ids(s.legal_search('신고','tokens'))
 with pytest.raises(ValueError):s.find_article('제6조의2',document_id='mock-legal-disclosure')
def test_read_schema_handles(factory):
 s=factory();h=offer(s,'article:ko-article');opts=s.response_schema()['properties']['actions']['items']['anyOf'];item=next(x for x in opts if x['properties']['tool']['enum']==['READ'])
 assert item['properties']['args']['properties']['source_id']['enum']==[h]
def test_empty_scoped_list_relaxes_only_optional_scope(factory):
 s=factory('성과급');s.execute('OPEN_TERM',{'term_id':'performance'});r=s.execute('LIST',{'term_ids':['performance'],'match':'any','document_id':'mock-customers'})
 assert r['total']==0;retry=next(a for a in r['recovery_actions'] if a['tool']=='LIST');assert 'document_id' not in retry['args'];assert ids(s.execute(retry['tool'],retry['args']))=={'article:mock-staff'}
def test_open_term_proposes_linked_list(factory):
 s=factory('성과급');r=s.execute('OPEN_TERM',{'term_id':'performance'});s.last=[{'tool':'OPEN_TERM','args':{'term_id':'performance'},'result':r,'status':'OK'}];s.context()
 opts=s.response_schema()['properties']['actions']['items']['anyOf'];assert {x['properties']['tool']['enum'][0] for x in opts}=={'LIST','STOP'}
def test_list_proposes_exact_read(factory):
 s=factory('성과급');s.execute('OPEN_TERM',{'term_id':'performance'});r=s.execute('LIST',{'term_ids':['performance'],'match':'any'});s.last=[{'tool':'LIST','args':{'term_ids':['performance']},'result':r,'status':'OK'}];s.context()
 opts=s.response_schema()['properties']['actions']['items']['anyOf'];assert {x['properties']['tool']['enum'][0] for x in opts}=={'READ','STOP'}
 assert next(x for x in opts if x['properties']['tool']['enum']==['READ'])['properties']['args']['properties']['source_id']['enum']==[r['items'][0]['read_handle']]
def test_korean_search_preserved(factory):
 s=factory()
 for query,mode,sid in [('주요사항보고서','phrase','article:ko-spacing'),('수탁자의 기록을','tokens','article:ko-particle'),('特殊關係人','tokens','article:ko-hanja'),('승인없이 거래하여서는 아니된다','phrase','article:ko-negation')]:
  r=s.legal_search(query,mode);assert ids(r)=={sid}
  for item in r['items']:
   for hit in item['match_spans']:assert s.t.sources[sid]['text'][hit['start']:hit['end']]==hit['text']
def test_modes_preserved(factory):
 s=factory('전문검색해서 원격 출장 알려줘')
 with pytest.raises(ValueError,match='REQUEST_MODE'):s.execute('GREP',{'query':'원격'})
 s.execute('SEARCH',{'query':'원격 출장','mode':'fulltext'});assert not s.pending()
def test_storage_parent_contract():
 mods,_=load(False);store,m,g=fixtures.build(A/'dataset/synthetic-sources.json')
 store.db.execute("UPDATE source_unit SET parent_id='999' WHERE document_id='mock-staff'")
 with pytest.raises(ValueError,match='parent missing'):mods['bound'].bind_structure(m,store)
 store.db.close()
