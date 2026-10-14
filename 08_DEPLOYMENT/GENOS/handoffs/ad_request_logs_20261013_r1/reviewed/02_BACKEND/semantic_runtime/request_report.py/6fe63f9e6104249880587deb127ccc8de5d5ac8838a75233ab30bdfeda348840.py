"""Request-local GENOS live trace and completed report on a shared volume.

The journal remains the detailed source of truth. The live log shows readable
decisions plus an explicitly marked, unparsed model-output block. A request-local
JSONL sidecar preserves returned content, refusal and filter signals for diagnosis.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import copy_context
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import queue
import sqlite3
import tempfile
import threading
import time
from typing import Any
import uuid

from . import observability as obs
from .request_summary import report_directory, team_name


# Independent of asyncio's default executor: a gateway may close its event loop
# immediately after service() returns. Keep completion I/O off that return path.
_FINALIZER_QUEUE = queue.Queue(maxsize=8)
_FINALIZER_SLOTS = threading.BoundedSemaphore(8)
_FINALIZER_LOCK = threading.Lock()
_FINALIZER_THREADS = []
_REPORT_LOG = obs.get_logger('request-report')


def _finalizer_worker():
    while True:
        context, report = _FINALIZER_QUEUE.get()
        try:
            context.run(report.finalize)
        except Exception as exc:
            # A failed optional report must not kill the shared worker.
            obs.event(_REPORT_LOG, 'shared_report.worker_failed', level=logging.ERROR,
                      error_type=type(exc).__name__)
        finally:
            _FINALIZER_SLOTS.release()
            _FINALIZER_QUEUE.task_done()


def _start_finalizers():
    with _FINALIZER_LOCK:
        while len(_FINALIZER_THREADS) < 2:
            thread = threading.Thread(target=_finalizer_worker, daemon=True,
                                      name='genos-report-finalizer')
            thread.start()
            _FINALIZER_THREADS.append(thread)


class DeferredReport:
    """Bounded, best-effort shared reporting; the runtime journal stays authoritative.

    Detach the live handler and stop its heartbeat before returning to the
    gateway. Final journal polling, JSON/TXT publication and NFS close all run
    on a daemon worker, including when the request is cancelled. A process kill
    may interrupt shared copies; it does not remove the original journal.
    """

    def __init__(self, root, runtime, *, request_id, api_type, request, events,
                 component='legal_agent', started_at=None):
        self.root, self.runtime = root, runtime
        self.request_id, self.api_type = request_id, api_type
        self.request, self.events = request, events
        self.started_at = started_at or datetime.now(timezone.utc)
        self.component = component
        self.team = team_name(request)
        self.log_path = None
        self.record_id = uuid.uuid4().hex
        self.handler = self.context = None
        self.result = None
        self.admitted = False
        self._live_ready = threading.Event()
        self._live_lock = threading.Lock()
        self._detached = False

    def __enter__(self):
        self.admitted = _FINALIZER_SLOTS.acquire(blocking=False)
        if not self.admitted:
            obs.event(_REPORT_LOG, 'shared_report.skipped', level=logging.WARNING,
                      reason='report_capacity_reached')
            return self
        try:
            _start_finalizers()
            context = copy_context()
            threading.Thread(target=lambda: context.run(self._initialize_live),
                             name='genos-report-open', daemon=True).start()
        except BaseException:
            _FINALIZER_SLOTS.release()
            self.admitted = False
            raise
        return self

    def _initialize_live(self):
        """Shared directory/open errors and stalls must not delay an answer."""
        opened = False
        try:
            self.context = safe_live_log(self.root, self.request_id, self.runtime,
                                         team_id=self.team, started_at=self.started_at,
                                         component=self.component,
                                         attach=False)
            path, handler, error = self.context.__enter__()
            opened = True
            with self._live_lock:
                self.log_path, self.handler = path, handler
                if handler:
                    if self._detached:
                        handler.stop_event.set()
                    else:
                        logging.getLogger(obs.ROOT).addHandler(handler)
            if self.log_path is not None:
                self.record_id = self.log_path.stem
            if error:
                obs.event(_REPORT_LOG, 'shared_live.failed', level=logging.ERROR, error_type=error)
            if handler:
                run_id = next((row.get('run_id') for row in reversed(list(self.events))
                               if isinstance(row.get('run_id'), str) and _RUN_ID.fullmatch(row['run_id'])), None)
                if run_id is None and isinstance(self.result, dict):
                    result_body = self.result.get('body')
                    candidate = result_body.get('run_id') if isinstance(result_body, dict) else None
                    if isinstance(candidate, str) and _RUN_ID.fullmatch(candidate):
                        run_id = candidate
                if run_id is not None:
                    handler.run_id = run_id
                body = self.request.get('json') if isinstance(self.request.get('json'), dict) else self.request
                handler.queue_detail('AD INPUT / COMMAND' if self.component == 'ad_mode' else 'RAG INPUT / QUESTION', {
                    'question': body.get('question') or body.get('q') or '',
                    'api_type': self.api_type, 'use_llm': body.get('use_llm', True),
                    **{key: body[key] for key in ('scope', 'team_id') if key in body},
                })
                # The complete event list remains in the final report. Replay
                # its opening event when shared storage became ready late.
                opening = next((row for row in self.events if row['event']=='request.started'), None)
                if opening:
                    record = logging.LogRecord(obs.ROOT, logging.INFO, __file__, 0,
                                               'request.started', (), None)
                    record.created = datetime.fromisoformat(opening['ts']).timestamp()
                    record.fields = {key:value for key,value in opening.items()
                                     if key not in {'ts','level','logger','event'}}
                    handler.writer.handle(record)
        except Exception as exc:
            if not opened:
                self.context = None
            obs.event(_REPORT_LOG, 'shared_live.failed', level=logging.ERROR,
                      error_type=type(exc).__name__)
        finally:
            self._live_ready.set()

    def __exit__(self, exc_type, exc, traceback):
        if not self.admitted:
            return False
        self.detach()
        if exc_type is not None:
            obs.event(_REPORT_LOG, 'request.interrupted', error_type=exc_type.__name__)
        # Captured rows are immutable after append. The report worker receives a
        # stable event list; request/result snapshots are taken by complete().
        self.events = list(self.events)
        _FINALIZER_QUEUE.put_nowait((copy_context(), self))
        return False

    def detach(self):
        with self._live_lock:
            self._detached = True
            if self.handler:
                # No live NFS handler may intercept request.returning on this thread.
                logging.getLogger(obs.ROOT).removeHandler(self.handler)
                self.handler.stop_event.set()

    def complete(self, result):
        if self.admitted:
            self.request = deepcopy(self.request)
            self.result = deepcopy(result)

    def _event(self, name, **fields):
        obs.event(_REPORT_LOG, name, **fields)
        if self.handler:
            self.handler.write_detail(name, fields)

    def finalize(self):
        phase = 'shared_report'
        try:
            self._live_ready.wait()
            if self.result is None:
                return
            body = self.result.get('body') or {}
            answer = body.get('answer') if isinstance(body, dict) else None
            # Publish the compact QA row before detailed journal/report I/O.
            # Snapshot writes run on this finalizer, never on the gateway thread.
            try:
                from .request_summary import make_row, write_row, refresh
                directory = report_directory(self.root, self.team, self.started_at, component=self.component)
                report_path = directory / (self.record_id + '.json')
                row = make_row(self.request, self.result, self.events, request_id=self.request_id,
                               started_at=self.started_at, directory=directory,
                               log_path=self.log_path, report_path=report_path)
                if row:
                    write_row(directory, self.record_id, _scrub(row))
                    refresh(directory)
                    self._event('shared_summary.written', team=self.team)
            except Exception as exc:
                self._event('shared_summary.failed', level=logging.ERROR, error_type=type(exc).__name__)
            if self.handler:
                self.handler.poll_journal()
                self.handler.write_detail('SERVICE RETURN SCHEDULED', {
                    'event': next((row for row in reversed(self.events)
                                   if row['event'] == 'request.returning'), {}),
                    'delivery_confirmed': False,
                })
                summary = {
                    'http_status': self.result.get('status', 200),
                    'answer': answer.get('text') if isinstance(answer, dict) else body.get('text'),
                    **({key: body.get(key) for key in ('status', 'error', 'detail')}
                       if isinstance(body, dict) else {}),
                }
                self.handler.write_detail('FINAL RESPONSE / ANSWER', {
                    key: value for key, value in summary.items() if value is not None})
            self._event('shared_report.started')
            with obs.step(_REPORT_LOG, 'shared_report.publish'):
                path = write_report(self.root, self.runtime, request_id=self.request_id,
                                    api_type=self.api_type, request=self.request,
                                    result=self.result, events=self.events,
                                    requested_at=self.started_at, live_log_path=self.log_path,
                                    record_id=self.record_id, component=self.component)
            if self.handler and self.component == 'ad_mode':
                # AD has its own durable SQL journal, not a legal run journal.
                ad_journal = json.loads(path.read_text(encoding='utf-8'))['journal']
                for call in ad_journal.get('calls', []):
                    self.handler.write_detail('AD MODEL REQUEST', {
                        'sequence': call['sequence'], 'input': call.get('input')})
                    self.handler.write_detail('AD MODEL RESPONSE', {
                        'sequence': call['sequence'], 'response': call.get('model_output'),
                        'plan': call.get('plan'), 'receipt': call.get('receipt')})
                for error in ad_journal.get('errors', []):
                    self.handler.write_detail('AD FAILURE', error)
            self._event('shared_report.written', path=str(path))
            phase = 'shared_trace'
            self._event('shared_trace.started')
            with obs.step(_REPORT_LOG, 'shared_trace.publish'):
                trace = write_readable_report(path)
            self._event('shared_trace.written', path=str(trace))
        except Exception as exc:
            self._event(phase + '.failed', level=logging.ERROR,
                        error_type=type(exc).__name__)
        finally:
            if self.context is not None:
                self.context.__exit__(None, None, None)


_SECRET_FIELDS = ("authorization", "password", "secret", "credential", "api_key", "access_token", "refresh_token")
_RUN_ID = re.compile(r"[a-f0-9]{32}\Z")
_LIVE_DIAGNOSTIC_FIELD_NAMES = frozenset({
    'diagnostics_version', 'thinking_requested', 'thinking_control_present',
    'stream_requested', 'thinking_observation', 'reasoning_field_present',
    'reasoning_nonempty', 'thought_channel_marker_present', 'reasoning_chars',
    'max_tokens', 'prompt_tokens', 'completion_tokens', 'total_tokens',
    'cached_tokens', 'reasoning_tokens', 'request_bytes', 'response_bytes',
    'response_content_chars', 'tool_argument_chars', 'finish_reason',
})
_FULLTEXT_DIAGNOSTIC_FIELD_NAMES = frozenset(['active_searches_at_finish', 'active_searches_at_start', 'active_searches_peak', 'allowed_count', 'batch_cpu_ms', 'batch_no', 'batch_rows', 'batch_wall_ms', 'bounds_enabled', 'bounds_tokenize_ms', 'cache_size', 'concurrency_scope', 'connect_ms', 'cpu_nr_throttled_delta', 'cpu_throttled_usec_delta', 'facts_ms', 'fetched_count', 'index_bytes', 'indexed_source_count', 'involuntary_switches_delta', 'limit', 'location_count', 'major_faults_delta', 'mapping_status', 'minor_faults_delta', 'mmap_size', 'page_size', 'progress_event_count', 'result_count', 'route_handle_ms', 'scheduler_wait_ms', 'scope_filter_ms', 'scope_rejected_count', 'search_id', 'selected_count', 'source_cache_hits', 'source_json_chars', 'source_json_cpu_ms', 'source_json_decode_ms', 'source_load_errors', 'source_lookup_count', 'source_sql_count', 'source_sql_cpu_ms', 'source_sql_execute_ms', 'source_sql_fetch_ms', 'source_sql_max_ms', 'sql_count', 'sql_execute_cpu_ms', 'sql_execute_ms', 'sql_fetch_batch_count', 'sql_fetch_cpu_ms', 'sql_fetch_max_batch_ms', 'sql_fetch_ms', 'sql_first_row_cpu_ms', 'sql_first_row_ms', 'sql_status', 'temp_store', 'term_count', 'thread_cpu_ms', 'thread_id', 'thread_non_cpu_ms', 'thread_read_bytes_delta', 'thread_read_chars_delta', 'thread_read_syscalls_delta', 'uses_temp_sort', 'voluntary_switches_delta', 'work_ms'])
_LIVE_FIELD_NAMES = (frozenset({
    'query_count', 'match_count', 'cache_overflow', 'law_count', 'action_count', 'branch_count',
    'sql_count','sql_execute_ms','sql_first_row_ms','sql_fetch_ms','scope_filter_ms','fetched_count',
    'selected_count','begin_ms','body_ms','commit_ms','committed','dropped_count','write_error_count',
    'process_id','sqlite_version','mount_type',
    'cpu_throttled_usec_delta','cpu_nr_throttled_delta',
    "attempt_no", "phase", "schema", "step", "file", "file_size",
    "duration_ms", "remaining_ms", "http_status", "status",
    "work_ms", "thread_cpu_ms", "start_log_ms", "previous_log_ms",
    "previous_event", "previous_step", "elapsed_ms", "diagnostic_revision", "observability_revision",
    "document_count", "unit_count", "checked_count", "cache_hit",
    "team_selected", "request_id", "run_id", "worker_id",
    "scan_elapsed_ms", "scan_limit_ms", "deadline_scope",
    "error_type", "error_code", "failure_kind", "retry_scheduled", "retryable",
    "read_actions", "queued", "selected_count", "read_complete_count",
    "read_partial_count", "source_chars", "answer_chars", "question_chars",
    "ok", "gate", "cycle",
}) | _LIVE_DIAGNOSTIC_FIELD_NAMES) | _FULLTEXT_DIAGNOSTIC_FIELD_NAMES
_LIVE_SCALAR = re.compile(r"[A-Za-z0-9_.:-]{1,96}\Z")
_OPAQUE_KEY = re.compile(r"(^id$|_id$|_ids$|^hash$|_hash$|_sha256$|^seq$|_seq$|^version$|_version$|_revision$|_cursor$)")
_SKIP_EVENTS = frozenset({"MODEL_VIEW", "ATTEMPT_SENT", "TOOL_RESERVED", "STAGE_ARTIFACT",
                          "ACTION_COMPLETED", "PUBLICATION_PREPARED", "PUBLICATION_EXPORTED"})


def _human_value(value: Any) -> Any:
    """Retain substantive model/tool text, omitting bookkeeping identifiers."""
    if isinstance(value, dict):
        return {key: _human_value(item) for key, item in value.items()
                if not _OPAQUE_KEY.search(str(key)) and key not in {
                    "metadata", "binding", "receipt", "source_artifact", "provenance"}}
    if isinstance(value, list):
        return [_human_value(item) for item in value]
    return value


def _model_reply(response: Any) -> Any:
    if not isinstance(response, dict):
        return response
    body = response.get("body_json") or response.get("body") or response
    if isinstance(body, dict):
        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message") or first.get("delta") or {}
                content = message.get("content") if isinstance(message, dict) else None
                if not content and isinstance(message, dict):
                    calls = message.get('tool_calls') or []
                    if len(calls) == 1 and isinstance(calls[0], dict):
                        content = (calls[0].get('function') or {}).get('arguments')
                if isinstance(content, str):
                    try:
                        return json.loads(content)
                    except ValueError:
                        return content
                if content is not None:
                    return content
    return _human_value(body)


def _tool_summary(record: dict[str, Any], *, evidence_count=None) -> dict[str, Any]:
    action = record.get("request") or {}
    args = action.get("args", {}) if isinstance(action, dict) else {}
    result = record.get("result") or {}
    summary: dict[str, Any] = {"tool": record.get("tool"), "status": record.get("status")}
    if type(evidence_count) is int and evidence_count >= 0 and record.get('tool') == 'case_evidence_rebind':
        summary['returned_count'] = evidence_count
        summary['reason'] = '저장된 원문을 현재 요청의 권한·자료 세대와 대조해 재결속'
    if isinstance(args, dict):
        summary["input"] = {key: value for key, value in args.items()
                            if key in {"query", "text", "mode", "view", "relation", "depth"}}
    if isinstance(result, dict):
        if record.get("status") == "ERROR" and result.get("server_reason"):
            summary["server_reason"] = _one_line(result["server_reason"], 600)
        budget = result.get("budget")
        if isinstance(budget, dict) and isinstance(budget.get("duration_ms"), int):
            summary["duration_ms"] = budget["duration_ms"]
        for key in ("reason", "message", "count", "total", "truncated"):
            if key in result:
                summary[key] = result[key]
        for key in ("items", "hits", "matches", "sources", "results"):
            items = result.get(key)
            if isinstance(items, list):
                summary["returned_count"] = len(items)
                summary["examples"] = [
                    {field: _one_line(item[field], 300) for field in
                     ("name", "title", "heading", "label", "text", "snippet", "status")
                     if field in item} if isinstance(item, dict) else _one_line(item, 300)
                    for item in items[:5]]
                break
    return summary


def _live_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and _LIVE_SCALAR.fullmatch(value):
        return value
    return None


def _live_diagnostic_value(key: str, value: Any) -> str | None:
    """Keep missing metadata visible and reject text under numeric/flag keys."""
    if value is None:
        return 'null'
    if key in {'thinking_requested', 'thinking_control_present', 'stream_requested',
               'reasoning_field_present', 'reasoning_nonempty', 'thought_channel_marker_present'}:
        return str(value).lower() if type(value) is bool else None
    if key == 'thinking_observation':
        return value if value in ('unknown', 'no_reasoning_reported', 'reasoning_reported') else None
    if key == 'finish_reason':
        return value if value in ('stop', 'length', 'tool_calls', 'function_call', 'content_filter') else None
    if key == 'diagnostics_version':
        return _live_value(value)
    return str(value) if type(value) is int and value >= 0 else None


def _fulltext_diagnostic_value(key, value):
    """Numbers and fixed status labels only; no question/source text."""
    if value is None:
        return 'null'
    if key in {'uses_temp_sort', 'bounds_enabled'}:
        return str(value).lower() if type(value) is bool else None
    if key == 'search_id':
        return value if isinstance(value, str) and _RUN_ID.fullmatch(value) else None
    if key == 'concurrency_scope':
        return value if value == 'process' else None
    if key in {'sql_status', 'mapping_status'}:
        return value if value in ('completed', 'failed') else None
    if type(value) in (int, float):
        if value == value and abs(value) != float('inf'):
            return str(value) if value >= 0 or key == 'cache_size' else None
    return None

class _LiveLog(logging.Handler):
    """Write progress immediately and mirror the request journal as it commits."""

    def __init__(self, request_id: str, stream, runtime: Path | None = None):
        super().__init__()
        self.request_id = request_id
        self.stream = stream
        self.failed = False
        self.started = time.monotonic()
        self.last_at = self.started
        self.last_heartbeat = self.started
        self.last_event = "request.opened"
        self._opening_written = False
        self.active_steps: list[str] = []
        self.runtime = runtime
        self.run_id: str | None = None
        self.journal_path: Path | None = None
        self.last_seq = 0
        self.poll_error: str | None = None
        self.poll_lock = threading.Lock()
        self.stop_event = threading.Event()
        # Handler.handle acquires its I/O lock only AFTER filters. An unrelated
        # request must not wait on this request's slow NFS write/heartbeat.
        self.addFilter(lambda record: not self.stop_event.is_set() and
                       (getattr(record, 'fields', {}) or {}).get('request_id') == self.request_id)
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.writer = obs.AsyncHandler(self, max_records=512, max_bytes=1024*1024)

    def handle(self, record):
        # Do not acquire the stream/heartbeat lock on the request thread.
        if self.filter(record):self.writer.handle(record)
        return True

    def flush_batch(self):
        if not self.failed:
            try:self.stream.flush()
            except OSError:self._write_failed()

    def _write_failed(self):
        if not self.failed:
            self.failed=True
            obs.event(_REPORT_LOG,'shared_live.write_failed',level=logging.ERROR,
                      request_id=self.request_id,write_error_count=1)

    def start(self) -> None:
        self.heartbeat_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.writer.drain(2)
        self.heartbeat_thread.join(timeout=2)
        self.poll_journal()

    def _heartbeat_loop(self) -> None:
        while not self.stop_event.wait(1):
            self.poll_journal()
            self.heartbeat()

    def write_detail(self, label: str, value: Any, *, stamp: str | None = None) -> None:
        """Append one substantive block, keeping secret redaction."""
        if self.failed:
            return
        timestamp = stamp or datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        safe = _scrub(value)
        from .legal_agent.readable_log import render_detail
        try:
            rendered = render_detail(label, safe)
        except (TypeError, ValueError, KeyError, AttributeError):
            rendered = '판단 요약 미완료 · 형식을 확인할 수 없는 응답입니다. 원본은 요청 JSON 보고서와 journal에 보존합니다.'
        if rendered is None:
            rendered = safe if isinstance(safe, str) else json.dumps(safe, ensure_ascii=False, indent=2, default=str)
        self.acquire()
        try:
            self.stream.write(f"\n{timestamp} === {label} ===\n{rendered}\n")
            self.stream.flush()
            self.last_event = label.replace(" ", ".")
            self.last_at = time.monotonic()
        except OSError:
            self.failed = True
        finally:
            self.release()

    def queue_detail(self, label: str, value: Any) -> None:
        """Initial question tracing must not wait for the shared file writer."""
        record = logging.LogRecord(obs.ROOT + '.request-report', logging.INFO,
                                   __file__, 0, 'shared_trace.detail', (), None)
        record.fields = {'request_id': self.request_id}
        record.live_detail = (label, deepcopy(value))
        self.writer.handle(record)

    def poll_journal(self) -> None:
        with self.poll_lock:
            self._poll_journal()

    def _poll_journal(self) -> None:
        def raw_model_block(data, phase, presented):
            # This is received output, never a request prompt or an inferred
            # pre-filter answer. Preserve content strings without JSON decoding,
            # numbered-reference mapping, whitespace folding or truncation.
            import hashlib
            response = data.get('response')
            response = response if isinstance(response, dict) else {}
            body = response.get('body_json')
            body = body if body is not None else response.get('body')
            choices = body.get('choices') if isinstance(body, dict) else None
            choices = choices if isinstance(choices, list) else []
            request = data.get('request')
            messages = request.get('messages', []) if isinstance(request, dict) else []
            correction = None
            if isinstance(messages, list) and len(messages) > 2:
                try:
                    correction = json.loads(messages[-1].get('content') or '{}')
                except (ValueError, TypeError, AttributeError):
                    pass
            raw = {'raw_log_revision': 'llm-raw-log-20260929-r1',
                'request_id': self.request_id, 'run_id': self.run_id,
                'attempt_id': data.get('attempt_id'), 'logical_call_id': data.get('logical_call_id'),
                'attempt_no': data.get('attempt_no'), 'view_id': data.get('view_id'),
                'phase': phase, 'source_stage': presented.get('source_stage'),
                'model': body.get('model') if isinstance(body, dict) else None,
                'http_status': response.get('status_code'), 'transport_status': data.get('status'),
                'schema_repair': isinstance(correction, dict) and bool(correction.get('repair')),
                'validation_error': correction.get('error') if isinstance(correction, dict) else None,
                'body_sha256': response.get('body_sha256'),
                'response_bytes': response.get('response_bytes'), 'choices': [],
                'received_body': body}
            for index, choice in enumerate(choices):
                if not isinstance(choice, dict):
                    raw['choices'].append({'position': index, 'invalid_choice': choice})
                    continue
                message = choice.get('message') or choice.get('delta') or {}
                message = message if isinstance(message, dict) else {}
                raw['choices'].append({'position': index, 'index': choice.get('index'),
                    'finish_reason': choice.get('finish_reason'),
                    'content': message.get('content'), 'refusal': message.get('refusal'),
                    'tool_calls': message.get('tool_calls'), 'function_call': message.get('function_call')})
            if response.get('body_text') is not None:
                raw['body_text'] = response['body_text']
            if isinstance(body, dict):
                for key in ('error', 'guardrail', 'guardrails', 'guardrail_result',
                            'moderation', 'blocked', 'safety'):
                    if key in body:
                        raw[key] = body[key]
            elif body is not None:
                raw['non_object_body'] = body
            safe = _scrub(raw)
            safe['redaction_applied'] = safe != raw
            lines = [json.dumps({k: v for k, v in safe.items() if k not in ('choices', 'received_body', 'body_text')},
                               ensure_ascii=False, indent=2, default=str)]
            def literal(label, value):
                if isinstance(value, str):
                    lines.append(label + ' chars=' + str(len(value)) + ' sha256=' +
                                 hashlib.sha256(value.encode('utf-8')).hexdigest())
                    lines.extend(['<<< BEGIN ' + label + ' >>>', value, '<<< END ' + label + ' >>>'])
                else:
                    lines.append(label + '=' + json.dumps(value, ensure_ascii=False, default=str))
            for choice in safe['choices']:
                lines.append('choice=' + json.dumps({k: v for k, v in choice.items()
                    if k not in ('content', 'refusal', 'tool_calls', 'function_call')}, ensure_ascii=False))
                literal('message.content', choice.get('content'))
                if choice.get('refusal') is not None:
                    literal('message.refusal', choice['refusal'])
                calls = choice.get('tool_calls')
                for call in calls if isinstance(calls, list) else []:
                    if isinstance(call, dict):
                        function = call.get('function') or {}
                        if isinstance(function, dict):
                            literal('tool_call.function.arguments', function.get('arguments'))
                if choice.get('function_call') is not None:
                    function = choice['function_call']
                    if isinstance(function, dict):
                        literal('function_call.arguments', function.get('arguments'))
            if 'body_text' in safe:
                literal('response.body_text', safe['body_text'])
            # Write on the existing journal/log worker, never the model thread.
            # Failure of the diagnostic sidecar must not suppress the live block.
            try:
                target = self.log_path.with_suffix('.llm_raw.jsonl')
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
                if hasattr(os, 'O_NOFOLLOW'):
                    flags |= os.O_NOFOLLOW
                fd = os.open(target, flags, 0o640)
                with os.fdopen(fd, 'a', encoding='utf-8') as stream:
                    os.fchmod(stream.fileno(), 0o640)
                    stream.write(json.dumps(safe, ensure_ascii=False, default=str) + '\n')
            except (OSError, TypeError, AttributeError):
                lines.append('raw_sidecar_status=UNAVAILABLE; received content remains in this block and journal')
            return '\n'.join(lines)

        if self.failed or self.runtime is None or self.run_id is None:
            return
        try:
            if self.journal_path is None:
                paths = list((self.runtime / "legal-agent" / "runs").glob(f"*/{self.run_id}/journal.sqlite"))
                if len(paths) != 1:
                    return
                self.journal_path = paths[0]
            with sqlite3.connect(f"file:{self.journal_path}?mode=ro", uri=True, timeout=1) as db:
                db.row_factory = sqlite3.Row
                events = db.execute("SELECT * FROM event WHERE seq>? ORDER BY seq", (self.last_seq,)).fetchall()
                if not events:
                    return
                tables = {name for (name,) in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                blocks: list[tuple[int, str, Any, str | None]] = []
                from .progress import ProgressCapture
                projected = []
                projection = ProgressCapture(self.request_id, self.runtime, projected.append)
                projection.run_id = self.run_id
                projection._bind_scope(db)
                scope_row = db.execute("SELECT payload_json FROM event WHERE kind='CASE_EXECUTION_CONTEXT' ORDER BY seq DESC LIMIT 1").fetchone()
                if scope_row and projection.admitted is not None:
                    documents = json.loads(scope_row[0]).get('documents')
                    if isinstance(documents, list) and all(isinstance(d, str) for d in documents) and set(documents)<=projection.admitted:
                        projection.admitted = frozenset(documents)
                for event in events:
                    seq = event["seq"]
                    stamp = event["created_at"] if "created_at" in event.keys() else None
                    payload = json.loads(event["payload_json"])
                    kind = event["kind"]
                    if kind == 'CASE_JUDGMENT_ACCEPTED' and projection.admitted is not None:
                        projected.clear()
                        projection._case_judgment(db, seq)
                        blocks.extend((seq, 'AGENT STAGE RESULT', item, stamp) for item in projected)
                    elif kind == "WORKFLOW_TURN":
                        decision = payload.get("decision", {}) if isinstance(payload, dict) else {}
                        blocks.append((seq, "AGENT DECISION", decision, stamp))
                    elif kind in {"WORKFLOW_REPAIR", "SEMANTIC_REPAIR", "QUESTION_PLAN"}:
                        blocks.append((seq, kind.replace("_", " "), _human_value(payload), stamp))
                    elif kind not in _SKIP_EVENTS and kind not in {
                            "ATTEMPT_RESERVED", "ATTEMPT_FINISHED", "OBSERVATION", "ACTION_PROPOSED"}:
                        from .legal_agent.readable_log import DIAGNOSTIC_EVENTS
                        detail = payload if kind in DIAGNOSTIC_EVENTS else _human_value(payload)
                        if detail:
                            blocks.append((seq, f"AGENT {kind.replace('_', ' ')}", detail, stamp))
                    if kind == "OBSERVATION" and "observation" in tables:
                        for row in db.execute("SELECT * FROM observation WHERE created_seq=?", (seq,)):
                            record = _decode_json_columns(dict(row))
                            evidence_count = None
                            if record.get('tool') == 'case_evidence_rebind' and 'observation_evidence' in tables:
                                evidence_count = db.execute('SELECT COUNT(*) FROM observation_evidence WHERE observation_id=?',
                                    (record['observation_id'],)).fetchone()[0]
                            blocks.append((seq, "TOOL RESULT", _tool_summary(record, evidence_count=evidence_count), stamp))
                    if kind in {"ATTEMPT_RESERVED", "ATTEMPT_FINISHED"} and "model_attempt" in tables:
                        attempt_id = payload.get("attempt_id") if isinstance(payload, dict) else None
                        attempt = db.execute("SELECT * FROM model_attempt WHERE attempt_id=?", (attempt_id,)).fetchone()
                        if attempt is not None:
                            data = _decode_json_columns(dict(attempt))
                            view = db.execute("SELECT phase FROM model_view WHERE view_id=?",
                                              (data.get("view_id"),)).fetchone() if "model_view" in tables else None
                            phase = view["phase"] if view is not None else None
                            if kind == "ATTEMPT_RESERVED":
                                from .legal_agent.readable_log import wire_view
                                presented = wire_view(data.get('request') or {})
                                blocks.append((seq, "MODEL CALL", {
                                    "phase": presented.get('source_stage') or phase,
                                    "view": presented, "attempt": data.get("attempt_no"),
                                    "status": "started"}, stamp))
                            else:
                                reply = _model_reply(data.get("response"))
                                request = data.get('request') or {}
                                messages = request.get('messages', []) if isinstance(request, dict) else []
                                presented = {}
                                if len(messages) > 1 and isinstance(messages[1], dict):
                                    try:
                                        content = json.loads(messages[1].get('content') or '{}')
                                        if isinstance(content, dict) and isinstance(content.get('view'), dict):
                                            presented = content['view']
                                    except (ValueError, TypeError):
                                        pass
                                blocks.append((seq, 'MODEL RAW RESPONSE',
                                               raw_model_block(data, phase, presented), stamp))
                                blocks.append((seq, "MODEL RESPONSE / LLM ANSWER", {
                                    "phase": phase, "status": data.get("status"),
                                    "source_stage": presented.get('source_stage'),
                                    "reply": reply, "view": presented}, stamp))
                projection.close()
            for index, (seq, label, value, stamp) in enumerate(blocks):
                self.write_detail(label, value, stamp=stamp)
                if self.failed:
                    break
                if index + 1 == len(blocks) or blocks[index + 1][0] != seq:
                    self.last_seq = seq
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, sqlite3.OperationalError) and any(
                    item in str(exc).lower() for item in ("locked", "no such table")):
                return
            error = type(exc).__name__
            if error != self.poll_error:
                self.poll_error = error
                self.write_detail("TRACE READER ERROR", {"error_type": error,
                                                         "detail": _one_line(exc, 200)})

    def heartbeat(self) -> None:
        self.acquire()
        try:
            if self.failed:
                return
            now = time.monotonic()
            if now - self.last_at < 9 or now - self.last_heartbeat < 10:
                return
            stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            active = self.active_steps[-1] if self.active_steps else "none"
            line = (f"{stamp} INFO    request.heartbeat elapsed_ms={int((now-self.started)*1000)} "
                    f"idle_ms={int((now-self.last_at)*1000)} last_event={self.last_event} active_step={active}\n")
            try:
                self.stream.write(line)
                self.stream.flush()
                self.last_heartbeat = now
            except OSError:
                self.failed = True
        finally:
            self.release()

    def emit(self, record: logging.LogRecord) -> None:
        fields = getattr(record, "fields", {}) or {}
        if self.failed or (fields.get("request_id") != self.request_id and record.getMessage()!='logging.queue.loss'):
            return
        if hasattr(record, 'live_detail'):
            label, value = record.live_detail
            self.write_detail(label, value, stamp=datetime.fromtimestamp(
                record.created, timezone.utc).isoformat(timespec='milliseconds'))
            return
        run_id = fields.get("run_id")
        if isinstance(run_id, str) and _RUN_ID.fullmatch(run_id):
            self.run_id = run_id
        event = _live_value(record.getMessage())
        if event is None:
            return
        if event == 'request.started':
            if self._opening_written:
                return
            self._opening_written = True
        stamp = datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds")
        details = []
        if 'diagnostics_version' in fields:
            details.append('live_diagnostics_version=thinking-live-20260928-r3')
        for key in sorted(_LIVE_FIELD_NAMES):
            if key in fields:
                safe = (_fulltext_diagnostic_value(key, fields[key]) if key in _FULLTEXT_DIAGNOSTIC_FIELD_NAMES else (_live_diagnostic_value(key, fields[key])
                        if key in _LIVE_DIAGNOSTIC_FIELD_NAMES else _live_value(fields[key])))
                if safe is not None:
                    details.append(f"{key}={safe}")
        try:
            self.stream.write(f"{stamp} {record.levelname:<7} {event}"
                              + (" " + " ".join(details) if details else "") + "\n")
            if isinstance(fields.get('failure_diagnostics'),dict):
                from .legal_agent.readable_log import failure_rows
                self.stream.write('\n'.join(failure_rows(_scrub(fields['failure_diagnostics'])))+'\n')
            if record.exc_info and record.exc_info[0]:
                # The live shared log must show the failing frame and original
                # exception immediately, even if final report publication fails.
                traceback = logging.Formatter().formatException(record.exc_info)
                self.stream.write(obs._redact_secrets(traceback) + "\n")
            elif getattr(record,'async_exception',None):
                self.stream.write(record.async_exception+'\n')
            self.last_event = event
            self.last_at = time.monotonic()
            step = _live_value(fields.get("step"))
            if step and event == "step.started":
                self.active_steps.append(step)
            elif step and event in {"step.finished", "step.failed"} and step in self.active_steps:
                self.active_steps.pop(len(self.active_steps) - 1 - self.active_steps[::-1].index(step))
        except OSError:
            # A transient NFS failure must not turn a RAG answer into HTTP 500.
            self._write_failed()


@contextmanager
def live_log(root: Path, request_id: str, runtime: Path | None = None, *,
             team_id: str = 'unassigned', started_at: datetime | None = None,
             attach: bool = True, component: str = 'legal_agent'):
    """Create a request-scoped NFS .log before work starts and append as it runs."""
    obs.configure()
    directory = report_directory(root, team_id, started_at, component=component)
    safe_id = re.sub(r"[^A-Za-z0-9_.:-]", "_", request_id)[:64]
    path = directory / f"{safe_id}-{uuid.uuid4().hex[:12]}.log"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o640)
    os.fchmod(fd, 0o640)
    stream = os.fdopen(fd, "w", encoding="utf-8", buffering=8192)
    handler = _LiveLog(request_id, stream, runtime)
    handler.log_path = path
    logger = logging.getLogger(obs.ROOT)
    if attach:
        logger.addHandler(handler)
    handler.start()
    try:
        yield path, handler
    finally:
        handler.stop()
        logger.removeHandler(handler)
        handler.close()
        # The writer owns the eventual close even when NFS is still blocked.
        handler.writer.finish(stream.close)
        handler.writer.worker.join(timeout=2)


@contextmanager
def safe_live_log(root: Path, request_id: str, runtime: Path | None = None, **kwargs):
    """Keep NFS logging failure separate from the request result."""
    context = live_log(root, request_id, runtime, **kwargs)
    try:
        path, handler = context.__enter__()
    except (OSError, ValueError) as exc:
        yield None, None, type(exc).__name__
        return
    try:
        yield path, handler, None
    finally:
        context.__exit__(None, None, None)


class _RequestCapture(logging.Handler):
    def __init__(self, request_id: str):
        super().__init__()
        self.request_id = request_id
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        fields = getattr(record, "fields", {}) or {}
        if fields.get("request_id") != self.request_id:
            return
        record = obs.prepared_record(record)
        event = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                 "level": record.levelname, "logger": record.name,
                 "event": record.getMessage(), **record.fields}
        if getattr(record, 'async_exc_type', None):
            event["exc_type"] = record.async_exc_type
        self.events.append(event)


@contextmanager
def capture_events(request_id: str):
    """Collect only this request's existing structured container events."""
    obs.configure()
    handler = _RequestCapture(request_id)
    root = logging.getLogger(obs.ROOT)
    root.addHandler(handler)
    try:
        yield handler.events
    finally:
        root.removeHandler(handler)
        handler.close()


