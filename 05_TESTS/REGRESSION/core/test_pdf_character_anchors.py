import copy
import pytest
from lawrag.core.structure import pipeline,recipe_visual_loop as loop
from lawrag.core.structure.model import Block

def fixture():
    blocks=[Block(i,t,page=1) for i,t in enumerate(['제1조(목적) 가','제2조(정의) 나','제3조(적용) 다','제4조(지원기준) ① 실제 비용에 대해 [ 별표 1] 에서 정한 기준으로 지원한다.','② 다음 항의 본문이다.'])]
    recipe={'tag':'anchors','version':1,'levels':[['kr_article'],['circled']]}
    result=pipeline.interpret(copy.deepcopy(blocks),doc='fixture',llm=None,ledger=None,ladder_hint=recipe['levels'],partial_order=[('kr_article','circled')])
    return blocks,recipe,result

def test_nested_article_paragraph_with_distinct_offsets_rebuild():
    blocks,recipe,result=fixture();original=copy.deepcopy(blocks)
    same=[n for n in result.nodes() if n.block_idx==3]
    assert {n.family for n in same}=={'kr_article','circled'}
    rebuilt=loop.build(pipeline,blocks,recipe,{'kr_article':{},'circled':{}},loop.inventory(result))
    assert loop.inventory(rebuilt)==loop.inventory(result)
    assert blocks==original
    assert len({r[3] for r in loop.inventory(rebuilt) if r[2]==3})==2

@pytest.mark.parametrize('mutation',['offset','missing','sibling','reverse','marker','span'])
def test_shared_block_invalid_anchors_still_fail(mutation):
    blocks,_,result=fixture();same=[n for n in result.nodes() if n.block_idx==3];parent=next(n for n in same if n.family=='kr_article');child=next(n for n in same if n.family=='circled');c=next(c for c in result.candidates if c.id==child.candidate_id)
    if mutation=='offset':c.offset=0
    if mutation=='missing':child.candidate_id='absent'
    if mutation=='sibling':parent.children.remove(child);result.tree.append(child)
    if mutation=='reverse':child.level=parent.level
    if mutation=='marker':c.surface='invented'
    if mutation=='span':child.span=(3,len(blocks)+1)
    with pytest.raises(ValueError):loop.check_source_anchors(result,blocks)

def test_numbered_inventory_requires_source_candidate():
    _,_,result=fixture();result.candidates=[]
    with pytest.raises(ValueError,match='source candidate'):loop.inventory(result)
