"""Request-scoped activity summaries from scoped reads and committed decisions.

Document labels require the server-owned journal binding and admitted scope.
Never project raw model responses, prompts, source text or hidden reasoning.
"""
from __future__ import annotations

from .legal_agent import journal_storage
from contextlib import contextmanager
import logging
import hashlib
import json
from .oracle_runtime_paths import Path
from .oracle_dp_io import DPError
from .oracle_query_state import StateConflict
import re
from . import runtime_sqlite as sqlite3
import threading
import time


_RUN_ID = re.compile(r"[a-f0-9]{32}\Z")
REVISION = "rag-live-judgments-20261105-r1"
_WORKFLOW_STAGES = {
    'INTAKE': '대사 요청과 비교 범위를 확인 중',
    'FIND_INTERNAL': '내규 원문을 조사 중',
    'FIND_EXTERNAL': '외규 원문을 조사 중',
    'ITEM_REVIEW': '항목별 내규·외규 근거를 검토 중',
    'DEFINE_CONCEPTS': '찾은 내규의 개념과 조항 범위를 정하는 중',
    'ITEM_RESEARCH': '미확인 항목의 원문을 추가 조사 중',
    'VERIFY_BASIS': '비교할 원문과 근거 연결을 확인 중',
    'REPAIR_SCOPE': '추가로 확인할 비교 범위를 검토 중',
    'COMPARE': '내규·외규의 차이와 적용 범위를 비교 중',
    'REPORT': '대사 결과와 미확인 사항을 정리 중',
}
_DOCUMENT_STAGES = {
    'INTAKE': '문서 대사할 내규 문서를 확인 중',
    'INVENTORY': '문서 전체를 읽기 묶음으로 나누는 중',
    'GROUPS': '문서 전체를 묶음별로 대사 중',
    'REPORT': '문서 대사 결과를 정리 중',
}
_DOCUMENT_WORKFLOW = 'risk_team_document_compare_workflow'
_STAGE_LABELS = dict(zip(
    ("INTENT", "PLAN", "RECALL", "READ", "SELECT", "ASSESS", "COMPOSE"),
    ("질문 이해", "검색 계획", "자료 검색", "원문 확인", "근거 선택", "적용 판단", "답변 작성")))
_CASE_STAGES = {
    "INTENT": ("조사 목적과 적용 개념을 확인 중", "질문의 목적과 확인할 사항을 정리했습니다"),
    "PLAN": ("조사할 문서 범위와 검색 경로를 정리 중", "검색에 사용할 표현을 정했습니다"),
    "RECALL": ("관련 원문 후보를 검색 중", "검색 결과를 확인했습니다"),
    "READ": ("원문과 명시 참조를 열람 중", "확인할 원문을 확보했습니다"),
    "SELECT": ("읽은 원문에서 답변 근거를 선별 중", "답변에 쓸 근거를 선택했습니다"),
    "ASSESS": ("현재 사실과 원문의 조건·단서를 검토 중", "원문을 바탕으로 질문을 판단했습니다"),
    "COMPOSE": ("확인한 판단과 근거로 답변을 작성 중", "확인한 판단과 근거로 답변을 작성했습니다"),
}
_CASE_MODEL_STAGES = {
    "memory-resolve": "질문·정정·최종 확인 요청을 구분 중",
    "memory-resolve-repair": "질문·정정 요청에 맞게 실행 방법을 다시 확인 중",
    "memory-command-check": "요청에 맞는 실행 방법을 확인 중",
    "memory-intent": _CASE_STAGES["INTENT"][0],
    "memory-guided-answer": "확인한 내용과 다음 질문을 정리 중",
    "memory-assess": _CASE_STAGES["ASSESS"][0],
    "memory-assess-check": "현재 판단이 원문과 조건에 맞는지 검토 중",
    "memory-assess-repair": "원문 검토 결과에 따라 현재 판단을 수정 중",
    "memory-compose": _CASE_STAGES["COMPOSE"][0],
    "memory-compose-check": "작성한 답변이 확인된 판단과 근거를 유지하는지 검토 중",
    "memory-compose-repair": "확인된 판단과 근거에 맞춰 답변 표현을 수정 중",
    "memory-history": "저장된 질문·정정 이력을 확인 중",
    "memory-reuse-check": "확정 경험의 조건과 현재 질문을 비교 중",
}
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
    "source_recall.discover.started": ("phase", "관련 자료를 검색 중"),
    "source_recall.global.finished": ("candidate", "검색 후보를 확인함"),
    "source_recall.scoped.finished": ("candidate", "범위별 검색 후보를 확인함"),
    "source_recall.query.finished": ("candidate", "Fulltext 검색으로 원문 후보를 찾음"),
    "source_recall.read.started": ("reading", "후보 원문을 열람 중"),
    "source_recall.read.progress": ("reading", "후보 원문을 열람 중"),
    "source_recall.finished": ("read_complete", "원문 열람을 확인함"),
    "model.attempt.started": ("model_wait", "내부 모델 응답을 기다리는 중"),
    "model.attempt.received": ("phase", "내부 모델 응답을 받음"),
    "model.attempt.failed": ("phase", "내부 모델 호출을 다시 확인 중"),
    "model.output.invalid": ("repair", "모델 응답 형식을 확인 중"),
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
    return value if limit is None or len(value) <= limit else value[:limit-1] + "…"


