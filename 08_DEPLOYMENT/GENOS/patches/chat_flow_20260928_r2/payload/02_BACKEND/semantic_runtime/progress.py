"""Request-scoped activity summaries from scoped reads and committed decisions.

Document labels require the server-owned journal binding and admitted scope.
Never project raw model responses, prompts, source text or hidden reasoning.
"""
from __future__ import annotations

from contextlib import contextmanager
import logging
import hashlib
import json
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
_TOOLS = {"search": "관련 자료 검색", "read": "원문 열람", "browse": "목차 확인",
          "follow_reference": "명시 참조 확인", "follow_relations": "연결 근거 확인",
          "inspect_relation": "연결 상세 확인", "locate": "조문 위치 확인",
          "match_terms": "용어 확인", "term_occurrences": "용어 출현 위치 확인"}
_VERDICTS = {"SUPPORTED": "원문 부합", "NEEDS_RESEARCH": "추가 근거 필요",
             "NEEDS_REWRITE": "수정 필요", "ANSWERED": "답변 요구 충족",
             "CONDITIONAL": "조건부 답변", "MISSING_FACT": "사실 확인 필요",
             "READY": "답변 작성 가능", "BOUNDED": "확인된 범위에서 답변",
             "CLARIFY": "추가 사실 확인 필요"}


def _compact(value, limit=180):
    if not isinstance(value, str):
        return ""
    value = " ".join("".join(c if c.isprintable() else " " for c in value).split())
    return value if len(value) <= limit else value[:limit-1] + "…"


