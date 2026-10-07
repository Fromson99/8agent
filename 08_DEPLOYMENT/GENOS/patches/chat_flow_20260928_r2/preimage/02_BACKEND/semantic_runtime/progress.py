"""Request-scoped, content-free projection of committed legal-agent activity.

The journal and container logs are audit data, not a chat protocol.  Only
fixed labels and numeric counters leave this module; source titles require a
separate per-user authorization contract that the current workflow lacks.
"""
from __future__ import annotations

from contextlib import contextmanager
import logging
from pathlib import Path
import re
import sqlite3
import threading
import time


_RUN_ID = re.compile(r"[a-f0-9]{32}\Z")
_PHASES = {
    "investigate": "질문과 확인 대상을 검토 중",
    "select_sources": "답변 근거를 선택 중",
    "review": "법적 판단과 예외를 검토 중",
    "compose": "답변 초안을 작성 중",
    "repair": "검토 결과에 따라 다시 확인 중",
    "rebuttal": "반론과 예외를 검토 중",
}
_EVENTS = {
    "request.started": ("phase", "요청을 접수함"),
    "binding.resolved": ("phase", "자료 세대를 확인함"),
    "session.open.ready": ("phase", "질문 범위를 확인함"),
    "bounded_source.started": ("phase", "확인할 원문을 계획 중"),
    "bounded_source.query_plan.finished": ("phase", "검색 계획을 확인함"),
    "source_recall.discover.started": ("phase", "관련 자료를 검색 중"),
    "source_recall.global.finished": ("candidate", "검색 후보를 확인함"),
    "source_recall.scoped.finished": ("candidate", "범위별 검색 후보를 확인함"),
    "source_recall.read.started": ("reading", "후보 원문을 열람 중"),
    "source_recall.read.progress": ("reading", "후보 원문을 열람 중"),
    "source_recall.finished": ("read_complete", "원문 열람을 확인함"),
    "model.attempt.started": ("model_wait", "내부 모델 응답을 기다리는 중"),
    "model.attempt.received": ("phase", "내부 모델 응답을 받음"),
    "model.attempt.failed": ("phase", "내부 모델 호출을 다시 확인 중"),
    "model.attempt.accepted": ("phase", "모델 결과 형식을 검증함"),
    "request.finished": ("phase", "요청 처리를 마침"),
}


class ProgressCapture(logging.Handler):
    def __init__(self, request_id, runtime, sink):
        super().__init__()
        self.request_id = request_id
        self.runtime = Path(runtime)
        self.sink = sink
        self.started = time.monotonic()
        self.seq = 0
        self.run_id = None
        self.last_journal_seq = 0
        self.last_model_phase = None
        self.sequence_lock = threading.Lock()
        self.poll_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.poller = threading.Thread(target=self._poll_loop, daemon=True)

    def start(self):
        self.poller.start()

    def stop(self):
        self.stop_event.set()
        self.poller.join(timeout=2)
        self.poll_journal()

    def publish(self, kind, label, *, count=None, basis=None):
        with self.sequence_lock:
            self.seq += 1
            event = {
                "schema_version": "rag-progress-v1", "request_id": self.request_id,
                "seq": self.seq, "kind": kind, "label": label[:120],
                "elapsed_ms": int((time.monotonic() - self.started) * 1000),
            }
            if self.run_id:
                event["run_id"] = self.run_id
            if type(count) is int and count >= 0:
                event["count"] = count
            if basis is not None:
                event["basis"] = basis
        try:
            self.sink(event)
        except (RuntimeError, OSError):
            # A disconnected progress consumer cannot fail the legal request.
            pass

    def emit(self, record):
        fields = getattr(record, "fields", {}) or {}
        if fields.get("request_id") != self.request_id:
            return
        run_id = fields.get("run_id")
        if isinstance(run_id, str) and _RUN_ID.fullmatch(run_id):
            self.run_id = run_id
        name = record.getMessage()
        mapped = _EVENTS.get(name)
        if mapped is None:
            return
        kind, label = mapped
        if name == "model.attempt.started":
            phase = fields.get("phase")
            self.last_model_phase = phase if phase in _PHASES else None
            if self.last_model_phase:
                label = _PHASES[self.last_model_phase] + " · 내부 모델 대기"
        count_key = "read_actions" if name == "source_recall.read.progress" else (
            "read_complete_count" if name == "source_recall.finished" else "selected_count")
        count = fields.get(count_key)
        self.publish(kind, label, count=count if type(count) is int else None,
                     basis={"kind": "OBS_EVENT", "name": name})

    def _poll_loop(self):
        while not self.stop_event.wait(1):
            self.poll_journal()

    def poll_journal(self):
        if not self.poll_lock.acquire(blocking=False):
            return
        try:
            self._poll_journal()
        finally:
            self.poll_lock.release()

    def _poll_journal(self):
        if not self.run_id:
            return
        try:
            matches = list((self.runtime / "legal-agent" / "runs").glob(
                f"*/{self.run_id}/journal.sqlite"))
            if len(matches) != 1:
                return
            with sqlite3.connect(f"file:{matches[0]}?mode=ro", uri=True, timeout=1) as db:
                rows = db.execute("SELECT seq,kind FROM event WHERE seq>? ORDER BY seq",
                                  (self.last_journal_seq,)).fetchall()
                for seq, event_kind in rows:
                    if event_kind == "OBSERVATION":
                        values = db.execute("SELECT tool,status FROM observation WHERE created_seq=?",
                                            (seq,)).fetchall()
                        for tool, status in values:
                            if tool == "read":
                                count = db.execute("SELECT COUNT(*) FROM observation_evidence oe "
                                    "JOIN observation o USING(observation_id) WHERE o.created_seq=?", (seq,)).fetchone()[0]
                                complete = status in ("OK", "REUSED") and count > 0
                                label = "원문 열람 완료" if complete else "원문 열람 결과를 확인 중"
                                self.publish("read_complete" if complete else "reading",
                                             label, basis={"kind": "OBSERVATION", "journal_seq": seq})
                    elif event_kind in ("SOURCE_SELECTION", "BOUNDED_SOURCE_SELECTION"):
                        selected = db.execute("SELECT COUNT(*) FROM entity_head h JOIN entity_version v "
                            "USING(kind,entity_id,version) WHERE h.kind='source_selection' "
                            "AND h.validity='CURRENT' AND json_extract(v.payload_json,'$.status')='SELECTED'").fetchone()[0]
                        self.publish("selected", "답변 검토용 근거를 선택함", count=selected,
                                     basis={"kind": event_kind, "journal_seq": seq})
                    elif event_kind == "SOURCE_SELECTION_EXCLUDED":
                        self.publish("revised", "이전 근거 선택을 재검토함",
                                     basis={"kind": event_kind, "journal_seq": seq})
                    elif event_kind in ("REVIEW_V2", "REVIEW_V3", "REVIEW", "ANSWER_REVIEW"):
                        self.publish("review", "답변 근거와 판단을 검토함",
                                     basis={"kind": event_kind, "journal_seq": seq})
                    self.last_journal_seq = seq
        except (OSError, sqlite3.Error):
            # Observability must never change the legal answer path.
            return


@contextmanager
def capture(request_id, runtime, sink):
    handler = ProgressCapture(request_id, runtime, sink)
    root = logging.getLogger("genos")
    root.addHandler(handler)
    handler.start()
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        handler.stop()
        handler.close()
