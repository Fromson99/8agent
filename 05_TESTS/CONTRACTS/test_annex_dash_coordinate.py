"""Lossless annex identities at parser, stored lookup and source-goal boundaries."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest

from lawrag.core.legal_coordinate import LegalCoordinate, find_coordinates, parse_label
from lawrag.core.rag import refs
from lawrag.core.structure.viewer import annotate_coordinate_scopes
from semantic_runtime.inherited_navigation import _derive_bindings
from semantic_runtime.legal_agent import source_goal_control as goals, structure_query as sq
from semantic_runtime.legal_agent.output_contract import OutputContractError


@pytest.mark.parametrize('text,unit,n,dash',[
    ('별표 17-1','별표',17,1),('별표17-2','별표',17,2),
    ('별표 제17 - 1호','별표',17,1),('별지 제3-12호','별지',3,12),
    ('별표 7-23','별표',7,23),('별표 17','별표',17,None),
    ('별지 제2호','별지',2,None),
])
def test_label_reference_and_source_target_preserve_full_number(text,unit,n,dash):
    expected=LegalCoordinate(unit,n,dash=dash)
    question='위치는 '+text+'에 따른다.'
    occurrence=find_coordinates(question)[0]
    assert question[occurrence.start:occurrence.end]==text
    assert occurrence.coordinate==parse_label(text+'(기준)')==expected
    assert refs.find(question)[0].key()==refs.label_key(text)==expected.key()
    assert find_coordinates(expected.canonical_surface())[0].coordinate==expected
    row={'coordinate':text,'coordinate_scope':'annex' if unit=='별표' else 'form'}
    before=deepcopy(row)
    assert goals.target_coordinate(row)==expected.canonical_surface()
    assert goals.target_coordinate({**row,'coordinate':row['coordinate_scope']+':'+text})==expected.canonical_surface()
    assert row==before


def test_base_siblings_and_forms_have_distinct_keys():
    texts=['별표 17','별표 17-1','별표 17-2','별지 17-1']
    assert len({parse_label(t).key() for t in texts})==4
    assert refs.label_key('별표 17-1')==('별표',17,('dash',1,None))


@pytest.mark.parametrize('text',[
    '별표 17-','별표 17-1-2','별표 17-1 추가내용',
    '별표 17-1, 별표 17-2','별표 17-1부터 별표 17-2',
])
def test_incomplete_multiple_and_noncoordinate_targets_remain_rejected(text):
    with pytest.raises(OutputContractError) as error:
        goals.target_coordinate({'coordinate':text,'coordinate_scope':'annex'})
    assert error.value.issues[0]['code']=='SOURCE_TARGET_COORDINATE_INVALID'


def matcher():
    nodes=[dict(id=i,parent=None,family='annex',surface=t,title='기준',block=i,span=[i,i+1])
           for i,t in enumerate(['별표 17','별표 17-1','별표 17-2'])]
    annotate_coordinate_scopes(nodes,'law')
    raw={('d',str(n['id'])):{**n,'raw_structure':deepcopy(n)} for n in nodes}
    before=deepcopy(raw)
    units,coordinates=_derive_bindings(raw)
    assert raw==before
    return S(units=units,stored_coordinates=coordinates,documents={'d':'모의규정'},
             sources={},_unit_sources=lambda did,uid:[])


@pytest.mark.parametrize('text,uid',[('별표 17','0'),('별표 17-1','1'),('별표 17-2','2')])
def test_exact_catalogue_and_source_goal_match_only_selected_annex(text,uid):
    m=matcher();before=deepcopy(m.units)
    target=goals.target_coordinate({'coordinate':text,'coordinate_scope':'annex'})
    page=sq.catalogue(m,['d'],document_id='d',structure_filter={'coordinate':target,'coordinate_scope':'annex'})
    assert [r['unit_id'] for r in page['items']]==[uid]
    inv=S(s=S(matcher=m))
    goal={'document_id':'d','coordinate':target,'coordinate_scope':'annex'}
    for other in ['0','1','2']:
        assert goals.matches(inv,{'document_id':'d','unit_id':other},goal)==(other==uid)
    assert not goals.matches(inv,{'document_id':'other','unit_id':uid},goal)
    assert not goals.matches(inv,{'document_id':'d','unit_id':uid},{**goal,'coordinate_scope':'body'})
    with pytest.raises(ValueError,match='scope'):
        sq.catalogue(m,[],document_id='d',structure_filter={'coordinate':target,'coordinate_scope':'annex'})
    assert m.units==before


def test_missing_suffix_never_falls_back_to_base_or_sibling():
    m=matcher()
    page=sq.catalogue(m,['d'],document_id='d',structure_filter={'coordinate':'별표 17-3','coordinate_scope':'annex'})
    assert page['items']==[] and page['failure']['code']=='MISSING_COORDINATE'