def _objects(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


class ProgressCapture(logging.Handler):
    def __init__(self, request_id, runtime, sink):
        super().__init__()
        self.request_id = request_id
        self.runtime = Path(runtime)
        self.sink = sink
        self.started = time.monotonic()
        self.seq = 0
        self.run_id = None
        self.journal_path = None
        self.last_journal_seq = 0
        self.last_model_phase = None
        self.last_wait_key = None
        self.admitted = None
        self.binding_hash = None
        self.pending_reads = {}
        self.seen_reads = set()
        self.last_read_publish = -5.0
        self.sequence_lock = threading.Lock()
        self.poll_lock = threading.RLock()
        self.stop_event = threading.Event()
        self.poller = threading.Thread(target=self._poll_loop, daemon=True)

    def start(self):
        self.poller.start()

    def stop(self):
        self.stop_event.set()
        self.poller.join(timeout=2)
        self.poll_journal()
        self._flush_reads(force=True)

    def publish(self, kind, label, *, count=None, basis=None, details=None):
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
            if details:
                event["details"] = [_compact(d, 300) for d in details[:8]]
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
            if self.run_id is not None and self.run_id != run_id:
                return
            self.run_id = run_id
        name = record.getMessage()
        # Received/accepted are transport/schema diagnostics, not agent steps.
        if name in ("model.attempt.received", "model.attempt.accepted"):
            return
        if name in ("source_recall.read.started", "source_recall.read.progress") and self.admitted is not None:
            # The scoped reader provides document-level activity. Numeric page
            # counters stay in logs rather than interrupting those paragraphs.
            return
        if name == "source.read.started":
            if self.admitted is None:
                self.poll_journal()
            if self.admitted is not None and fields.get("document_id") in self.admitted:
                title = _compact(fields.get("document_name"), 100)
                section = _compact(fields.get("heading"), 80)
                if title:
                    self._queue_read("reading", " · ".join(filter(None, (title, section))),
                                     {"kind": "OBS_EVENT", "name": name})
            return
        mapped = _EVENTS.get(name)
        if mapped is None:
            return
        kind, label = mapped
        if name == "request.finished":
            self.poll_journal()
            self._flush_reads(force=True)
        if name == "model.attempt.started":
            self.poll_journal()
            self._flush_reads(force=True)
            phase = fields.get("phase")
            self.last_model_phase = phase if phase in _PHASES else None
            stage = self._model_stage() if self.admitted is not None else None
            key = stage or self.last_model_phase
            if key is not None and key == self.last_wait_key:
                return
            self.last_wait_key = key
            if self.last_model_phase:
                label = _PHASES[self.last_model_phase] + " · 내부 모델 대기"
                if self.admitted is not None:
                    label = {"source-query-plan": "검색할 문서와 검색어를 정리 중",
                             "source-triage": "읽은 원문에서 질문에 맞는 근거를 선별 중",
                             "source-omission-review": "빠진 근거가 있는지 확인 중",
                             "bounded-question-plan": "질문에서 답해야 할 사항을 정리 중"}.get(stage, label)
        count_key = "read_actions" if name == "source_recall.read.progress" else (
            "read_complete_count" if name == "source_recall.finished" else "selected_count")
        count = fields.get(count_key)
        self.publish(kind, label, count=count if type(count) is int else None,
                     basis={"kind": "OBS_EVENT", "name": name})

    def _journal_path(self):
        if not self.run_id:
            return None
        if self.journal_path is not None:
            return self.journal_path
        matches = list((self.runtime / "legal-agent" / "runs").glob(
            f"*/{self.run_id}/journal.sqlite"))
        if len(matches) == 1:
            self.journal_path = matches[0]
        return self.journal_path

    def _bind_scope(self, db):
        if self.admitted is not None:
            return
        try:
            row = db.execute("SELECT run_id,binding_json,binding_hash FROM run WHERE singleton=1").fetchone()
            if not row or row[0] != self.run_id:
                return
            binding = json.loads(row[1])
            canonical = json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(canonical.encode()).hexdigest() != row[2]:
                return
            scope = binding.get("scope", {}).get("document_version_ids")
            if not isinstance(scope, list) or not all(isinstance(d, str) for d in scope):
                return
            self.admitted, self.binding_hash = frozenset(scope), row[2]
        except (sqlite3.Error, ValueError, TypeError, AttributeError):
            return

    def _model_stage(self):
        try:
            path = self._journal_path()
            if path:
                with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.2) as db:
                    row = db.execute("SELECT body_json FROM model_view ORDER BY created_seq DESC LIMIT 1").fetchone()
                    if row:
                        return json.loads(row[0]).get("source_stage")
        except (OSError, sqlite3.Error, ValueError, AttributeError):
            pass
        return None

    def _queue_read(self, kind, title, basis):
        with self.poll_lock:
            key = (kind, title)
            if key in self.seen_reads:
                return
            self.seen_reads.add(key)
            self.pending_reads[key] = basis
            self._flush_reads()

    def _flush_reads(self, force=False):
        if not self.poll_lock.acquire(blocking=False):
            return
        try:
            if not self.pending_reads or (not force and time.monotonic()-self.last_read_publish < 5):
                return
            for kind in ("reading", "read_complete"):
                rows = [(key, basis) for key, basis in self.pending_reads.items() if key[0] == kind]
                for offset in range(0, len(rows), 8):
                    chunk = rows[offset:offset+8]
                    self.publish(kind, "원문 열람 시작" if kind == "reading" else "원문 열람 결과",
                        count=len(chunk), details=[key[1] for key, _ in chunk], basis=chunk[-1][1])
                    for key, _ in chunk:
                        self.pending_reads.pop(key, None)
            self.last_read_publish = time.monotonic()
        finally:
            self.poll_lock.release()

    def _source_label(self, db, evidence_id):
        if self.admitted is None:
            return None
        row = db.execute("SELECT source_id,document_id,metadata_json FROM evidence_unit WHERE evidence_id=?",
                         (evidence_id,)).fetchone()
        if not row or row[1] not in self.admitted:
            return None
        metadata = json.loads(row[2])
        title = _compact(metadata.get("document_name"), 100)
        if not title:
            return None
        return row[0], " · ".join(filter(None, (title, _compact(metadata.get("heading"), 80))))

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
        self._flush_reads()

    def _poll_journal(self):
        if not self.run_id:
            return
        try:
            path = self._journal_path()
            if path is None:
                return
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.2) as db:
                self._bind_scope(db)
                rows = db.execute("SELECT seq,kind FROM event WHERE seq>? ORDER BY seq",
                                  (self.last_journal_seq,)).fetchall()
                for seq, event_kind in rows:
                    if event_kind == "OBSERVATION":
                        values = db.execute("SELECT tool,status FROM observation WHERE created_seq=?",
                                            (seq,)).fetchall()
                        for tool, status in values:
                            if tool == "read":
                                if self.admitted is not None:
                                    self._read_result(db, seq, status)
                                    continue
                                count = db.execute("SELECT COUNT(*) FROM observation_evidence oe "
                                    "JOIN observation o USING(observation_id) WHERE o.created_seq=?", (seq,)).fetchone()[0]
                                complete = status in ("OK", "REUSED") and count > 0
                                label = "원문 열람 완료" if complete else "원문 열람 결과를 확인 중"
                                self.publish("read_complete" if complete else "reading",
                                             label, basis={"kind": "OBSERVATION", "journal_seq": seq})
                            elif self.admitted is not None and tool in _TOOLS:
                                row = db.execute("SELECT request_json,result_json FROM observation WHERE created_seq=?",
                                                 (seq,)).fetchone()
                                action, result = json.loads(row[0]), json.loads(row[1])
                                query = _compact(action.get("args", {}).get("query"), 120)
                                details = ["검색어: " + query] if query else []
                                if status not in ("OK", "REUSED"):
                                    details.append("결과가 없거나 추가 확인이 필요함")
                                self.publish("candidate", _TOOLS[tool] + " 결과", count=len(result.get("items", [])),
                                             details=details, basis={"kind": "OBSERVATION", "journal_seq": seq})
                    elif event_kind in ("SOURCE_SELECTION", "BOUNDED_SOURCE_SELECTION"):
                        if self.admitted is not None:
                            self._flush_reads(force=True)
                            self._selection(db, seq, event_kind)
                            self.last_journal_seq = seq
                            continue
                        selected = db.execute("SELECT COUNT(*) FROM entity_head h JOIN entity_version v "
                            "USING(kind,entity_id,version) WHERE h.kind='source_selection' "
                            "AND h.validity='CURRENT' AND json_extract(v.payload_json,'$.status')='SELECTED'").fetchone()[0]
                        self.publish("selected", "답변 검토용 근거를 선택함", count=selected,
                                     basis={"kind": event_kind, "journal_seq": seq})
                    elif event_kind == "SOURCE_SELECTION_EXCLUDED":
                        details = []
                        if self.admitted is not None:
                            payload = self._payload(db, seq)
                            row = db.execute("SELECT payload_json FROM entity_version WHERE kind='source_selection' "
                                "AND entity_id=? AND version=?", (payload.get("selection_id"), payload.get("version"))).fetchone()
                            previous = json.loads(row[0]) if row else {}
                            source = self._source_label(db, previous.get("evidence_id"))
                            if source and previous.get("binding_hash") == self.binding_hash:
                                details = [source[1] + " · 이전 선택 철회 · 새 근거 선택으로 대체됨"]
                        self.publish("revised", "이전 근거 선택을 재검토함",
                                     details=details, basis={"kind": event_kind, "journal_seq": seq})
                    elif event_kind in ("REVIEW_V2", "REVIEW_V3", "REVIEW", "ANSWER_REVIEW"):
                        details = self._review(db, seq) if self.admitted is not None else []
                        self.publish("review", "답변 근거와 판단을 검토함", details=details,
                                     basis={"kind": event_kind, "journal_seq": seq})
                    elif event_kind == "QUESTION_PLAN" and self.admitted is not None:
                        payload = self._payload(db, seq).get("plan", {})
                        details = []
                        for demand in _objects(payload.get("demands")):
                            text = _compact(demand.get("requirement"))
                            missing = _compact(demand.get("missing_fact"), 100)
                            if text:
                                details.append(text + (" · 추가 확인: " + missing if missing else ""))
                        self.publish("decision", "질문에서 확인할 사항을 정리함", details=details,
                                     basis={"kind": event_kind, "journal_seq": seq})
                    elif event_kind in ("FINAL_REVIEW_SKIPPED", "FINAL_REVIEW_ADVISORY"):
                        label = ("설정에 따라 추가 최종 검토를 생략함" if event_kind == "FINAL_REVIEW_SKIPPED"
                                 else "최종 검토 결과를 참고 사항으로 기록함")
                        self.publish("review", label, basis={"kind": event_kind, "journal_seq": seq})
                    self.last_journal_seq = seq
        except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError):
            # Observability must never change the legal answer path.
            return

    def _payload(self, db, seq):
        row = db.execute("SELECT payload_json FROM event WHERE seq=?", (seq,)).fetchone()
        value = json.loads(row[0]) if row else {}
        return value if isinstance(value, dict) else {}

    def _read_result(self, db, seq, status):
        ids = db.execute("SELECT oe.evidence_id,o.result_json FROM observation_evidence oe "
                         "JOIN observation o USING(observation_id) WHERE o.created_seq=?", (seq,)).fetchall()
        for ident, result_json in ids:
            source = self._source_label(db, ident)
            if source is None:
                continue
            result = json.loads(result_json)
            coverage = result.get("coverage") or result.get("budget", {}).get("coverage") or {}
            covered = coverage.get("complete")
            complete = status in ("OK", "REUSED") and (covered is True or
                (covered is None and "next_cursor" in result and result["next_cursor"] is None))
            detail = source[1] + (" · 열람 완료" if complete else " · 일부 열람, 나머지 확인 필요")
            self._queue_read("read_complete", detail, {"kind": "OBSERVATION", "journal_seq": seq})

    def _selection(self, db, seq, event_kind):
        values = db.execute("SELECT payload_json FROM entity_version WHERE kind='source_selection' "
                            "AND created_seq=? ORDER BY entity_id,version", (seq,)).fetchall()
        details, seen = [], set()
        for (raw,) in values:
            selection = json.loads(raw)
            # The server has verified this evidence before committing a choice.
            source = self._source_label(db, selection.get("evidence_id"))
            if source is None or selection.get("binding_hash") != self.binding_hash:
                continue
            status, tier = selection.get("status"), selection.get("tier")
            outcome = ("핵심 근거 채택" if tier == "CORE" else "보완 근거 채택") if status == "SELECTED" else {
                "REJECTED": "근거 제외", "DEFERRED": "판단 보류", "EXCLUDED": "근거 제외"}.get(status, "판단 보류")
            reason = _compact(selection.get("relevance_reason") or selection.get("reason"), 120)
            key = source[0], outcome, reason
            if key in seen:
                continue
            seen.add(key)
            details.append(source[1] + " · " + outcome + (" · 이유: " + reason if reason else ""))
        basis = {"kind": event_kind, "journal_seq": seq}
        for start in range(0, len(details), 8):
            chunk = details[start:start+8]
            self.publish("selected", "근거 선택 결과", count=len(chunk), details=chunk, basis=basis)
        if not details:
            self.publish("selected", "근거 선택 결과를 기록함", basis=basis)

    def _review(self, db, seq):
        payload = self._payload(db, seq)
        review = payload.get("review", payload)
        details = []
        for check in _objects(review.get("checks")) + _objects(review.get("obligation_checks")):
            refs = check.get("evidence", [])
            if not isinstance(refs, list) or any(self._source_label(db, ref) is None for ref in refs):
                continue
            outcome = _VERDICTS.get(check.get("verdict") or check.get("status"))
            if outcome:
                source_names = list(dict.fromkeys(self._source_label(db, ref)[1] for ref in refs))
                text = " / ".join(source_names[:2]) + (" · " if source_names else "") + outcome
                reason = _compact(check.get("reason"), 120)
                details.append(text + (" · 이유: " + reason if reason else ""))
        return details


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
