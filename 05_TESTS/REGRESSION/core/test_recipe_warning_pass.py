"""Mechanical admission and bounded review contracts; no real model/network calls."""
import copy
import json
import sqlite3
from pathlib import Path

import pytest

from lawrag.core import ingest, parse_adapter
from lawrag.core.structure import pipeline, recipe_runtime as runtime, recipe_basic, recipe_pages, viewer
from lawrag.core.structure.model import Block
from lawrag.pipeline import genos_admission as admission, genos_build as build, genos_stages as stages
from .test_recipe_runtime import isolated_env, install_transport, response, regional_document


def transport(monkeypatch, verdict='approve', finish='stop', malformed=False):
    monkeypatch.setenv('STRUCTURE_RECIPE_PROTOCOL','basic')
    monkeypatch.setenv('STRUCTURE_RECIPE_ACCEPT_WARNINGS','on')
    monkeypatch.delenv('STRUCTURE_RECIPE_MAX_PAGES',raising=False)
    seen=[]
    def http(session,url,payload):
        seen.append(payload)
        value = ({'unexpected':'schema mismatch'} if malformed else
                 {'verdict':verdict,'corrections':[],'summary':'Synthetic review only'})
        body=response(value,finish)
        body['choices'][0]['message']['content']=json.dumps(value)
        return body
    install_transport(monkeypatch,http)
    return seen


@pytest.mark.parametrize('verdict,finish,malformed',[
    ('hold','stop',False),('missing_rules','stop',False),('source_error','stop',False),
    ('approve','length',False),('approve','stop',True)])
def test_inconclusive_review_saves_warning_without_approval_or_splits(tmp_path,monkeypatch,verdict,finish,malformed):
    monkeypatch.setenv('STRUCTURE_RECIPE_REVIEW_MAX_TOKENS','1024')
    seen=transport(monkeypatch,verdict,finish,malformed)
    pdf,blocks=regional_document(tmp_path,3);before=copy.deepcopy(blocks)
    result,review=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='warning')
    assert review['status']=='accepted_with_warnings' and review['model_calls']==len(seen)==3
    assert blocks==before and len(result.tree)==3
    coverage=review['coverage']
    assert coverage['windows']==[[1],[2],[3]] and not coverage['visually_reviewed_pages']
    expected = 'COMPACT_RESPONSE_INVALID' if malformed else 'OUTPUT_LENGTH_LIMIT' if finish=='length' else verdict
    assert {w['code'] for w in coverage['review_warnings']}=={expected}
    assert len(coverage['review_warnings'])==3 and all(not w['approved'] for w in coverage['review_warnings'])
    assert all(req['max_tokens']==1024 for req in seen)
    for req in seen:
        content=req['messages'][1]['content']
        assert len([c for c in content if c['type']=='image_url'])==2
        assert set(json.loads(next(c['text'] for c in content if c['type']=='text')))=={'available_patterns'}
    payload=viewer.payload(result,blocks,pdf);payload['recipe_review']=review
    assert admission.validate_structure('warning',{'doc_id':'warning','recipe_review':review},payload)['accepted']
    _,resumed=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='warning')
    assert resumed['status']=='accepted_with_warnings' and not resumed['reused']
    assert len(seen)==3  # checkpoint reuse is recorded as warnings, never visual approval


