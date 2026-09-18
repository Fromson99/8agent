"""Structural source intervals must include their original opening block."""
import pytest
from lawrag.core.structure import dp, viewer
from lawrag.core.structure.model import Candidate, Block, StructureResult
from lawrag.pipeline.genos_admission import preserve_unowned_source, validate_structure

@pytest.mark.parametrize('levels',[(2,2),(3,2),(1,2,1)])
def test_markers_within_one_paragraph_keep_nonempty_source_spans(levels):
    candidates=[Candidate(id=str(i),family='synthetic',surface=str(i),block_idx=0,offset=i*5,
                          activated=True,activated_level=level) for i,level in enumerate(levels)]
    candidates.append(Candidate(id='end',family='synthetic',surface='end',block_idx=2,
                                activated=True,activated_level=0))
    blocks=[Block(i,text) for i,text in enumerate(['모의 문단의 여러 경계','이어지는 원문','다음 구역'])]
    result=StructureResult(doc='synthetic');result.candidates=candidates;result.tree=dp.build_tree(candidates,len(blocks))
    nodes=list(result.nodes())
    assert all(lo<=n.block_idx<hi<=len(blocks) for n in nodes for lo,hi in [n.span])
    assert any('same-block boundary' in n.activation_reason for n in nodes)
    payload=preserve_unowned_source(viewer.payload(result,blocks))
    validate_structure('synthetic',{'doc_id':'synthetic'},payload)
    assert [b['text'] for b in payload['blocks']]==[b.text for b in blocks]
    assert any('문자 단위' in w for w in payload['warnings'])

def test_different_paragraph_boundaries_are_unchanged():
    cs=[Candidate(id=str(i),family='synthetic',block_idx=i,activated=True,activated_level=0) for i in [0,2]]
    assert [n.span for n in dp.build_tree(cs,4)]==[(0,2),(2,4)]

def test_out_of_bounds_opener_still_rejected():
    c=Candidate(id='bad',family='synthetic',block_idx=2,activated=True,activated_level=0)
    with pytest.raises(ValueError,match='outside'):dp.build_tree([c],2)