def _objects(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


class ProgressCapture(logging.Handler):
    def __init__(self, request_id, runtime, sink, *, compact_public=True):
        super().__init__()
        self.request_id = request_id
        self.runtime = Path(runtime)
        self.sink = sink
        self.compact_public = compact_public
        self.started = time.monotonic()
        self.seq = 0
        self.summary_stages = set()
        self.run_id = None
        self.journal_path = None
        self.journal_unavailable = False
        self.last_journal_seq = 0
        self.last_model_phase = None
        self.last_wait_key = None
        self.admitted = None
        self.binding_hash = None
        self.pending_reads = {}
        self.current_read_document = None
        self.law_decision_states = {}
        self.seen_reads = set()
        self.judgment_sequences = {}
        self.vector_previews = []
        self.last_read_publish = -5.0
        self.sequence_lock = threading.Lock()
        self.poll_lock = threading.RLock()
        self.child_captures = {}
        self.workflow_source_reads = False
        self.workflow_stage = None
        self.workflow_id = None
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
                if isinstance(basis,dict) and basis.get('detail_mode') in {'full_error', 'judgment'}:
                    from . import observability as obs
                    event['details'] = [obs._redact_secrets(d) for d in details if isinstance(d,str)]
                else:
                    event["details"] = [_compact(d, 300) for d in details[:8]]
        from .chat_adapter import views
        # Retain scoped source labels for the source-list renderer. Other
        # progress still follows the compact public policy; model I/O remains
        # private. _activity has already checked admitted document identities.
        source_activity = (isinstance(basis, dict) and basis.get('detail_mode') == 'activity'
            and basis.get('kind') in {'LAW_FULLTEXT_DIRECTORY', 'SOURCE_FULLTEXT_RESULTS', 'UNIT_READ_STARTED', 'WORKFLOW_CHECKPOINT', 'WORKFLOW_SOURCE_READ'})
        view = views()
        event = view.public_event(event)
        if event is None:
            return
        if self.compact_public and not (source_activity or view._decision_card(event)):
            event = view.compact_event(event)
            if event is None:
                return
            stage = event['basis']['stage']
            with self.sequence_lock:
                order = views()._SUMMARY_ORDER
                if stage in self.summary_stages or (self.summary_stages and
                        order.index(stage) < max(order.index(s) for s in self.summary_stages)):
                    return
                self.summary_stages.add(stage)
        try:
            self.sink(event)
        except (RuntimeError, OSError):
            # A disconnected progress consumer cannot fail the legal request.
            pass

    def emit(self, record):
        fields = getattr(record, "fields", {}) or {}
        if fields.get("request_id") != self.request_id and fields.get('workflow_request_id') != self.request_id:
            return
        run_id = fields.get('workflow_run_id') or fields.get("run_id")
        if isinstance(run_id, str) and _RUN_ID.fullmatch(run_id):
            if self.run_id is not None and self.run_id != run_id:
                return
            self.run_id = run_id
        name = record.getMessage()
        if name in {'workflow.started', 'workflow.stage.changed', 'workflow.failed'}:
            self.poll_journal()
            return
        if record.levelno >= logging.ERROR or name in {'model.output.invalid', 'model.attempt.failed'}:
            return  # Original record remains in the diagnostic handlers.
        if record.levelno >= logging.ERROR:
            from .request_report import _scrub
            value=fields.get('error_diagnostics') or fields.get('failure_diagnostics')
            if value is not None:
                self.publish('decision','실행 오류 · '+str(fields.get('error_event') or name),
                    details=[json.dumps(_scrub(value),ensure_ascii=False,indent=2,default=str)],
                    basis={'kind':'OBS_EVENT','name':name,'detail_mode':'full_error'})
                return
        # Received/accepted are transport/schema diagnostics, not agent steps.
        if name in ("model.attempt.started", "model.attempt.received", "model.attempt.accepted",
                    "binding.resolved", "session.open.ready", "bounded_source.started",
                    "source_recall.discover.started", "source_recall.global.finished",
                    "source_recall.scoped.finished", "source_recall.query.finished",
                    "source_recall.read.started", "source_recall.read.progress",
                    "source_recall.finished", "source.read.started"):
            return
        mapped = _EVENTS.get(name)
        if mapped is None:
            return
        kind, label = mapped
        if name == "model.output.invalid":
            label = ("모델 응답의 형식·판단 오류를 수정하도록 재요청 중"
                     if fields.get("repair_scheduled") is True
                     else "모델 응답의 형식·판단 오류 수정 횟수를 소진함")
        if name == "request.finished":
            self.poll_journal()
            self._flush_reads(force=True)
            if fields.get('ok') is False:return
        self.publish(kind, label, basis={"kind": "OBS_EVENT", "name": name})

    def _journal_path(self):
        if not self.run_id:
            return None
        if self.journal_path is not None:
            return self.journal_path
        from .request_journals import paths
        matches = paths(self.runtime, self.run_id)
        if len(matches) == 1:
            self.journal_path = matches[0]
        return self.journal_path

    def _bind_scope(self, db):
        try:
            from .request_journals import scope
            value = scope(db, self.run_id)
            if value is None or (self.binding_hash is not None and self.binding_hash != value[1]):
                self.admitted = None
            elif self.admitted is None:
                self.admitted, self.binding_hash = value
        except (sqlite3.Error, ValueError, TypeError, AttributeError):
            self.admitted = None
            return

    def _model_stage(self):
        try:
            path = self._journal_path()
            if path:
                with journal_storage.connect(f"file:{path}?mode=ro", uri=True, timeout=0.2) as db:
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
        return row[0], " · ".join(filter(None, (title, _compact(metadata.get("read_location") or metadata.get("heading"), 160))))

    def _poll_loop(self):
        while not self.stop_event.wait(1):
            self.poll_journal()

    def poll_journal(self):
        if not self.poll_lock.acquire(blocking=False):
            return
        try:
            if self.journal_unavailable:
                return
            self._poll_children()
            self._poll_journal()
        except StateConflict:
            return  # A newer Oracle snapshot can be read at the next poll.
        except DPError as exc:
            # Journal display is optional. Keep the answer and prior cards if
            # the read-only observer loses access or exhausts its own budget.
            self.journal_unavailable = True
            from . import observability as obs
            obs.event(obs.get_logger('progress'), 'progress.journal.unavailable',
                      level=logging.WARNING, request_id=self.request_id,
                      run_id=self.run_id, error_type=type(exc).__name__)
        finally:
            self.poll_lock.release()
        self._flush_reads()

    def _poll_children(self):
        from .request_journals import children
        path = self._journal_path()
        if path is None or path.parent.parent != self.runtime/'workflows':
            return
        try:
            for row in children(path, self.run_id):
                ident = row['run_id']
                if ident not in self.child_captures:
                    # Child completions are not completion of the parent answer.
                    # Only scoped source activity is projected into its stream.
                    def source_sink(event):
                        if (event.get('basis') or {}).get('kind') in {
                                'LAW_FULLTEXT_DIRECTORY', 'SOURCE_FULLTEXT_RESULTS', 'UNIT_READ_STARTED', 'WORKFLOW_SOURCE_READ'}:
                            self.publish(event['kind'], event['label'], count=event.get('count'),
                                         basis=event.get('basis'), details=event.get('details'))
                    child = ProgressCapture(self.request_id, self.runtime, source_sink)
                    child.run_id, child.journal_path = ident, row['path']
                    child.workflow_source_reads = True
                    self.child_captures[ident] = child
                self.child_captures[ident].poll_journal()
                self.child_captures[ident]._flush_reads(force=True)
        except (OSError, sqlite3.Error, ValueError, TypeError):
            return  # Best-effort display; never retries or changes execution.

    def _workflow_checkpoint(self, db, seq, created=False):
        payload = self._payload(db, seq)
        if created:
            self.workflow_id = payload.get('workflow_id')
        if self.workflow_id not in ('risk_team_compare_workflow', _DOCUMENT_WORKFLOW):
            return
        stage = 'INTAKE' if created else payload.get('stage')
        status = 'running' if created else payload.get('status')
        key = (stage, status)
        if key == self.workflow_stage:
            return
        label = (_DOCUMENT_STAGES if self.workflow_id == _DOCUMENT_WORKFLOW else _WORKFLOW_STAGES).get(stage)
        if stage == 'END':
            label = {'completed': '대사 결과를 정리했습니다',
                     'partial': '확인된 범위의 대사 결과와 미확인 사항을 정리했습니다',
                     'failed': '대사 처리를 완료하지 못했습니다'}.get(status)
        if not label:
            return
        self.workflow_stage = key
        self.publish('phase', label, basis={'kind': 'WORKFLOW_CHECKPOINT',
            'journal_seq': seq, 'stage': stage, 'state': status, 'detail_mode': 'activity'})

    def _poll_journal(self):
        if not self.run_id:
            return
        try:
            path = self._journal_path()
            if path is None:
                return
            with journal_storage.connect(f"file:{path}?mode=ro", uri=True, timeout=0.2) as db:
                self._bind_scope(db)
                rows = db.execute("SELECT seq,kind FROM event WHERE seq>? ORDER BY seq",
                                  (self.last_journal_seq,)).fetchall()
                for seq, event_kind in rows:
                    if event_kind in {'WORKFLOW_CREATED', 'WORKFLOW_CHECKPOINT'} and self.admitted is not None:
                        self._workflow_checkpoint(db, seq, event_kind == 'WORKFLOW_CREATED')
                    elif event_kind == 'DOCUMENT_COMPARE_PROGRESS' and self.admitted is not None and self.workflow_id == _DOCUMENT_WORKFLOW:
                        value = self._payload(db, seq)
                        if all(type(value.get(k)) is int for k in ('done', 'total', 'units', 'different')):
                            self.publish('phase', '문서 대사 진행: 읽기 묶음 %d/%d · 대사 단위 %d · 차이 %d건'
                                         % (value['done'], value['total'], value['units'], value['different']),
                                         basis={'kind': 'WORKFLOW_CHECKPOINT', 'journal_seq': seq, 'stage': 'GROUPS',
                                                'state': 'running', 'detail_mode': 'activity'})
                    elif event_kind == "CASE_EXECUTION_CONTEXT":
                        documents = self._payload(db, seq).get("documents")
                        if (self.admitted is not None and isinstance(documents, list)
                                and all(isinstance(d, str) for d in documents)
                                and set(documents) <= self.admitted):
                            self.admitted = frozenset(documents)
                    elif event_kind == "INITIAL_VECTOR_CANDIDATES":
                        self.vector_previews = (self.vector_previews + [self._payload(db, seq)])[-4:]
                    elif event_kind == "CASE_JUDGMENT_ACCEPTED" and self.admitted is not None:
                        self._flush_reads(force=True)
                        self._case_judgment(db, seq)
                    elif self.admitted is not None and event_kind in {
                            'SOURCE_FULLTEXT_RESULTS', 'UNIT_READ_CHOICE',
                            'UNIT_READ_STARTED', 'UNIT_READ_FINISHED', 'LAW_FULLTEXT_DIRECTORY',
                            'LAW_SELECTION_DECISION','LAW_BRANCH_DECISION','LAW_INVESTIGATION_STATUS',
                            'LAW_STRUCTURE_DIRECTORY','LAW_DOCUMENT_STRUCTURE','LAW_STRUCTURE_RECOVERY'}:
                        self._activity(db, seq, event_kind)
                    elif event_kind in {'ATTEMPT_SENT', 'ATTEMPT_FINISHED'}:
                        pass  # Full model I/O remains in the journal and request report.
                    elif event_kind == "MEMORY_FULLTEXT_REENTRY":
                        payload = self._payload(db, seq)
                        queries = payload.get('selection', {}).get('search_queries') or []
                        self.current_read_document = None
                        self.law_decision_states.clear()
                        self.publish("revised", "자료 검색 단계로 돌아갑니다 · 추가 원문이 필요합니다",
                                     details=['새 검색어: '+_compact(q, 120) for q in queries[:4] if isinstance(q, str)],
                                     basis={"kind": event_kind, "journal_seq": seq, "stage": "RECALL"})
                    elif event_kind == "UNIT_CANDIDATE_ACQUISITION_STOPPED":
                        from .legal_agent.readable_log import acquisition_summary
                        payload = self._payload(db, seq)
                        label, details = acquisition_summary(payload)
                        if isinstance(payload.get('diagnostics'),dict):
                            from .legal_agent.investigation_diagnostics import scoped_report
                            from .legal_agent.readable_log import diagnostic_rows
                            diagnostic=scoped_report(payload['diagnostics'],self.admitted or set())
                            details=details[:2]+diagnostic_rows(diagnostic,full=False)
                        if len(details)>8:
                            details=details[:7]+[f'외 {len(details)-7}개 표시 행 · 전체 상세: journal 이벤트 {seq} / 요청 로그']
                        self.publish('decision', label, count=payload.get('read_groups'),
                            basis={'kind':event_kind,'journal_seq':seq,'detail_mode':'activity'}, details=details)
                    elif event_kind in {'REFERENCE_NAVIGATION_STATUS','SOURCE_INVESTIGATION_INCOMPLETE'} and self.admitted is not None:
                        from .legal_agent.investigation_diagnostics import scoped_report
                        from .legal_agent.readable_log import diagnostic_rows
                        diagnostic=scoped_report(self._payload(db,seq),self.admitted)
                        details=diagnostic_rows(diagnostic,full=True)
                        self.publish('decision','연결 조사 중단 사유' if diagnostic['pending'] else '연결 조사 상태 확인',
                            details=details,basis={'kind':event_kind,'journal_seq':seq,'detail_mode':'full_error'})
                    elif event_kind == 'UNIT_FIRST_DECISION_SUFFICIENT':
                        reason = _reason(self._payload(db, seq).get('reason'), 180)
                        self.publish('decision', '현재 원문으로 충분성을 확인해 추가 연결 읽기를 생략함',
                            details=['이유: '+reason] if reason else [],
                            basis={'kind':event_kind,'journal_seq':seq,'detail_mode':'activity'})
                    elif event_kind == 'CASE_STAGE_REENTRY' and self.admitted is not None:
                        payload = self._payload(db, seq)
                        stage = payload.get('stage') or 'SELECT'
                        self.current_read_document = None
                        self.law_decision_states.clear()
                        self.publish('revised', _STAGE_LABELS.get(stage, '근거 선택') + ' 단계로 돌아갑니다',
                            details=[_reason(g.get('reason'), 240) for g in _objects(payload.get('gaps')) if _reason(g.get('reason'), 240)],
                            basis={'kind':event_kind,'journal_seq':seq,'stage':stage})
                    elif event_kind == 'INVESTIGATION_POINT_RETURNED' and self.admitted is not None:
                        payload = self._payload(db, seq)
                        self.current_read_document = None
                        self.law_decision_states.clear()
                        self.publish('revised', '앞서 확인한 자료 검색·열람 단계로 돌아갑니다',
                            details=['이유: '+_reason(payload.get('reason'), 240)],
                            basis={'kind':event_kind,'journal_seq':seq})
                    elif event_kind == 'REFERENCE_GROUP_DECISION' and self.admitted is not None:
                        self._reference_activity(db, seq)
                    elif event_kind == "CASE_RESPONSE_METADATA":
                        status = self._payload(db, seq).get("status")
                        label = {"READY": "현재 질문의 답변 발행을 준비함",
                                 "REUSED": "확정 경험을 현재 질문에 재결속한 답변 발행을 준비함",
                                 "STORED": "사용자가 최종 확인한 경험을 저장함",
                                 "CLARIFY": "다음 조사에 필요한 사실 확인을 요청함",
                                 "REMAPPED": "이 질문의 과거 경험 연결을 수정함"}.get(status)
                        if label and status not in {'READY', 'REUSED'}:
                            self.publish("decision", label,
                                         basis={"kind": event_kind, "journal_seq": seq})
                    elif event_kind == "OBSERVATION":
                        values = db.execute("SELECT tool,status FROM observation WHERE created_seq=?",
                                            (seq,)).fetchall()
                        for tool, status in values:
                            if self.workflow_source_reads and self.admitted is not None and tool in {'read', 'read_node'}:
                                if status in {'OK', 'REUSED'}:
                                    self._read_result(db, seq, status)
                            elif tool == "read":
                                if self.admitted is not None:
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
                            "AND h.validity='CURRENT' AND json_extract(journal_text(v.payload_json),'$.status')='SELECTED'").fetchone()[0]
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
                    elif event_kind == "REQUEST_ROUTED":
                        payload = self._payload(db, seq)
                        mode = payload.get("mode") or ("SEARCH" if payload.get("agent_required") else "DIRECT")
                        labels = {"SEARCH": "법률 검색", "CASE": "관련 법령을 찾아 질문을 검토합니다", "BROWSE": "자료 현황 조회",
                                  "DIRECT": "인사·역할 안내", "OUT_OF_DOMAIN": "서비스 범위 밖"}
                        label = labels.get(mode)
                        if label:
                            reason = _reason(payload.get("reason"), 240)
                            self.publish("decision", "요청 판단: " + label,
                                         details=["이유: " + reason] if reason else [],
                                         basis={"kind": event_kind, "journal_seq": seq})
                    elif event_kind == "FINAL_REVIEW_ADVISORY":
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

    def _activity(self, db, seq, event_kind):
        payload = self._payload(db, seq)
        basis = {'kind': event_kind, 'journal_seq': seq, 'detail_mode': 'activity'}
        if event_kind == 'LAW_FULLTEXT_DIRECTORY':
            rows = [r for r in _objects(payload.get('laws')) if r.get('document_id') in self.admitted]
            names = list(dict.fromkeys(_compact(r.get('name') or r['document_id']) for r in rows))
            # Keep every law on its own line, including pages larger than eight.
            # Actual SQL search words are displayed at the accepted RECALL
            # checkpoint. Its full query expansions remain in the journal.
            for offset in range(0, max(1, len(names)), 8):
                details = names[offset:offset+8]
                self.publish('candidate', '자료 검색 · 관련 법령을 찾았습니다' if names else '자료 검색 · 일치하는 법령이 없습니다',
                    details=details, basis=basis)
            if payload.get('has_more_laws'):
                self.publish('candidate', '자료 검색 · 다음 페이지에도 법령 후보가 있습니다', basis=basis)
            return
        if event_kind in {'LAW_STRUCTURE_DIRECTORY', 'LAW_DOCUMENT_STRUCTURE', 'LAW_STRUCTURE_RECOVERY'}:
            did = payload.get('document_id')
            if did is not None and did not in self.admitted:
                return
            if event_kind == 'LAW_STRUCTURE_DIRECTORY':
                rows = [r for r in _objects(payload.get('items')) if r.get('document_id') in self.admitted]
                if did is None and not rows:
                    # Global misses have no verified document identity to display.
                    return
                fields = payload.get('structure_filter') or {}
                details = [('구조 조건 ' + key + ': ' + _compact(fields[key], 150))
                           for key in ('coordinate', 'title', 'coordinate_scope') if fields.get(key)]
                details += ['구조 검색: ' + _compact(q, 180) for q in payload.get('queries', [])]
                details += ['조회 결과: ' + _compact(payload.get('lookup_status') or '목록')]
                failure = payload.get('failure') or {}
                if failure:
                    details += [_compact(failure.get('code')) + ' · ' + _compact(failure.get('message'), 180),
                                '다음 탐색: ' + _compact(failure.get('suggested_action'), 180)]
                for offset in range(0, max(1, len(rows)), max(1, 8-len(details))):
                    entries = rows[offset:offset+max(1, 8-len(details))]
                    self.publish('candidate', '자료 검색 · 문서 구조 조회', details=details + [
                        _compact(r.get('document_name'), 100) + ' · ' + _compact(r.get('coordinate') or r.get('surface'), 100)
                        + ' · ' + _compact(r.get('title'), 100) for r in entries], basis=basis)
                return
            if event_kind == 'LAW_DOCUMENT_STRUCTURE':
                path = ' → '.join(_compact(r.get('coordinate') or r.get('surface') or r.get('title'), 80)
                                  for r in _objects(payload.get('path')))
                details = [_compact(payload.get('document_name'), 100), '현재 위치: ' + (path or '문서 목차'),
                           '하위 목차: ' + str(payload.get('total', 0)) + '개']
                self.publish('candidate', '자료 검색 · 현재 문서 목차 확인', details=details, basis=basis)
                return
            self.publish('decision', '자료 검색 · 구조 탐색으로 전환', details=[
                _compact(payload.get('document_name'), 100), _compact(payload.get('reason'), 180),
                '원문 추가 확인 없이 후보 페이지 ' + str(payload.get('pages_without_new_original', 0)) + '회',
                _compact(payload.get('next_step'), 180)], basis=basis)
            return
        if event_kind == 'LAW_SELECTION_DECISION':
            law = payload.get('law') or {}
            if law.get('document_id') not in self.admitted:
                return
            selecting = payload.get('status') == 'INVESTIGATE'
            # Repeated navigation turns often reaffirm the same law choice.
            key = law['document_id']
            if self.law_decision_states.get(key) == selecting:
                return
            self.law_decision_states[key] = selecting
            self.publish('decision', '근거 선택 · 이 법령을 검토 대상으로 선택합니다' if selecting else '근거 선택 · 이 법령은 보류합니다',
                details=[_compact(law.get('name')), '이유: ' + _reason(payload.get('reason'), 240)], basis=basis)
            return
        if event_kind == 'LAW_INVESTIGATION_STATUS':
            limitations = [_compact(v, 240) for v in payload.get('completion_limitations', [])]
            if limitations:
                self.publish('decision', '근거 선택 · 추가 확인이 필요한 내용입니다', details=limitations[:3], basis=basis)
            return
        if event_kind == 'SOURCE_FULLTEXT_RESULTS':
            rows = [r for r in _objects(payload.get('locations')) if r.get('document_id') in self.admitted]
            names = list(dict.fromkeys(_compact(r.get('document_name')) for r in rows if r.get('document_name')))
            for offset in range(0, max(1, len(names)), 7):
                self.publish('candidate', '자료 검색 · 본문 검색 결과',
                    details=(['본문 검색어: ' + _compact(payload.get('query'), 280)] if offset == 0 else []) + names[offset:offset+7], basis=basis)
            return
        if event_kind != 'UNIT_READ_STARTED' or payload.get('document_id') not in self.admitted:
            return
        if self.current_read_document == payload['document_id']:
            return
        self.current_read_document = payload['document_id']
        self.publish('reading', '원문 확인 · 법령 본문을 읽기 시작합니다',
            details=[self._activity_name({**payload, 'location': payload.get('read_location') or payload.get('location')})], basis=basis)

    def _reference_activity(self, db, seq):
        payload = self._payload(db, seq)
        anchor, target = payload.get('anchor') or {}, payload.get('target') or {}
        if anchor.get('document_id') not in self.admitted or target.get('document_id') not in self.admitted:
            return
        decision = payload.get('decision') or {}
        action = {'FOLLOW':'연결 근거 읽기 선택','SKIP':'연결 읽기 생략','DEFER':'연결 판단 보류'}.get(decision.get('action'))
        if not action:
            return
        details = ['입력: '+self._activity_name({**anchor,'location':anchor.get('heading')}),
                   '연결 대상: '+self._activity_name({**target,'location':target.get('heading')})]
        reason = _reason(decision.get('reason'), 160)
        if reason:
            details.append('이유: '+reason)
        applicability = _reason(decision.get('applicability_reason'), 160)
        if applicability:
            details.append('적용 판단: '+applicability)
        self.publish('decision', action, details=details,
            basis={'kind':'REFERENCE_GROUP_DECISION','journal_seq':seq,'detail_mode':'activity'})

    @staticmethod
    def _activity_name(row):
        return ' · '.join(filter(None, (_compact(row.get('document_name'), 100),
                                       _compact(row.get('location'), 160))))

    def _model_io(self, db, seq, event_kind):
        """Summarize the actual wire view; model outputs remain proposals here."""
        from .legal_agent.readable_log import input_rows, output_rows, wire_view, phase_label
        event = self._payload(db, seq)
        row = db.execute('SELECT request_json,response_json,status FROM model_attempt WHERE attempt_id=?',
                         (event.get('attempt_id'),)).fetchone()
        if not row:
            return
        request = json.loads(row[0])
        from .detailed_log_storage import is_reference
        if is_reference(request):
            saved=db.execute('SELECT v.body_json FROM model_view v JOIN model_attempt a USING(view_id) WHERE a.attempt_id=?',
                             (event.get('attempt_id'),)).fetchone()
            view=json.loads(saved[0]) if saved else {}
        else:view = wire_view(request)
        stage = view.get('source_stage') or request.get('phase') or '에이전트'
        basis = {'kind': event_kind, 'journal_seq': seq, 'detail_mode': 'activity'}
        if event_kind == 'ATTEMPT_SENT':
            self.publish('model_wait', phase_label(stage) + ' · 입력 전달',
                         details=input_rows(view), basis=basis)
        else:
            from .request_report import _model_reply
            reply = _model_reply(json.loads(row[1])) if row[1] else None
            details = ['출력 상태: ' + row[2]]
            if row[2] == 'SUCCEEDED':
                details += output_rows(reply, view)
            self.publish('decision', '에이전트 출력 수신 · 실행·채택 여부는 후속 검증',
                         details=details, basis=basis)

    def _case_judgment(self, db, seq):
        """Project accepted native v6 checkpoints, never their model/body payloads."""
        event = self._payload(db, seq)
        stage = event.get("stage")
        if stage not in _CASE_STAGES:
            return
        row = db.execute("SELECT payload_json,payload_hash FROM entity_version "
                         "WHERE kind='case_stage' AND entity_id=? AND created_seq=?",
                         ("case:" + stage, event.get("validated_seq", seq))).fetchone()
        if not row:
            return
        newest = db.execute("SELECT MAX(created_seq) FROM entity_version WHERE kind='case_stage' AND entity_id=?", ("case:" + stage,)).fetchone()[0]
        if event.get("validated_seq", seq) != newest or seq <= self.judgment_sequences.get(stage, -1):
            return
        payload = json.loads(row[0])
        actual = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
        if actual != row[1] or actual != event.get("payload_hash"):
            return
        self.judgment_sequences[stage] = seq
        rebound = isinstance(event.get("origin"), dict)
        label = _STAGE_LABELS[stage] + " · " + _CASE_STAGES[stage][1]
        if rebound:
            label = {"INTENT": "확정 경험의 조사 목적을 현재 질문에 재결속함",
                     "PLAN": "확정 경험의 조사 계획을 현재 범위에 재결속함",
                     "RECALL": "확정 경험의 검색 기록을 현재 원문에 재결속함",
                     "READ": "확정 경험의 열람 근거를 현재 원문에 재결속함",
                     "SELECT": "확정 경험의 선택 근거를 현재 원문에 재결속함",
                     "ASSESS": "확정 경험의 판단을 현재 조건에 재결속함"}.get(stage, label)
        basis = {"kind": "CASE_JUDGMENT_ACCEPTED", "journal_seq": seq,
                 "stage": stage, "state": "REBOUND" if rebound else "COMPLETED",
                 "detail_mode": "judgment", "judgment_revision": seq, "payload_hash": actual}
        details, count = [], None
        kind = "phase"
        if stage == "INTENT":
            details = [_compact(i.get('question'), 280) for i in _objects(payload.get('issues')) if i.get('question')][:3]
            purpose = _compact(payload.get('purpose'), 280)
            if purpose and not details:
                details.append({'GENERAL_RULE_EXPLANATION':'법령의 일반 규칙과 정의를 확인합니다',
                                'CASE_APPLICATION':'제시된 상황에 법령을 적용해 판단합니다'}.get(purpose, purpose))
            concepts = [_compact(c, 80) for c in payload.get('concepts', [])
                        if isinstance(c, str) and not c.startswith('system:')]
            if concepts:
                details.append('확인할 개념: ' + ' / '.join(concepts))
        elif stage == "PLAN":
            details = ['본문 검색어: ' + _compact(q, 280) for q in payload.get('queries', []) if isinstance(q, str)]
        elif stage == "RECALL":
            count = len(payload.get("selected_for_read", []))
            catalogue = payload.get('discovery', {}).get('law_navigation', {})
            terms = catalogue.get('terms', [])
            if catalogue.get('search_policy') == 'vector-initial-v1':
                # The first search was vector similarity; the question words were not a body search.
                details = self._vector_candidates(catalogue)
            elif terms:
                details.append('본문 검색에 사용한 단어: ' + ' / '.join(_compact(t, 60) for t in terms))
        elif stage == "READ":
            count = len(payload.get('originals', []))
        elif stage == "SELECT":
            kind = "selected"
            review_pending = bool((payload.get('investigation_state') or {}).get('read_judgments'))
            action = '최종 검토에 전달' if review_pending else '근거 채택'
            if review_pending and not rebound:
                label = '근거 선택 · 최종 검토 대상을 정했습니다'
            reasons = {}
            navigation = payload.get('law_navigation') or {}
            law_reasons = {r.get('law_id'): _reason(r.get('reason'), None)
                           for r in _objects(navigation.get('law_decisions'))}
            for branch in _objects(navigation.get('branches')):
                reasons[branch.get('source_id')] = (_reason(branch.get('reason'), None)
                                                   or law_reasons.get(branch.get('law_id')))
            labels = payload.get("label_to_source", {})
            for decision in _objects(payload.get("decisions")):
                for choice in _objects(decision.get("decision", {}).get("choices")):
                    source = labels.get(choice.get("id"))
                    if source:
                        reasons[source] = _reason(choice.get("reason"), None)
            for source_id in payload.get("final_ids", []):
                originals = _objects(payload.get('selected_originals'))
                if 'selected_originals' in payload:
                    names = list(dict.fromkeys(name for original in originals
                        if original.get('source_id') == source_id
                        for ident in original.get('evidence_ids', [])
                        for name in self._evidence_names(db, ident, source_id)))
                else:
                    names = self._case_source_names(db, source_id)
                reason = reasons.get(source_id)
                if names:
                    details.append(names[0] + " · " + action + (" · 이유: " + reason if reason else ""))
            count = len(details)
        elif stage == "ASSESS":
            kind = "decision"
            claims = _objects(payload.get('claims'))
            for claim in claims:
                labels = self._claim_source_names(db, claim)
                if labels and isinstance(claim.get('text'), str):
                    names = ' / '.join(labels)
                    details.append('현재 판단: ' + _reason(claim['text'], None) + ' · 근거: ' + names)
            count = len(details)
            if not claims and not rebound:
                label = '적용 판단 · 이번 검토에서 확정한 결론이 없습니다'
            limits = payload.get('limitations', [])
            if self.compact_public and 'limitation_items' in payload:
                from .legal_agent.completion_contracts import public_limitations, USER_LIMITATION_PRESENTATION
                limits = public_limitations(payload, {'limitation_presentation': USER_LIMITATION_PRESENTATION})
            details += ['미확인 사항: ' + _reason(v, None) for v in limits if isinstance(v, str)]
        elif stage == "COMPOSE":
            if payload.get('source_excerpt_reply'):
                label = '답변 작성 · 확인한 원문을 정리했습니다'
            else:
                details = ['현재 확정된 판단과 근거를 답변에 배치했습니다']
        if details:
            for start in range(0, len(details), 8):
                self.publish(kind, label, count=count,
                             details=details[start:start+8], basis=basis)
        else:
            self.publish(kind, label, count=count, basis=basis)

    def _vector_candidates(self, catalogue, shown=5):
        rows = [r for r in _objects(catalogue.get('vector_candidates'))
                if self.admitted is None or r.get('document_id') in self.admitted]
        top = [r.get('source_id') for r in rows[:shown]]
        names = {}
        # The preview event precedes this RECALL checkpoint in the same journal (read in seq order).
        for event in reversed(self.vector_previews):
            preview = _objects(event.get('preview'))
            if (event.get('publication_id') == catalogue.get('vector_publication')
                    and [item.get('source_id') for item in preview] == top):
                names = {item['source_id']: item for item in preview}
                break
        dual = catalogue.get('dual') if isinstance(catalogue.get('dual'), dict) else None
        details = [('벡터 후보 ' + str(len(rows)) + '개 · 본문 검색 후보 ' + str(dual.get('fulltext', 0)) + '개 · 따로 표시') if dual else ('벡터·본문 검색 후보 ' + str(len(rows)) + '개 · 합친 순') if catalogue.get('fusion') else ('벡터 후보 ' + str(len(rows)) + '개 · 가까운 순')]
        for sid in top:
            item = names.get(sid) or {}
            label = ' · '.join(v for v in (_compact(item.get('document_name'), 60), _compact(item.get('article'), 60)) if v)
            if label:
                details.append(label)
        if len(rows) > shown:
            details.append('외 ' + str(len(rows) - shown) + '개')
        return details

    def _claim_source_names(self, db, claim):
        sources = dict.fromkeys([claim.get('source_id'), *(item.get('source_id')
            for item in _objects(claim.get('evidence')))])
        if 'span_receipts' not in claim:
            groups = [self._case_source_names(db, source) for source in sources]
            return list(dict.fromkeys(rows[0] for rows in groups)) if all(groups) else []
        spans = _objects(claim['span_receipts'])
        if {span.get('source_id') for span in spans} != sources.keys():
            return []
        labels = []
        for span in spans:
            source = self._source_label(db, span.get('evidence_id'))
            if not source or source[0] != span.get('source_id'):
                return []
            labels.append(source[1])
        return list(dict.fromkeys(labels))

    def _case_source_names(self, db, source_id):
        rows = db.execute("SELECT evidence_id FROM evidence_unit WHERE source_id=?",
                          (source_id,)).fetchall()
        return list(dict.fromkeys(source[1] for row in rows
                                 if (source := self._source_label(db, row[0])) is not None))

    def _evidence_names(self, db, ident, source_id):
        source = self._source_label(db, ident)
        if source is None or source[0] != source_id:
            return []
        row = db.execute('SELECT metadata_json FROM evidence_unit WHERE evidence_id=?', (ident,)).fetchone()
        metadata = json.loads(row[0])
        location = metadata.get('read_location') or metadata.get('heading') or ''
        if not isinstance(location, str) or ' / ' not in location:
            return [source[1]]
        title = _compact(metadata.get('document_name'), 100)
        return [title+' · '+_compact(part, 160) for part in location.split(' / ') if part.strip()]

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
            self._queue_read("read_complete", detail, {"kind": "WORKFLOW_SOURCE_READ" if self.workflow_source_reads else "OBSERVATION",
                "journal_seq": seq, "detail_mode": "activity"})

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
            reason = _reason(selection.get("relevance_reason") or selection.get("reason"), 120)
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
                reason = _reason(check.get("reason"), 120)
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


def _reason(value, limit):
    from .legal_agent.judgment_view import reason_text
    text = reason_text(value)
    for code, label in {'CASE':'법령 조사','START':'새 질문 조사','SUCCEEDED':'처리 완료',
                        'DIRECT':'바로 안내','RESEARCH':'추가 검색','FINISH':'조사 마무리'}.items():
        text = re.sub(r'(?<![A-Za-z0-9_])'+code+r'(?![A-Za-z0-9_])', label, text)
    return _compact(text, limit)
