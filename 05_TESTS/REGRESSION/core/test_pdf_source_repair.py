import copy
from pathlib import Path
from types import SimpleNamespace
import pytest
from lawrag.core.structure import pipeline, recipe_visual_loop as loop, recipe_pages
from lawrag.core.structure.model import Block

def fixture():
 bs=[Block(i,t) for i,t in enumerate(['제1조(목적) 가','제2조(정의) 나','제3조(범위) 다','제4조(조건) ① 실제 내용이다.','② 다음 내용이다.'])]
 r={'tag':'test','version':1,'levels':[['kr_article'],['circled']]}
 b=pipeline.interpret(copy.deepcopy(bs),doc='test',ladder_hint=r['levels'],partial_order=[('kr_article','circled')],llm=None)
 return bs,r,b

def test_restore_source_backed_numbered_marker():
 bs,r,b=fixture();anchors=loop.inventory(b);missing=next(a for a in anchors if a[0]=='circled' and a[1]==(1,));before=copy.deepcopy(bs)
 new=loop.build(pipeline,bs,r,{'kr_article':{},'circled':{}},[a for a in anchors if a!=missing])
 assert missing in loop.inventory(new) and bs==before

def test_unexplained_removal_is_blocked_but_explicit_reference_preserves_text():
 bs,r,b=fixture();c=next(c for c in b.candidates if c.activated and c.family=='circled' and c.ordinal==(1,));cat={'kr_article':{},'circled':{}}
 new=loop.build(pipeline,bs,{**r,'reference_candidates':[c.id]},cat,loop.inventory(b))
 assert not any(n.candidate_id==c.id for n in new.nodes())
 assert '① 실제 내용' in bs[3].text
 def omit(*a,**k):return copy.deepcopy(new)
 with pytest.raises(ValueError,match='dropped without reference'):
  loop.build(SimpleNamespace(interpret=omit),bs,r,cat,loop.inventory(b))

@pytest.mark.parametrize('draft',[False,True])
def test_invented_marker_rejected_even_in_draft(draft):
 bs,r,b=fixture();c=next(c for c in b.candidates if c.activated);c.surface='FAKE'
 with pytest.raises(ValueError,match='source'):
  loop.build(SimpleNamespace(interpret=lambda *a,**k:b),bs,r,{'kr_article':{},'circled':{}},loop.inventory(b),draft=draft)

def test_unknown_reference_rejected():
 bs,r,b=fixture()
 with pytest.raises(ValueError,match='reference candidate'):
  loop.build(pipeline,bs,{**r,'reference_candidates':['invented']},{'kr_article':{},'circled':{}},loop.inventory(b),draft=True)

def test_draft_invalid_span_becomes_evidence_but_cannot_approve():
 bs,r,b=fixture();n=next(iter(b.nodes()));n.span=(n.block_idx,n.block_idx)
 with pytest.raises(ValueError):recipe_pages.audit(bs,b,[{'page':1,'risks':[]}])
 risks=recipe_pages.audit(bs,b,[{'page':1,'risks':[]}],strict=False)
 assert 'invalid_tree_source_span' in risks[1]
 data=loop.context(bs,{'kr_article':{},'circled':{}},r,b);data['hard_code_issues']=['invalid_tree_source_span'];calls=[]
 def approve(*args):calls.append(args);return {'verdict':'approve','issues':[],'reviewed_state_id':args[2]['reviewed_state_id']}
 with pytest.raises(ValueError,match='cannot be approved'):loop.request_review('test',data,{'kr_article':{},'circled':{}},approve)
 assert len(calls)==2 and 'validation_feedback' in calls[1][2]

def test_reference_only_revision_counts_as_progress_and_requires_visible_source():
 bs,r,b=fixture();data=loop.context(bs,{'kr_article':{},'circled':{}},r,b);c=next(c for c in b.candidates if c.activated and c.family=='circled' and c.offset>0)
 revised={**r,'reference_candidates':[c.id]}
 got=loop.request_review('test',data,{'kr_article':{},'circled':{}},lambda *a:{'reviewed_state_id':a[2]['reviewed_state_id'],'verdict':'revise','issues':[{'blocks':[c.block_idx],'reason':'inline reference'}],'recipe':revised})
 assert got['recipe']==revised and loop.recipe_signature(r)!=loop.recipe_signature(revised)
 with pytest.raises(ValueError,match='unseen'):loop.check_visible_references(revised,{'source_candidates':[]})
 with pytest.raises(ValueError,match='unseen'):loop.check_visible_references(r,{'recipe':revised,'source_candidates':[]})

