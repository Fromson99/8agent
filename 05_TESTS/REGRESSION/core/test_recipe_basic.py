"""Basic-first, source-bounded wiring contracts with synthetic HTTP responses."""
import copy
import json
import re
import base64
import hashlib

import fitz
import pytest

from lawrag.core.structure import pipeline, recipe_runtime as runtime, recipe_basic as basic
from lawrag.core.structure import recipe_regions as regions, recipe_visual_loop as loop
from lawrag.core.structure.model import Block
from .test_recipe_runtime import isolated_env, install_transport, response, regional_document


def wire(monkeypatch, *, correction=False, unsupported=False, fail_review=False, repeats=False,
         cutoff_pages=None, cycle=False, bad_block=False, conflicting_approval=False,
         reject_finding=False, reconsider_approve=False):
    monkeypatch.setenv('STRUCTURE_RECIPE_PROTOCOL','basic')
    seen=[];corrected=False
    def http(session,url,payload):
        nonlocal corrected
        content=payload['messages'][1]['content']
        data=json.loads(content if isinstance(content,str) else next(b['text'] for b in content if b['type']=='text'))
        forbidden={'source_blocks','recipe','actual_structure','observed_markers','visual_evidence',
                   'reviewed_state_id','active_regions','supported_methods','code_issues','hard_code_issues'}
        assert not forbidden & set(data)
        assert 'BODY_TAIL_TOKEN' not in json.dumps(data)
        task=('visual_review' if 'available_patterns' in data else
              'body_verification' if 'findings' in data else
              'correction_scope' if 'regions' in data else 'parent_relations')
        images=[b for b in content if b['type']=='image_url'] if isinstance(content,list) else []
        row={**copy.deepcopy(data),'task':task,'image_count':len(images)}
        row['image_hashes']=[hashlib.sha256(base64.b64decode(b['image_url']['url'].split(',',1)[1])).hexdigest()
                             for b in images]
        if task=='visual_review':
            ps=re.search(r'실제 페이지 순서: ([0-9, ]+)\.',payload['messages'][0]['content']).group(1)
            row['page_window']=[int(p) for p in ps.split(',')]
            assert len(images)==2*len(row['page_window'])
        else:
            assert not images
        seen.append(row)
        if task=='visual_review':
            if fail_review:return 401
            if cutoff_pages and len(row['page_window'])>cutoff_pages:
                return response({'incomplete':True},'length')
            verdict='missing_rules' if unsupported else 'revise' if correction and (not corrected or repeats) else 'approve'
            if reconsider_approve and data.get('reconsider'): verdict='approve'
            corrections=([{'page':1,'block':1,'change':'숫자 항목은 한글 번호 아래에 있어야 한다.'}]
                         if verdict=='revise' else [])
            if bad_block:corrections=[{'page':1,'block':999,'change':'잘못된 위치'}];verdict='revise'
            if conflicting_approval:
                corrections=[{'page':1,'block':0,'change':'수정 필요'}];verdict='approve'
            value={'verdict':verdict,'corrections':corrections,
                   'summary':'모든 조항이 정확하게 인식되고 올바르게 구조화되었습니다.' if verdict=='approve' else '수정 필요'}
        elif task=='body_verification':
            assert all(set(f)=={'body','current_placement','vlm_judgment'} for f in data['findings'])
            value={'decisions':[{'verdict':'recheck' if reject_finding else 'accept',
                                'reason':'이미 조문 본문으로 포함되어 있습니다. 다시 확인하세요.' if reject_finding else '원문에서 한글 번호 아래의 숫자 항목입니다.'}
                               for f in data['findings']]}
        elif task=='correction_scope':
            r=data['regions'][0]
            value={'start_block':r['start_block'],'end_block':r['end_block']}
        elif task=='parent_relations':
            choices=data['patterns']
            outer=next(c['id'] for c in choices if any(s.startswith('가') for s in c['examples']))
            value={'parents':{c['id']:'ROOT' if c['id']==outer else outer for c in choices}}
            if cycle:
                ids=[c['id'] for c in choices]
                value={'parents':{a:ids[(i+1)%len(ids)] for i,a in enumerate(ids)}}
            corrected=True
        else:raise AssertionError(task)
        body=response(value);body['choices'][0]['message']['content']=json.dumps(value)
        return body
    install_transport(monkeypatch,http)
    return seen