def test_call_budget_bounds_long_document_without_discarding_it(tmp_path,monkeypatch):
    seen=transport(monkeypatch)
    monkeypatch.setenv('STRUCTURE_RECIPE_MAX_CALLS','2')
    pdf,blocks=regional_document(tmp_path,5)
    tree,review=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='budget')
    assert len(seen)==review['model_calls']==2 and len(tree.tree)==5
    assert review['status']=='accepted_with_warnings'
    assert review['coverage']['visually_reviewed_pages']==[1,2]
    warnings=review['coverage']['review_warnings']
    assert len(warnings)==1 and warnings[0]['pages']==[3,4,5]
    assert warnings[0]['details']['calls']==2
    budget=review['coverage']['call_budget']
    assert budget['fresh_pass_min_calls']==5 and budget['minimum_exceeds_limit']
    events=[json.loads(line) for line in (tmp_path/'structure-recipe-runs'/review['run_id']/'events.jsonl').read_text().splitlines()]
    assert sum(e['event']=='recipe.review.budget_exhausted' for e in events)==1
    assert not [e for e in events if e['event']=='recipe.review.start' and e['window_number']>3]
    _,resumed=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='budget')
    assert len(seen)==2 and resumed['status']=='accepted_with_warnings'
    assert resumed['coverage']['visually_reviewed_pages']==[1,2]
    assert resumed['coverage']['review_warnings'][0]['pages']==[3,4,5]


def test_explicit_basic_batch_width_is_honored_without_overlaps(tmp_path,monkeypatch):
    seen=transport(monkeypatch)
    monkeypatch.setenv('STRUCTURE_RECIPE_MAX_PAGES','6')
    pdf,blocks=regional_document(tmp_path,10)
    _,review=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='width')
    assert review['coverage']['windows']==[list(range(1,7)),list(range(7,11))]
    assert len(seen)==2 and review['status']=='visual_approved'


def test_unreadable_source_is_not_quality_warning(tmp_path,monkeypatch):
    seen=transport(monkeypatch)
    pdf,blocks=regional_document(tmp_path)
    with pytest.raises(runtime.NeedsReview,match='source_blocks_missing_ocr_required'):
        runtime.revise_pdf(pipeline,blocks[:1],pdf,store=tmp_path/'store',document='missing')
    assert not seen


def test_frontmatter_is_preserved_without_inventing_a_heading():
    original={'nodes':[{'id':0,'parent':None,'block':2,'span':[2,4]}],
              'blocks':[{'idx':i,'text':s,'node':None if i<2 else 0} for i,s in enumerate(
                  ['모의 규정','제정 2026. 1. 1.','제1조','본문'])]}
    before=copy.deepcopy(original)
    with pytest.raises(ValueError,match='어느 구조 마디'):
        admission.validate_structure('x',{'doc_id':'x'},original)
    preserved=admission.preserve_unowned_source(original)
    assert original==before
    assert [b['text'] for b in preserved['blocks']]==[b['text'] for b in original['blocks']]
    assert preserved['nodes'][0]==original['nodes'][0]
    assert preserved['nodes'][1]['inferred_heading'] is False
    assert preserved['nodes'][1]['span']==[0,2]
    assert admission.preserve_unowned_source(preserved)==preserved
    assert admission.validate_structure('x',{'doc_id':'x','passed':False,'score':0},preserved)['accepted']
    preserved['nodes'][0]['parent']=99
    with pytest.raises(ValueError,match='parent'):
        admission.validate_structure('x',{'doc_id':'x'},admission.preserve_unowned_source(preserved))


def test_plain_text_without_detectable_headings_can_be_saved():
    source={'nodes':[],'blocks':[{'idx':0,'text':'번호 없는 원문','node':None}]}
    result=admission.preserve_unowned_source(source)
    assert admission.validate_structure('x',{'doc_id':'x'},result)['accepted']
    result['blocks'][0]['text']=''
    with pytest.raises(ValueError,match='읽을 수 있는'):
        admission.validate_structure('x',{'doc_id':'x'},result)


def test_default_internal_profile_does_not_disable_authored_basic():
    from lawrag.core.internal_rules import PROFILE
    blocks=[Block(0,'제1조(목적)'),Block(1,'① 모의 본문')]
    assert recipe_basic.seed(blocks,PROFILE)['templates']['basic']==recipe_basic.default_template()
    blocks.append(Block(2,'가. 다른 번호'))
    assert recipe_basic.seed(blocks,PROFILE)['templates']['basic']['hints']==PROFILE


