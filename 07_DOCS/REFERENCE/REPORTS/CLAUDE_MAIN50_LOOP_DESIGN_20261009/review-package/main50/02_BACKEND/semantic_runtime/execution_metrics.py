"""Request-local public timing from physical transport boundaries, never journal counts."""
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time
from . import observability as obs

_CURRENT = ContextVar('rag_execution_metrics', default=None)
log = obs.get_logger('execution_metrics')

def purpose(value):
    value = str(value or '')
    if value.startswith(('memory-resolve','memory-command','memory-history','memory-reuse','memory-intent')): return 'request'
    if value.startswith(('source-','select_sources','investigate')): return 'sources'
    if value.startswith(('memory-assess','review','repair','rebuttal')): return 'assessment'
    if value.startswith(('memory-compose','compose')): return 'answer'
    return 'model'

class Metrics:
    def __init__(self):
        self.started = time.perf_counter()
        self.calls = []
        self.lock = threading.Lock()

    def begin(self, stage):
        with self.lock:
            row = {'number': len(self.calls)+1, 'purpose': stage, 'duration_ms': None}
            self.calls.append(row)
            return row

    def finish(self, row, duration):
        with self.lock: row['duration_ms'] = duration

    def snapshot(self):
        with self.lock: calls = [dict(row) for row in self.calls]
        return {'schema_version': 'rag-execution-stats-v1', 'count_basis': 'transport-attempts',
                'llm_calls': len(calls), 'calls': calls,
                'llm_duration_ms': sum(row['duration_ms'] for row in calls if row['duration_ms'] is not None),
                'timing_complete': all(row['duration_ms'] is not None for row in calls),
                'request_duration_ms': max(0, int((time.perf_counter()-self.started)*1000))}

@contextmanager
def capture():
    metrics = Metrics(); token = _CURRENT.set(metrics)
    try: yield metrics
    finally:
        _CURRENT.reset(token)
        obs.event(log, 'execution.metrics', execution_stats=metrics.snapshot())

@contextmanager
def transport_attempt(stage, attempt_id):
    metrics = _CURRENT.get(); stage = purpose(stage)
    row = metrics.begin(stage) if metrics is not None else None
    started = time.perf_counter()
    obs.event(log, 'model.call.started', attempt_id=attempt_id, purpose=stage)
    try: yield
    finally:
        duration = max(0, int((time.perf_counter()-started)*1000))
        if metrics is not None: metrics.finish(row, duration)
        obs.event(log, 'model.call.finished', attempt_id=attempt_id, purpose=stage, duration_ms=duration)
