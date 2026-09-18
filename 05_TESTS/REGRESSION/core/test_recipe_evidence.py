import base64, copy, hashlib, json
from pathlib import Path
import fitz
import pytest
from lawrag.core.structure import pipeline, recipe_runtime as runtime, recipe_pages, recipe_evidence as ev, recipe_visual_loop as loop, viewer
from lawrag.core.structure.model import Block


def document(tmp_path, count=20):
    path=tmp_path/'source.pdf';blocks=[]
    with fitz.open() as doc:
        for p in range(1,count+1):
            page=doc.new_page();page.insert_text((50,50),f'Heading and source {p}')
            blocks.append(Block(len(blocks),f'제{p}조(제목) 내용입니다.',page=p,bbox=[50,40,400,65],bbox_origin='TOPLEFT'))
        doc.save(path)
    return path, blocks


def test_sampling_has_contiguous_middle_and_end_context(tmp_path):
    path,blocks=document(tmp_path)
    tree=pipeline.interpret(copy.deepcopy(blocks),doc='sample',llm=None,ledger=None)
    with fitz.open(path) as doc:inv=recipe_pages.inventory(doc,blocks)
    plan=ev.sample(inv,blocks,tree,{'kr_article':{}})
    assert {1,10,20} <= set(plan['selected_pages'])
    assert len(plan['selected_pages'])<=12
    for chunk in plan['chunks']:
        ps=chunk['pages'];assert ps==list(range(ps[0],ps[-1]+1))
        assert chunk['block_ids']==[b.idx for b in blocks if b.page in ps]
    assert set(plan['selected_pages']).isdisjoint(plan['not_selected_pages'])


def test_overlay_reuses_viewer_rectangles_and_binds_tree(tmp_path):
    path,blocks=document(tmp_path,2);tree=pipeline.interpret(copy.deepcopy(blocks),doc='overlay',llm=None,ledger=None)
    images,manifest=ev.review_images(path,blocks,tree,[1],tmp_path/'images')
    payload=viewer.payload(tree,blocks,path)
    assert manifest['visible_blocks'][0]['rect']==payload['blocks'][0]['rect']
    assert manifest['visible_blocks'][0]['node']==payload['blocks'][0]['node']
    assert len(images)==2
    assert images[0]!=images[1]
    for image,row in zip(images,manifest['images']):
        assert hashlib.sha256(base64.b64decode(image.split(',',1)[1])).hexdigest()==row['sha256']
    with fitz.open(path) as pdf:
        assert base64.b64decode(images[0].split(',',1)[1]) == pdf[0].get_pixmap(
            matrix=fitz.Matrix(1.5,1.5), alpha=False).tobytes('png')
    old=manifest['tree_sha256'];tree.tree[0].title='changed'
    _,changed=ev.review_images(path,blocks,tree,[1],tmp_path/'changed')
    assert changed['tree_sha256']!=old


def test_overlay_labels_unselected_blocks_for_image_only_feedback(tmp_path,monkeypatch):
    path,blocks=document(tmp_path,1)
    blocks[0].text='A source heading without a recognized marker'
    tree=pipeline.interpret(copy.deepcopy(blocks),doc='missing',llm=None,ledger=None)
    assert not tree.nodes()
    labels=[];insert=fitz.Page.insert_text
    def capture(page,point,text,*args,**kwargs):
        labels.append(text)
        return insert(page,point,text,*args,**kwargs)
    monkeypatch.setattr(fitz.Page,'insert_text',capture)
    images,_=ev.review_images(path,blocks,tree,[1],tmp_path/'images')
    assert 'b0 BODY' in labels and 'owner=none' in labels and images[0]!=images[1]


