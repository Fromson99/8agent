"""Small P1 contract tests: no model, corpus, index, or on-disk database."""
from copy import deepcopy
import importlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = Path(os.environ.get('ADR1067_OPTIMIZED_SNAPSHOT', ROOT /
    '02_BACKEND/lawrag/research/candidates/adr_1067/profile-optimized-r1/snapshot')).resolve()
RUNTIME = SNAPSHOT / '02_BACKEND/semantic_runtime'
ALIAS = 'adr1067_latency_runtime'
spec = importlib.util.spec_from_file_location(ALIAS, RUNTIME / '__init__.py',
    submodule_search_locations=[str(RUNTIME)])
package = importlib.util.module_from_spec(spec)
sys.modules[ALIAS] = package
spec.loader.exec_module(package)


def module(name):
    return importlib.import_module(ALIAS + '.' + name)


prep = module('legal_agent.schema_preparation')


@pytest.fixture(autouse=True)
def isolated_alias_logging(monkeypatch):
    """Alias imports must not replace the canonical runtime's process logger."""
    obs = module('observability')
    # configure() closes existing handlers, so moving this test-only module to
    # its own logger preserves the canonical handlers and their live workers.
    name = 'adr1067_latency_test'
    logger = logging.getLogger(name)
    before = (list(logger.handlers), logger.level, logger.propagate, logger.disabled)
    for handler in before[0]:
        logger.removeHandler(handler)
    monkeypatch.setattr(obs, 'ROOT', name)
    monkeypatch.setattr(obs, '_CONFIGURED', False)
    try:
        yield
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
            worker = getattr(handler, 'worker', None)
            if worker is not None:
                worker.join(2)
        for handler in before[0]:
            logger.addHandler(handler)
        logger.setLevel(before[1])
        logger.propagate, logger.disabled = before[2:]


def error_signature(error):
    return (type(error).__name__, str(error), error.validator, error.validator_value,
        list(error.path), list(error.schema_path),
        [error_signature(child) for child in error.context])


SCHEMA = {'type': 'object', 'properties': {
    'choice': {'enum': ['READ', 'PENDING']},
    'target': {'type': 'string'},
    'rows': {'type': 'array', 'items': {'type': 'integer'}}},
    'required': ['choice', 'target'], 'additionalProperties': False,
    'anyOf': [{'properties': {'choice': {'const': 'READ'}, 'target': {'enum': ['T1']}}},
              {'properties': {'choice': {'const': 'PENDING'}, 'target': {'const': ''}}}]}


@pytest.mark.parametrize('schema,value', [
    (SCHEMA, {'choice': 'READ', 'target': 'T1'}),
    (SCHEMA, {'choice': 'READ', 'target': 'other', 'rows': [None, 'bad']}),
    (SCHEMA, {'choice': 'unknown', 'extra': 1}),
    ({'type': 'not-a-type'}, {}),
    ({'$schema': 'http://json-schema.org/draft-07/schema#', 'type': 'array',
      'items': [{'type': 'integer'}, {'type': 'string'}]}, ['bad', 2]),
    ({'$defs': {'row': {'type': 'integer'}}, 'type': 'array',
      'items': {'$ref': '#/$defs/row'}}, ['bad']),
    (False, {'unexpected': 1}),
])
def test_cached_validation_matches_jsonschema_including_best_match(schema, value):
    cache = prep.OrderedSchemaValidators()
    try:
        jsonschema.validate(value, schema)
    except (jsonschema.ValidationError, jsonschema.SchemaError) as expected:
        for _ in range(2):
            with pytest.raises(type(expected)) as actual:
                cache.validate(value, schema)
            assert error_signature(actual.value) == error_signature(expected)
    else:
        assert cache.validate(value, schema) is None
        assert cache.validate(value, schema) is None


def test_preparation_reused_but_instances_revalidated(monkeypatch):
    cls = jsonschema.validators.validator_for(SCHEMA)
    original = cls.check_schema
    calls = []
    monkeypatch.setattr(cls, 'check_schema', lambda schema: (calls.append(deepcopy(schema)), original(schema))[1])
    cache = prep.OrderedSchemaValidators()
    cache.validate({'choice': 'READ', 'target': 'T1'}, SCHEMA)
    with pytest.raises(jsonschema.ValidationError):
        cache.validate({'choice': 'READ', 'target': 'T2'}, deepcopy(SCHEMA))
    assert len(calls) == 1