def nested_pdf(tmp_path):
    texts=['가. Alpha','1. Bravo','2. Charlie','나. Delta','1. Echo','2. Foxtrot']
    blocks=[];pdf=tmp_path/'nested.pdf'
    with fitz.open() as doc:
        for p in range(2):
            page=doc.new_page()
            for i,text in enumerate(texts[p*3:p*3+3]):
                page.insert_text((50,60+i*40),'Synthetic marker '+str(i))
                blocks.append(Block(p*3+i,text,page=p+1,bbox=[50,40+i*40,450,70+i*40],bbox_origin='TOPLEFT'))
        doc.save(pdf)
    return pdf,blocks


def test_default_is_basic(monkeypatch,tmp_path):
    wire(monkeypatch)
    monkeypatch.delenv('STRUCTURE_RECIPE_PROTOCOL')
    assert runtime.GenosCalls(runtime.Journal(tmp_path,'default'),[]).protocol=='basic'


def test_authored_basic_is_applied_before_first_visual_request(tmp_path,monkeypatch):
    seen=wire(monkeypatch)
    pdf,blocks=regional_document(tmp_path)
    blocks[1].text='① 수정듀레이션은 1.5년 이하, CMA RP는 0.8년 이하이다.'
    tree,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='authored')
    assert meta['runtime']=='genos-recipe-v38-output-contract-recovery'
    assert meta['model_calls']==1 and len(seen)==1 and seen[0]['task']=='visual_review'
    assert not any(n.family.startswith('dot_number') for n in tree.nodes())
    recipe=json.loads(next((tmp_path/'structure-recipe-runs').glob('*/basic-initial-template.json')).read_text())
    assert recipe['templates']['basic']==basic.default_template()
    cached_tree,cached=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='authored')
    assert cached['reused'] and cached['model_calls']==0
    assert loop.tree_record(cached_tree)==loop.tree_record(tree)


def test_first_call_reviews_exact_basic_and_contains_no_full_body(tmp_path,monkeypatch):
    seen=wire(monkeypatch)
    pdf,blocks=regional_document(tmp_path)
    blocks[0].text+=' X'*500+' BODY_TAIL_TOKEN'
    expected=pipeline.interpret(copy.deepcopy(blocks),doc='expected',llm=None,ledger=None)
    tree,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='basic')
    assert seen[0]['task']=='visual_review' and seen[0]['image_count']==4
    assert basic.structure_signature(tree)==basic.structure_signature(expected)
    # Positive summary is not a defect and creates no follow-up approval call.
    assert meta['status']=='visual_approved' and meta['model_calls']==1
    methods=seen[0]['available_patterns']
    assert any('가.' in m for m in methods)
    assert 'ㄱ.' not in json.dumps(methods,ensure_ascii=False)
    journal=next((tmp_path/'structure-recipe-runs').glob('*/call-1-*-input.json'))
    assert set(json.loads(journal.read_text())['data'])=={'available_patterns'}
    evidence=json.loads(next(journal.parent.glob('viewer-evidence-*/evidence.json')).read_text())
    assert seen[0]['image_hashes']==[r['sha256'] for r in evidence['images']]
    assert all(r['text']==b.text for r,b in zip(json.loads(next((tmp_path/'structure-recipe-runs').glob('*/blocks.json')).read_text()),blocks))
    count=len(seen)
    again,cached=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='basic')
    assert cached['reused'] and len(seen)==count and loop.tree_record(tree)==loop.tree_record(again)


def test_parent_template_is_executed_by_code_then_rechecked(tmp_path,monkeypatch):
    seen=wire(monkeypatch,correction=True)
    pdf,blocks=nested_pdf(tmp_path)
    original=copy.deepcopy(blocks)
    hints={'ladder_hint':[['dot_number:1'],['hangul_jamo']],'strict_ladder':True}
    before=pipeline.interpret(copy.deepcopy(blocks),doc='wrong',llm=None,ledger=None,**hints)
    tree,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='correct',hints=hints)
    assert basic.structure_signature(tree)!=basic.structure_signature(before)
    assert [n.surface for n in tree.tree]==['가.','나.']
    assert [[c.surface for c in n.children] for n in tree.tree]==[['1.','2.'],['1.','2.']]
    assert blocks==original and meta['status']=='visual_approved'
    tasks=[x['task'] for x in seen]
    assert tasks==['visual_review','body_verification','correction_scope','parent_relations','visual_review']
    assert [x['image_count'] for x in seen]==[4,0,0,0,4]
    final=json.loads(next((tmp_path/'structure-recipe-runs').glob('*/final-template.json')).read_text())
    assert any(t['parent_map'].get('dot_number:1')=='hangul_jamo' for t in final['templates'].values())
    # Persisted rules alone rebuild the result without any further model call.
    rebuilt=regions.build(pipeline,blocks,final)
    assert loop.tree_record(rebuilt)==loop.tree_record(tree)


