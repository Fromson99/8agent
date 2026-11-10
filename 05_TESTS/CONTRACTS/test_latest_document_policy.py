import copy,json,sqlite3
from pathlib import Path
from contextlib import closing
import pytest
from semantic_runtime.filename_versions import select,load_exceptions,DEFAULT_EXCEPTIONS,latest_marks
from semantic_runtime.search_selection import Selection,selection_path
from semantic_runtime.storage import Store
from lawrag.pipeline.search_selection import plan,activate,rollback
from lawrag.pipeline.document_representations import select_latest_internal
from test_search_selection import metadata_generation

def rows(names,folder='internal/folder'):
 return [dict(document_id=str(i),source_artifact_sha256=str(i)*64,path=folder+'/'+n,filename=n,filename_source='relative_path',has_original=True) for i,n in enumerate(names)]
def config():return load_exceptions(DEFAULT_EXCEPTIONS)[0]
def selected(names):return {r['filename']:r for r in select(rows(names),config())}

@pytest.mark.parametrize('title,date', [('대차업무준칙','2026.05.04'),('인덱스북운용준칙','20260529'),('주식운용준칙','20210723'),('투자리스크관리준칙','20160111')])
def test_user_pins(title,date):
 r=selected([title+'_'+date+'.gul.docx',title+'_20300101.docx'])
 assert r[title+'_'+date+'.gul.docx']['status']=='LATEST'
 assert r[title+'_20300101.docx']['physical_exclusion_candidate']

def test_index_spacing_is_independent():
 r=selected(['인덱스북운용준칙_20260529.docx','인덱스북운용준칙_20240101.docx','인덱스북 운용준칙_20240101.docx','인덱스북 운용 준칙_20260101.docx'])
 assert r['인덱스북운용준칙_20260529.docx']['status']=='LATEST'
 assert r['인덱스북운용준칙_20240101.docx']['status']=='EXCLUDED'
 assert all(v['status']=='KEEP' for n,v in r.items() if ' ' in n)
 assert r['인덱스북운용준칙_20260529.docx']['title_key']!=r['인덱스북 운용준칙_20240101.docx']['title_key']

def test_month_exact_and_keep_both():
 r=selected(['삼성POP골든랩 관리준칙_2023년 5월 개정(최종).docx','삼성POP골든랩 관리준칙_20220101.docx','위탁증거금 징수지침_20240101.docx','위탁증거금 징수지침_20250101.docx'])
 assert r['삼성POP골든랩 관리준칙_2023년 5월 개정(최종).docx']['date']=='2023-05'
 assert all(r[n]['status']=='KEEP' for n in r if n.startswith('위탁'))

def test_attachment_families_and_singleton():
 r=selected(['선물옵션 리스크관리 관리준칙_20260101.docx','선물옵션 리스크관리 관리준칙_[별첨1]_20230101.docx','선물옵션 리스크관리 관리준칙_[별첨1]_20240101.docx','선물옵션 리스크관리 관리준칙_[별첨2]_20220101.docx'])
 assert len([x for x in r.values() if x['status']=='LATEST'])==3
 assert selected(['무날짜준칙.docx'])['무날짜준칙.docx']['status']=='LATEST'

def test_review_retained_mark_does_not_invent_date():
 r=select(rows(['모의준칙.docx','모의준칙_20240101.docx']),config())
 assert all(x['status']=='REVIEW' for x in r)
 assert all(x['is_latest'] and x['date_verified'] is False for x in latest_marks(r))

def test_missing_explicit_target_and_original_are_honest():
 events=[];r=select(rows(['대차업무준칙_20240101.docx']),config(),events)
 assert r[0]['status']=='REVIEW' and r[0]['date']=='2024-01-01'
 assert any(e['status']=='TARGET_NOT_FOUND' for e in events)
 input=rows(['대차업무준칙_20260504.docx']);input[0]['has_original']=False
 assert select(input,config())[0]['status']=='REVIEW'

def test_invalid_and_overlapping_configuration(tmp_path):
 from semantic_runtime.filename_versions import validate_exceptions
 c=config();c['rules'].append(copy.deepcopy(c['rules'][0]))
 with pytest.raises(ValueError):validate_exceptions(c)
 c=config();c['rules'][-1]['title_spacing']='any'
 with pytest.raises(ValueError):validate_exceptions(c)
 p=tmp_path/'bad.json';p.write_text('{"rules":[],"rules":[]}')
 with pytest.raises(ValueError,match='duplicate'):load_exceptions(p)

