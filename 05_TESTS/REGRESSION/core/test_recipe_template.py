import copy,json
import pytest,jsonschema
from lawrag.core.structure import pipeline,recipe_template as t,recipe_visual_loop as loop
from lawrag.core.structure.model import Block


def rule(parent=t.ROOT,position='line_start',sequence='consecutive',reset='parent'):
    return dict(parent_family=parent,heading_position=position,sequence=sequence,reset_scope=reset,rationale='synthetic source pattern')


def nested():
    blocks=[Block(i,s) for i,s in enumerate(['가. 준비','1. 자료','2. 검토','나. 실행','1. 시작','2. 확인','다. 종료','1. 기록','2. 보관'])]
    base=pipeline.interpret(copy.deepcopy(blocks),doc='synthetic',llm=None,ledger=None)
    catalog={c.family_key:{} for c in base.candidates}
    outer=next(f for f in catalog if f.startswith('hangul_jamo'))
    inner=next(f for f in catalog if f.startswith('dot_number'))
    rules={outer:rule(reset='document'),inner:rule(outer)}
    return blocks,base,catalog,t.compile_recipe(rules,catalog),outer,inner


def test_nested_numbering_and_unseen_tail_use_same_template():
    blocks,base,catalog,recipe,outer,inner=nested();before=copy.deepcopy(blocks)
    result=loop.build(pipeline,blocks,recipe,catalog,loop.inventory(base))
    assert [n.surface for n in result.tree]==['가.','나.','다.']
    assert [[n.surface for n in p.children] for p in result.tree]==[['1.','2.']]*3
    assert len(result.stats['template_compilation'])==9
    assert not result.stats['template_issues'] and blocks==before
    # Same frozen rules apply beyond the initial sample, without adding IDs.
    short=loop.build(pipeline,blocks[:3],recipe,catalog,())
    assert result.tree[0].surface==short.tree[0].surface
    assert 'heading_candidates' not in recipe and 'reference_candidates' not in recipe


def test_reset_scope_is_executed_and_sequence_errors_cannot_approve():
    blocks,base,catalog,recipe,outer,inner=nested()
    recipe['heading_rules'][inner]['reset_scope']='document'
    draft=loop.build(pipeline,blocks,recipe,catalog,(),draft=True)
    assert [x['block'] for x in draft.stats['template_issues'] if x['kind']=='number_sequence_violation']==[4,7]
    with pytest.raises(ValueError,match='grammar violations'):loop.build(pipeline,blocks,recipe,catalog,())


@pytest.mark.parametrize('sequence,passed',[('increasing',True),('consecutive',False)])
def test_gap_contract(sequence,passed):
    blocks,_,catalog,recipe,outer,inner=nested();blocks[2].text='3. 검토'
    recipe['heading_rules'][inner]['sequence']=sequence
    result=loop.build(pipeline,blocks,recipe,catalog,(),draft=True)
    assert bool(result.stats['template_issues']) is not passed


def test_parent_edge_checked_beyond_numeric_depth():
    blocks,_,catalog,recipe,outer,inner=nested()
    extra='other';catalog[extra]={};rules=copy.deepcopy(recipe['heading_rules']);rules[extra]=rule();rules[inner]['parent_family']=extra
    draft=loop.build(pipeline,blocks,t.compile_recipe(rules,catalog),catalog,(),draft=True)
    assert any(x['kind']=='parent_family_mismatch' for x in draft.stats['template_issues'])


