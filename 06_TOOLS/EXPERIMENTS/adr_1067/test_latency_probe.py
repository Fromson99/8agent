"""Small synthetic ADR1067 probe contracts. No corpus, API server or model calls.

R2 pure test bodies are reused from the preserved audit source with candidate
bindings. Historical package/install tests are deliberately not redirected.
Run with -c /dev/null --noconftest and PYTHONDONTWRITEBYTECODE=1.
"""
import ast
import asyncio
import contextvars
import gc
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1067'
SNAPSHOT = Path(os.environ.get('ADR1067_SNAPSHOT', BASE / 'profile-baseline-r1/snapshot')).resolve()
sys.path.insert(0, str(SNAPSHOT))
sys.path.insert(0, str(SNAPSHOT / '02_BACKEND'))
spec = importlib.util.spec_from_file_location('genos_timing_probe', SNAPSHOT / 'genos_timing_probe.py')
p = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = p
spec.loader.exec_module(p)
from semantic_runtime import execution_metrics as em, query_latency

R2 = ROOT / '09_ARTIFACTS/AUDITS/20261024-function-timing-r2/test_probe.py'
R2_CASES = (
    'test_disabled_preserves_identity', 'test_nested_wall_cpu_and_counts',
    'test_original_exception_and_guard_preserved', 'test_limits_do_not_skip_application',
    'test_time_limit_does_not_skip_application', 'test_source_repeat_privacy_and_bound',
    'test_segments_cpu_wait_gc_and_code_lines', 'test_library_inside_checkout_is_not_own_code',
    'test_gc_inside_probe_locks_does_not_deadlock', 'test_sample_mode_no_hooks',
    'test_invalid_settings_default_with_warning', 'test_sampler_failure_keeps_result',
    'test_proc_unavailable_keeps_segments', 'test_boundary_error_and_body_exception_preserved',
    'test_sample_table_and_segment_limits', 'test_privacy_no_arguments_or_locals',
    'test_scope_cleanup_gc_callback_and_sampler_thread',
    'test_concurrent_request_isolation_and_warning', 'test_cancellation_restores_context_and_reports',
    'test_output_failure_does_not_change_result', 'test_setup_failure_does_not_change_result',
    'test_switch_off_no_install', 'test_span_keeps_mutable_fields_and_error',
    'test_sql_rows_exact_results_and_failure', 'test_real_read_cost_has_repeated_source_calls',
)


def _r2_case(name):
    parsed = ast.parse(R2.read_text())
    helpers = {'run_profile','invoke','cpu_work','wait_work','scoped','segmented'}
    nodes = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in helpers]
    case = next(node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == 'ProbeTests')
    case.body = [node for node in case.body if isinstance(node, ast.FunctionDef) and node.name in ('setUp', name)]
    module = ast.fix_missing_locations(ast.Module(body=nodes+[case], type_ignores=[]))
    namespace = {**globals(), '__file__':str(R2), 'AUDIT':R2.parent, 'PACKAGE':SNAPSHOT}
    exec(compile(module, str(R2), 'exec'), namespace)
    return namespace['ProbeTests'](name)


@pytest.mark.parametrize('name', R2_CASES)
def test_preserved_r2_pure_contract(name):
    _r2_case(name).debug()


def test_candidate_modules_and_common_bytes_are_exact():
    assert Path(em.__file__).resolve().is_relative_to(SNAPSHOT)
    assert Path(query_latency.__file__).resolve().is_relative_to(SNAPSHOT)
    for name in ('genos_timing_probe.py','02_BACKEND/semantic_runtime/query_latency.py',
                 '02_BACKEND/semantic_runtime/execution_metrics.py'):
        assert (BASE/'profile-baseline-r1/snapshot'/name).read_bytes() == (BASE/'profile-optimized-r1/snapshot'/name).read_bytes()
    historical = ROOT/'08_DEPLOYMENT/GENOS/handoffs/function_timing_20261024_r2/payload/genos_timing_probe.py'
    assert hashlib.sha256(historical.read_bytes()).hexdigest() == 'f9945873bf24e4956ad4dfa6477f6654dfbad63ffe222d43ad338d5ddaa967b9'


def test_every_current_target_installs_and_is_idempotent():
    coverage = p.install()
    assert coverage['missing'] == []
    assert len(coverage['installed']) == sum(map(len,p.TARGETS.values()))+1
    from semantic_runtime.legal_agent import law_navigation, decision_projection
    assert law_navigation.schema_validate._genos_timing_probe == p.REVISION
    assert decision_projection.validate._genos_timing_probe == p.REVISION
    original = law_navigation.schema_validate
    assert p.install() is coverage
    assert law_navigation.schema_validate is original


def test_coarse_mode_no_sampler_or_gc_and_counter_allowlist(monkeypatch):
    monkeypatch.setenv('GENOS_FUNCTION_TIMING_MODE','coarse')
    emitted = []
    before = tuple(gc.callbacks)
    with p.request_scope('synthetic', emit=lambda event,**fields:emitted.append((event,fields))) as collector:
        assert not any(t.name == 'genos-timing-sampler' and t.is_alive() for t in threading.enumerate())
        assert tuple(gc.callbacks) == before
        with query_latency.span('schema.prepare', schema_bytes=17) as values:
            values.update(cache_hit=1, cache_bypass=0, question='PRIVATE', document_id='PRIVATE',
                          arbitrary_number=99, row_count=float('nan'), source_bytes='PRIVATE')
            value = 42
    result = collector.result
    assert value == 42
    assert result['mode'] == 'coarse' and not result['sampling_enabled'] and not result['gc_observation_enabled']
    assert result['sampling']['ticks'] == 0
    assert result['numeric_counters']['span.schema.prepare'] == {'schema_bytes':17,'cache_hit':1,'cache_bypass':0}
    assert 'PRIVATE' not in json.dumps(result)
    assert [event for event,_ in emitted] == ['timing.probe.started','timing.probe.summary']


