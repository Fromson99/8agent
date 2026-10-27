"""Connection roots follow the explicit choice, not cumulative acquisition."""
from copy import deepcopy
import pytest
from semantic_runtime.legal_agent import connection_scope as cs, law_candidates as lc
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError
from test_selected_connection_scope import fixture


def setup(monkeypatch):
    inv, add = fixture(monkeypatch)
    inv.bind_reference_delivery = lambda **kw: None
    monkeypatch.setattr(lc, 'token', lambda s, k, v: k + digest(v)[:20])
    original = inv.s.store.source
    inv.s.store.source = lambda d, b: {**original(d, b), 'unit_id': str(b)}
    pages = [add('a', 'article92', 4, list(range(4, 10)), context=[0, 1, 2, 3]),
             add('b', 'article97', 10, [10])]
    return inv, {'sources': pages, 'references': {}}


def test_reading_whole_article_does_not_query_or_present_any_connections(monkeypatch):
    inv, data = setup(monkeypatch)
    def forbidden(*a, **kw):
        pytest.fail('catalog must wait for explicit connection scope selection')
    monkeypatch.setattr(cs, 'preview', forbidden)
    before = deepcopy(inv.p)
    actions = {}
    cs.offer_choices(inv, data, actions)
    assert inv.p == before and data['references']['dependency_cards'] == []
    assert actions and all(a['action'] == 'FOLLOW_CONNECTION' for a in actions.values())
    assert all(c['connection_preview']['status'] == 'NOT_SELECTED' for c in data['connection_scope_choices'])


@pytest.mark.parametrize('uid,expected', [('4', {'4','5','6','7','8','9'}),
    ('5', {'5','6','7','8','9'}), ('6', {'6','7','8'}), ('7', {'7'})])
def test_whole_paragraph_item_and_subitem_can_be_chosen_without_rereading(monkeypatch, uid, expected):
    inv, data = setup(monkeypatch)
    choices = cs.candidates(inv, data)
    chosen = next(s for s, _ in choices if s['structural_selection'].get('unit_id') == uid)
    assert {p['block_id'] for m in chosen['members'] for p in m['spans']} == expected
    original = deepcopy(inv.p['selected'])
    cs.accept(inv, chosen, data, '이 범위의 연결 필요')
    seen = []
    def preview(i, s, *, preparation=None):
        seen.append(s['id'])
        return {'status':'COMPLETE','groups':[], 'connection_count':0, 'absence_proven':False}
    monkeypatch.setattr(cs, 'preview', preview)
    cs.offer_choices(inv, data, {})
    assert seen == [chosen['id']]
    assert inv.p['selected'] == original
    assert data['references']['selected_scope_id'] == chosen['id']


def test_narrow_selection_replaces_whole_article_and_removes_stale_read_handles(monkeypatch):
    inv, data = setup(monkeypatch)
    choices = cs.candidates(inv, data)
    wide = next(s for s,_ in choices if s['structural_selection'].get('unit_id') == '4')
    narrow = next(s for s,_ in choices if s['structural_selection'].get('unit_id') == '6')
    cs.accept(inv, wide, data, '전체 연결')
    cs.accept(inv, narrow, data, '선택한 호의 연결')
    with pytest.raises(ContractError, match='final selected scope'):
        cs.validate_inline_read(inv, {'connection':{'scope_id':wide['id']}}, data, '이전 전체 범위의 읽기')
    seen=[]
    monkeypatch.setattr(cs, 'preview', lambda i,s,*,preparation=None: (seen.append(s['id']) or
        {'status':'COMPLETE','groups':[], 'connection_count':0, 'absence_proven':False}))
    actions = {'stale':{'id':'stale','action':'READ_ARTICLES','label':'old',
        'identity':{'connection':{'scope_id':wide['id']}}}}
    cs.offer_choices(inv, data, actions)
    assert seen == [narrow['id']] and 'stale' not in actions
    assert len(inv.p['connection_scope_history']) == 2


def test_partial_page_never_adds_unseen_siblings_or_context(monkeypatch):
    inv, data = setup(monkeypatch)
    data['sources'][0]['spans'] = [s for s in data['sources'][0]['spans'] if s['block_id'] in {'0','4','5','6','7'}]
    chosen = next(s for s,_ in cs.candidates(inv, data) if s['structural_selection'].get('unit_id') == '6')
    assert {p['block_id'] for m in chosen['members'] for p in m['spans']} == {'6','7'}
    assert chosen['structural_selection']['delivered_only']


def test_subscope_refs_keep_presented_pages_with_additional_metadata(monkeypatch):
    inv, data = setup(monkeypatch)
    for span in data['sources'][0]['spans']:
        span['presentation_metadata'] = 'not part of original span identity'
    _, refs = next((s, refs) for s, refs in cs.candidates(inv, data)
        if s['structural_selection'].get('unit_id') == '6')
    assert refs == [data['sources'][0]['id']]
