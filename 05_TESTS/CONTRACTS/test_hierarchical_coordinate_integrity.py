"""Regression cases for parent-qualified headings and immutable legacy trees."""
from copy import deepcopy
from types import SimpleNamespace as S

import pytest

from lawrag.core.structure.viewer import annotate_coordinate_scopes
from semantic_runtime.inherited_navigation import _derive_bindings
from semantic_runtime.legal_agent import structure_selection as ss, structure_query as sq
from semantic_runtime.legal_agent.errors import ContractError


def nodes():
    rows = [
        (0, None, 'kr_편', '제1편'), (1, 0, 'kr_장', '제1장'),
        (2, 1, 'kr_article', '제1조'),
        (3, None, 'kr_편', '제2편'), (4, 3, 'kr_장', '제1장'),
        (5, 4, 'kr_절', '제1절'), (6, 5, 'kr_article', '제434조'),
    ]
    return [dict(id=i, parent=p, family=f, surface=s, title='', block=i,
                 span=[i, i+1]) for i, p, f, s in rows]


def matcher(legacy=True, extra=()):
    rows = nodes() + list(extra)
    annotate_coordinate_scopes(rows, 'law')
    if legacy:
        rows[4]['coordinate_scope'] = 'repeated'
        rows[4]['coordinate_key'] = 'repeated:제2편 > 제1장:4'
    raw = {('d', str(n['id'])): {**n, 'parent': str(n['parent']) if n['parent'] is not None else None,
                                'raw_structure': deepcopy(n)} for n in rows}
    units, coordinates = _derive_bindings(raw)
    return S(units=units, stored_coordinates=coordinates, documents={'d':'모의법'},
             sources={}, _unit_sources=lambda did, uid: [])


def select(n=434, unit='조', path=None):
    return {'coordinate_scope':'body', 'groups':[{'parent_path':path or [], 'unit':unit,
            'include':[{'kind':'SINGLE','value':{'n':n}}], 'exclude':[]}]}


def test_division_identity_uses_ancestors_but_article_identity_stays_global():
    rows=nodes(); annotate_coordinate_scopes(rows, 'law')
    assert all(n['coordinate_scope']=='body' for n in rows)
    assert rows[1]['coordinate_key']=='body:제1편 > 제1장'
    assert rows[4]['coordinate_key']=='body:제2편 > 제1장'
    assert rows[6]['coordinate_key']=='body:제434조'
    rows.append(dict(id=7,parent=3,family='kr_장',surface='제1장',block=7))
    annotate_coordinate_scopes(rows, 'law')
    assert rows[-1]['coordinate_scope']=='repeated'


@pytest.mark.parametrize('legacy', [False, True])
def test_article_lookup_and_explicit_heading_path_cross_restarted_division(legacy):
    m=matcher(legacy); before=deepcopy(m.units)
    assert ss.resolve(select(), m, 'd', ['d'])['unit_ids']==['6']
    path=[{'unit':'편','n':2},{'unit':'장','n':1},{'unit':'절','n':1}]
    record=ss.resolve(select(path=path), m, 'd', ['d'])
    assert record['unit_ids']==['6']; ss.verify(record,m,['d'])
    assert m.units==before


def test_omitted_parent_does_not_guess_repeated_heading_number():
    with pytest.raises(ss.SelectionError) as e:
        ss.resolve(select(n=1,unit='장'),matcher(),'d',['d'])
    assert e.value.code=='AMBIGUOUS_ENDPOINT'


@pytest.mark.parametrize('scope',['annex','addendum','form'])
def test_nonbody_ancestor_still_blocks_body_search(scope):
    m=matcher();m.units[('d','3')]['coordinate_scope']=scope
    with pytest.raises(ss.SelectionError) as e:ss.resolve(select(),m,'d',['d'])
    assert e.value.code=='MISSING_ENDPOINT'


def test_repeated_article_is_blocked_but_ambiguous_heading_does_not_hide_unique_article():
    m=matcher();m.units[('d','6')]['coordinate_scope']='repeated'
    with pytest.raises(ss.SelectionError):ss.resolve(select(),m,'d',['d'])
    m=matcher(); m.units[('d','7')]={**m.units[('d','4')], 'coordinate_scope':'body'}
    m.stored_coordinates[('d','7')]=m.stored_coordinates[('d','4')]
    assert ss.resolve(select(),m,'d',['d'])['unit_ids']==['6']
    with pytest.raises(ss.SelectionError) as e:
        ss.resolve(select(n=1,unit='장',path=[{'unit':'편','n':2}]),m,'d',['d'])
    assert e.value.code=='AMBIGUOUS_ENDPOINT'


def test_legacy_container_metadata_and_acl_remain_bound():
    m=matcher();record=ss.resolve(select(),m,'d',['d'])
    with pytest.raises(ContractError,match='authorization'):ss.verify(record,m,[])
    m.units[('d','4')]['title']='changed'
    with pytest.raises(ContractError,match='metadata'):ss.verify(record,m,['d'])


def test_remote_parent_lookup_does_not_iterate_the_corpus():
    m=matcher(); original=m.units
    class Remote(dict):
        def items(self): raise AssertionError('corpus scan')
        def children_for(self,did,parent):
            return [(k,v) for k,v in original.items() if k[0]==did and v['parent']==parent]
    m.coordinate_index=sq.coordinate_index(m)
    m.units=Remote(original)
    assert ss.resolve(select(),m,'d',['d'])['unit_ids']==['6']


def test_displayed_divisions_are_disambiguated_by_parent():
    m=matcher(False); tree=sq.document_tree(m,'d')
    assert not sq.tree_row(m,'d','4',tree)['ambiguous']


def test_fused_entry_intent_is_displayed_without_hashing_an_object():
    from semantic_runtime.legal_agent.readable_log import render_detail
    envelope={'routing':{'mode':'CASE','reason':'법령 설명'},
              'intent':{'purpose':'상법 제434조 설명','issues':[{'question':'결의 요건'}]},
              'search':{'mode':'STRUCTURE','reason':'명시된 조문 조회'}}
    rendered=render_detail('MODEL RESPONSE / LLM ANSWER',{'reply':envelope,'phase':'request-entry'})
    assert '상법 제434조 설명' in rendered and 'STRUCTURE' in rendered
    assert '결의 요건' in rendered