def test_explicit_template_not_overridden_by_indent():
 bs=[Block(i,t,page=1,bbox=[x,100,500,120],text_x=x) for i,(t,x) in enumerate([('제1장 총칙',200),('제1조(목적) 본문',40),('① 항의 내용',40),('제2장 적용',240),('제2조(범위) 본문',40),('제3장 보칙',240),('제3조(기타) 본문',40)])]
 levels=[['kr_장'],['kr_article'],['circled']]
 r=pipeline.interpret(bs,doc='indented',ladder_hint=levels,strict_ladder=True,llm=None)
 chapters=[n for n in r.nodes() if n.family=='kr_장']
 assert len(chapters)==3 and all(n.level==0 for n in chapters)
 assert all(n.family=='kr_장' for n in r.tree)
 for n in r.nodes():assert n.level==next(i for i,row in enumerate(levels) if n.family in row)

def test_exact_missing_catalog_feedback():
 with pytest.raises(ValueError,match="missing=.*b"):
  loop.validate({'tag':'x','version':1,'levels':[['a']]},{'a':{},'b':{}})

def test_strict_template_requires_template():
 with pytest.raises(ValueError,match='requires an explicit template'):
  pipeline.interpret([Block(0,'제1조(목적) 본문')],doc='test',strict_ladder=True)

@pytest.mark.parametrize('draft',[False,True])
def test_explicit_article_heading_cannot_be_demoted(draft):
 bs,r,b=fixture();c=next(c for c in b.candidates if c.family=='kr_article' and c.offset==0)
 with pytest.raises(ValueError,match='Protected source headings'):
  loop.build(pipeline,bs,{**r,'reference_candidates':[c.id]},{'kr_article':{},'circled':{}},loop.inventory(b),draft=draft)

def test_reference_state_explains_exclusion_and_protection():
 bs,r,b=fixture();c=next(c for c in b.candidates if c.family=='circled' and c.offset>0)
 new=loop.build(pipeline,bs,{**r,'reference_candidates':[c.id]},{'kr_article':{},'circled':{}},loop.inventory(b))
 ctx=loop.context(bs,{},r,new);byid={x['id']:x for x in ctx['source_candidates']}
 assert byid[c.id]['excluded_as_reference'] and not byid[c.id]['protected_heading']
 assert any(x['protected_heading'] for x in byid.values() if x['family']=='kr_article')

@pytest.mark.parametrize('count',[1,8,10,16])
def test_schema_and_validator_share_observed_depth_limit(count):
 import jsonschema
 cat={f'f{i}':{} for i in range(count)};r={'tag':'composite','version':1,'levels':[[f] for f in cat]}
 jsonschema.validate(r,loop.recipe_schema(cat));assert loop.validate(r,cat)==r['levels']

def test_composite_depth_remains_bounded():
 import jsonschema
 cat={f'f{i}':{} for i in range(17)};r={'tag':'bounded','version':1,'levels':[[f] for f in cat]}
 with pytest.raises(ValueError):loop.validate(r,cat)
 with pytest.raises(jsonschema.ValidationError):jsonschema.validate(r,loop.recipe_schema(cat))

def test_heading_decision_restores_family_rejected_source_marker(monkeypatch):
 bs,r,b=fixture();wanted=next(c for c in b.candidates if c.family=='circled' and c.ordinal==(1,));original=pipeline.s2_family
 def reject(cands):
  out=original(cands)
  for c in cands:
   if c.id==wanted.id:c.survives=False;c.s=-10
  return out
 monkeypatch.setattr(pipeline,'s2_family',reject)
 plain=pipeline.interpret(copy.deepcopy(bs),doc='test',ladder_hint=r['levels'],strict_ladder=True)
 assert not any(n.candidate_id==wanted.id for n in plain.nodes())
 fixed=loop.build(pipeline,bs,{**r,'heading_candidates':[wanted.id]},{'kr_article':{},'circled':{}},loop.inventory(plain))
 assert any(n.candidate_id==wanted.id for n in fixed.nodes())
 assert '① 실제 내용' in bs[3].text

