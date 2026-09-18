import sys,json
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from run_probe import load,A
import fixtures
@pytest.fixture
def factory():
 mods,_=load(False);resources=[]
 def make(q='규정을 찾아줘',legal=True,scope=None):
  store,m,g=fixtures.build(A/'dataset/synthetic-sources.json');resources.append(store)
  cls=mods['legal'].LegalSession if legal else mods['controlled'].RoutedSession
  s=cls(m,m.tools,g,q,scope or sorted(m.documents),{'max_calls':16,'active_chars':18000,'context_chars':60000});resources.append(s)
  return s
 yield make
 for r in resources:
  if getattr(r,'fts',None):r.fts.close()
  if hasattr(r,'db'):r.db.close()
def ids(result):return {x['id'] for x in result['items']}
def test_original_spans_spacing(factory):
 s=factory();r=s.legal_search('주요사항보고서','phrase');assert ids(r)=={'article:ko-spacing'}
 for item in r['items']:
  for hit in item['match_spans']:assert s.t.sources[item['id']]['text'][hit['start']:hit['end']]==hit['text']
def test_fulltext_prefix_particles(factory):
 s=factory();assert ids(s.search('수탁자 기록 보존',mode='fulltext'))=={'article:ko-particle'}
def test_query_particle_variant(factory):
 s=factory();assert ids(s.legal_search('수탁자의 기록을','tokens'))=={'article:ko-particle'}
def test_hanja_literal_and_pair(factory):
 s=factory();r=s.legal_search('特殊關係人','tokens');assert ids(r)=={'article:ko-hanja'}
 assert all(x['text'] for x in r['items'][0]['match_spans'])
def test_no_negation_dropped(factory):
 s=factory();assert ids(s.legal_search('승인없이 거래하여서는 아니된다','phrase'))=={'article:ko-negation'}
 assert not ids(s.legal_search('승인없이 거래하여도 된다','phrase'))
def test_subarticle_kept(factory):
 s=factory();assert ids(s.find_article('6조의 2 제2항',branch='body'))=={'article:ko-article'}
 assert not ids(s.find_article('제6조',branch='body'))
def test_appendix_distinct(factory):
 s=factory();assert ids(s.find_article('제6조의2',branch='appendix'))=={'article:ko-collision'}
 assert s.find_article('제6조의2',branch='any')['status']=='NEEDS_SELECTION'
def test_outside_scope(factory):
 s=factory(scope=['mock-staff']);assert not ids(s.legal_search('신고','tokens'))
 with pytest.raises(ValueError):s.find_article('제6조의2',document_id='mock-legal-disclosure')
def test_strict_grep_unchanged(factory):
 s=factory();assert not ids(s.search('성과급 휴직',mode='literal'))
 assert ids(s.search('성과급 휴직',mode='fulltext'))=={'article:mock-staff'}
def test_requested_mode_gate(factory):
 s=factory('원격 출장을 전문검색해서 알려줘',legal=False)
 with pytest.raises(ValueError,match='REQUEST_MODE'):s.execute('GREP',{'query':'원격'})
 s.execute('SEARCH',{'query':'원격 출장','mode':'fulltext'});assert s.search_mode_receipts
 assert not s.pending()
def test_fulltext_negated_not_enforced(factory):
 s=factory('전문검색은 하지 말고 문구를 찾아줘');assert s.contract['search_mode'] is None
def test_first_document_gate(factory):
 s=factory('먼저 고객 규정을 확인해 봐. 이후 직원 성과급 휴직 예외를 찾아줘',legal=False)
 assert s.prerequisite_pending()=='mock-customers'
 s.context();s.source_card('article:mock-staff')
 with pytest.raises(ValueError,match='PREREQUISITE'):s.execute('READ',{'source_id':'article:mock-staff'})
 out=s.execute('READ',{'source_id':'article:mock-customers'});assert s.prerequisite_pending()
 s.delivered.add(out['id']);assert not s.prerequisite_pending()
 assert s.execute('READ',{'source_id':'article:mock-staff'})['text']
def test_completion_mode_gate(factory):
 s=factory('전문검색해서 원격 출장 알려줘')
 with pytest.raises(ValueError,match='REQUEST_INCOMPLETE'):s.execute('STOP',{'status':'sufficient','unresolved':[]})
def test_checkpoint_schema_enum(factory):
 s=factory();s.execute('CHECKPOINT',{'name':'here'})
 schema=s.response_schema();opts=schema['properties']['actions']['items']['anyOf'];back=next(x for x in opts if x['properties']['tool']['enum']==['BACK'])
 assert back['properties']['args']['properties']['name']['enum']==['','here']
 with pytest.raises(ValueError):s.execute('BACK',{'name':'invented'})
def test_controlled_no_korean_tools(factory):
 s=factory(legal=False);opts=s.response_schema()['properties']['actions']['items']['anyOf'];names={x['properties']['tool']['enum'][0] for x in opts}
 assert not names&{'LEGAL_SEARCH','FIND_ARTICLE'}
 with pytest.raises(ValueError):s.execute('LEGAL_SEARCH',{'query':'규정','mode':'phrase'})
def test_empty_recovery_no_gold(factory):
 s=factory();r=s.execute('GREP',{'query':'성과급 휴직'});assert r['status']=='EMPTY'
 assert any(x['tool']=='SEARCH' for x in r['recovery_actions']);assert any(x['tool']=='LEGAL_SEARCH' for x in r['recovery_actions'])
def test_read_quote_provenance(factory):
 s=factory();s.legal_search('주요사항보고서','phrase');r=s.execute('READ',{'source_id':'article:ko-spacing'});s.delivered.add(r['id']);s.issues={'I':'기한·예외'}
 j=s.execute('JUDGE',{'segment_id':r['id'],'status':'adopted','issue_id':'I','quote_ref':r['quote_refs'][0]['id'],'claim':'3영업일; 전산 장애 시 복구 다음 영업일'})
 assert j['quote']==s.t.sources['article:ko-spacing']['text']
 with pytest.raises(ValueError):s.execute('JUDGE',{'segment_id':r['id'],'status':'adopted','issue_id':'I','quote_ref':'forged','claim':'X'})
def test_numeric_boundaries(factory):
 s=factory();assert not ids(s.legal_search('12년','tokens'));assert not ids(s.find_article('제62조'))
def test_missing_search_not_read(factory):
 s=factory();s.legal_search('주요사항보고서','phrase');assert not s.read_segments and not s.judgments
