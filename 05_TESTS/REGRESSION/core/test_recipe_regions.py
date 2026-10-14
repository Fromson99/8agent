import copy,json
import pytest,jsonschema,fitz
from lawrag.core.structure import pipeline,recipe_regions as r,recipe_template as t,recipe_visual_loop as loop,recipe_pages,recipe_runtime as runtime,viewer
from lawrag.core.structure.model import Block


def rule(parent=t.ROOT):return {'parent_family':parent,'heading_position':'line_start','sequence':'consecutive','reset_scope':'parent','rationale':'synthetic source'}


def make():
    texts=['가. 준비','1. 자료','2. 확인','나. 실행','1. 시작','2. 종료','1. 새 양식','가. 항목','나. 점검','2. 다음 양식','가. 내용','나. 완료']
    blocks=[Block(i,x,page=i//6+1,element_index=100+i,bbox=[50,50+i%6*40,400,70+i%6*40],bbox_origin='TOPLEFT') for i,x in enumerate(texts)]
    regions=[{'start_block':0,'end_block':6,'template_id':'outer_hangul','label':'first','reason':'source pattern'},{'start_block':6,'end_block':12,'template_id':'outer_number','label':'second','reason':'changed source pattern'}]
    templates={}
    for reg in regions:
        local=r.local_source(blocks,reg);base=pipeline.interpret(copy.deepcopy(local),doc='source',llm=None,ledger=None);cat=r.observed_catalog(base,local)
        h=next(f for f in cat if f.startswith('hangul_jamo'));n=next(f for f in cat if f.startswith('dot_number'))
        outer,inner=(h,n) if reg['start_block']==0 else (n,h)
        templates[reg['template_id']]=t.compile_recipe({outer:rule(),inner:rule(outer)},cat)
    return blocks,{'tag':r.VERSION,'version':1,'source_block_count':12,'regions':regions,'templates':templates}


def test_same_number_family_has_different_roles_by_region():
    blocks,recipe=make();before=copy.deepcopy(blocks);result=loop.build(pipeline,blocks,recipe,{},())
    assert [n.surface for n in result.tree]==['가.','나.','1.','2.']
    assert [[c.surface for c in n.children] for n in result.tree]==[['1.','2.'],['1.','2.'],['가.','나.'],['가.','나.']]
    assert not result.stats['template_issues'] and blocks==before
    assert len({c.id for c in result.candidates})==len(result.candidates)
    for n in result.nodes():
        assert n.element_index==blocks[n.block_idx].element_index
        reg=recipe['regions'][0 if n.block_idx<6 else 1]
        assert reg['start_block']<=n.span[0]<n.span[1]<=reg['end_block']
    assert not result.ladder.rungs and len(result.stats['region_ladders'])==2
    assert len(loop.tree_record(result)['region_plan'])==2


def test_repeated_template_restarts_state_at_each_instance():
    blocks,recipe=make()
    for i in range(6,12):blocks[i].text=blocks[i-6].text
    recipe['regions'][1]['template_id']='outer_hangul';recipe['templates'].pop('outer_number')
    for rule_ in recipe['templates']['outer_hangul']['heading_rules'].values():rule_['reset_scope']='document' if rule_['parent_family']==t.ROOT else 'parent'
    result=loop.build(pipeline,blocks,recipe,{},())
    assert [n.surface for n in result.tree]==['가.','나.','가.','나.'] and not result.stats['template_issues']


@pytest.mark.parametrize('mode',['gap','overlap','empty','uncovered','unknown_template','manual_edit'])
def test_invalid_coverage_is_rejected(mode):
    _,recipe=make()
    if mode=='gap':recipe['regions'][1]['start_block']=7
    if mode=='overlap':recipe['regions'][1]['start_block']=5
    if mode=='empty':recipe['regions'][1]['end_block']=6
    if mode=='uncovered':recipe['regions'].pop();recipe['templates'].pop('outer_number')
    if mode=='unknown_template':recipe['regions'][0]['template_id']='missing'
    if mode=='manual_edit':recipe['heading_candidates']=['c1']
    with pytest.raises(ValueError):r.validate(recipe)


@pytest.mark.parametrize('starts',[[1,6],[0,6,6],[0,8,6],[0,4],[0,12]])
def test_bad_or_unseen_transition_evidence_rejected(starts):
    data={'source_block_count':12,'allowed_start_blocks':[0,6]}
    answer={'regions':[{'start_block':i,'template_id':'format','label':'part','reason':'test'} for i in starts]}
    with pytest.raises(ValueError):r.compile_plan(answer,data)


def test_transition_outline_sees_tail_and_preserves_all_block_coverage():
    blocks,recipe=make();base=pipeline.interpret(copy.deepcopy(blocks),doc='outline',llm=None,ledger=None);data=r.transition_evidence(blocks,base)
    assert [x['block'] for x in data['outline']]==list(range(12)) and 6 in data['allowed_start_blocks']
    answer={'regions':[{k:v for k,v in reg.items() if k!='end_block'} for reg in recipe['regions']]}
    plan=r.compile_plan(answer,data)
    assert [i for reg in plan for i in range(reg['start_block'],reg['end_block'])]==list(range(12))


def test_region_template_change_preserves_other_formats_and_boundaries():
    _,recipe=make();tid='outer_number';family=next(iter(recipe['templates'][tid]['heading_rules']));updated=copy.deepcopy(recipe['templates'][tid]['heading_rules'][family]);updated['sequence']='increasing'
    result=r.apply(recipe,[{'template_id':tid,'family':family,'rule':updated}])
    assert result['templates']['outer_hangul']==recipe['templates']['outer_hangul'] and result['regions']==recipe['regions']
    assert r.signature(result)!=r.signature(recipe)
    label_only=copy.deepcopy(recipe);label_only['regions'][0]['label']='new label';assert r.signature(label_only)==r.signature(recipe)


def test_merge_preserves_bbox_and_table_attachment_global_coordinates(tmp_path):
    blocks,recipe=make();blocks[11].kind='table';blocks[11].text='table source';result=loop.build(pipeline,blocks,recipe,{},())
    attachments=[a for n in result.nodes() for a in n.attachments]
    assert any(a['block']==11 and a['element_index']==111 for a in attachments)
    pdf=tmp_path/'two.pdf'
    with fitz.open() as doc:doc.new_page();doc.new_page();doc.save(pdf)
    payload=viewer.payload(result,blocks,pdf)
    assert payload['blocks'][6]['idx']==6 and payload['blocks'][6]['rect']
    owner=payload['blocks'][11]['node'];assert payload['nodes'][owner]['block']>=6
    assert len(payload['stats']['region_ladders'])==2


def test_resegment_requires_evidence_and_cannot_apply_instance_edits():
    _,recipe=make();data={'recipe':recipe,'source_blocks':[{'idx':6,'text':'new format'}]}
    def call(phase,system,request,schema,vision):
        return {'verdict':'resegment','reviewed_state_id':request['reviewed_state_id'],'issues':[{'blocks':[6],'reason':'different numbering hierarchy begins here'}],'template_changes':[]}
    result=r.adjudicate_review('test',data,{},call)
    assert result['verdict']=='resegment' and result['recipe']==recipe
    bad=call('','',{'reviewed_state_id':'x'},None,True);bad['candidate_changes']=[{'candidate_id':'c1'}]
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,r.review_schema())


def test_review_normalizes_only_syntax_and_retains_raw_evidence():
    _,recipe=make();data={'recipe':recipe,'source_blocks':[{'idx':6,'text':'source'}]};saved={}
    def call(phase,system,request,schema,vision):
        return {'verdict':' APPROVE ','reviewed_state_id':request['reviewed_state_id'],'issues':[],'template_changes':[]}
    answer=r.adjudicate_review('test',data,{},call,save=lambda name,value:saved.update({name:value}))
    assert answer['verdict']=='approve'
    assert saved['test-raw-review.json']['verdict']==' APPROVE '
    assert saved['test-normalization.json']['repairs']==['verdict_case_whitespace']


def test_conflicting_review_is_clarified_without_implicit_approval():
    _,recipe=make();data={'recipe':recipe,'source_blocks':[{'idx':6,'text':'source'}]}
    tid='outer_number';family=next(iter(recipe['templates'][tid]['heading_rules']))
    rule=copy.deepcopy(recipe['templates'][tid]['heading_rules'][family]);rule['sequence']='increasing'
    edit={'template_id':tid,'family':family,'rule':rule};seen=[]
    def call(phase,system,request,schema,vision):
        seen.append(copy.deepcopy(request))
        return {'verdict':'approve' if len(seen)==1 else 'revise','reviewed_state_id':request['reviewed_state_id'],
                'issues':[],'template_changes':[edit,edit]}
    answer=r.adjudicate_review('test',data,{},call)
    assert len(seen)==2 and 'validation_feedback' in seen[1]
    assert answer['verdict']=='revise' and len(answer['template_changes'])==1
    assert r.signature(answer['recipe'])!=r.signature(recipe)


def test_repeated_conflict_is_pending_and_cannot_turn_into_approval():
    _,recipe=make();data={'recipe':recipe,'source_blocks':[{'idx':6,'text':'source'}]};seen=[];saved={}
    def call(phase,system,request,schema,vision):
        seen.append(phase)
        return {'verdict':'approve','reviewed_state_id':request['reviewed_state_id'],
                'issues':[{'blocks':[6],'reason':'still unresolved'}] if len(seen)==1 else [],'template_changes':[]}
    with pytest.raises(ValueError,match='review_pending'):
        r.adjudicate_review('test',data,{},call,save=lambda name,value:saved.update({name:value}))
    assert len(seen)==2 and saved['test-pending.json']['status']=='review_pending'


@pytest.mark.parametrize('repeat_previous',[False,True])
def test_stalled_review_reports_exact_controls_and_reason(repeat_previous):
    _,recipe=make();data={'recipe':recipe,'source_blocks':[{'idx':6,'text':'private source'}]}
    tid='outer_number';family=next(iter(recipe['templates'][tid]['heading_rules']))
    rule=copy.deepcopy(recipe['templates'][tid]['heading_rules'][family])
    rule['rationale']='private model explanation only'
    if repeat_previous:rule['sequence']='increasing'
    edit={'template_id':tid,'family':family,'rule':rule}
    seen_levels=[r.signature(r.apply(recipe,[edit]))] if repeat_previous else []
    requests=[];saved={}
    def call(phase,system,request,schema,vision):
        requests.append(copy.deepcopy(request))
        return {'verdict':'revise','reviewed_state_id':request['reviewed_state_id'],
                'issues':[],'template_changes':[edit]}
    with pytest.raises(r.ReviewPending) as failure:
        r.adjudicate_review('test',data,{},call,seen_levels=seen_levels,save=lambda n,v:saved.update({n:copy.deepcopy(v)}))
    code='REPEATED_STRUCTURE' if repeat_previous else 'NO_EXECUTABLE_CHANGE'
    assert failure.value.diagnostic['code']==code and len(requests)==2
    assert code in requests[1]['validation_feedback']
    assert 'Never invent a rule change' in requests[1]['validation_feedback']
    comparison=requests[1]['rule_comparison'][0]
    assert comparison['changed_fields']==(['sequence'] if repeat_previous else [])
    assert comparison['rationale_changed'] is True
    pending=saved['test-pending.json']
    assert pending['code']==code and pending['rule_comparison']==[comparison]
    assert 'private' not in json.dumps(failure.value.diagnostic)


def test_stalled_review_can_return_an_actual_executable_correction():
    _,recipe=make();data={'recipe':recipe,'source_blocks':[{'idx':6,'text':'source'}]}
    tid='outer_number';family=next(iter(recipe['templates'][tid]['heading_rules']));seen=[]
    def call(phase,system,request,schema,vision):
        seen.append(copy.deepcopy(request))
        rule=copy.deepcopy(recipe['templates'][tid]['heading_rules'][family])
        if len(seen)>1:rule['sequence']='increasing'
        return {'verdict':'revise','reviewed_state_id':request['reviewed_state_id'],'issues':[],
                'template_changes':[{'template_id':tid,'family':family,'rule':rule}]}
    result=r.adjudicate_review('test',data,{},call)
    assert len(seen)==2 and seen[1]['rule_comparison'][0]['changed_fields']==[]
    assert result['verdict']=='revise' and r.signature(result['recipe'])!=r.signature(recipe)


def test_boundary_revision_rebuilds_and_rechecks_prior_window(tmp_path,monkeypatch):
    pdf=tmp_path/'source.pdf';blocks=[]
    with fitz.open() as doc:
        for p in range(1,9):
            page=doc.new_page();page.insert_text((50,50),f'Article {p}')
            blocks.append(Block(p-1,f'제{p}조(제목) 내용입니다.',page=p,bbox=[50,40,400,65],bbox_origin='TOPLEFT'))
        doc.save(pdf)
    monkeypatch.setenv('STRUCTURE_RECIPE_REVIEW_MODE','adaptive');monkeypatch.setenv('STRUCTURE_RECIPE_MAX_PAGES','3');monkeypatch.setenv('STRUCTURE_RECIPE_TAGS',str(tmp_path/'tags.json'))
    calls=[];detects=0;reviews=0;first_approved=None
    class Fake:
        def bind_recovery(self,*args):pass  # non-network compiler fixture
        def __init__(self,journal,images,**kw):self.images=images;self.calls=0;self.model='synthetic-no-provider'
        def __call__(self,phase,system,data,schema,vision):
            nonlocal detects,reviews,first_approved
            self.calls+=1;calls.append((phase,data))
            if 'regions' in schema['properties']:
                detects+=1
                return {'regions':[{'start_block':i,'template_id':'same_format','label':'synthetic region','reason':'independent numbering scope'} for i in ([0] if detects==1 else [0,4])]}
            if 'families' in schema['properties']:
                return {'families':{f:{'parent_family':t.ROOT,'heading_position':'line_start','sequence':'increasing','reset_scope':'document','rationale':'source'} for f in data['catalog']}}
            if 'opinions' in schema['properties']:return {'opinions':[],'summary':'No defects observed'}
            reviews+=1
            if reviews==1:first_approved=data['page_window']
            issues=[{'blocks':[data['source_blocks'][0]['idx']],'reason':'Format restarts; inspect global boundary outline'}] if reviews==2 else []
            return {'opinion_decisions':[],'verdict':'resegment' if reviews==2 else 'approve','issues':issues,'template_changes':[],'reviewed_state_id':data['reviewed_state_id']}
    monkeypatch.setattr(runtime,'GenosCalls',Fake)
    result,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='boundary-contract')
    assert detects==2 and len(result.stats['region_plan'])==2
    after=[d for p,d in calls if p.startswith('window-review-2')]
    assert after and after[0]['page_window']==first_approved
    assert any(n.block_idx==4 and n.span[1]<=8 for n in result.nodes())
    events=[json.loads(line) for line in (tmp_path/'structure-recipe-runs'/meta['run_id']/'events.jsonl').read_text().splitlines()]
    correction=next(e for e in events if e['event']=='recipe.correction')
    assert correction['approvals_invalidated'] and correction['corrections']==1 and correction['replans']==1
    assert any(e['event']=='recipe.review.start' and e['revision']==2 and e['window_number']==1 for e in events)
    count=len(calls);replay,cached=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='boundary-contract')
    assert len(calls)==count and cached['model_calls']==0 and loop.tree_record(replay)==loop.tree_record(result)