@pytest.mark.parametrize('refs,heads',[([],['unknown']),(['c1'],['c1'])])
def test_invalid_heading_decision_rejected(refs,heads):
 bs,r,b=fixture()
 with pytest.raises(ValueError):loop.build(pipeline,bs,{**r,'reference_candidates':refs,'heading_candidates':heads},{'kr_article':{},'circled':{}},loop.inventory(b))

def test_heading_decisions_require_visible_source_and_change_signature():
 _,r,_=fixture();new={**r,'heading_candidates':['c0']}
 assert loop.recipe_signature(r)!=loop.recipe_signature(new)
 with pytest.raises(ValueError,match='unseen'):loop.check_visible_references(new,{'source_candidates':[]})
 loop.check_visible_references(new,{'source_candidates':[{'id':'c0'}]})


def test_invalid_review_gets_exact_error_feedback_then_valid_source_revision():
 bs,r,b=fixture();c=next(c for c in b.candidates if c.family=='circled' and c.offset>0);cat={'kr_article':{},'circled':{}};data=loop.context(bs,cat,r,b);calls=[]
 def provider(*args):
  calls.append(args)
  out={**r,'heading_candidates':['not-visible'] if len(calls)==1 else [c.id]}
  return {'reviewed_state_id':args[2]['reviewed_state_id'],'verdict':'revise','issues':[{'blocks':[c.block_idx],'reason':'recover source marker'}],'recipe':out}
 got=loop.request_review('review',data,cat,provider)
 assert got['recipe']['heading_candidates']==[c.id] and len(calls)==2
 assert 'not-visible' in calls[1][2]['validation_feedback']['error']

def test_invalid_review_cannot_erase_its_reported_issue_by_approving():
 bs,r,b=fixture();cat={'kr_article':{},'circled':{}};data=loop.context(bs,cat,r,b);calls=[]
 def provider(*args):
  calls.append(args)
  return {'reviewed_state_id':args[2]['reviewed_state_id'],'verdict':'revise','issues':[{'blocks':[0],'reason':'wrong structure'}],'recipe':{**r,'heading_candidates':['bad']}} if len(calls)==1 else {'verdict':'approve','issues':[],'reviewed_state_id':args[2]['reviewed_state_id']}
 with pytest.raises(ValueError,match='cannot be approved'):loop.request_review('review',data,cat,provider)
 assert len(calls)==2

def test_window_patch_preserves_outside_and_clears_only_visible():
 _,r,_=fixture();old={**r,'heading_candidates':['old','visible'],'reference_candidates':['ref-old']};data={'recipe':old,'source_candidates':[{'id':'visible'},{'id':'new'}]}
 got=loop.merge_window_decisions({**r,'heading_candidates':['new'],'reference_candidates':[]},data)
 assert got['heading_candidates']==['new','old'] and got['reference_candidates']==['ref-old']
 loop.check_visible_references(got,data)
 assert old['heading_candidates']==['old','visible']

def test_omitted_decision_field_preserves_previous_visible_state():
 _,r,_=fixture();old={**r,'heading_candidates':['visible']};got=loop.merge_window_decisions(r,{'recipe':old,'source_candidates':[{'id':'visible'}]})
 assert got['heading_candidates']==['visible']
 with pytest.raises(ValueError,match='unseen'):loop.merge_window_decisions({**r,'heading_candidates':['unknown']},{'recipe':old,'source_candidates':[]})

def test_context_labels_parser_hint_without_source_mutation():
 bs,r,b=fixture();before=copy.deepcopy(bs);ctx=loop.context(bs,{},r,b)
 assert all('is_heading' not in row for row in ctx['source_blocks'])
 assert any('parser_heading_hint' in row for row in ctx['source_blocks'])
 assert bs==before