def test_raw_and_sql_share_decision_and_persist_mark(tmp_path):
 names=['인덱스북운용준칙_20260529.docx','인덱스북운용준칙_20240101.docx','인덱스북 운용준칙_20200101.docx','단독준칙.docx']
 rr=[{'path':'internal/folder/'+n,'document_id':str(i),'source':'internal','sha256':str(i)*64} for i,n in enumerate(names)]
 got,excluded=select_latest_internal(rr)
 assert len(got)==3 and all(r['is_latest'] and r['filename_version']['is_latest'] for r in got)
 assert len(excluded)==1 and not excluded[0]['selection']['is_latest']
 g=metadata_generation(tmp_path,[(str(i),'internal/folder/'+n,{}) for i,n in enumerate(names)])
 original=(g/'store.sqlite').read_bytes();v=plan(g,latest=True);receipt=activate(v)
 assert v['counts']['latest_internal_documents']==3
 with closing(Store(g)) as s:
  s.selection.require_latest()
  actual=[json.loads(r[0])['document_metadata'] for r in s.db.execute('SELECT json FROM document')]
  assert all(r['is_latest'] is True and r['latest_selection']['is_latest'] for r in actual)
  with pytest.raises(KeyError):s.source('1','1')
 assert (g/'store.sqlite').read_bytes()==original
 assert activate(v)['state']=='ALREADY_APPLIED'
 rollback(receipt['receipt'])
 with closing(Store(g)) as s:
  with pytest.raises(ValueError,match='required'):s.selection.require_latest()
  assert s.db.execute('SELECT count(*) FROM document').fetchone()[0]==4

def test_shared_external_alias_and_unknown_are_preserved(tmp_path):
 g=metadata_generation(tmp_path,[('a','internal/folder/모의준칙_20240101.docx',{'aliases':[{'source_category':'external','relative_path':'external/law.docx'}]}),('b','internal/folder/모의준칙_20250101.docx',{}),('c','external/외규.docx',{'source_category':'external'})])
 v=plan(g,latest=True);assert not v['excluded'];activate(v)
 with closing(Store(g)) as s:
  assert s.db.execute('SELECT count(*) FROM document').fetchone()[0]==3
  assert json.loads(s.db.execute('SELECT json FROM document WHERE document_id="c"').fetchone()[0])['document_metadata'].get('is_latest') is None

def test_sidecar_tamper_and_stale_plan_fail(tmp_path):
 g=metadata_generation(tmp_path,[('a','internal/f/모의준칙_20240101.docx',{}),('b','internal/f/모의준칙_20250101.docx',{})]);v=plan(g,latest=True)
 bad=copy.deepcopy(v);bad['latest_documents'][0]['is_latest']=True
 with pytest.raises(ValueError,match='plan changed'):activate(bad)
 activate(v);s=Store(g);p=selection_path(g);p.write_text(p.read_text()+' ')
 with pytest.raises(ValueError,match='restart'):s.check_unchanged()
 s.close()
 bad=copy.deepcopy(v);bad['latest_documents'][0]['locations'][0]['reason']='forged';p.write_text(json.dumps(bad))
 with pytest.raises(ValueError,match='approved selection'):Store(g)

def test_exceptions_edit_requires_new_plan(tmp_path):
 p=tmp_path/'exceptions.json';p.write_bytes(DEFAULT_EXCEPTIONS.read_bytes())
 g=metadata_generation(tmp_path,[('a','internal/f/인덱스북운용준칙_20260529.docx',{}),('b','internal/f/인덱스북운용준칙_20240101.docx',{})]);v=plan(g,latest=True,exceptions=p)
 c=json.loads(p.read_text());next(r for r in c['rules'] if r['id']=='index-book-20260529')['date']='2024-01-01';p.write_text(json.dumps(c))
 with pytest.raises(ValueError,match='plan changed'):activate(v)
 assert plan(g,latest=True,exceptions=p)['excluded'][0]['document_id']=='a'