def test_schema_mutation_and_property_order_are_distinct():
    cache = prep.OrderedSchemaValidators()
    schema = {'type': 'object', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'string'}}}
    cache.validate({'a': 1, 'b': 'ok'}, schema)
    schema['properties'] = dict(reversed(list(schema['properties'].items())))
    cache.validate({'a': 1, 'b': 'ok'}, schema)
    assert len(cache._entries) == 2
    for order in [('a', 'b'), ('b', 'a')]:
        current = {**schema, 'properties': {key: schema['properties'][key] for key in order}}
        with pytest.raises(jsonschema.ValidationError) as expected:
            jsonschema.validate({'a': None, 'b': None}, current)
        with pytest.raises(jsonschema.ValidationError) as actual:
            cache.validate({'a': None, 'b': None}, current)
        assert error_signature(actual.value) == error_signature(expected.value)
    enum = {'enum': ['T1']}
    cache.validate('T1', enum)
    enum['enum'][:] = ['T2']
    with pytest.raises(jsonschema.ValidationError): cache.validate('T1', enum)
    cache.validate('T2', enum)


def test_owned_cache_is_bounded_and_does_not_cross_requests():
    cache = prep.OrderedSchemaValidators(max_entries=1, max_bytes=100)
    cache.validate('T1', {'enum': ['T1']})
    cache.validate('T2', {'enum': ['T2']})
    assert len(cache._entries) == 1 and cache._bytes <= 100
    oversized = {'enum': ['T' * 200]}
    cache.validate('T' * 200, oversized)
    assert len(cache._entries) == 1 and cache._bytes <= 100
    first, second = SimpleNamespace(), SimpleNamespace()
    prep.validate(1, {'type': 'integer'}, owner=first)
    prep.validate(1, {'type': 'integer'}, owner=second)
    assert first._navigation_schema_validators is not second._navigation_schema_validators


def test_invalid_schema_not_cached_and_python_only_values_do_not_alias():
    cache = prep.OrderedSchemaValidators()
    with pytest.raises(jsonschema.SchemaError): cache.validate({}, {'type': 'unknown'})
    assert not cache._entries
    cache.validate('T1', {'enum': ['T1']})
    with pytest.raises(jsonschema.SchemaError): cache.validate('T1', {'enum': ('T1',)})
    assert len(cache._entries) == 1


def test_external_reference_uses_original_validation(monkeypatch):
    calls = []
    monkeypatch.setattr(prep.jsonschema, 'validate', lambda value, schema: calls.append((value, schema)))
    schema = {'$ref': 'urn:external:resource'}
    cache = prep.OrderedSchemaValidators()
    cache.validate({}, schema)
    cache.validate({}, schema)
    assert calls == [({}, schema), ({}, schema)] and not cache._entries


def test_schema_cache_does_not_bypass_current_state_revision(monkeypatch):
    nav = module('legal_agent.law_navigation')
    schema = {'type': 'object', 'properties': {'expected_state_version': {'type': 'integer'}}}
    inv = nav.Investigation.__new__(nav.Investigation)
    inv.p = {'groups': {}, 'state_version': 2}
    inv.policy = {}
    inv.control = True
    value = {'next_action': 'PENDING', 'expected_state_version': 1}
    prep.validate(value, schema, owner=inv)
    monkeypatch.setattr(nav, 'decision_schema', lambda *args: schema)
    with pytest.raises(nav.ContractError, match='stale investigation state version'):
        inv.validate(value, {}, {})
    assert len(inv._navigation_schema_validators._entries) == 1


