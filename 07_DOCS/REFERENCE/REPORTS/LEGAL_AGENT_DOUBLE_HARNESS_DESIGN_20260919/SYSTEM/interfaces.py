"""Proposed interfaces for implementation. No production controller is implemented."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, ContextManager, Sequence

Json = Mapping[str, Any]

@dataclass(frozen=True)
class RequestContext:
    run_id: str
    query: Json
    binding: Json
    binding_hash: str
    allowed_document_ids: frozenset[str]
    deadline_monotonic: float

@dataclass(frozen=True)
class Snapshot:
    state_revision: int
    evidence_revision: int
    entities: Json
    frontier: tuple[Json, ...]
    binding_hash: str

@dataclass(frozen=True)
class ModelView:
    view_id: str
    phase: str
    base_state_revision: int
    evidence_revision: int
    body: Json
    evidence_ids: tuple[str, ...]

@dataclass(frozen=True)
class AttemptTicket:
    attempt_id: str
    logical_call_id: str
    attempt_no: int
    view_id: str
    deadline_monotonic: float

@dataclass(frozen=True)
class TransportResult:
    status: str
    raw_response: Json | None
    receipt: Json
    error_code: str | None

@dataclass(frozen=True)
class CommitResult:
    state_revision: int
    evidence_revision: int
    assigned_ids: Json
    stale_entities: tuple[Json, ...]

@dataclass(frozen=True)
class Finalization:
    result: Json
    control: Json

class WorkRepository(Protocol):
    def create(self, request: Json, context: RequestContext, profile: Json) -> Snapshot: ...
    def snapshot(self) -> Snapshot: ...
    def save_view(self, view: ModelView) -> None: ...
    def reserve_attempt(self, view: ModelView, *, logical_call_id: str,
                        request_body: Json, phase: str) -> AttemptTicket: ...
    def mark_attempt_sent(self, ticket: AttemptTicket) -> None: ...
    def finish_attempt(self, ticket: AttemptTicket, response: TransportResult) -> None: ...
    def apply_proposal(self, view: ModelView, proposal: Json, *, event_id: str) -> CommitResult: ...
    def record_observation(self, action: Json, observation: Json) -> CommitResult: ...
    def save_stage(self, stage: str, payload: Json, dependency_hash: str) -> str: ...
    def invalidate_from(self, stage: str, reason: str) -> None: ...
    def prepare_publication(self, final_result: Json, destination_key: str) -> str: ...
    def mark_published(self, result_hash: str) -> None: ...

class SourceResources(Protocol):
    def open_for_request(self, context: RequestContext) -> ContextManager[SourceSession]: ...

class SourceSession(Protocol):
    def execute(self, action: Json, context: RequestContext) -> Json: ...
    def materialize_exact_spans(self, spans: Sequence[Json]) -> tuple[Json, ...]: ...

class ModelTransport(Protocol):
    def send_once(self, *, body: Json, ticket: AttemptTicket) -> TransportResult: ...

class ModelGateway(Protocol):
    def generate(self, phase: str, view: ModelView, schema_name: str) -> Json: ...

class StageRunner(Protocol):
    def execute(self, node_id: str, values: Mapping[str, Json], *,
                legal_session: LegalSession) -> Mapping[str, Json]: ...

class LegalSession(Protocol):
    request: Json
    context: RequestContext
    work: WorkRepository
    model: ModelGateway
    sources: SourceSession
    def investigate(self) -> Json: ...
    def select(self, retrieval: Json) -> Json: ...
    def assemble(self, selection: Json) -> Json: ...
    def answer_and_review(self, assembled: Json) -> Finalization: ...
    def source_only(self) -> Json: ...

class LegalCoordinator(Protocol):
    def run(self, session: LegalSession, stages: StageRunner) -> Json: ...

class ServingLegalAgent(Protocol):
    config: Json
    def open_session(self, request: Json, context: RequestContext) -> ContextManager[LegalSession]: ...
    def get_index(self) -> Any: ...
    def retrieve(self, plan: Json, use_llm: bool = False) -> Json: ...

