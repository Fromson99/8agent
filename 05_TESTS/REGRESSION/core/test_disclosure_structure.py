"""Disclosure syntax and source contracts on authored fixtures; no model evaluation."""
import copy
import json
import sqlite3
from pathlib import Path

import pytest

from lawrag.core.structure import pipeline, recipe_basic, recipe_regions, recipe_pages, viewer
from lawrag.core.structure.model import Block
from lawrag.core.structure.proposers import kr_article, writing_guidance
from lawrag.pipeline.genos_admission import preserve_unowned_source, validate_structure
from semantic_runtime.term_references import compile_references


@pytest.mark.parametrize('text,ordinal', [
    ('제2-1-1조(공모개요)', (2, 1, 1)),
    ('제 19 - 3 - 1 조(구조)', (19, 3, 1)),
    ('제2-1-1조의2(특례)', (2, 1, 1, 2)),
    ('제10조의2(특례)', (10, 2)), ('제10조(원칙)', (10,)),
])
def test_complete_article_marker_keeps_source_span(text, ordinal):
    found = kr_article.propose(Block(0, text), None)
    assert len(found) == 1
    assert found[0].ordinal == ordinal and found[0].construction == 'full'
    assert text[found[0].offset:found[0].end] == found[0].surface


@pytest.mark.parametrize('text', ['작성지침에 따른다.', '【 작성지침 】에 따른다.', '본문의 【 작성지침 】', '[작성지침)'])
def test_guidance_mentions_are_not_headings(text):
    assert not writing_guidance.propose(Block(0, text), None)


def test_guidance_source_offsets_and_table_safety():
    text = '  【 작성지침 】  '
    c, = writing_guidance.propose(Block(0, text), None)
    assert text[c.offset:c.end] == c.surface == '【 작성지침 】'
    assert not writing_guidance.propose(Block(0, text, kind='table'), None)
    c, = writing_guidance.propose(Block(0, '앞 문장\n【 작성지침 】'), None)
    assert c.construction == 'fragment'


def test_disclosure_profile_keeps_guidance_with_its_article_or_paragraph():
    texts = ['제1부 통칙', '제1장 통칙', '제1절 일반사항', '제1-1-1조(작성내용)',
             '① 첫 항의 본문', '【 작성지침 】', 'ⅰ. 첫 지침', '모의 병합 표 원문',
             'ⅱ. 둘째 지침', '② 둘째 항의 본문', '【 작성지침 】', 'ⅰ. 둘째 항 지침',
             '제1-1-2조(항 없는 작성내용)', '모의 본문', '【 작성지침 】', 'ⅰ. 조에 붙는 지침']
    blocks = [Block(i, text, page=1 if i < 8 else 2, kind='table' if i == 7 else 'text')
              for i, text in enumerate(texts)]
    before = copy.deepcopy(blocks)
    recipe = recipe_basic.seed(blocks)
    assert recipe['regions'][0]['reason'].startswith('disclosure-v1:')
    result = recipe_regions.build(pipeline, blocks, recipe, draft=True)
    parents = {}
    def walk(nodes, parent=None):
        for n in nodes:
            parents[n.block_idx] = parent
            walk(n.children, n.block_idx)
    walk(result.tree)
    assert {idx: parents[idx] for idx in [0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 14, 15]} == {
        0: None, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 3, 10: 9, 11: 10, 12: 2, 14: 12, 15: 14}
    recipe_pages.audit(blocks, result, [])
    payload = preserve_unowned_source(viewer.payload(result, blocks))
    assert validate_structure('synthetic-disclosure', {'doc_id': 'synthetic-disclosure'}, payload)['accepted']
    assert blocks == before and [b['text'] for b in payload['blocks']] == texts
    explicit = {'partial_order': [['roman_lower', 'circled']]}
    assert recipe_basic.seed(blocks, explicit)['templates']['basic']['hints'] == explicit


def test_inline_compound_citation_does_not_select_disclosure_profile():
    blocks = [Block(0, '제1조(목적)'), Block(1, '본문에서 제2-1-1조를 참조한다.'),
              Block(2, '【 작성지침 】')]
    assert not recipe_basic.seed(blocks)['regions'][0]['reason'].startswith('disclosure-v1:')


def test_compound_reference_resolves_full_coordinate_and_keeps_span():
    with sqlite3.connect(':memory:') as db:
        db.executescript('CREATE TABLE source(id TEXT,json TEXT); CREATE TABLE reference(id TEXT,document_id TEXT,json TEXT); CREATE TABLE reference_end(source_id TEXT,reference_id TEXT);')
        for ident, heading, text in [
            ('a', '제2-1-1조', '제2-1-1조(대상) 모의 원문'),
            ('b', '제2-1-2조', '제2-1-2조(참조) 제 2 - 1 - 1 조를 준용한다.')]:
            source = {'id': ident, 'document_id': 'mock', 'document_name': '모의기준',
                      'heading': heading, 'blocks': [{'block_id': ident, 'text': text}]}
            db.execute('INSERT INTO source VALUES (?,?)', (ident, json.dumps(source)))
        assert compile_references(db) == (1, 0)
        ref = json.loads(db.execute('SELECT json FROM reference').fetchone()[0])
        assert ref['locator'] == '제2-1-1조' and ref['target_source_ids'] == ['a']
        assert ref['source_text'][ref['mention_start']:ref['mention_end']] == '제 2 - 1 - 1 조'


def test_long_document_review_plan_exposes_calls_not_prompt_size():
    assert len(recipe_pages.basic_windows(range(1, 405), 404, 1)) == 404
    assert len(recipe_pages.basic_windows(range(1, 405), 404, 4)) == 101


def test_template_change_invalidates_outer_structure_cache(tmp_path, monkeypatch):
    from lawrag.pipeline.genos_stages import parser_identity, structure_key
    path = tmp_path/'disclosure.json'
    path.write_text(recipe_basic.DISCLOSURE_TEMPLATE.read_text())
    monkeypatch.setattr(recipe_basic, 'DISCLOSURE_TEMPLATE', path)
    monkeypatch.setenv('STRUCTURE_RECIPE_VLM', 'off')
    root = Path(__file__).resolve().parents[3]
    before = parser_identity(root)
    path.write_text(path.read_text()+'\n')
    after = parser_identity(root)
    assert before['structure_resources_sha256'] != after['structure_resources_sha256']
    assert structure_key({'path':'mock.pdf'}, {}, before) != structure_key({'path':'mock.pdf'}, {}, after)