def test_unsupported_method_is_held_not_invented(tmp_path,monkeypatch):
    seen=wire(monkeypatch,unsupported=True)
    pdf,blocks=regional_document(tmp_path)
    with pytest.raises(runtime.NeedsReview,match='document_grammar_extension_required'):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='unsupported')
    assert not any(x['task']=='parent_relations' for x in seen)
    assert not (tmp_path/'structure-recipes.json').exists()


def test_http_failure_does_not_start_rule_generation(tmp_path,monkeypatch):
    seen=wire(monkeypatch,fail_review=True)
    pdf,blocks=regional_document(tmp_path)
    with pytest.raises(runtime.NeedsReview):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='failure')
    assert len(seen)==1 and seen[0]['task']=='visual_review'
    assert not (tmp_path/'structure-recipes.json').exists()


def test_repeated_structure_cannot_be_approved(tmp_path,monkeypatch):
    seen=wire(monkeypatch,correction=True,repeats=True)
    pdf,blocks=nested_pdf(tmp_path)
    hints={'ladder_hint':[['dot_number:1'],['hangul_jamo']],'strict_ladder':True}
    with pytest.raises(runtime.NeedsReview):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='repeat',hints=hints)
    assert any(x.get('correction') for x in seen if x['task']=='parent_relations')
    assert not (tmp_path/'structure-recipes.json').exists()


def test_initial_template_preserves_hints_and_does_not_create_rules():
    recipe,blocks=nested_pdf_fixture()
    assert not recipe['templates']['basic']['heading_rules']
    baseline=pipeline.interpret(copy.deepcopy(blocks),doc='basic',llm=None,ledger=None,
                                **recipe['templates']['basic']['hints'])
    assert loop.tree_record(regions.build(pipeline,blocks,recipe))==loop.tree_record(baseline)


def nested_pdf_fixture():
    # Pure code contract: no image/provider needed.
    blocks=[Block(0,'가. Parent',page=1),Block(1,'1. Child',page=1)]
    hints={'ladder_hint':[['hangul_jamo'],['dot_number:1']],'strict_ladder':True}
    recipe=basic.seed(blocks,hints)
    return recipe,blocks


def test_scoped_install_keeps_other_source_regions():
    recipe,blocks=nested_pdf_fixture()
    rule={'parent_family':'$document','heading_position':'line_start','sequence':'unordered',
          'reset_scope':'parent','rationale':'Synthetic'}
    proposed=basic.grammar.compile_recipe({'dot_number:1':rule},{'dot_number:1':{}})
    updated=basic.install(recipe,recipe['regions'][0],{'start_block':1,'end_block':2},proposed)
    assert updated['regions'][0]['template_id']=='basic' and updated['regions'][0]['end_block']==1
    assert [(r['start_block'],r['end_block']) for r in updated['regions']]==[(0,1),(1,2)]
    assert updated['templates']['basic']==recipe['templates']['basic']


def test_all_pages_reviewed_with_bounded_text_and_overlapping_splits(tmp_path,monkeypatch):
    seen=wire(monkeypatch,cutoff_pages=2)
    pdf,blocks=regional_document(tmp_path,count=6)
    _,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='split')
    assert meta['coverage']['visually_reviewed_pages']==list(range(1,7))
    actions=[x for x in seen if x['task']=='visual_review' and len(x['page_window'])<=2]
    assert actions
    for p in range(1,6):assert any({p,p+1}<=set(x['page_window']) for x in actions)
    events=[json.loads(line) for line in next((tmp_path/'structure-recipe-runs').glob('*/events.jsonl')).read_text().splitlines()]
    assert any(e['event']=='recipe.output.split' for e in events)


