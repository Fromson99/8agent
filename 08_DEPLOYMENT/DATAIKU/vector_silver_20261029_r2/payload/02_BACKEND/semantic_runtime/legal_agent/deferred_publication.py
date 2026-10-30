"""Publish a completed legal answer after the caller has received its envelope.

The FINAL answer is already present in the request journal's answer artifact.
The in-process worker is only a fast path; startup recovery can publish that
artifact if the process exits before this worker finishes.
"""
from __future__ import annotations

import logging
from pathlib import Path
import queue
import threading

from .. import observability as obs
from ..contracts import Contracts
from ..storage import Store
from .obligation_repository import ObligationRepository
from .publication import owner_lock, prepare, export
from .source_bundle import validate_current


log = obs.get_logger('publication')
_QUEUE = queue.Queue(maxsize=8)
_THREAD = None
_LOCK = threading.Lock()


def _publish(job):
    journal, generation, contracts_root, runs, result, release = job
    with owner_lock(journal.parent, blocking=True):
        repo = ObligationRepository(journal)
        store = None
        try:
            if repo.run()['status'] != 'RUNNING':
                return
            store = Store(generation, verify=False)
            repo.publication_guard = lambda value: validate_current(repo, value, store)
            with obs.step(log, 'publication.prepare'):
                prepare(repo, result, release, Contracts(contracts_root))
            with obs.step(log, 'publication.export'):
                export(repo, runs)
            obs.event(log, 'publication.completed', run_id=repo.run()['run_id'])
        finally:
            if store is not None:
                store.close()
            repo.close()


def _worker():
    while True:
        job = _QUEUE.get()
        try:
            _publish(job)
        except Exception:
            obs.event(log, 'publication.failed', level=logging.ERROR, exc_info=True,
                      journal=str(job[0]))
        finally:
            _QUEUE.task_done()


def schedule(journal, generation, contracts_root, runs, result, release):
    """Reserve capacity before returning; fail visibly if publication is saturated."""
    global _THREAD
    with _LOCK:
        if _THREAD is None or not _THREAD.is_alive():
            _THREAD = threading.Thread(target=_worker, daemon=True,
                                       name='genos-publication')
            _THREAD.start()
        _QUEUE.put_nowait((Path(journal), Path(generation), Path(contracts_root),
                           Path(runs), result, release))
