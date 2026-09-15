import copy
import pytest
from lawrag.core.parse_adapter import Element
from lawrag.core.structure.model import Block

def elements(label='page_header', second='1. 행정규칙 일반론 009', shift=0):
    return [Element(index=0,type=label,text='1. 행정규칙 일반론 007',page=1,bbox=[300,700,490,690]),
            Element(index=1,type='text',text='제1조(목적) 본문',page=1,bbox=[50,600,490,550]),
            Element(index=2,type=label,text=second,page=3,bbox=[300,700+shift,490,690+shift]),
            Element(index=3,type='text',text='제2조(정의) 본문',page=3,bbox=[50,600,490,550])]

def test_running_furniture_context_preserves_every_original_record():
    source=elements();before=copy.deepcopy(source);blocks=Block.from_elements(source)
    assert source==before and len(blocks)==len(source)
    assert [b.idx for b in blocks]==list(range(4))
    assert [b.text for b in blocks]==[e.text for e in source]
    assert [b.page for b in blocks]==[e.page for e in source]
    assert [b.bbox for b in blocks]==[e.bbox for e in source]
    assert [b.kind for b in blocks]==['furniture','text','furniture','text']
    assert not blocks[0].proposes and blocks[1].proposes

@pytest.mark.parametrize('mode',['body','single','offset','same_counter','no_counter','missing_geometry','middle'])
def test_weak_furniture_evidence_does_not_hide_heading(mode):
    source=elements()
    if mode=='body':source=elements(label='section_header')
    if mode=='single':source=source[:2]
    if mode=='offset':source=elements(shift=30)
    if mode=='same_counter':source=elements(second='1. 행정규칙 일반론 007')
    if mode=='no_counter':source[0].text=source[2].text='1. 행정규칙 일반론'
    if mode=='missing_geometry':source[0].bbox=source[2].bbox=None
    if mode=='middle':
        for p in [1,3]:
            source += [Element(index=len(source),type='text',text='위쪽 본문',page=p,bbox=[20,800,490,790]),Element(index=len(source)+1,type='text',text='아래 본문',page=p,bbox=[20,400,490,390])]
    assert all(b.kind=='text' for b in Block.from_elements(source))

@pytest.mark.parametrize('text',['[별지 1]','[별표 1]','별표 제1호'])
def test_annex_furniture_label_cannot_hide_real_marker(text):
    source=elements();source[0].text=text+' 007';source[2].text=text+' 009'
    assert all(b.kind=='text' for b in Block.from_elements(source))

def test_standalone_page_number_requires_parser_label_and_edge():
    source=elements();source[0].text='007';source[2].text='009'
    blocks=Block.from_elements(source)
    assert blocks[0].kind==blocks[2].kind=='furniture'
    source[0].type=source[2].type='text'
    assert all(b.kind=='text' for b in Block.from_elements(source))