def test_actions_digest_once_preserves_menu_binding_and_updates_on_change(monkeypatch):
    tasks = module('legal_agent.navigation_tasks')
    contracts = module('contracts')
    events = []
    session = SimpleNamespace(repo=SimpleNamespace(event=lambda *row: events.append(row)), scope={'D1'},
        context=SimpleNamespace(request={'question': '질문'}),
        matcher=SimpleNamespace(unit_fulltext=SimpleNamespace(manifest={'index_sha256': 'index'})))
    inv = SimpleNamespace(policy={'task_local_navigation': True}, p={}, s=session)
    actions = {'T1': {'id': 'T1', 'action': 'BROWSE_STRUCTURE', 'identity': {'document_id': 'D1'}, 'label': '목차'},
        'T2': {'id': 'T2', 'action': 'RESEARCH', 'identity': {}, 'label': '검색'}}
    data = {'state_version': 1, 'chain_frame_id': 'frame1', 'sources': []}
    expected_hash = contracts.digest(actions)
    calls = []
    def counted(value):
        if value is actions: calls.append(1)
        return contracts.digest(value)
    monkeypatch.setattr(tasks, 'digest', counted)
    result, selected = tasks.project(inv, deepcopy(data), actions)
    expected_context = contracts.digest({'state_version': 1, 'chain_frame_id': 'frame1',
        'actions_hash': expected_hash, 'source_hash': contracts.digest([]), 'current': 'CATALOGUE'})
    assert len(calls) == 1
    assert result['task_navigation']['full_actions_hash'] == expected_hash
    assert result['task_navigation']['context_hash'] == expected_context
    assert inv.p['navigation_review_tasks']['task_frame']['full_actions_hash'] == expected_hash
    assert selected['T1'] == actions['T1']
    assert all(row['identity']['task_frame_hash'] == expected_context
        for row in selected.values() if row['action'] == 'OPEN_TASK')
    actions['T2']['label'] = '새 검색'
    changed, _ = tasks.project(inv, deepcopy(data), actions)
    assert len(calls) == 2
    assert changed['task_navigation']['full_actions_hash'] != expected_hash


@pytest.mark.parametrize('fail_evidence', [False, True])
def test_save_view_single_encoding_exact_hash_and_atomic_failure(monkeypatch, fail_evidence):
    repo_module = module('legal_agent.repository')
    digest = module('contracts').digest
    repo = repo_module.WorkRepository.__new__(repo_module.WorkRepository)
    repo.db = sqlite3.connect(':memory:', isolation_level=None)
    repo.db.execute('CREATE TABLE model_view(id,phase,state_revision,evidence_revision,body_json,body_hash,seq)')
    repo.db.execute('CREATE TABLE presentation(view_id,evidence_id,text_hash)')
    repo.db.execute('CREATE TABLE test_event(kind,payload)')
    repo.run = lambda: {'state_revision': 3, 'evidence_revision': 5}
    def event(kind, payload):
        repo.db.execute('INSERT INTO test_event VALUES(?,?)', (kind, json.dumps(payload)))
        return 7
    repo.event = event
    def evidence(ident):
        if fail_evidence: raise repo_module.ContractError('evidence changed')
        return {'text_hash': 'source-hash'}
    repo.evidence = evidence
    original_encode = repo_module.encoded
    encodes = []
    def counted(value):
        encodes.append(deepcopy(value))
        return original_encode(value)
    monkeypatch.setattr(repo_module, 'encoded', counted)
    try:
        if fail_evidence:
            with pytest.raises(repo_module.ContractError, match='evidence changed'):
                repo.save_view('review', {'text': '원문', 'rows': [2, 1]}, ['E1'])
            assert repo.db.execute('SELECT count(*) FROM model_view').fetchone()[0] == 0
            assert repo.db.execute('SELECT count(*) FROM test_event').fetchone()[0] == 0
        else:
            body = repo.save_view('review', {'text': '원문', 'rows': [2, 1]}, ['E1'])
            row = repo.db.execute('SELECT * FROM model_view').fetchone()
            assert row == (body['view_id'], 'review', 3, 5, original_encode(body), digest(body), 7)
            payload = json.loads(repo.db.execute('SELECT payload FROM test_event').fetchone()[0])
            assert payload == {'view_id': body['view_id'], 'hash': digest(body)}
            assert repo.db.execute('SELECT * FROM presentation').fetchone() == (body['view_id'], 'E1', 'source-hash')
        assert len(encodes) == 1
    finally:
        repo.db.close()
