"""Synthetic whole-document contracts; no live model or quality comparison."""
import copy
import json
import fitz
import pytest
from lawrag.core.structure import pipeline, recipe_pages as pages, recipe_runtime as runtime
from lawrag.core.structure.model import Block
from semantic_runtime import genos
from .test_recipe_runtime import isolated_env, response


def document(tmp_path, count=20):
    pdf=tmp_path/'long.pdf';blocks=[]
    with fitz.open() as doc:
        for p in range(1,count+1):
            page=doc.new_page();page.insert_text((50,50),f'Article {p} source content')
            blocks += [Block(len(blocks),f'제{p}조(제목) 본문 내용이다.',page=p),
                       Block(len(blocks)+1,'본문 문장을 이어서 설명한다.',page=p)]
        doc.save(pdf)
    return pdf,blocks


def provider(monkeypatch, *, bad=False, revise=False):
    seen=[];revised=False
    def request(target,path,payload):
        nonlocal revised
        data=json.loads(payload['messages'][1]['content'][0]['text']);seen.append(data)
        image_count=len(payload['messages'][1]['content'])-1
        assert image_count==len(data['page_window'])*(2 if data.get('visual_evidence') else 1)
        if 'outline' in data:
            return response({'regions':[{'start_block':0,'template_id':'body','label':'body','reason':'synthetic source'}]})
        if 'region_instances' in data:
            return response({'families':{f:{'parent_family':('$document' if f!='kr_article' or 'kr_장' not in data['catalog'] or revise=='hierarchy' else 'kr_장'),'heading_position':'line_start','sequence':'increasing','reset_scope':'document','rationale':'synthetic source'} for f in data['catalog']}})
        if bad:
            return response({'verdict':'missing_rules','reviewed_state_id':data['reviewed_state_id'],'issues':[{'blocks':[99999],'reason':'unseen'}],'template_changes':[]})
        if revise and (not revised or revise is True):
            revised=True;changes=[]
            if revise=='hierarchy':
                rule=dict(data['recipe']['templates']['body']['heading_rules']['kr_article']);rule['parent_family']='kr_장'
                changes=[{'template_id':'body','family':'kr_article','rule':rule}]
            return response({'verdict':'revise','reviewed_state_id':data['reviewed_state_id'],'template_changes':changes,'issues':[]})
        return response({'verdict':'approve','reviewed_state_id':data['reviewed_state_id'],'issues':[],'template_changes':[]})
    monkeypatch.setattr(genos,'request_json',request)
    return seen


def test_long_pdf_sampling_full_source_and_cache(tmp_path,monkeypatch):
    pdf,blocks=document(tmp_path);seen=provider(monkeypatch)
    original=copy.deepcopy(blocks)
    result,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='long.pdf')
    assert blocks==original
    assert len(list(result.nodes()))==20
    assert meta['status']=='visual_sampled'
    coverage=meta['coverage']
    assert coverage['code_checked_pages']==list(range(1,21))
    assert set(coverage['visually_reviewed_pages'])=={1,2,19,20}
    assert len(coverage['not_visually_reviewed_pages'])==16
    assert all(len(x['page_window'])<=6 for x in seen if 'recipe' in x)
    assert any(10 in x['page_window'] for x in seen if 'outline' in x)
    assert max(b['idx'] for x in seen for b in x['source_blocks'])==39
    count=len(seen)
    _,cached=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='long.pdf')
    assert cached['reused'] and cached['coverage']==coverage and len(seen)==count
    tags=tmp_path/'structure-recipes.json';value=json.loads(tags.read_text())
    value['documents']['long.pdf']['coverage']['visual_scope']='full';runtime.atomic(tags,value)
    with pytest.raises(runtime.NeedsReview):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='long.pdf')
    assert len(seen)==count


def test_table_and_sequence_anomalies_are_reviewed_with_neighbours(tmp_path,monkeypatch):
    pdf,blocks=document(tmp_path);seen=provider(monkeypatch)
    blocks[19].kind='table';blocks[19].text='열 제목 | 값'
    blocks[24].text='제99조(이상 번호) 본문'
    with pytest.raises(runtime.NeedsReview):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='table.pdf')
    reviews=[d for d in seen if 'recipe' in d]
    assert any({9,10,11}<=set(d['page_window']) for d in reviews)
    assert any(d.get('hard_code_issues') for d in reviews)
    assert not (tmp_path/'structure-recipes.json').exists()