def test_issue_aliases_preserve_source_error_and_do_not_approve():
    _,recipe=make();data={'recipe':recipe,'source_blocks':[{'idx':6,'text':'source'}]};saved={}
    def call(phase,system,request,schema,vision):
        return {'verdict':'source_error','reviewed_state_id':request['reviewed_state_id'],
                'issues':[{'block':6,'explanation':'Possible duplicated numbering; verify source',
                           'family':'paren_number:both','kind':'source_error'}],'template_changes':[]}
    result=r.adjudicate_review('test',data,{},call,save=lambda name,value:saved.update({name:value}))
    assert result['verdict']=='source_error' and result['recipe']==recipe
    assert result['issues'][0]['blocks']==[6]
    assert 'Possible duplicated numbering' in result['issues'][0]['reason']
    assert 'family: paren_number:both' in result['issues'][0]['reason']
    assert 'kind: source_error' in result['issues'][0]['reason']
    assert saved['test-raw-review.json']['issues'][0]['block']==6


@pytest.mark.parametrize('issue',[
    {'block':6,'blocks':[7],'explanation':'finding'},
    {'block':6,'reason':'one','explanation':'different'},
    {'block':'6','explanation':'finding'},
    {'block':True,'explanation':'finding'},
    {'block':6,'explanation':'finding','unknown':'must not discard'},
    {'block':99999,'explanation':'unseen source'},
])
def test_ambiguous_or_unseen_issue_aliases_remain_pending(issue):
    _,recipe=make();data={'recipe':recipe,'source_blocks':[{'idx':6,'text':'source'}]}
    def call(phase,system,request,schema,vision):
        return {'verdict':'source_error','reviewed_state_id':request['reviewed_state_id'],
                'issues':[issue],'template_changes':[]}
    with pytest.raises(ValueError,match='review_pending'):r.adjudicate_review('test',data,{},call)
