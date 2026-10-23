"""Stored reference extents and original acquisition must agree across consumers."""
from copy import deepcopy
import pytest
from conftest import term_glossary
from semantic_runtime.legal_agent import unit_relations as rel, unit_reading as ur, connection_scope as cs
from test_batch_reference_navigation import connected
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.repository import text_hash


@pytest.mark.parametrize('connected', ['① 「모의승인규정」 제1조에 따른 추가 기준을 확인한다.'], indirect=True)
@pytest.mark.parametrize('target_scope', ['full', 'partial'])
def test_article_only_reference_uses_canonical_extent_for_acquisition(connected, target_scope):
    s, _ = connected
    s.profile.setdefault('candidate_navigation', {})['investigation_control'] = True
    reads = {}
    for did in ('d', 'detail'):
        source = next(v for v in s.tools.sources.values() if v['document_id'] == did)
        uid = '2' if did == 'd' and target_scope == 'partial' else '0'
        hit = rel.hit_for(s, source['id'], uid)
        option = next(o for o in ur.offers(s, hit) if o['id'] == 'subtree:' + uid)
        reads[did] = ur.read(s, hit, option, action_state={'count': 0, 'chars': 0})
    anchor = reads['detail']['source_id']
    scope = {'members': [{'source_id': anchor, 'spans': [p for e in reads['detail']['evidence'] for p in e['spans']]}]}
    with cs.bound(s, scope):
        groups, _, _, _ = rel.catalog(s, [anchor], reads, set())
    group = next(g for g in groups if g['target']['document_id'] == 'd')
    connection = group['connections'][0]
    assert connection['endpoint_block_ids'] == ['0', '1', '2', '3']
    assert connection['already_read'] is (target_scope == 'full')
    option = next(r for r in rel.menu(group, 'R1')['read_options'] if r[0] == 'subtree:0')
    assert option[-1] == connection['already_read']


@pytest.mark.parametrize('uid', range(8))
def test_endpoint_extent_uses_stored_tree_at_every_level(monkeypatch, uid):
    from test_selected_connection_scope import fixture
    inv, add = fixture(monkeypatch)
    add('all', 's', 0, range(11))
    endpoint = {'source_id': 's', 'unit_id': str(uid), 'block_ids': []}
    expected = list(map(str, range(*inv.s.matcher.units['d', str(uid)]['span'])))
    assert set(rel.endpoint_blocks(inv.s, endpoint)) == set(expected)
    endpoint['block_ids'] = [expected[-1]]
    assert rel.endpoint_blocks(inv.s, endpoint) == [expected[-1]]


@pytest.mark.parametrize('kind', ['partial', 'split', 'corrupt', 'unauthorized', 'outside'])
def test_acquisition_requires_complete_authorized_codepoint_ranges(monkeypatch, kind):
    from test_selected_connection_scope import fixture
    inv, add = fixture(monkeypatch)
    page = add('a', 's', 6, [6])
    s = inv.s
    s.profile = {'candidate_navigation': {'investigation_control': True}}
    full = page['spans'][0]
    mid = len(full['text']) // 2
    partial = {**full, 'end_cp': mid, 'text': full['text'][:mid]}
    rows = [partial]
    if kind == 'split':rows.append({**full, 'start_cp': mid, 'text': full['text'][mid:]})
    if kind == 'corrupt':rows[0]['span_hash'] = text_hash('잘못된 원문')
    if kind == 'unauthorized':s.scope = []
    if kind == 'outside':rows[0]['block_id'] = 'missing'
    records = {'read': {'source_id': 's', 'evidence': [{'spans': rows}]}}
    if kind in ('corrupt', 'unauthorized', 'outside'):
        with pytest.raises(ContractError):rel.acquired_blocks(s, records)
    else:
        known, _ = rel.acquired_blocks(s, records)
        assert rel.blocks_covered(['6'], known['s']) is (kind == 'split')
        assert not rel.blocks_covered([], known['s'])


@pytest.mark.parametrize('kind', ['missing_unit', 'outside', 'missing_child_extent', 'empty_source', 'unauthorized'])
def test_invalid_endpoint_never_broadens_to_entire_source(monkeypatch, kind):
    from test_selected_connection_scope import fixture
    inv, add = fixture(monkeypatch)
    add('a', 's', 6, [6, 7, 8])
    endpoint = {'source_id': 's', 'unit_id': '6', 'block_ids': []}
    if kind == 'missing_unit':endpoint['unit_id'] = 'absent'
    if kind == 'outside':endpoint['block_ids'] = ['9']
    if kind == 'missing_child_extent':endpoint.update(unit_id=None, target_level='provision')
    if kind == 'empty_source':
        inv.s.tools.sources['s']['blocks'] = []
        endpoint['unit_id'] = None
    if kind == 'unauthorized':inv.s.scope = []
    with pytest.raises(ContractError):rel.endpoint_blocks(inv.s, endpoint)


@pytest.mark.parametrize('connected', ['① 「모의승인규정」 제1조에 따른 추가 기준을 확인한다.'], indirect=True)
def test_reference_resume_does_not_reopen_acquired_article_only_endpoint(connected):
    from test_batch_reference_navigation import decision
    s, _ = connected
    s.profile.setdefault('candidate_navigation', {})['investigation_control'] = True
    origin = next(v for v in s.tools.sources.values() if v['document_id'] == 'detail')
    hit = rel.hit_for(s, origin['id'], '0')
    record = ur.read(s, hit, next(o for o in ur.offers(s, hit) if o['id'] == 'subtree:0'),
                     action_state={'count': 0, 'chars': 0})
    selected = {'origin': record};state = {};read_state = {'count': 0, 'chars': 0};calls = []
    scope = {'members': [{'source_id': origin['id'], 'spans': [p for e in record['evidence'] for p in e['spans']]}]}
    def invoke(system, data, schema, phase, timeout):
        calls.append(data)
        value = decision(data)
        for row in value['decisions']:
            row.update(action='FOLLOW', scopes=['subtree:0'], applicability='APPLIES')
        return value
    with cs.bound(s, scope):
        kwargs = dict(read_state=read_state, seconds_left=lambda: 120, max_context_chars=80000,
                      max_model_batches=1, state=state)
        rel.navigate('추가 기준', s, selected, invoke, **kwargs)
        before = deepcopy(read_state)
        rel.navigate('추가 기준', s, selected, invoke, **kwargs)
        assert len(calls) == 1 and read_state == before
        groups, _, _, _ = rel.catalog(s, [origin['id']], selected, set())
        assert groups and all(c['already_read'] for g in groups for c in g['connections'])
