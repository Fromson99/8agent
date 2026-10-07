from copy import deepcopy
import json
import pytest
from fixtures import KEY, RAW, CUT, bundle, capabilities, lift_parent, load, node, setup


@pytest.fixture(scope='module')
def m():
    return load()


def recommend(m, p=None, *, origin='fulltext', kind='source_located', caps=None):
    p = p or setup(m)
    memory = m.Memory(bundle(m), p, {KEY})
    event = m.observation(p, kind, ['entry-current'], origin_tool=origin)
    return memory, memory.observe(event, caps if caps is not None else capabilities())


@pytest.mark.parametrize('origin', ['fulltext', 'vector_knn', 'explicit_reference', 'document_structure'])
def test_tool_origin_is_metadata_not_trigger_identity(m, origin):
    _, result = recommend(m, origin=origin)
    assert len(result['items']) == 1
    assert result['items'][0]['concept_id'] == 'concept:scope-check'


@pytest.mark.parametrize('kind', ['source_located', 'evidence_acquired', 'relation_followed'])
def test_observation_adapter_supports_location_read_and_relation(m, kind):
    _, result = recommend(m, kind=kind)
    assert result['items'][0]['node_ids'] == ['target-current']


def test_two_agent_tool_adapters_consume_identical_data(m):
    p = setup(m); data = bundle(m); before = json.dumps(data, sort_keys=True)
    result = m.Memory(data, p, {KEY}).observe(m.observation(p, 'source_located', ['entry-current']), capabilities())
    item = result['items'][0]
    a = m.compile_actions(item, p, capabilities('read'), {KEY})
    b = m.compile_actions(item, p, capabilities('fetch_fragment'), {KEY})
    assert a[0]['tool'] == 'read' and b[0]['tool'] == 'fetch_fragment'
    assert a[0]['args']['target'] == b[0]['arguments']['fragment_key'] == 'U-target-new'
    assert json.dumps(data, sort_keys=True) == before


def test_changed_generation_renamed_and_reordered_nodes(m):
    p = setup(m, projection_id='other-agent-generation-999')
    p.nodes = dict(reversed(list(p.nodes.items())))
    _, result = recommend(m, p)
    assert result['items'][0]['projection_id'] == p.id
    assert m.compile_actions(result['items'][0], p, capabilities(), {KEY})[0]['args']['target'] == 'U-target-new'


def test_merged_nodes_reconnect_but_located_is_not_read(m):
    p = setup(m, layout='merged'); memory = m.Memory(bundle(m), p, {KEY})
    located = memory.observe(m.observation(p, 'source_located', ['merged-current']), capabilities())
    assert located['items'][0]['node_ids'] == ['merged-current']
    acquired = memory.observe(m.observation(p, 'evidence_acquired', ['merged-current']), capabilities())
    assert acquired['items'] == []


def test_split_nodes_compile_multiple_current_reads(m):
    p = setup(m, layout='split'); _, result = recommend(m, p)
    assert result['items'][0]['node_ids'] == ['part-1', 'part-2']
    assert [a['args']['target'] for a in m.compile_actions(result['items'][0], p, capabilities(), {KEY})] == ['P-new-1', 'P-new-2']


def test_split_anchor_requires_complete_observed_coverage(m):
    p = setup(m); mid = CUT//2
    p = m.Projection('split-entry', p.documents, {'a': node(m, RAW, 0, mid, 'a'),
        'b': node(m, RAW, mid, CUT, 'b'), 't': node(m, RAW, CUT, len(RAW), 't')})
    memory = m.Memory(bundle(m), p, {KEY})
    assert not memory.observe(m.observation(p, 'source_located', ['a']), capabilities())['items']
    assert memory.observe(m.observation(p, 'source_located', ['a','b']), capabilities())['items']


def test_changed_source_requires_revalidation(m):
    _, result = recommend(m, setup(m, raw=RAW+' 개정 내용'))
    assert result['items'] == [] and 'SOURCE_VERSION_CHANGED' in result['fallback_reasons']


