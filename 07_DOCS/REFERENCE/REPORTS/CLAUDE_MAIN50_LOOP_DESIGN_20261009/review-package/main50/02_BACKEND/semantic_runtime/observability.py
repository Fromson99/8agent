"""Credential-safe, one-line JSON events for GENOS container logs."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
import sys
import time
import threading
from typing import Any, Iterator
import uuid
from collections import deque
from copy import copy
import atexit


ROOT = "genos"
_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("genos_log_context", default={})
_FORBIDDEN_PARTS = ("TOKEN", "KEY", "PASSWORD", "SECRET", "AUTHORIZATION")
_CONTENT_KEYS = frozenset(
    {"question", "answer", "content", "text", "prompt", "context", "quote", "chunks", "raw"}
)
_TOKEN_COUNT_FIELDS = frozenset(
    {"prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens",
     "cached_tokens", "max_tokens"}
)
_CONFIGURED = False
_LAST_LOG: ContextVar[Any] = ContextVar("genos_last_log_timing", default=None)
_DETAIL_EVENTS = frozenset({
    'catalogue.cache.hit', 'folder_catalogue.cached', 'matcher.cache.hit',
    'tools.cache.hit', 'glossary.file.cached', 'glossary.pool.hit',
    'sources.lexical_schema.cached', 'sources.structure_ready',
    'session.resources.started', 'session.resources.ready',
    'journal.transaction.timings',
})


def _secret_values() -> tuple[str, ...]:
    secrets = {
        item
        for name, item in os.environ.items()
        if item and name.upper() != 'STRUCTURE_RECIPE_MAX_TOKENS'
        and any(part in name.upper() for part in _FORBIDDEN_PARTS)
    }
    return tuple(sorted(secrets, key=len, reverse=True))


def _redact_secrets(value: str, *, secrets=None) -> str:
    result = value
    for secret in _secret_values() if secrets is None else secrets:
        result = result.replace(secret, "[REDACTED]")
    return result


def _safe_fields(fields: dict[str, Any], *, secrets=None) -> dict[str, Any]:
    # A fresh snapshot per event observes credential rotation without scanning
    # the entire process environment for every string and every output handler.
    if secrets is None:
        secrets = _secret_values()
    def safe_value(value):
        if isinstance(value, str):
            return _redact_secrets(value, secrets=secrets)
        if isinstance(value, dict):
            return _safe_fields(value, secrets=secrets)
        if isinstance(value, (list, tuple)):
            return [safe_value(item) for item in value]
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return _redact_secrets(str(value), secrets=secrets)
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        # Only known nonnegative integer counts may bypass the credential filter.
        # A string/dict under a count-shaped key must never expose a credential.
        if key.lower() in _TOKEN_COUNT_FIELDS:
            if value is None or (type(value) is int and value >= 0):
                safe[key] = value
            continue
        upper = key.upper()
        if key.lower() in _CONTENT_KEYS or any(part in upper for part in _FORBIDDEN_PARTS):
            continue
        safe[key] = safe_value(value)
    return safe


def prepared_record(record):
    """One sanitized snapshot shared by the container, live log and capture."""
    if getattr(record, '_genos_sanitized', False):
        return record
    prepared = getattr(record, '_genos_prepared', None)
    if prepared is not None:
        return prepared
    prepared = copy(record)
    prepared.msg = record.getMessage(); prepared.args = ()
    secrets = _secret_values()
    prepared.fields = _safe_fields(getattr(record, 'fields', {}) or {}, secrets=secrets)
    if record.exc_info and record.exc_info[0]:
        prepared.async_exc_type = record.exc_info[0].__name__
        prepared.async_exception = _redact_secrets(
            logging.Formatter().formatException(record.exc_info), secrets=secrets)
    prepared.exc_info = None; prepared.exc_text = None
    prepared.queue_bytes = (len(json.dumps(prepared.fields, ensure_ascii=False, default=str).encode())
                            + len(str(prepared.msg).encode())
                            + len(getattr(prepared, 'async_exception', '').encode()) + 256)
    if hasattr(prepared, 'live_detail'):
        prepared.queue_bytes += len(json.dumps(prepared.live_detail, ensure_ascii=False, default=str).encode())
    prepared._genos_sanitized = True
    record._genos_prepared = prepared
    return prepared


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record = prepared_record(record)
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(record.fields)
        if record.exc_info and record.exc_info[0]:
            payload["exc_type"] = record.exc_info[0].__name__
            payload["traceback"] = _redact_secrets(self.formatException(record.exc_info))
        elif getattr(record,'async_exception',None):
            payload['exc_type'] = record.async_exc_type
            payload['traceback'] = record.async_exception
        return json.dumps(payload, ensure_ascii=False, default=str)


class AsyncHandler(logging.Handler):
    """Bounded, nonblocking I/O handoff. The journal is never routed through this queue."""
    def __init__(self, target, *, max_records=1024, max_bytes=2*1024*1024):
        super().__init__()
        self.target=target;self.max_records=max_records;self.max_bytes=max_bytes
        self.queue=deque();self.bytes=0;self.dropped=0;self.write_errors=0
        self.condition=threading.Condition();self.busy=False;self.stopping=False
        self.on_finish=None
        self.worker=threading.Thread(target=self._write,name='genos-log-writer',daemon=True)
        self.worker.start()

    def handle(self, record):
        if self.filter(record):self.emit(record)
        return True

    def emit(self, record):
        queued=prepared_record(record)
        size=queued.queue_bytes
        critical=record.levelno>=logging.ERROR or queued.msg in {'request.returning','ask.finished','rag.answer_returning'}
        fallback=False
        with self.condition:
            record_limit=self.max_records if critical else max(1,self.max_records-64)
            byte_limit=self.max_bytes if critical else self.max_bytes*3//4
            if self.stopping or size>byte_limit or len(self.queue)>=record_limit or self.bytes+size>byte_limit:
                if record.levelno>=logging.ERROR:
                    fallback=True
                else:
                    self.dropped+=1
                    return
            else:
                self.queue.append((queued,size));self.bytes+=size
                self.condition.notify()
        if fallback:
            # An oversized error or a saturated queue must remain visible in
            # full. The normal asynchronous path stays bounded.
            self.target.acquire()
            try:
                self.target.emit(queued)
                if hasattr(self.target,'flush_batch'):self.target.flush_batch()
            finally:self.target.release()

    def _write(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.queue or self.stopping)
                if not self.queue:break
                batch=[]
                for _ in range(min(64,len(self.queue))):
                    record,size=self.queue.popleft();self.bytes-=size;batch.append(record)
                dropped=self.dropped;self.dropped=0;errors=self.write_errors;self.write_errors=0
                self.busy=True
            if dropped or errors:
                loss=logging.LogRecord(ROOT+'.logging',logging.WARNING,__file__,0,'logging.queue.loss',(),None)
                loss.fields={'dropped_count':dropped,'write_error_count':errors}
                batch.insert(0,loss)
            try:
                self.target.acquire()
                try:
                    for record in batch:self.target.emit(record)
                    if hasattr(self.target,'flush_batch'):self.target.flush_batch()
                finally:self.target.release()
            except Exception:
                with self.condition:self.write_errors+=1
            finally:
                with self.condition:self.busy=False;self.condition.notify_all()
        if self.on_finish is not None:
            try:self.on_finish()
            except OSError:pass

    def drain(self, timeout=2):
        with self.condition:
            return self.condition.wait_for(lambda:not self.queue and not self.busy,timeout)

    def finish(self, callback=None):
        with self.condition:
            if callback is not None:self.on_finish=callback
            self.stopping=True;self.condition.notify_all()

    def close(self):
        self.finish();self.drain(0.2)
        super().close()


class _BatchStream(logging.StreamHandler):
    def emit(self, record):
        self.stream.write(self.format(record)+self.terminator)
    def flush_batch(self):self.stream.flush()


def cpu_pressure():
    """Optional local cgroup counters. Missing permissions/layout mean unknown."""
    from pathlib import Path
    result={}
    try:
        rows=(Path('/sys/fs/cgroup')/'cpu.stat').read_text().splitlines()
        for row in rows:
            key,value=row.split()
            if key in {'nr_throttled','throttled_usec','usage_usec'}:result[key]=int(value)
    except (OSError,ValueError):pass
    return result


def environment_facts(path):
    from pathlib import Path
    import sqlite3
    facts={'sqlite_version':sqlite3.sqlite_version,'process_id':os.getpid(),'cpu_counters':cpu_pressure()}
    try:
        resolved=str(Path(path).resolve());best='';kind='unknown'
        for row in Path('/proc/self/mountinfo').read_text().splitlines():
            left,right=row.split(' - ',1);mount=left.split()[4].replace('\\040',' ')
            if (resolved==mount or resolved.startswith(mount.rstrip('/')+'/')) and len(mount)>len(best):
                best=mount;kind=right.split()[0]
        facts['mount_type']=kind
    except (OSError,ValueError,IndexError):facts['mount_type']='unknown'
    return facts


def configure() -> None:
    """Install one stderr handler; GENOS collects stdout/stderr as container logs."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger(ROOT)
    for handler in list(root.handlers):
        if getattr(handler, "_genos_system_capture", False):
            continue  # Early process diagnostics must survive lazy RAG setup.
        root.removeHandler(handler)
        handler.close()
    stream = _BatchStream(sys.stderr)
    stream.setFormatter(JsonFormatter())
    handler = AsyncHandler(stream)
    atexit.register(handler.drain,2)
    root.addHandler(handler)
    level = os.environ.get("GENOS_LOG_LEVEL", "INFO").strip().upper()
    root.setLevel(getattr(logging, level, logging.INFO))
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure()
    return logging.getLogger(f"{ROOT}.{name}")


