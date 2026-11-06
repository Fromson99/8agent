from copy import deepcopy
import pytest
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.ontology_work.authoring_model import AuthoringFailure
from semantic_runtime.ontology_work.wiki_projection import compile_selection
from test_wiki_workspace import env, ws, seed, projection_generator
from jsonschema import Draft202012Validator


def project_output(value):
    # The shared synthetic generator models the older norm wire representation.
    accumulation = value['accumulation']
    links = accumulation.pop('norm_links')
    node, = accumulation['graph']['nodes']
    link, = links
    assert link['node_id'] == node['id']
    node['source_norm'] = {'source': link['source'], 'norm_index': link['norm_index']}
    return value


@pytest.mark.parametrize('failures', [0, 1, 3, 4, 5])
def test_projection_reopens_after_repair_or_stops_at_five(env, ws, failures):
    item = seed(env, ws)
    calls, attempts = [], []
    base = projection_generator(env, item, calls)
    def generate(prompt, context, schema):
        value, receipt = base(prompt, context, schema)
        if 'statements' not in context:
            return value, receipt
        value = project_output(value)
        attempts.append(deepcopy(context))
        if len(attempts) <= failures:
            value['coverage'][0]['node_ids'] = ['nonexistent']
        else:
            Draft202012Validator(schema).validate(value)
        return value, receipt
    ws.generate = generate
    args = dict(statement_ids=[item.sid], purpose='원문 규칙 재사용', profile_id=env.profile_id,
                profile_work_hash=env.profile_work_hash, originals=[env.source])
    if failures == 5:
        with pytest.raises(ContractError, match='unknown graph node'):
            compile_selection(env.w, ws, **args)
        with pytest.raises(ContractError, match='INVALID'):
            compile_selection(env.w, ws, **args)
    else:
        row = compile_selection(env.w, ws, **args)
        assert env.w.preview(row['bundle_id'])['paths'][0]['body'] == ws.item(item.sid)['content']['text']
        assert compile_selection(env.w, ws, **args)['reused']
    assert [a['call_budget']['attempt'] for a in attempts] == list(range(1, min(failures+1, 5)+1))
    assert all(a['call_budget']['maximum'] == 5 for a in attempts)
    for i, a in enumerate(attempts[1:], 1):
        assert len(a['repair']['prior_errors']) == i
        assert item.sid in a['repair']['previous']['error']
        assert a['repair']['previous']['response']['coverage'][0]['node_ids'] == ['nonexistent']


def test_unknown_never_replays(ws):
    sent = []
    def unknown(*args):
        sent.append(1)
        raise AuthoringFailure('UNKNOWN', {'physical_calls': 1})
    ws.generate = unknown
    def run():
        return ws._job('WIKI_PROPOSE', {}, 'test', {}, lambda value: None)
    with pytest.raises(AuthoringFailure):
        run()
    with pytest.raises(ContractError, match='UNKNOWN'):
        run()
    assert len(sent) == 1


def test_stale_binding_stops_before_repair(ws):
    calls = []
    def check():
        if calls:
            raise ContractError('stale binding')
    def generate(*args):
        calls.append(1)
        return {}, {}
    ws.generate = generate
    with pytest.raises(ContractError, match='stale binding'):
        ws._job('WIKI_PROJECT', {}, 'test', {}, lambda value: None, check)
    with pytest.raises(ContractError, match='BINDING_FAILED'):
        ws._job('WIKI_PROJECT', {}, 'test', {}, lambda value: None, check)
    assert calls == [1]
