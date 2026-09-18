"""Contract checks for the explicitly selected, human-authored mock template."""
import copy
import json
from pathlib import Path

from lawrag.core.structure import pipeline, recipe_visual_loop as loop, viewer, recipe_basic as basic
from lawrag.core.structure.model import Block


def test_mock_template_preserves_body_tables_and_independent_end_sections():
    recipe = json.loads((Path(__file__).parents[2]/'FIXTURES/structure/mock_internal_rules_v1.json').read_text())
    blocks = [
        Block(0, '제1조(범위)'),
        Block(1, '일반 본문은 별도 제목이 아니다. 제2조를 인용한다.'),
        Block(2, '제2조(RP)'),
        Block(3, '① 듀레이션은 1.5년 이하, CMA RP는 0.8년 이하로 관리한다.'),
        Block(4, '② 다음 표를 적용한다.'),
        Block(5, '비용 | 1.5%\n연도 | 2026년', kind='table'),
        Block(6, '별첨1(모의 상품 출시 흐름)', is_heading=True, heading_level=1),
        Block(7, '상품 제안 → 승인 → 출시.'),
        Block(8, '부칙'),
        Block(9, '이 모의 준칙은 2026년 9월 1일부터 적용한다.'),
    ]
    original = copy.deepcopy(blocks)
    baseline = pipeline.interpret(copy.deepcopy(blocks), doc='mock-contract', llm=None, ledger=None)
    result = loop.build(pipeline, blocks, recipe, {f:{} for f in recipe['heading_rules']}, loop.inventory(baseline))
    assert blocks == original
    assert [n.block_idx for n in result.tree] == [0,2,6,8]
    assert [n.block_idx for n in result.tree[1].children] == [3,4]
    assert not any(n.family.startswith('dot_number') for n in result.nodes())
    payload = viewer.payload(result, blocks)
    by_id = {n['id']:n for n in payload['nodes']}
    owners = {b['idx']:by_id[b['node']]['block'] for b in payload['blocks'] if b['node'] is not None}
    assert {b:owners[b] for b in [1,5,7,9]} == {1:0,5:4,7:6,9:8}
    assert result.fitness_passed and not result.stats['template_issues']


def test_default_basic_selects_the_authored_fixture():
    fixture = json.loads((Path(__file__).parents[2]/'FIXTURES/structure/mock_internal_rules_v1.json').read_text())
    assert basic.default_template() == fixture
    blocks = [Block(0, '제1조(RP)'), Block(1, '① 듀레이션은 1.5년 이하이다.')]
    recipe = basic.seed(blocks)
    assert recipe['templates']['basic'] == fixture
    result = loop.build(pipeline, blocks, recipe, {}, [])
    assert [(n.family, n.block_idx) for n in result.nodes()] == [('kr_article',0),('circled',1)]


def test_basic_keeps_other_formats_and_explicit_hints():
    blocks = [Block(0, '제1조(범위)'), Block(1, '가. 다른 번호 체계')]
    value = basic.seed(blocks)
    assert basic.is_basic(value['templates']['basic'])
    assert 'outside basic-v1' in value['regions'][0]['reason']
    blocks = [Block(0, '제1조(범위)')]
    hints = {'ladder_hint':[['kr_article']], 'strict_ladder':True}
    assert basic.seed(blocks,hints)['templates']['basic']['hints'] == hints


def test_basic_rule_resource_invalidates_cache_identity(tmp_path, monkeypatch):
    original = basic.resources_identity()
    path = tmp_path/'basic.json'
    value = basic.default_template()
    value['heading_rules']['kr_article']['sequence'] = 'increasing'
    path.write_text(json.dumps(value))
    monkeypatch.setattr(basic, 'DEFAULT_TEMPLATE', path)
    assert basic.resources_identity() != original