def _scrub(value: Any, *, secrets=None) -> Any:
    if secrets is None:
        secrets = obs._secret_values()
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if any(part in str(key).lower() for part in _SECRET_FIELDS)
                      else _scrub(item, secrets=secrets)) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, secrets=secrets) for item in value]
    if isinstance(value, str):
        return obs._redact_secrets(value, secrets=secrets)
    return value


def _decode_json_columns(row: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(row.items()):
        if key.endswith("_json") and isinstance(value, str):
            try:
                row[key[:-5]] = json.loads(value)
                del row[key]
            except ValueError:
                pass
    return row


def _journal(runtime: Path, run_id: str) -> dict[str, Any]:
    if not _RUN_ID.fullmatch(run_id):
        return {"status": "NO_VALID_RUN_ID"}
    parent = runtime / "legal-agent" / "runs"
    paths = list(parent.glob(f"*/{run_id}/journal.sqlite"))
    if not paths:
        return {"status": "NOT_FOUND"}
    if len(paths) != 1:
        return {"status": "AMBIGUOUS", "matches": len(paths)}
    with sqlite3.connect(f"file:{paths[0]}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        tables: dict[str, list[dict[str, Any]]] = {}
        names = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for name in names:
            quoted_name = name.replace('"', '""')
            rows = db.execute(f'SELECT * FROM "{quoted_name}"').fetchall()
            tables[name] = [_decode_json_columns(dict(row)) for row in rows]
        version = db.execute("PRAGMA user_version").fetchone()[0]
    # Each journal event is followed by records created at that sequence.
    # Rows without an event coordinate are retained once as final state.
    created: dict[int, list[dict[str, Any]]] = {}
    state: dict[str, list[dict[str, Any]]] = {}
    for name, rows in tables.items():
        if name == "event":
            continue
        for row in rows:
            seq = row.get("created_seq")
            if isinstance(seq, int):
                created.setdefault(seq, []).append({"table": name, "record": row})
            else:
                state.setdefault(name, []).append(row)
    timeline = [{"event": row, "created_records": created.get(row["seq"], [])}
                for row in sorted(tables.get("event", []), key=lambda item: item["seq"])]
    return {"status": "FOUND", "journal_version": version, "timeline": timeline, "state": state}


def write_report(root: Path, runtime: Path, *, request_id: str, api_type: str,
                 request: dict[str, Any], result: dict[str, Any],
                 events: list[dict[str, Any]], requested_at: datetime | None = None,
                 live_log_path: Path | None = None, record_id: str | None = None,
                 component: str = 'legal_agent') -> Path:
    """Atomically publish one complete JSON report; callers handle I/O failure."""
    body = result.get("body") if isinstance(result, dict) else None
    run_id = body.get("run_id") if isinstance(body, dict) else None
    requested_at = requested_at or datetime.now(timezone.utc)
    directory = report_directory(root, team_name(request), requested_at, component=component)
    safe_id = run_id if isinstance(run_id, str) and _RUN_ID.fullmatch(run_id) else request_id
    safe_id = re.sub(r"[^A-Za-z0-9_.:-]", "_", safe_id)[:64]
    target = directory / f"{safe_id}-{uuid.uuid4().hex[:12]}.json"
    if record_id is not None:
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', record_id) or record_id in {'.', '..'}:
            raise ValueError('invalid request report record ID')
        target = directory / (record_id + '.json')
    if live_log_path is not None:
        if live_log_path.parent.resolve() != directory.resolve():
            raise ValueError('live log and request report must use the same team/date directory')
        target = live_log_path.with_suffix('.json')
    with obs.step(_REPORT_LOG, 'shared_report.journal'):
        if component == 'ad_mode':
            from .ad_request_report import journal as ad_journal
            journal = ad_journal(runtime, request_id, request)
        else:
            journal = _journal(runtime, run_id) if isinstance(run_id, str) else {"status": "NO_RUN_ID"}
    report = _scrub({
        "schema_version": "genos-request-report-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_at": requested_at.isoformat(),
        "team_id": team_name(request),
        "component": component,
        "live_log_path": str(live_log_path) if live_log_path is not None else None,
        "request_id": request_id,
        "run_id": run_id,
        "api_type": api_type,
        "contains_internal_content": True,
        "coverage": "Recorded application events and journal state, including prompts, model replies, tool results, decisions and final response. Model hidden reasoning is unavailable.",
        "request": request,
        "service_events": events,
        "journal": journal,
        "result": result,
    })
    fd, temporary = tempfile.mkstemp(prefix=".request-report-", dir=directory)
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            with obs.step(_REPORT_LOG, 'shared_report.json'):
                json.dump(report, stream, ensure_ascii=False, indent=2, default=str)
                stream.write("\n")
                stream.flush()
            with obs.step(_REPORT_LOG, 'shared_report.fsync'):
                os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)
    return target


def _one_line(value: Any, limit: int = 800) -> str:
    text = str(value if value is not None else "")
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _event_time(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _action_line(action: Any) -> str:
    if not isinstance(action, dict):
        return "action=invalid"
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    parts = ["tool=" + _one_line(action.get("tool"), 40)]
    for key in ("mode", "query"):
        if key in args:
            parts.append(key + "=" + _one_line(args[key], 160))
    return " ".join(parts)


def format_readable_report(report: dict[str, Any]) -> str:
    """Render a chronological, bounded human trace from the same saved JSON."""
    if report.get('component') == 'ad_mode':
        from .ad_request_report import readable
        return readable(report)
    journal = report.get("journal") or {}
    timeline = journal.get("timeline") or []
    result = report.get("result") or {}
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    answer = body.get("answer") if isinstance(body.get("answer"), dict) else {}
    assembly = body.get("assembly") if isinstance(body.get("assembly"), dict) else {}
    term_agent = assembly.get("term_agent") if isinstance(assembly.get("term_agent"), dict) else {}
    bundle = term_agent.get("source_bundle") if isinstance(term_agent.get("source_bundle"), dict) else {}
    attempts = {}
    for row in timeline:
        for created in row.get("created_records") or []:
            if created.get("table") == "model_attempt":
                record = created.get("record") or {}
                attempts[record.get("attempt_id")] = record

    rows = []
    for index, event in enumerate(report.get("service_events") or []):
        rows.append((_event_time(event.get("ts")), 0, index, "service", event))
    for index, row in enumerate(timeline):
        event = row.get("event") or {}
        rows.append((_event_time(event.get("created_at")), 1, index, "journal", row))
    rows.sort(key=lambda item: item[:3])

    request = report.get("request") if isinstance(report.get("request"), dict) else {}
    if isinstance(request.get("json"), dict):
        request = request["json"]
    lines = ["GENOS 요청 실행 기록", "=" * 24,
             "질문: " + _one_line(request.get("question") or request.get("q")),
             "api_type: " + _one_line(report.get("api_type")),
             "journal: " + _one_line(journal.get("status")),
             "HTTP: " + _one_line(result.get("status")), "", "시간순 이벤트", "-" * 24]
    for timestamp, _, _, source, item in rows:
        stamp = timestamp.isoformat() if timestamp.year > 1 else "time-unknown"
        if source == "service":
            event = item
            fields = []
            for key in (("phase", "schema", "model", "http_status", "error_type", "duration_ms") + tuple(sorted(_LIVE_DIAGNOSTIC_FIELD_NAMES))) + tuple(sorted(_FULLTEXT_DIAGNOSTIC_FIELD_NAMES)):
                if key in _FULLTEXT_DIAGNOSTIC_FIELD_NAMES:
                    if key in event:
                        safe = _fulltext_diagnostic_value(key, event[key])
                        if safe is not None:
                            fields.append(key + '=' + safe)
                else:
                    if key in _LIVE_DIAGNOSTIC_FIELD_NAMES:
                        if key in event:
                            safe = _live_diagnostic_value(key, event[key])
                            if safe is not None:
                                fields.append(key + "=" + safe)
                    elif event.get(key) is not None:
                        fields.append(key + "=" + _one_line(event[key], 100))
            lines.append(f"{stamp} [service/{_one_line(event.get('level'), 16)}] "
                         + _one_line(event.get("event"), 100) + (" " + " ".join(fields) if fields else ""))
            if isinstance(event.get('failure_diagnostics'),dict):
                from .legal_agent.readable_log import failure_rows
                lines.extend(failure_rows(_scrub(event['failure_diagnostics'])))
            continue
        event = item.get("event") or {}
        kind = _one_line(event.get("kind"), 80)
        lines.append(f"{stamp} [journal] {kind}")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        from .legal_agent.readable_log import DIAGNOSTIC_EVENTS, render_detail
        if kind in DIAGNOSTIC_EVENTS:
            lines.append(render_detail('AGENT '+kind.replace('_',' '),_scrub(payload)))
        if kind == "WORKFLOW_TURN":
            decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
            lines.append("  intent=" + _one_line(decision.get("intent"), 40))
            for number, action in enumerate(decision.get("actions") or []):
                lines.append(f"  action[{number}] " + _action_line(action))
        elif kind in ("WORKFLOW_REPAIR", "SEMANTIC_REPAIR"):
            for error in payload.get("errors") or []:
                if isinstance(error, dict):
                    lines.append("  rejected " + _one_line(error.get("field"), 80)
                                 + ": " + _one_line(error.get("message")))
                    for action in error.get("corrective_actions") or []:
                        lines.append("  suggested " + _action_line(action))
        elif kind == "ATTEMPT_FINISHED":
            attempt = attempts.get(payload.get("attempt_id")) or {}
            response = attempt.get("response") if isinstance(attempt.get("response"), dict) else {}
            lines.append("  model_status=" + _one_line(payload.get("status"), 40)
                         + " http_status=" + _one_line(response.get("status_code"), 20))
        for created in item.get("created_records") or []:
            if created.get("table") == "observation":
                observation = created.get("record") or {}
                lines.append("  observation tool=" + _one_line(observation.get("tool"), 40)
                             + " status=" + _one_line(observation.get("status"), 40))

    run = next(iter((journal.get("state") or {}).get("run") or []), {})
    lines.extend(["", "최종 상태", "-" * 24,
                  "run_status: " + _one_line(run.get("status")),
                  "gate: " + _one_line(run.get("gate")),
                  "source_bundle: " + _one_line(bundle.get("status")),
                  "claims: " + str(len(answer.get("claims") or [])),
                  "answer_chars: " + str(len(str(answer.get("text") or ""))),
                  "", "상세 원장: 같은 이름의 .json 파일 (내부 자료 포함)"])
    return "\n".join(lines) + "\n"


def write_readable_report(report_path: Path) -> Path:
    """Write a same-name TXT sidecar without altering the authoritative JSON."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    target = report_path.with_suffix(".txt")
    fd, temporary = tempfile.mkstemp(prefix=".request-trace-", dir=report_path.parent)
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(format_readable_report(report))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)
    return target
