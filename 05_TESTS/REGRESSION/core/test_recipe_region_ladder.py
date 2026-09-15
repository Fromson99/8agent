import copy
from lawrag.core.structure import pipeline,recipe_template as t,recipe_visual_loop as loop,recipe_regions as r
from lawrag.core.structure.model import Block

def test_single_source_style_executes_strict_template():
    blocks=[Block(0,'합성 문서 제목',is_heading=True,heading_level=1,size_ratio=1.4,bbox=[50,50,400,80],bbox_origin='TOPLEFT')]
    rule={'parent_family':'$document','heading_position':'source_style','sequence':'unordered','reset_scope':'document','rationale':'synthetic title'}
    template=t.compile_recipe({'style_h:1':rule},{'style_h:1':{}})
    result=loop.build(pipeline,blocks,template,{'style_h:1':{}},())
    assert len(result.nodes())==1 and result.nodes()[0].surface=='합성 문서 제목'
    assert result.nodes()[0].level==0 and result.ladder.rungs[0].families==['style_h:1']
    # Without an explicit template, original inference still treats this as a singleton.
    vanilla=pipeline.interpret(copy.deepcopy(blocks),doc='original',llm=None,ledger=None)
    assert not vanilla.ladder.rungs and vanilla.ladder.singletons==['style_h:1']

def test_singleton_region_merges_with_numbered_body_and_preserves_source():
    blocks=[Block(0,'합성 제목',is_heading=True,heading_level=1),Block(1,'제1조(내용) 본문'),Block(2,'제2조(절차) 본문')]
    r0={'parent_family':'$document','heading_position':'source_style','sequence':'unordered','reset_scope':'document','rationale':'title'}
    r1={**r0,'heading_position':'line_start','sequence':'consecutive'}
    recipe={'tag':r.VERSION,'version':1,'source_block_count':3,'regions':[{'start_block':0,'end_block':1,'template_id':'title','label':'title','reason':'source'},{'start_block':1,'end_block':3,'template_id':'body','label':'body','reason':'source'}],'templates':{'title':t.compile_recipe({'style_h:1':r0},{'style_h:1':{}}),'body':t.compile_recipe({'kr_article':r1},{'kr_article':{}})}}
    original=copy.deepcopy(blocks);result=loop.build(pipeline,blocks,recipe,{},())
    assert [(n.block_idx,n.span) for n in result.tree]==[(0,(0,1)),(1,(1,2)),(2,(2,3))]
    assert blocks==original and len({c.id for c in result.candidates})==3
