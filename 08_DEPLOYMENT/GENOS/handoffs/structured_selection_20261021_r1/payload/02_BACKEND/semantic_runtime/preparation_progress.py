"""Process-local preparation telemetry; never reads data, credentials or NFS.

Counters describe observed work, not readiness or permission to use a release.
The existing Oracle journal and verification remain authoritative.
"""
from __future__ import annotations

import threading
import time

from . import observability as obs


class Progress:
    def __init__(self):
        self.lock = threading.Lock()
        self.clear()

    def clear(self):
        with self.lock:
            self.fields = {}
            self.started = self.phase_started = self.advanced = time.monotonic()
            self.sql_started = None
            self.last_log = 0.0

    def update(self, phase=None, *, force=False, **counts):
        # Only implementation-owned labels and numeric counters enter telemetry.
        allowed = {'table', 'rows_done', 'rows_total', 'asset_index', 'assets_total',
                   'parts_done', 'parts_total', 'bytes_done', 'bytes_total',
                   'files_done', 'files_total', 'cache_hit', 'release_id'}
        if set(counts) - allowed:
            raise ValueError('unknown preparation counter')
        now = time.monotonic()
        with self.lock:
            changed_phase = phase is not None and phase != self.fields.get('phase')
            if changed_phase:
                self.fields = {**{k: v for k, v in self.fields.items()
                                  if k in {'release_id', 'sql_calls', 'sql_status'}}, 'phase': phase}
                self.phase_started = now
            changed = changed_phase or any(self.fields.get(k) != v for k, v in counts.items())
            self.fields.update(counts)
            if changed:
                self.advanced = now
            emit = force or changed_phase or now - self.last_log >= 15
            if emit:
                self.last_log = now
        if emit:
            obs.event(obs.get_logger('preparation'), 'preparation.progress', **self.snapshot())

    def sql(self, status, call):
        now = time.monotonic()
        with self.lock:
            self.fields['sql_calls'] = call
            self.fields['sql_status'] = status
            if status == 'STARTED':
                self.sql_started = now
            else:
                self.sql_started = None
                if status == 'ACKNOWLEDGED':
                    self.advanced = now

    def snapshot(self):
        now = time.monotonic()
        with self.lock:
            if not self.fields:
                return {}
            return {**self.fields,
                    'elapsed_seconds': round(now - self.started, 1),
                    'phase_elapsed_seconds': round(now - self.phase_started, 1),
                    'last_progress_age_seconds': round(now - self.advanced, 1),
                    'sql_in_flight': self.sql_started is not None,
                    'sql_elapsed_seconds': round(now - self.sql_started, 1) if self.sql_started is not None else 0}


current = Progress()