def test_basic_context_budget_stops_before_provider_and_never_approves(tmp_path,monkeypatch):
    seen=wire(monkeypatch)
    monkeypatch.setenv('STRUCTURE_RECIPE_REVIEW_MAX_CHARS','1000')
    monkeypatch.setattr(basic,'capabilities',lambda _: [{'example':'x'*1200}])
    pdf,blocks=regional_document(tmp_path,count=3)
    with pytest.raises(runtime.NeedsReview,match='document_context_budget_exceeded'):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='input-limit')
    assert seen==[] and not (tmp_path/'structure-recipes.json').exists()
    events=[json.loads(line) for line in next((tmp_path/'structure-recipe-runs').glob('*/events.jsonl')).read_text().splitlines()]
    assert any(e.get('reason')=='INPUT_CONTEXT_LIMIT' for e in events)


def test_parent_cycle_is_feedback_and_never_executed(tmp_path,monkeypatch):
    seen=wire(monkeypatch,correction=True,cycle=True)
    pdf,blocks=nested_pdf(tmp_path)
    original=copy.deepcopy(blocks)
    with pytest.raises(runtime.NeedsReview):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='cycle')
    attempts=[x for x in seen if x['task']=='parent_relations']
    assert len(attempts)==2 and 'Parent cycle' in attempts[1]['correction']['message']
    assert blocks==original and not (tmp_path/'structure-recipes.json').exists()


@pytest.mark.parametrize('failure',['bad_block','conflicting_approval'])
def test_image_review_cannot_invent_source_ids_or_approve_corrections(tmp_path,monkeypatch,failure):
    seen=wire(monkeypatch,**{failure:True})
    pdf,blocks=regional_document(tmp_path)
    with pytest.raises(runtime.NeedsReview,match='COMPACT_RESPONSE_INVALID'):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document=failure)
    assert len(seen)==3 and all(r['task']=='visual_review' for r in seen)
    assert 'correction' in seen[1] and not (tmp_path/'structure-recipes.json').exists()


def test_visual_approval_does_not_waive_code_corruption(tmp_path,monkeypatch):
    from lawrag.core.structure import recipe_pages
    seen=wire(monkeypatch)
    pdf,blocks=regional_document(tmp_path)
    monkeypatch.setattr(recipe_pages,'audit',lambda *a,**k:{1:['invalid_tree_parent']})
    with pytest.raises(runtime.NeedsReview,match='reviewer_hold'):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='code-corrupt')
    assert len(seen)==1 and not (tmp_path/'structure-recipes.json').exists()
    assert next((tmp_path/'structure-recipe-runs').glob('*/*-code-approval-blocked.json')).exists()


def test_disputed_finding_returns_to_vlm_before_any_template_change(tmp_path,monkeypatch):
    seen=wire(monkeypatch,correction=True,reject_finding=True,reconsider_approve=True)
    pdf,blocks=nested_pdf(tmp_path)
    expected=pipeline.interpret(copy.deepcopy(blocks),doc='expected',llm=None,ledger=None)
    tree,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='disputed')
    assert [r['task'] for r in seen]==['visual_review','body_verification','visual_review']
    assert seen[1]['findings'][0]['body']=='가. Alpha\n\n1. Bravo\n\n2. Charlie'
    assert seen[2]['reconsider'][0]['reviewer_reason'].startswith('이미 조문')
    assert seen[2]['image_hashes']==seen[0]['image_hashes']
    assert basic.structure_signature(tree)==basic.structure_signature(expected)
    assert meta['status']=='visual_approved'


def test_persistent_disagreement_is_bounded_and_resume_cannot_reset_rounds(tmp_path,monkeypatch):
    seen=wire(monkeypatch,correction=True,reject_finding=True)
    pdf,blocks=nested_pdf(tmp_path)
    for _ in range(2):
        with pytest.raises(runtime.NeedsReview,match='reviewer_hold'):
            runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='disputed')
    assert len(seen)==6  # 3 VLM + 3 text checks, none added on resume.
    assert all(r['task'] in {'visual_review','body_verification'} for r in seen)
    assert not (tmp_path/'structure-recipes.json').exists()