def test_inline_paragraph_after_parent_title_but_not_prose_reference():
    blocks=[Block(0,'제1조(정의) ① 첫째 내용'),Block(1,'② 둘째 내용'),Block(2,'본문에서 ①을 인용한다.'),Block(3,'제2조(대상) ① 다음 내용')]
    base=pipeline.interpret(copy.deepcopy(blocks),doc='inline',llm=None,ledger=None)
    catalog={c.family_key:{} for c in base.candidates if c.construction!='fragment'}
    article=next(f for f in catalog if f.startswith('kr_article'))
    circle=next(f for f in catalog if f.startswith('circled'))
    recipe=t.compile_recipe({f:rule(article,'line_start_or_parent_title') if f==circle else rule(reset='document') for f in catalog},catalog)
    result=loop.build(pipeline,blocks,recipe,catalog,(),draft=True)
    nodes=[n for n in result.nodes() if n.family==circle]
    assert [(n.block_idx,n.surface) for n in nodes]==[(0,'①'),(1,'②'),(3,'①')]
    assert blocks[2].text=='본문에서 ①을 인용한다.'


@pytest.mark.parametrize('extra',[{'candidate_ids':['c5']},{'block_ids':[4]},{'text_equals':'가. 준비'},{'regex':'.*'},{'document_id':'krx'}])
def test_rule_forbids_instance_selectors_and_text_exceptions(extra):
    with pytest.raises(jsonschema.ValidationError):t.compile_recipe({'f':{**rule(),**extra}},{'f':{}})


@pytest.mark.parametrize('field',['heading_candidates','reference_candidates'])
def test_recipe_rejects_legacy_instance_overrides(field):
    recipe=t.compile_recipe({'f':rule()},{'f':{}});recipe[field]=[]
    with pytest.raises(ValueError,match='instance overrides'):loop.validate(recipe,{'f':{}})


def test_cycle_and_unknown_parent_rejected():
    for parent in ['f','unknown']:
        with pytest.raises(ValueError):t.compile_recipe({'f':rule(parent)},{'f':{}})


def test_edit_changes_all_instances_and_preserves_other_families():
    _,_,catalog,recipe,outer,inner=nested()
    changed=t.apply(recipe,[{'family':inner,'rule':rule(outer,sequence='increasing')}],catalog)
    assert changed['heading_rules'][outer]==recipe['heading_rules'][outer]
    assert t.signature(changed)!=t.signature(recipe)
    unchanged=copy.deepcopy(recipe);unchanged['heading_rules'][inner]['rationale']='different words only'
    assert t.signature(unchanged)==t.signature(recipe)


def review_data():
    return {'recipe':t.compile_recipe({'f':rule()},{'f':{}}),'source_blocks':[{'idx':0,'text':'1. title'}],'visual_evidence':{'images':[{'sha256':'image-one'}]}}


@pytest.mark.parametrize('mode',['stale','image_changed','noop','candidate_edit','unresolved','unknown_family'])
def test_invalid_review_rejected(mode):
    data=review_data()
    if mode=='unresolved':data['hard_code_issues']=[{'kind':'number_sequence_violation'}]
    stale=loop.digest(data)
    if mode=='image_changed':data['visual_evidence']['images'][0]['sha256']='image-two'
    def call(phase,system,request,schema,vision):
        out={'verdict':'approve','issues':[],'reviewed_state_id':request['reviewed_state_id'],'template_changes':[]}
        if mode=='stale':out['reviewed_state_id']='wrong'
        if mode=='image_changed':out['reviewed_state_id']=stale
        if mode=='noop':out.update(verdict='revise',template_changes=[{'family':'f','rule':rule()}])
        if mode=='candidate_edit':out['candidate_changes']=[{'candidate_id':'c5','decision':'reference'}]
        if mode=='unknown_family':out.update(verdict='revise',template_changes=[{'family':'unknown','rule':rule()}])
        return out
    with pytest.raises(ValueError,match='invalid_template_review'):t.request_review('test',data,{'f':{}},call)


def test_review_contains_only_template_edits():
    data=review_data()
    def call(phase,system,request,schema,vision):
        assert 'candidate_changes' not in schema['properties']
        return {'verdict':'revise','issues':[{'blocks':[0],'reason':'gaps allowed'}],'reviewed_state_id':request['reviewed_state_id'],'template_changes':[{'family':'f','rule':rule(sequence='increasing')}]}
    got=t.request_review('test',data,{'f':{}},call)
    assert got['recipe']['heading_rules']['f']['sequence']=='increasing'
