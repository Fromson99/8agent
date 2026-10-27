"""Server-owned question coordinates, immutable request binding, and deadlines."""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import re
import time
import uuid
from ..contracts import digest
from .errors import ContractError, DeadlineExceeded


def now():
    return datetime.now(timezone.utc).isoformat()


def question_pieces(question):
    # Exact, contiguous partition. The model only selects IDs, never numeric offsets.
    pieces, start = [], 0
    for match in re.finditer(r'[?？!！\n]+(?:[ \t]*)|$', question):
        if len(pieces) == 63:
            # Review has a bounded 64-item schema. Preserve the entire remainder
            # as one exact segment instead of dropping text or making review impossible.
            if start < len(question):
                pieces.append({'id': 'Q64', 'text': question[start:], 'start_cp': start, 'end_cp': len(question)})
            break
        end = match.end()
        if end > start:
            pieces.append({'id': f'Q{len(pieces)+1}', 'text': question[start:end], 'start_cp': start, 'end_cp': end})
            start = end
    assert ''.join(p['text'] for p in pieces) == question
    return pieces


@dataclass(frozen=True)
class RequestContext:
    run_id: str
    query: dict
    request: dict
    binding: dict
    deadline: float
    deadline_at: str

    @classmethod
    def create(cls, query, request, binding, wall_seconds, run_id=None):
        run_id = run_id or uuid.uuid4().hex
        if not re.fullmatch('[a-f0-9]{32}', run_id):
            raise ContractError('invalid run ID')
        return cls(run_id, query, request, binding, time.monotonic()+wall_seconds,
                   (datetime.now(timezone.utc)+timedelta(seconds=wall_seconds)).isoformat())

    @property
    def binding_hash(self):
        return digest(self.binding)

    @property
    def pieces(self):
        return question_pieces(self.query['question'])

    def remaining(self):
        left = self.deadline-time.monotonic()
        if left <= 0:
            raise DeadlineExceeded('request deadline exceeded')
        return left