def test_denied_scope_does_not_expose_concept(m):
    p = setup(m); memory = m.Memory(bundle(m), p, set())
    result = memory.observe(m.observation(p, 'source_located', ['entry-current']), capabilities())
    assert result == {'items': [], 'fallback_reasons': ['DENIED_SCOPE']}


def test_overlapping_targets_are_ambiguous(m):
    p = setup(m); nodes = deepcopy(p.nodes); nodes['duplicate-target'] = nodes['target-current']
    p = m.Projection('ambiguous', p.documents, nodes); _, result = recommend(m, p)
    assert result['items'] == [] and 'AMBIGUOUS_MAPPING' in result['fallback_reasons']


def test_missing_target_coverage_returns_fallback(m):
    _, result = recommend(m, setup(m, include_target=False))
    assert result['items'] == [] and 'MISSING_COVERAGE' in result['fallback_reasons']


def test_stale_observation_and_compiled_action_rejected(m):
    p = setup(m); memory, result = recommend(m, p)
    event = m.observation(p, 'source_located', ['entry-current']); event['projection_id'] = 'old'
    assert memory.observe(event, capabilities())['items'] == []
    with pytest.raises(ValueError, match='stale action'):
        m.compile_actions(result['items'][0], setup(m, projection_id='new'), capabilities(), {KEY})


def test_missing_capability_does_not_substitute_fulltext(m):
    _, result = recommend(m, caps={})
    assert result == {'items': [], 'fallback_reasons': ['MISSING_CAPABILITY']}


def test_exit_is_request_local_and_never_modifies_memory(m):
    p = setup(m); memory, result = recommend(m, p); data = deepcopy(memory.bundle)
    memory.reject(result['items'][0]['concept_id'])
    event = m.observation(p, 'source_located', ['entry-current'])
    assert memory.observe(event, capabilities())['items'] == []
    assert memory.bundle == data
    assert m.Memory(data, p, {KEY}).observe(event, capabilities())['items']
    with pytest.raises(ValueError):
        memory.reject('unoffered')


def test_origin_span_tamper_rejected(m):
    p = setup(m); nodes = deepcopy(p.nodes)
    nodes['target-current']['origin_spans'][0]['text'] = '틀린 원문'
    with pytest.raises(ValueError, match='exact origin'):
        m.Projection('bad-map', p.documents, nodes)


def test_bundle_tamper_and_runtime_fields_rejected(m):
    data = bundle(m); data['concepts'][0]['objective'] = '변조'
    with pytest.raises(ValueError, match='hash/version'):
        m.Memory(data, setup(m), {KEY})
    data = bundle(m); data['concepts'][0]['generation_id'] = 'leaked'
    data['sha256'] = m.digest({k:v for k,v in data.items() if k != 'sha256'})
    with pytest.raises(ValueError, match='runtime-specific'):
        m.validate(data)


def test_current_action_cannot_be_redirected_to_other_valid_node(m):
    p = setup(m); _, result = recommend(m, p); item = result['items'][0]
    item['node_ids'] = ['entry-current']
    with pytest.raises(ValueError, match='origin anchor'):
        m.compile_actions(item, p, capabilities(), {KEY})


def test_legacy_concepts_lift_without_old_source_tool_or_generation_ids(m):
    data, p = lift_parent(m)
    assert len(data['concepts']) == 4 and data['provenance']['episode_count'] == 10
    serial = json.dumps(data['concepts'], ensure_ascii=False)
    assert all(term not in serial for term in ('source_id', 'generation_id', 'trigger_tool', 'fulltext', 'unit_id'))
    result = m.Memory(data, p, {KEY}).observe(m.observation(p, 'source_located', ['new-node-1'], origin_tool='vector'), capabilities('fetch_fragment'))
    assert {i['concept_id'] for i in result['items']} == {c['id'] for c in data['concepts']}
    assert all(a['tool'] == 'fetch_fragment' for i in result['items'] for a in m.compile_actions(i, p, capabilities('fetch_fragment'), {KEY}))