def test_overlay_owned_body_has_owner_and_labels_do_not_cover_source(tmp_path, monkeypatch):
    path, blocks = document(tmp_path, 1)
    blocks.append(Block(1, '표제가 없는 일반 본문입니다.', page=1,
                        bbox=[50,68,400,90], bbox_origin='TOPLEFT'))
    tree = pipeline.interpret(copy.deepcopy(blocks), doc='owned-body', llm=None, ledger=None)
    labels = []
    insert = fitz.Page.insert_text
    def capture(page, point, text, *args, **kwargs):
        labels.append((point, text, kwargs.get('fontsize', 0)))
        return insert(page, point, text, *args, **kwargs)
    monkeypatch.setattr(fitz.Page, 'insert_text', capture)
    _, manifest = ev.review_images(path, blocks, tree, [1], tmp_path/'images')
    owner = manifest['visible_blocks'][1]['node']
    assert owner is not None
    assert f'in n{owner} L0' in [text for _, text, _ in labels]
    assert 'owner=none' not in [text for _, text, _ in labels]
    offset = manifest['images'][1]['transform']['source_offset_points']
    assert all(point[0] < offset[0] and size >= 8.5 for point, _, size in labels)
    assert ev.block_label({'idx':2, 'opens':[], 'kind':'table', 'node':owner},
                          {owner:{'id':owner, 'level':0}}) == ['b2 TABLE', f'in n{owner} L0']


def test_overlay_blank_page_remains_reviewable(tmp_path):
    path = tmp_path/'blank.pdf'
    with fitz.open() as pdf:
        pdf.new_page()
        pdf.save(path)
    result = pipeline.interpret([], doc='blank', llm=None, ledger=None)
    images, manifest = ev.review_images(path, [], result, [1], tmp_path/'images')
    assert len(images) == 2 and manifest['visible_blocks'] == []
    assert manifest['images'][1]['transform']['source_offset_points'] == [168,38]


def test_end_to_end_bound_images_full_execution_and_zero_call_cache(tmp_path,monkeypatch):
    path,blocks=document(tmp_path)
    monkeypatch.setenv('STRUCTURE_RECIPE_VLM','on');monkeypatch.setenv('STRUCTURE_RECIPE_REVIEW_MODE','adaptive')
    monkeypatch.setenv('STRUCTURE_RECIPE_TAGS',str(tmp_path/'tags.json'))
    seen=[]
    class FakeCalls:
        def __init__(self,journal,images,**kwargs):self.images=images;self.calls=0;self.model='synthetic-no-provider'
        def __call__(self,phase,system,data,schema,vision):
            self.calls+=1;seen.append(data)
            if 'regions' in schema['properties']:
                return {'regions':[{'start_block':0,'template_id':'one','label':'same format','reason':'continuous article numbering'}]}
            if 'families' in schema['properties']:
                return {'families':{k:{'parent_family':'$document','heading_position':'line_start','sequence':'consecutive','reset_scope':'document','rationale':'synthetic contract'} for k in data['catalog']}}
            assert 'visual_evidence' in data
            for image,row in zip(self.images,data['visual_evidence']['images']):
                assert hashlib.sha256(base64.b64decode(image.split(',',1)[1])).hexdigest()==row['sha256']
            assert len(self.images)==2*len(data['page_window'])
            if 'opinions' in schema['properties']:
                return {'opinions':[],'summary':'No visual defects in synthetic source'}
            check=dict(data);state=check.pop('reviewed_state_id')
            assert check.pop('vlm_opinions')==[]
            assert state==loop.digest(check)
            return {'verdict':'approve','issues':[],'reviewed_state_id':state,'template_changes':[],
                    'opinion_decisions':[]}
    monkeypatch.setattr(runtime,'GenosCalls',FakeCalls)
    original=copy.deepcopy(blocks)
    tree,meta=runtime.revise_pdf(pipeline,blocks,path,store=tmp_path/'store',document='contract')
    assert len(list(tree.nodes()))==20 and blocks==original
    assert meta['status']=='visual_sampled'
    assert any(10 in x.get('page_window',[]) for x in seen)
    count=len(seen);replay,cached=runtime.revise_pdf(pipeline,blocks,path,store=tmp_path/'store',document='contract')
    assert cached['reused'] and cached['model_calls']==0 and len(seen)==count
    assert loop.tree_record(replay)==loop.tree_record(tree)
