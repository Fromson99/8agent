from lawrag.core.structure.model import Block, Candidate, StructureResult
from lawrag.core.structure import dp, recipe_pages
from lawrag.core.structure.source_lines import split


def test_siblings_no_longer_share_source_interval():
    original = Block(0, '① 첫 항목\n② 둘째 항목\n③ 셋째 항목', bbox=[1, 2, 3, 4], element_index=7)
    blocks = split([original])
    assert len(blocks) == 3
    assert ''.join(b.text for b in blocks) == original.text
    assert all(b.element_index == 7 and b.bbox == original.bbox for b in blocks)
    assert [b.source_range['characters'] for b in blocks] == [[0, 7], [7, 15], [15, 22]]
    nodes = [Candidate(id=str(i), family='circled', surface=b.text[0], block_idx=i,
                       activated=True, activated_level=1) for i, b in enumerate(blocks)]
    result = StructureResult(doc='synthetic', tree=dp.build_tree(nodes, len(blocks)))
    recipe_pages.audit(blocks, result, [])


def test_parent_child_and_next_parent_boundary():
    blocks = split([Block(0, '1. 첫 절\n① 자식\n2. 다음 절\n① 다음 자식')])
    assert len(blocks) == 4
    candidates = [Candidate(id=str(i), family='dot_number' if i % 2 == 0 else 'circled',
                  block_idx=i, activated=True, activated_level=1+i%2)
                  for i in range(4)]
    tree = dp.build_tree(candidates, 4)
    assert tree[0].span == (0, 2) and tree[0].children[0].span == (1, 2)
    recipe_pages.audit(blocks, StructureResult(doc='test', tree=tree), [])


def test_tables_dates_inline_and_plain_lines_not_split():
    for text in ('22.04.01\n24.10.01', '인용 ① 및 ②', '첫 줄\n둘째 줄'):
        assert len(split([Block(0, text)])) == 1
    assert len(split([Block(0, '①\n②', kind='table')])) == 1


def test_dump_keeps_source_char_range():
    blocks = split([Block(0, '① 가\n② 나')])
    assert blocks[1].dump()['source_range']['characters'][0] == 4