def test_sampling_deadline_stops_only_observer():
    collector = p.Collector(max_seconds=-1, mode='sample', hooks=False)
    sampler = p.Sampler(collector, 2)
    sampler.thread.start()
    sampler.thread.join(timeout=1)
    assert not sampler.thread.is_alive()
    assert 'SAMPLING_DEADLINE' in collector.warnings
    before = len(collector.gc_events)
    collector.gc_event(time.perf_counter_ns(), 10, 0)
    assert len(collector.gc_events) == before
    collector.sample(time.perf_counter_ns(),10,False)
    assert collector.ticks == 0
    assert sum([1,2,3]) == 6


def test_model_attempt_union_clips_overlap_and_keeps_unknown_separate():
    assert p._union_ns([(0,20),(10,40),(50,70)],5,60) == 45
    assert em.interval_union_ms([(0,.020),(.010,.040),(.050,.070)], start=.005,end=.060) == pytest.approx(45)
    collector = p.Collector()
    token = collector.model_enter('source-read')
    unfinished = collector.summary()['model_attempt_timing']
    assert not unfinished['complete'] and unfinished['non_model_attempt_wall_ms'] is None
    assert unfinished['intervals'][0]['end_ms'] is None
    assert unfinished['raw_network_timing'] == 'NOT_MEASURED'
    assert token == 1


def test_coarse_schema_real_alias_and_parent_nonmodel_excludes_attempt(monkeypatch):
    monkeypatch.setenv('GENOS_FUNCTION_TIMING_MODE','coarse')
    from semantic_runtime.legal_agent import law_navigation
    original = {'type':'object','properties':{'n':{'type':'integer'}},'required':['n']}
    with p.request_scope('synthetic',emit=lambda *a,**k:None) as collector:
        with query_latency.span('navigation.build'):
            law_navigation.schema_validate({'n':1}, original)
            with em.transport_attempt('source-read','attempt-1'):
                time.sleep(.005)
    result = collector.result
    functions = {row['function']:row for row in result['functions']}
    assert functions['legal_agent.law_navigation.schema_validate']['calls'] == 1
    parent = functions['span.navigation.build']
    assert parent['wall_ms'] > parent['non_model_attempt_ms']
    assert result['model_attempt_timing']['completed_union_ms'] > 0
    assert result['model_calls'] == 1
    assert any(row['category'] == 'schema_validation' for row in result['attribution']['categories'])


def test_query_timed_is_request_local_and_disabled_env_stays_disabled(monkeypatch):
    monkeypatch.setenv('GENOS_QUERY_LATENCY','1')
    calls=[]
    @query_latency.timed('query.fixture')
    def work(value):
        calls.append(value)
        return value
    assert work('PRIVATE') == 'PRIVATE'
    monkeypatch.setenv('GENOS_FUNCTION_TIMING_MODE','coarse')
    with p.request_scope('synthetic',emit=lambda *a,**k:None) as collector:
        assert work(42) == 42
    assert len(calls) == 2
    assert collector.result['functions'][0]['function'] == 'span.query.fixture'
    assert 'PRIVATE' not in json.dumps(collector.result)


def test_timed_keeps_coroutine_and_generator_contract(monkeypatch):
    import inspect
    monkeypatch.setenv('GENOS_FUNCTION_TIMING_MODE','coarse')
    @query_latency.timed('query.async_fixture')
    async def work():
        await asyncio.sleep(0)
        return 42
    @query_latency.timed('query.generator_fixture')
    def rows():
        yield 42
    assert inspect.iscoroutinefunction(work) and inspect.isgeneratorfunction(rows)
    with p.request_scope('synthetic',emit=lambda *a,**k:None) as collector:
        assert asyncio.run(work()) == 42 and list(rows()) == [42]
    assert not collector.result['functions']


def test_artifact_sink_failure_preserves_application_exception(monkeypatch):
    monkeypatch.setenv('GENOS_FUNCTION_TIMING_MODE','coarse')
    error = RuntimeError('PRIVATE original exception')
    def fail(*args, **kwargs): raise ValueError('sink failure')
    with pytest.raises(RuntimeError) as caught:
        with p.request_scope('synthetic',emit=fail) as collector:
            raise error
    assert caught.value is error and collector.result is not None
    assert p._CURRENT.get() is None


def test_execution_metric_attempt_endpoints_keep_public_compatibility(monkeypatch):
    clock = iter([10.,10.1,10.35,10.5])
    monkeypatch.setattr(em, 'time', SimpleNamespace(perf_counter=lambda:next(clock)))
    monkeypatch.setattr(em, 'resident_bytes', lambda:None)
    monkeypatch.setattr(em.obs, 'event', lambda *a,**k:None)
    metrics = em.Metrics()
    token = em._CURRENT.set(metrics)
    try:
        with em.transport_attempt('source-read','synthetic'): pass
        value = metrics.snapshot()
    finally:
        em._CURRENT.reset(token)
    assert value['llm_calls'] == 1 and value['llm_duration_ms'] == 250
    assert value['request_duration_ms'] == 500
    timing = value['model_attempt_timing']
    assert timing['complete'] and timing['completed_union_ms'] == pytest.approx(250)
    assert timing['non_model_attempt_wall_ms'] == pytest.approx(250)
    assert timing['basis'] == 'MODEL_ATTEMPT' and timing['includes_adapter_parse_and_callbacks']