def event(
    logger: logging.Logger,
    name: str,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    if level == logging.INFO and name in _DETAIL_EVENTS:
        level = logging.DEBUG
    if not logger.isEnabledFor(level):
        return
    merged = {**_CONTEXT.get(), **fields}
    if name in {'request.started', 'rag.prepare.started'}:
        merged['observability_revision'] = 'response-overhead-20260928-r1'
    identity = (merged.get('request_id'), merged.get('run_id'), threading.get_ident())
    previous = _LAST_LOG.get()
    if previous is not None and previous[0] == identity:
        merged.update(previous_event=previous[1], previous_step=previous[2],
                      previous_log_ms=previous[3])
    started = time.perf_counter()
    logger.log(level, name, extra={"fields": merged}, exc_info=exc_info)
    # Includes formatting, handler locks and writes/flushes. No recursive log event.
    _LAST_LOG.set((identity, name, fields.get('step'),
                   round((time.perf_counter() - started) * 1000, 3)))


def new_request_id(candidate: Any = None) -> str:
    value = str(candidate or "").strip()
    if value and len(value) <= 64 and all(ch.isalnum() or ch in "_.:-" for ch in value):
        return value
    return uuid.uuid4().hex


@contextmanager
def context(**fields: Any) -> Iterator[None]:
    current = _CONTEXT.get()
    token = _CONTEXT.set({**current, **{k: v for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


@contextmanager
def step(logger: logging.Logger, name: str, **fields: Any) -> Iterator[None]:
    started = time.perf_counter()
    detailed = logger.isEnabledFor(logging.DEBUG)
    if detailed:
        event(logger, "step.started", level=logging.DEBUG, step=name, **fields)
    work_started = time.perf_counter()
    cpu_started = time.thread_time()
    def timings():
        return dict(duration_ms=int((time.perf_counter() - started) * 1000),
                    work_ms=round((time.perf_counter() - work_started) * 1000, 3),
                    thread_cpu_ms=round((time.thread_time() - cpu_started) * 1000, 3),
                    start_log_ms=round((work_started - started) * 1000, 3))
    try:
        yield
    except Exception:
        event(
            logger,
            "step.failed",
            level=logging.ERROR,
            exc_info=True,
            step=name,
            **timings(),
            **fields,
        )
        raise
    else:
        if detailed:
            event(logger, "step.finished", level=logging.DEBUG, step=name,
                  **timings(), **fields)


def safe_error(exc: BaseException) -> str:
    return _redact_secrets(f"{type(exc).__name__}: {exc}")[:1000]