def test_local_body_budget_never_sends_a_clipped_passage_or_modifies_tree(tmp_path,monkeypatch):
    seen=wire(monkeypatch,correction=True)
    pdf,blocks=nested_pdf(tmp_path)
    blocks[1].text+='x'*13000
    with pytest.raises(runtime.NeedsReview,match='reviewer_hold'):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='oversize')
    assert len(seen)==1 and seen[0]['task']=='visual_review'
    assert not (tmp_path/'structure-recipes.json').exists()


@pytest.mark.parametrize('hints,reason', [(None,'구조가 전혀 바뀌지'), ({'lang':'ko'},'수정 범위 밖')])
def test_scoped_correction_cannot_drop_an_untouched_single_article(tmp_path,hints,reason):
    blocks=[]
    for p in range(6):
        for text in [f'제{p+1}조(시험) 본문', '첫 번째 일반 본문입니다.', '두 번째 일반 본문입니다.']:
            blocks.append(Block(len(blocks),text,page=p+1))
    original=basic.seed(blocks,hints)
    data={'recipe':original,'source_blocks':[{'idx':i,'page':blocks[i].page} for i in range(6,15)]}
    calls=[]
    def call(phase,system,data,schema,vision):
        calls.append(copy.deepcopy(data))
        if phase.endswith('-scope'):return {'start_block':6,'end_block':15}
        return {'parents':{key:'ROOT' for key in schema['properties']['parents']['properties']}}
    journal=runtime.Journal(tmp_path,'scope-preservation')
    with pytest.raises(runtime.NeedsReview,match='소형 응답 검증 실패'):
        basic.correct(pipeline,blocks,data,[{'blocks':[7],'reason':'모의 수정'}],
                      'synthetic',call,journal,set())
    # The authored grammar now keeps the single trailing article even when split;
    # an unchanged proposal is rejected. The explicit legacy path still checks loss.
    assert any(reason in c.get('correction',{}).get('message','') for c in calls)
    assert len(regions.build(pipeline,blocks,original).nodes())==6
    assert len(regions.build(pipeline,blocks,original).tree)==6


@pytest.mark.parametrize('invalid',[
    {},
    {'decisions':[]},
    {'decisions':[{'verdict':'approve','reason':'잘못된 enum'}]},
    {'decisions':[{'verdict':'accept','reason':''}]},
    {'decisions':[{'verdict':'accept','reason':'이유','node':42}]},
    {'decisions':[{'verdict':'accept','reason':'첫째'},{'verdict':'accept','reason':'둘째'}]},
])
def test_body_verifier_repairs_malformed_response_before_accepting(tmp_path,invalid):
    blocks=[Block(0,'제1조(목적) 이 규정의 목적입니다.',page=1)]
    data={'placements':{0:{'heading_block':0,'description':'최상위 표제입니다.'}}}
    answer={'corrections':[{'block':0,'change':'다른 조 아래로 옮기세요.'}]}
    calls=[]
    def call(phase,system,request,schema,vision):
        assert not vision
        calls.append((phase,copy.deepcopy(request)))
        if len(calls)==1:return copy.deepcopy(invalid)
        return {'decisions':[{'verdict':'recheck','reason':'근거가 없어 원본을 다시 확인하세요.'}]}
    feedback=basic.verify_findings(answer,data,blocks,'body-contract',call,runtime.Journal(tmp_path,'schema'))
    assert len(calls)==2 and calls[1][0].endswith('-repair-1')
    assert calls[1][1]['previous_answer']==invalid and calls[1][1]['correction']
    assert len(feedback)==1 and feedback[0]['reviewer_reason']=='근거가 없어 원본을 다시 확인하세요.'


def test_body_verifier_schema_exhaustion_stops_without_approval(tmp_path):
    calls=[]
    def call(phase,system,request,schema,vision):
        calls.append(phase)
        return {'decisions':[]}
    with pytest.raises(runtime.NeedsReview,match='소형 응답 검증 실패') as caught:
        basic.verify_findings({'corrections':[{'block':0,'change':'모의 의견'}]},
            {'placements':{}},[Block(0,'검토할 실제 문장입니다.',page=1)],'body-contract',
            call,runtime.Journal(tmp_path,'schema-exhaustion'))
    assert len(calls)==2 and caught.value.diagnostic['code']=='COMPACT_RESPONSE_INVALID'
    assert all('-body-review' in c for c in calls)
