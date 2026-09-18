"""Source spelling/offset and final storage contracts, without model calls."""
import copy
import pytest
from lawrag.core.structure import pipeline, recipe_basic, recipe_regions, recipe_pages, viewer
from lawrag.core.structure.model import Block
from lawrag.core.structure.proposers import annex
from lawrag.pipeline.genos_admission import preserve_unowned_source, validate_structure


@pytest.mark.parametrize('text',[
    '부칙','부 칙','  부칙','\t부  칙\t','[부칙]','〔부 칙〕','【 부칙 】','(부칙)','（부칙）',
    '부칙(2026. 1. 1.)',' 부칙 <2026. 1. 1.>','부칙 [제123호, 2026. 1. 1.]',
    '부칙 2026년 1월 1일','부칙\n시행일 본문'])
def test_buchik_variants_keep_original_text_and_source_offsets(text):
    blocks=[Block(0,'제1조(목적) 본문',page=1),Block(1,text,page=1),Block(2,'시행일 본문',page=1)]
    before=copy.deepcopy(blocks)
    candidates=[c for c in annex.propose(blocks[1],None) if c.family=='buchik']
    assert len(candidates)==1
    c=candidates[0];assert text[c.offset:c.end]==c.surface
    result=recipe_regions.build(pipeline,blocks,recipe_basic.seed(blocks),draft=True)
    assert [(n.family,n.block_idx) for n in result.tree]==[('kr_article',0),('buchik',1)]
    recipe_pages.audit(blocks,result,[])
    payload=preserve_unowned_source(viewer.payload(result,blocks))
    assert validate_structure('mock',{'doc_id':'mock'},payload)['accepted']
    assert [b['text'] for b in payload['blocks']]==[b.text for b in before]
    assert blocks==before


@pytest.mark.parametrize('text',[
    '부칙에 따라 시행한다.','부칙을 적용한다.','부칙 제1조에 따른다.',
    '[부칙]에 따른 변경','부칙 (시행일)에 관한 설명','부칙이라는 표현',
    '본문은 부칙을 참조한다.','부칙은 다음과 같다.','부칙 2026년 개정에 따른다.',
    '[부칙)','부\n칙'])
def test_body_mentions_do_not_become_headings(text):
    assert not [c for c in annex.propose(Block(0,text),None) if c.family=='buchik']


def test_repeated_addenda_stay_independent_roots():
    texts=['제1조(목적)','본문',' 부칙 <2024. 1. 1.>','시행일 2024년',
           '[부 칙] (2026. 1. 1.)','시행일 2026년']
    blocks=[Block(i,t,page=1) for i,t in enumerate(texts)]
    result=recipe_regions.build(pipeline,blocks,recipe_basic.seed(blocks),draft=True)
    assert [(n.family,n.span) for n in result.tree]==[('kr_article',(0,2)),('buchik',(2,4)),('buchik',(4,6))]
    recipe_pages.audit(blocks,result,[])


@pytest.mark.parametrize('text',['앞 문장\n부칙','제2조(본문) 내용\n부칙','부칙\n시행일 본문\n부칙 (2026. 1. 1.)'])
def test_merged_headings_are_detected_without_empty_or_overlapping_units(text):
    blocks=[Block(0,'제1조(목적) 본문',page=1),Block(1,text,page=1),Block(2,'시행일 본문',page=1)]
    found=[c for c in annex.propose(blocks[1],None) if c.family=='buchik' and c.construction=='fragment']
    assert found and all(text[c.offset:c.end]==c.surface for c in found)
    result=recipe_regions.build(pipeline,blocks,recipe_basic.seed(blocks),draft=True)
    risks=recipe_pages.audit(blocks,result,[])
    assert 'supplementary_heading_shares_source_block' in risks[1]
    payload=preserve_unowned_source(viewer.payload(result,blocks))
    assert validate_structure('mock',{'doc_id':'mock'},payload)['accepted']
    assert [b['text'] for b in payload['blocks']]==[b.text for b in blocks]
