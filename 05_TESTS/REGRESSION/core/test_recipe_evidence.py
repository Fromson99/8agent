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
    old=manifest['tree_sha256'];tree.tree[0].title='changed'
    _,changed=ev.review_images(path,blocks,tree,[1],tmp_path/'changed')
    assert changed['tree_sha256']!=old


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
            check=dict(data);state=check.pop('reviewed_state_id');assert state==loop.digest(check)
            return {'verdict':'approve','issues':[],'reviewed_state_id':state,'template_changes':[]}
    monkeypatch.setattr(runtime,'GenosCalls',FakeCalls)
    original=copy.deepcopy(blocks)
    tree,meta=runtime.revise_pdf(pipeline,blocks,path,store=tmp_path/'store',document='contract')
    assert len(list(tree.nodes()))==20 and blocks==original
    assert meta['status']=='visual_sampled'
    assert any(10 in x.get('page_window',[]) for x in seen)
    count=len(seen);replay,cached=runtime.revise_pdf(pipeline,blocks,path,store=tmp_path/'store',document='contract')
    assert cached['reused'] and cached['model_calls']==0 and len(seen)==count
    assert loop.tree_record(replay)==loop.tree_record(tree)
