import copy,json
import pytest
from lawrag.pipeline.glossary_alignment import Matcher
from lawrag.core.structure import recipe_visual_loop as loop
from lawrag.core import parse_adapter,ingest

@pytest.mark.parametrize('text,want',[
 ('거래처ㆍ대리점 방문',['거래처','대리점']),('ㆍ거래처·대리점',['거래처','대리점']),
 ('사용자로부터 사용자로부터는 사용자로부터도',['사용자']*3),
 ('투자신탁은 허용한다. 투자는 가능하다.',['투자신탁','투자']),
 ('투자신탁상품과 투자금은 제외한다.',[]),('사용자이름과 거래처별조회',[]),
])
def test_lexical_boundaries_keep_source_offsets(text,want):
 hits=list(Matcher([(x,x) for x in ['거래처','대리점','사용자','투자','투자신탁']]).find(text))
 assert [h[0] for h in hits]==want
 assert all(text[lo:hi]==term for term,lo,hi,_ in hits)

@pytest.mark.parametrize('kind',['duplicate','depth','missing','schema','json'])
def test_initial_invalid_recipe_reaches_bounded_repair(kind):
 import jsonschema
 catalog={'a':{},'b':{}};seen=[];original={'source_blocks':[{'idx':0,'text':'untouched'}],'catalog':catalog}
 def call(phase,system,data,schema,vision):
  seen.append(copy.deepcopy(data))
  if len(seen)>1:return {'tag':'valid','version':1,'levels':[['a'],['b']]}
  if kind=='schema':raise jsonschema.ValidationError('maxItems')
  if kind=='json':raise json.JSONDecodeError('invalid json','x',0)
  levels={'duplicate':[['a'],['a'],['b']],'depth':[['a']]*8+[['b']],'missing':[['a']]}.get(kind)
  return {'tag':'invalid','version':1,'levels':levels}
 result=loop.request_recipe('assemble',original,catalog,call)
 assert result['tag']=='valid' and len(seen)==2
 assert seen[1]['validation_feedback'] and seen[1]['source_blocks']==original['source_blocks']
 assert 'validation_feedback' not in original

def test_repair_budget_and_transport_failure_are_separate():
 calls=[]
 def invalid(*args):calls.append(1);return {'tag':'bad','version':1,'levels':[['a'],['a']]}
 with pytest.raises(ValueError,match='exhausted'):loop.request_recipe('x',{}, {'a':{}},invalid)
 assert len(calls)==3
 def transport(*args):raise RuntimeError('unavailable')
 with pytest.raises(RuntimeError,match='unavailable'):loop.request_recipe('x',{}, {'a':{}},transport)

def test_cached_pdf_invalidates_old_ocr_and_source(tmp_path,monkeypatch):
 p=tmp_path/'a.pdf';p.write_bytes(b'placeholder');cache=tmp_path/'parse.json';calls=[];identity={'ocr':'korean','source':'new'}
 old=parse_adapter.ParseResult(str(p),'id','fake',False,stats={'parser_identity':{'ocr':'chinese'}})
 cache.write_text(json.dumps(parse_adapter.result_to_dump(old)))
 monkeypatch.setattr(parse_adapter,'pdf_parser_identity',lambda p:copy.deepcopy(identity))
 def parse(p):calls.append(1);return parse_adapter.ParseResult(str(p),'id','fake',False,stats={'parser_identity':copy.deepcopy(identity)})
 monkeypatch.setattr(parse_adapter,'parse',parse)
 from lawrag.core import typography
 monkeypatch.setattr(typography,'ensure_text_x',lambda *a:None)
 ingest.parse_cached(p,cache);ingest.parse_cached(p,cache);assert len(calls)==1
 identity['source']='changed';ingest.parse_cached(p,cache);assert len(calls)==2

def test_scanned_pdf_requires_verified_local_korean_assets(tmp_path,monkeypatch):
 p=tmp_path/'scan.pdf';p.write_bytes(b'fake');monkeypatch.setattr(parse_adapter,'is_born_digital',lambda p:(False,{}))
 monkeypatch.setattr(parse_adapter,'docling_version',lambda:'test');monkeypatch.setenv('STRUCTURE_OCR_MODEL_DIR',str(tmp_path/'absent'))
 with pytest.raises(ValueError,match='assets missing'):parse_adapter.pdf_parser_identity(p)


def test_source_build_failure_is_feedback_not_source_rewrite():
    seen=[]
    def call(phase,system,data,schema,vision):
        seen.append(copy.deepcopy(data));return {'tag':'valid','version':1,'levels':[['a'],['b']] if len(seen)==1 else [['b'],['a']]}
    def check(recipe):
        if recipe['levels'][0]==['a']:raise ValueError('Numbered source anchor inventory changed')
    result=loop.request_recipe('x',{'source_blocks':[{'text':'original'}]},{'a':{},'b':{}},call,check=check)
    assert result['levels']==[['b'],['a']]
    assert 'anchor inventory' in seen[1]['validation_feedback']['error']
    assert seen[1]['source_blocks']==[{'text':'original'}]