def test_source_ancestry_crosses_page_windows(tmp_path):
    pdf,blocks=document(tmp_path)
    blocks.insert(0,Block(0,'제1장 총칙',page=1))
    for i,b in enumerate(blocks):b.idx=i
    tree=pipeline.interpret(copy.deepcopy(blocks),doc='x',llm=None,ledger=None,
        ladder_hint=[['kr_장'],['kr_article']],partial_order=[('kr_장','kr_article')])
    ctx=pages.context(blocks,{},[10,11],tree)
    assert ctx['actual_structure']['nodes'][0]['block']==0
    assert ctx['actual_structure']['nodes'][0]['context_only']
    assert all(b['page'] in {10,11} for b in ctx['source_blocks'])
    assert any(n['parent_block']==0 for n in ctx['actual_structure']['nodes'][1:])


def test_repair_rebuilds_and_rechecks_before_publish(tmp_path,monkeypatch):
    pdf,blocks=document(tmp_path)
    blocks.insert(0,Block(0,'제1장 총칙',page=1))
    for i,b in enumerate(blocks):b.idx=i
    seen=provider(monkeypatch,revise='hierarchy')
    _,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='revise.pdf')
    reviews=[r for r in seen if 'recipe' in r]
    assert reviews[0]['recipe']['templates']['body']['parent_map']['kr_article']=='$document'
    assert reviews[1]['page_window']==reviews[0]['page_window']
    assert all(r['recipe']['templates']['body']['parent_map']['kr_article']=='kr_장' for r in reviews[1:])
    assert meta['coverage']['visual_scope']=='sampled'


@pytest.mark.parametrize('failure',['unseen','budget','ocr'])
def test_failed_windows_never_publish(tmp_path,monkeypatch,failure):
    pdf,blocks=document(tmp_path);seen=provider(monkeypatch,bad=failure=='unseen')
    if failure=='budget':monkeypatch.setenv('STRUCTURE_RECIPE_MAX_CALLS','1')
    if failure=='ocr':
        blocks=[b for b in blocks if b.page!=8]
        for i,b in enumerate(blocks):b.idx=i
    with pytest.raises(runtime.NeedsReview):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='failed.pdf')
    assert not (tmp_path/'structure-recipes.json').exists()
    if failure=='ocr':assert not seen


def test_overlapping_or_detached_spans_rejected(tmp_path):
    pdf,blocks=document(tmp_path)
    tree=pipeline.interpret(copy.deepcopy(blocks),doc='x',llm=None,ledger=None)
    tree.tree[0].span=(0,len(blocks))
    with fitz.open(pdf) as doc:inventory=pages.inventory(doc,blocks)
    with pytest.raises(ValueError,match='overlapping'):
        pages.audit(blocks,tree,inventory)


def test_mixed_scanned_page_enables_ocr(tmp_path):
    from lawrag.core.parse_adapter import is_born_digital
    pdf=tmp_path/'mixed.pdf'
    with fitz.open() as doc:
        p=doc.new_page()
        for y in range(40,400,20):p.insert_text((30,y),'Digitally encoded source text on this page.')
        p=doc.new_page()
        pix=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,20,20),False);pix.clear_with(255)
        p.insert_image(fitz.Rect(20,20,400,600),pixmap=pix)
        doc.save(pdf)
    born,stats=is_born_digital(pdf)
    assert not born and stats['scan_candidate_pages']==[2]




def test_version_only_revision_never_publishes_same_unfixed_tree(tmp_path,monkeypatch):
    pdf,blocks=document(tmp_path);seen=provider(monkeypatch,revise=True)
    with pytest.raises(runtime.NeedsReview):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='noop.pdf')
    assert any('validation_feedback' in row and 'invalid_review' in row for row in seen)
    assert not (tmp_path/'structure-recipes.json').exists()

def test_full_review_uses_all_pages_with_bounded_bbox_windows(tmp_path,monkeypatch):
    pdf,blocks=document(tmp_path);seen=provider(monkeypatch)
    monkeypatch.setenv('STRUCTURE_RECIPE_REVIEW_MODE','full')
    _,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='full')
    assert meta['status']=='visual_approved'
    assert meta['coverage']['visually_reviewed_pages']==list(range(1,21))
    assert not meta['coverage']['not_visually_reviewed_pages']
    assert all(len(d['page_window'])<=6 for d in seen if 'recipe' in d)