def test_actual_stage_stores_unowned_prefix_and_warning_in_source_sqlite(tmp_path,monkeypatch):
    seen=transport(monkeypatch,'hold')
    pdf,blocks=regional_document(tmp_path)
    blocks.insert(0,Block(0,'모의 규정 제목',page=1,bbox=[50,10,400,30],bbox_origin='TOPLEFT'))
    for idx,b in enumerate(blocks):b.idx=idx
    parsed=parse_adapter.ParseResult(str(pdf),'synthetic','synthetic',True,elements=[
        parse_adapter.Element(b.idx,'text',b.text,page=b.page,bbox=b.bbox,bbox_origin=b.bbox_origin) for b in blocks])
    monkeypatch.setattr(ingest,'parse_cached',lambda *a:parsed)
    row={'path':str(pdf),'sha256':build.sha(pdf),'document_id':build.sha(pdf)[:16],
         'name':'모의 규정','relative':'internal/source.pdf','source':'internal','folder':'내규',
         'doc_type':'','engine':'','kind':'internal'}
    plan={'files':[row],'format_assets':{}}
    folder,work=stages.structure(row,plan,tmp_path/'data',{'synthetic':'contract'},30,lambda s:None)
    stages.verify_structure(folder)
    stored=json.loads((folder/'structure'/row['document_id']/'result.json').read_text())
    meta=json.loads((folder/'structure'/row['document_id']/'meta.json').read_text())
    assert stored['source_preservation']['text_changed'] is False
    assert stored['recipe_review']['status']=='accepted_with_warnings'
    assert meta['structure_admission']['accepted'] and meta['structure_admission']['warnings']
    with sqlite3.connect(folder/'source.sqlite') as db:
        rows=db.execute('SELECT text,unit_id FROM source_block ORDER BY CAST(block_id AS INTEGER)').fetchall()
        assert [r[0] for r in rows]==[b.text for b in blocks]
        assert all(r[1] is not None for r in rows)
    assert len(seen)==2
    assert stages.structure(row,plan,tmp_path/'data',{'synthetic':'contract'},30,lambda s:None)[0]==folder
    assert len(seen)==2

    # Exercise the actual stage admission/reporting consumer, too.
    from types import SimpleNamespace
    monkeypatch.setenv('GENOS_PDF_PARSER','local')
    progress=SimpleNamespace(document=lambda *a:None,emit=lambda *a:None,
                             finish=lambda *a:None,error=lambda exc:pytest.fail(str(exc)))
    report=stages.execute(plan,SimpleNamespace(timeout=30),tmp_path/'data','warning-run','structure',
                         progress=progress,dependencies={'synthetic':'contract'})
    assert report['ok'] and report['passed']==1
    assert report['documents'][row['document_id']]['structure']=='PASSED'
    assert report['documents'][row['document_id']]['structure_warnings']
    assert len(seen)==2


def test_numbering_quality_issue_is_recorded_without_discarding_source(tmp_path,monkeypatch):
    transport(monkeypatch)
    pdf,blocks=regional_document(tmp_path,3)
    blocks[-1].text='제5조(누락 번호가 있는 모의 원문) 본문'
    before=copy.deepcopy(blocks)
    tree,review=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='sequence')
    assert blocks==before and len(tree.tree)==3
    assert review['status']=='accepted_with_warnings'
    assert any(w['code']=='structure_quality' for w in review['coverage']['review_warnings'])


def test_merged_buchik_passes_with_explicit_boundary_warning(tmp_path,monkeypatch):
    transport(monkeypatch)
    pdf,blocks=regional_document(tmp_path,2)
    blocks[1].text='제2조(본문) 기존 원문\n부칙'
    original=copy.deepcopy(blocks)
    result,review=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='mixed-buchik')
    assert blocks==original and len(result.tree)==2
    assert review['status']=='accepted_with_warnings'
    assert any(w['code']=='supplementary_heading_shares_source_block'
               for w in review['coverage']['review_warnings'])
