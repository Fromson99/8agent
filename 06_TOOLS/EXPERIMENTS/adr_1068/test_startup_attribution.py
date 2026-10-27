"""Finite startup attribution contracts: synthetic objects, no corpus or model."""
from contextlib import contextmanager, nullcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1068'
SNAPSHOT = Path(os.environ.get('ADR1068_SNAPSHOT', BASE / 'profile-baseline-r1/snapshot')).resolve()
sys.path[:0] = [str(SNAPSHOT / '02_BACKEND'), str(SNAPSHOT)]
spec = importlib.util.spec_from_file_location('genos_timing_probe', SNAPSHOT / 'genos_timing_probe.py')
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)
from semantic_runtime import query_latency


@pytest.fixture(autouse=True)
def coarse(monkeypatch):
    monkeypatch.setenv('GENOS_FUNCTION_TIMING_MODE', 'coarse')


def capture():
    return probe.request_scope('synthetic', emit=lambda *args, **kwargs: None)


def rows(collector):
    return {row['function']: row for row in collector.result['functions']}


def test_targets_install_and_common_files_match():
    coverage = probe.install()
    assert coverage['missing'] == []
    assert probe.STARTUP_LABELS <= probe.COARSE_TARGETS
    assert probe.REVISION == 'genos-function-timing-adr1068-r1'
    for label in ('legal_agent.memory_binding.RuntimeModel.ensure',
                  'legal_agent.request_entry.run', 'term_index.TermIndex.tools',
                  'navigation_match.ReverseMatcher._build'):
        assert label in coverage['installed']
        assert probe.classification(label) == 'startup_preparation'
    assert probe.classification('term_index.sha') == 'encode_hash'
    assert probe.classification('span.startup.session.construct') == 'startup_preparation'
    assert probe.classification('legal_agent.bounded_source_session.BoundedSourceSession.structured') == 'input_preparation'
    for name in ('genos_timing_probe.py', '02_BACKEND/semantic_runtime/document_agent.py',
                 '02_BACKEND/semantic_runtime/legal_agent_adapter.py', '02_BACKEND/semantic_runtime/resident_data.py'):
        assert (BASE/'profile-baseline-r1/snapshot'/name).read_bytes() == (BASE/'profile-optimized-r1/snapshot'/name).read_bytes()


def test_real_ensure_and_entry_failure_are_observed_without_model(tmp_path):
    from semantic_runtime.legal_agent import memory_binding, request_entry, bounded_source_session
    seen = []
    session = SimpleNamespace(profile={}, sources=SimpleNamespace(source=SimpleNamespace()),
        structured=lambda *a: None, work=SimpleNamespace(event=lambda *a: seen.append('event')))
    @contextmanager
    def resource(*args, **kwargs):
        seen.append('enter')
        try: yield session
        finally: seen.append('exit')
    pipeline = SimpleNamespace(term_agent=SimpleNamespace(unified=False, open_session=resource),
        plan=lambda *a: seen.append('plan') or {})
    model = memory_binding.RuntimeModel(pipeline, tmp_path, {'question':'PRIVATE_QUESTION',
        'request_id':'fixture', 'session_id':'fixture'}, {'document_ids':['PRIVATE_DOC']})
    failure = RuntimeError('PRIVATE_FAILURE')
    def reject(): raise failure
    class UnavailableProfile:
        @property
        def profile(self): raise failure
    with capture() as collected:
        assert model.ensure() is session
        assert model.ensure() is session
        with pytest.raises(RuntimeError) as error:
            request_entry.run(SimpleNamespace(executor=SimpleNamespace(model=SimpleNamespace(ensure=reject))),
                              {'utterance':'PRIVATE_QUESTION'})
        assert error.value is failure
        with pytest.raises(RuntimeError) as error:
            bounded_source_session.BoundedSourceSession.structured(
                UnavailableProfile(), 'PRIVATE_SYSTEM', {}, {}, 'request-entry', 10)
        assert error.value is failure
        model.close()
    result = rows(collected)
    assert seen == ['plan','enter','event','exit']
    assert result['legal_agent.memory_binding.RuntimeModel.ensure']['calls'] == 2
    assert result['legal_agent.request_entry.run']['errors'] == 1
    assert result['legal_agent.bounded_source_session.BoundedSourceSession.structured']['errors'] == 1
    assert 'PRIVATE' not in json.dumps(collected.result)


def test_resources_measure_entered_body_and_preserve_cleanup(monkeypatch):
    from semantic_runtime import document_agent as module
    seen = []
    def db(): return SimpleNamespace(close=lambda: seen.append('db.close'))
    tools = SimpleNamespace(db=db())
    glossary = SimpleNamespace(binding={'manifest_sha256':'m','dictionary_sha256':'d'},
        check_unchanged=lambda: seen.append('verify'), close=lambda: seen.append('glossary.close'))
    matcher = SimpleNamespace()
    index = SimpleNamespace(tools=lambda scope: tools, path='PRIVATE_PATH')
    fulltext = SimpleNamespace(connect=lambda: seen.append('connect') or db())
    agent = SimpleNamespace(config={}, get_index=lambda: index, get_fulltext=lambda: fulltext,
        pipeline=SimpleNamespace(store=SimpleNamespace(db=object(), path='PRIVATE_PATH',
            manifest={'generation_id':'g','store_sha256':'s'}), contracts=SimpleNamespace(root='PRIVATE_PATH'),
            term_agent=SimpleNamespace(unit_fulltext=fulltext)))
    monkeypatch.setattr(module, 'glossary_assets', lambda *a, **k: glossary)
    monkeypatch.setattr(module, 'load_origin_projection', lambda *a: {})
    monkeypatch.setattr(module, 'load_aliases', lambda *a: {})
    monkeypatch.setattr(module, 'ReverseMatcher', lambda *a, **k: matcher)
    monkeypatch.setattr(module, 'bind_structure', lambda *a: matcher)
    with capture() as collected:
        resource = module.ServingDocumentAgent.resources(agent, ['PRIVATE_DOC'])
        assert not collected.rows  # Constructing the contextmanager did no work.
        with resource as result:
            assert result == (index, tools, glossary, matcher)
            assert seen == ['connect','connect']
            with query_latency.span('synthetic.consumer'): pass
    measured = rows(collected)
    for part in ('index','tools','glossary','projections','matcher','fulltext'):
        assert measured['span.startup.resources.'+part]['calls'] == 1
    assert seen == ['connect','connect','verify','db.close','db.close','db.close','glossary.close']
    assert 'PRIVATE' not in json.dumps(collected.result)