def test_apply_failure_restores_previous(tmp_path,monkeypatch):
 g=metadata_generation(tmp_path,[('a','internal/f/모의준칙_20240101.docx',{}),('b','internal/f/모의준칙_20250101.docx',{})]);v=plan(g,latest=True)
 import semantic_runtime.storage as storage
 class Broken:
  def __init__(self,*a,**kw):raise RuntimeError('injected after-write failure')
 monkeypatch.setattr(storage,'Store',Broken)
 with pytest.raises(RuntimeError):activate(v)
 assert not selection_path(g).exists()
 assert any(json.loads(p.read_text())['state']=='FAILED_RESTORED' for p in selection_path(g).parent.glob('receipts/*/receipt.json'))

@pytest.mark.parametrize('mode',['legacy','compact-v2'])
def test_latest_policy_real_api(tmp_path,monkeypatch,term_glossary,mode):
 import test_search_selection as original
 import test_legal_agent_v5 as v5
 import test_legal_agent_double_harness as harness
 import semantic_runtime.search_selection as runtime
 C=Path(runtime.__file__).resolve().parents[2]
 monkeypatch.setattr(v5,'ROOT',C);monkeypatch.setattr(harness,'ROOT',C)
 monkeypatch.setattr(original,'plan',lambda g:plan(g,latest=True))
 original.test_existing_database_search_and_actual_api(tmp_path,monkeypatch,term_glossary,mode)


def test_native_marked_generation_needs_no_extra_sidecar(tmp_path):
 g=metadata_generation(tmp_path,[('a','internal/f/모의준칙.docx',{'is_latest':True,'filename_version':{'is_latest':True,'policy':'user-approved-retained-set-latest-v2','exceptions_sha256':'a'*64}})])
 with closing(Store(g)) as s:s.selection.require_latest();assert s.selection.native_latest_verified

def test_merge_titles_joins_typo_family_without_pinning_a_date():
 # 2026-11-10 사용자 지정: 파일명 오타 "상품원회운영지침"을 같은 지침 판본으로 묶되 최신은 파일명 날짜로.
 field=['상품위원회운영지침(20140612).gul.docx','상품위원회운영지침(20250625).docx','상품원회운영지침(20250625)_CCO거부권.docx','상품위원회운영지침(20251205)_조직개편.docx']
 events=[];r={x['filename']:x for x in select(rows(field),config(),events)}
 assert [n for n,x in r.items() if x['status']=='LATEST']==['상품위원회운영지침(20251205)_조직개편.docx']
 assert r['상품원회운영지침(20250625)_CCO거부권.docx']['status']=='OLDER' and r['상품원회운영지침(20250625)_CCO거부권.docx']['physical_exclusion_candidate']
 e=next(e for e in events if e['rule_id']=='product-committee-typo-merge')
 assert e['status']=='APPLIED' and e['merged_titles']==['상품원회운영지침','상품위원회운영지침']
 # a later edition wins with no rule change; a newer typo file wins the same way
 assert selected(field+['상품위원회운영지침(20260301).docx'])['상품위원회운영지침(20260301).docx']['status']=='LATEST'
 assert selected(['상품위원회운영지침(20251205).docx','상품원회운영지침(20260101).docx'])['상품원회운영지침(20260101).docx']['status']=='LATEST'
 # without the exception file the typo stays its own family (previous behaviour)
 plain={x['filename']:x for x in select(rows(field))}
 assert plain['상품원회운영지침(20250625)_CCO거부권.docx']['status']=='LATEST'
 # documents outside the rule are unchanged
 other=selected(['상품관리준칙(20151207).docx','상품관리준칙(20251205)_조직개편.docx'])
 assert other['상품관리준칙(20251205)_조직개편.docx']['status']=='LATEST' and other['상품관리준칙(20151207).docx']['status']=='OLDER'

def test_merge_titles_needs_two_titles():
 from semantic_runtime.filename_versions import validate_exceptions
 c=config();c['rules'].insert(0,{'id':'one','titles':['한제목준칙'],'action':'merge_titles','reason':'x'})
 with pytest.raises(ValueError,match='two titles'):validate_exceptions(c)
 c=config();c['rules'].insert(0,{'id':'dated','titles':['가준칙','나준칙'],'action':'merge_titles','date':'2026-01-01','reason':'x'})
 with pytest.raises(ValueError,match='date only'):validate_exceptions(c)