@pytest.mark.parametrize('fail', [False, True])
def test_session_prepare_spans_do_not_include_yield_and_cleanup_survives_error(tmp_path, monkeypatch, fail):
    from semantic_runtime import legal_agent_adapter as module, contracts
    from semantic_runtime.legal_agent import workflow_execution
    seen = []; phases = []
    (tmp_path/'store.sqlite').write_bytes(b'synthetic stat identity only')
    manifest = {'generation_id':'g','store_sha256':'s','export_allowed':False,'data_status':'SYNTHETIC'}
    local = SimpleNamespace(path=tmp_path, manifest=manifest, close=lambda: seen.append('store.close'))
    glossary = SimpleNamespace(binding={}, check_unchanged=lambda: seen.append('verify'))
    @contextmanager
    def resources(scope):
        seen.append('resource.enter')
        try: yield SimpleNamespace(manifest={'index_sha256':'i'}), object(), glossary, object()
        finally: seen.append('resource.exit')
    repo = SimpleNamespace(close=lambda: seen.append('repo.close'), fail=lambda code: seen.append('repo.fail'))
    source = object(); session = SimpleNamespace()
    agent = module.ServingLegalAgent.__new__(module.ServingLegalAgent)
    agent.pipeline = SimpleNamespace(store=local, contracts=SimpleNamespace(root=tmp_path))
    agent.config = {}; agent.profile = {'wall_seconds':30,'model_binding':None}; agent.domain = {}
    agent.unified = agent.v2 = agent.v3 = agent.v4 = agent.v5 = False
    monkeypatch.setattr(module, 'Store', lambda *a, **k: local)
    monkeypatch.setattr(module, 'ServingDocumentAgent', lambda *a: SimpleNamespace(resources=resources))
    monkeypatch.setattr(module, 'WorkRepository', lambda *a: repo)
    monkeypatch.setattr(module, 'SourceSession', lambda *a: source)
    monkeypatch.setattr(module, 'LegalSession', lambda *a: session)
    monkeypatch.setattr(module, 'owner_lock', lambda *a: nullcontext())
    monkeypatch.setattr(module.RequestContext, 'create', lambda *a: SimpleNamespace(deadline_at='2026-10-26',run_id='fixture'))
    monkeypatch.setattr(contracts, 'cached_code_sha', lambda *a: 'synthetic')
    monkeypatch.setattr(workflow_execution, 'bind_context', lambda value: value)
    monkeypatch.setattr(workflow_execution, 'register', lambda *a: None)
    event = module.obs.event
    def collect(logger, name, **fields):
        if name == 'session.prepare.timings': phases.append(fields)
        return event(logger, name, **fields)
    monkeypatch.setattr(module.obs, 'event', collect)
    failure = RuntimeError('PRIVATE_FAILURE')
    with capture() as collected:
        try:
            with agent._open_session({'use_llm':False}, query={'scope':{'document_version_ids':[]}}, runtime=tmp_path) as result:
                assert result is session
                assert 'span.startup.session.resources' in collected.rows
                with query_latency.span('synthetic.consumer'):
                    if fail: raise failure
        except RuntimeError as error:
            assert fail and error is failure
        else: assert not fail
    measured = rows(collected)
    for part in ('store','resources','context','journal','sources','gateway','construct'):
        assert measured['span.startup.session.'+part]['calls'] == 1
    assert phases[0]['diagnostic_revision'] == 'request-prepare-adr1068-r1'
    assert set(phases[0]['phases']) == {'session.'+p for p in ('store','resources','context','journal','sources','gateway','construct')}
    assert seen == (['resource.enter','repo.fail','resource.exit','repo.close','store.close'] if fail else
                    ['resource.enter','verify','resource.exit','repo.close','store.close'])
    assert 'PRIVATE' not in json.dumps(collected.result)


def test_tiny_hash_and_disabled_resident_connection_have_numeric_attribution(tmp_path):
    from semantic_runtime import navigation_agent, resident_data
    path = tmp_path/'private.sqlite'
    with sqlite3.connect(path) as db: db.execute('CREATE TABLE fixture(n INTEGER)')
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    pool = resident_data.ResidentPool(mode='off')
    with capture() as collected:
        assert navigation_agent.memoized_sha(path) == expected
        assert navigation_agent.memoized_sha(path) == expected
        db = pool.connect(path)
        assert db.execute('SELECT count(*) FROM fixture').fetchone()[0] == 0
        db.close()
    measured = rows(collected)
    assert measured['navigation_agent.memoized_sha']['calls'] == 2
    assert measured['span.startup.sqlite.connect']['calls'] == 1
    assert collected.result['numeric_counters']['span.startup.sqlite.connect'] == {
        'byte_count':path.stat().st_size, 'item_count':1}
    assert str(path) not in json.dumps(collected.result)
    categories = {row['category'] for row in collected.result['attribution']['categories']}
    assert {'encode_hash','startup_preparation'} <= categories
