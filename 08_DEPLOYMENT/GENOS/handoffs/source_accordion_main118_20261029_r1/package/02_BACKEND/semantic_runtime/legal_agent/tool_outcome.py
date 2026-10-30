"""Host-owned tool diagnostics. Pure classification; never retry or infer evidence."""
from dataclasses import asdict, dataclass, replace
import errno
import sqlite3
from jsonschema import ValidationError
from ..contracts import digest
from .errors import (ContractError, ProposalError, StaleProposal, BudgetExhausted,
                     DeadlineExceeded, TransportError, ToolExecutionError)

VERSION = 'tool-outcome-v1'
FAILURE_STATUSES = frozenset(('ERROR', 'NOT_EXECUTED', 'DENIED', 'UNKNOWN'))
_PRIORITY = {'AUTH': 0, 'INTEGRITY': 1, 'STATE': 2, 'UNKNOWN': 3,
             'INTERNAL': 4, 'DEADLINE': 5, 'BUDGET': 6, 'PROPOSAL': 7, 'TRANSIENT': 8}


@dataclass(frozen=True)
class ToolOutcome:
    surface: str
    name: str
    operation_key: str
    action_id: str | None
    binding_hash: str
    status: str
    execution: str
    effects: str
    failure_kind: str | None = None
    cause_code: str | None = None
    receipt_refs: tuple[str, ...] = ()
    remaining_target_refs: tuple[str, ...] = ()
    usage_ref: str = 'request-budget'
    failure_ref: str | None = None
    version: str = VERSION

    def to_dict(self):
        validate_outcome(self)
        value=asdict(self)
        for key in ('receipt_refs','remaining_target_refs'):value[key]=list(value[key])
        return value


def validate_outcome(value):
    if not isinstance(value, ToolOutcome) or value.version != VERSION:
        raise ContractError('unsupported tool outcome')
    if value.status not in {'SUCCESS','EMPTY','PARTIAL','FAILED','BLOCKED','INTERRUPTED'}:
        raise ContractError('invalid tool outcome status')
    if value.execution not in {'NOT_STARTED','STARTED','COMPLETED','UNKNOWN'}:
        raise ContractError('invalid tool execution state')
    if value.effects not in {'NONE','OBSERVATION_COMMITTED','DOMAIN_COMMITTED','UNKNOWN'}:
        raise ContractError('invalid tool effects state')
    if value.failure_kind is not None and value.failure_kind not in _PRIORITY:
        raise ContractError('invalid tool failure kind')
    if value.status in {'SUCCESS','EMPTY'} and (value.failure_kind or value.execution != 'COMPLETED' or value.effects == 'UNKNOWN'):
        raise ContractError('unconfirmed tool success')
    if value.status in {'FAILED','BLOCKED','INTERRUPTED'} and not value.failure_kind:
        raise ContractError('missing tool failure cause')
    if value.execution == 'NOT_STARTED' and value.effects != 'NONE':
        raise ContractError('unstarted tool cannot claim effects')
    if value.effects in {'OBSERVATION_COMMITTED','DOMAIN_COMMITTED'} and not value.receipt_refs:
        raise ContractError('committed tool effects require receipts')
    if value.status == 'PARTIAL' and not value.receipt_refs:
        raise ContractError('partial tool outcome requires receipts')
    if not value.operation_key or not value.binding_hash or not value.usage_ref:
        raise ContractError('tool outcome requires immutable binding and budget reference')
    return value


def from_dict(value):
    row = dict(value)
    for key in ('receipt_refs', 'remaining_target_refs'):
        row[key] = tuple(row.get(key, ()))
    return validate_outcome(ToolOutcome(**row))


def classify_exception(error):
    """A hard failure anywhere in the cause chain overrides a transient wrapper."""
    causes = []; seen = set(); current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        payload = getattr(current, 'tool_outcome', None)
        if payload is not None:
            outcome = from_dict(payload) if isinstance(payload, dict) else validate_outcome(payload)
            if outcome.failure_kind:
                causes.append((outcome.failure_kind, outcome.cause_code))
            if outcome.execution == 'UNKNOWN' or outcome.effects == 'UNKNOWN':
                causes.append(('UNKNOWN', 'TOOL_RECEIPT_UNKNOWN'))
        code = getattr(current, 'code', type(current).__name__)
        if isinstance(current, PermissionError): causes.append(('AUTH', code))
        elif isinstance(current, StaleProposal): causes.append(('STATE', code))
        elif isinstance(current, ContractError): causes.append(('INTEGRITY', code))
        elif isinstance(current, TransportError): causes.append(('UNKNOWN', code))
        elif isinstance(current, DeadlineExceeded): causes.append(('DEADLINE', code))
        elif isinstance(current, BudgetExhausted): causes.append(('BUDGET', code))
        elif isinstance(current, ProposalError): causes.append(('PROPOSAL', code))
        elif isinstance(current, ValidationError): causes.append(('PROPOSAL', 'TOOL_SCHEMA_INVALID'))
        elif isinstance(current, TimeoutError): causes.append(('TRANSIENT', 'SOURCE_TIMEOUT'))
        elif isinstance(current, sqlite3.OperationalError):
            sqlcode = getattr(current, 'sqlite_errorcode', None)
            causes.append(('TRANSIENT' if sqlcode in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else 'INTERNAL',
                           getattr(current, 'sqlite_errorname', None) or 'SOURCE_SQL_ERROR'))
        elif isinstance(current, OSError) and current.errno in (errno.EAGAIN, errno.ETIMEDOUT, errno.ECONNRESET):
            causes.append(('TRANSIENT', 'SOURCE_OS_' + errno.errorcode[current.errno]))
        elif not isinstance(current, ToolExecutionError): causes.append(('INTERNAL', code))
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return min(causes, key=lambda item: _PRIORITY[item[0]]) if causes else ('UNKNOWN', 'UNCLASSIFIED_TOOL_FAILURE')


def exception_outcome(error, *, action, binding_hash, action_id=None, execution='COMPLETED',
                      effects='NONE', receipt_refs=(), remaining_target_refs=(), surface='system'):
    kind, code = classify_exception(error)
    if execution == 'UNKNOWN' or effects == 'UNKNOWN':
        if _PRIORITY[kind] > _PRIORITY['UNKNOWN']: kind, code = 'UNKNOWN', 'TOOL_RECEIPT_UNKNOWN'
    return validate_outcome(ToolOutcome(surface, action['tool'],
        digest({'binding':binding_hash,'tool':action['tool'],'args':action['args']}), action_id,
        binding_hash, 'BLOCKED' if kind in {'AUTH','INTEGRITY','STATE'} else
        'INTERRUPTED' if execution == 'UNKNOWN' else 'FAILED', execution, effects,
        kind, code, tuple(receipt_refs), tuple(remaining_target_refs),
        failure_ref='action_context:'+action_id if action_id else None))


def normalize_result(result, *, action, binding_hash, action_id=None):
    """Old records with no execution receipt stay unknown, never 'not started'."""
    if result.get('tool_outcome'):
        outcome = from_dict(result['tool_outcome'])
        expected = digest({'binding':binding_hash,'tool':action['tool'],'args':action['args']})
        if outcome.operation_key != expected or outcome.binding_hash != binding_hash or outcome.action_id != action_id:
            raise ContractError('tool outcome binding changed')
        return outcome
    status = result.get('status')
    failure = result.get('failure') or {}
    kind = failure.get('kind'); code = failure.get('cause_code') or result.get('error_code')
    execution = failure.get('execution', 'UNKNOWN'); effects = failure.get('effects', 'UNKNOWN')
    receipts = tuple(result.get('evidence_ids', ())) + ((result['observation_id'],) if result.get('observation_id') else ())
    if status == 'DENIED': kind, execution, effects = 'AUTH', 'NOT_STARTED', 'NONE'
    elif status == 'NOT_EXECUTED':
        kind = kind or 'UNKNOWN'
        execution, effects = failure.get('execution', 'NOT_STARTED'), 'NONE'
    elif status in FAILURE_STATUSES: kind = kind or 'UNKNOWN'
    elif status in {'OK','REUSED','EMPTY','NOT_FOUND','PARTIAL','TRUNCATED','UNRESOLVED'}:
        if status in {'PARTIAL','TRUNCATED','UNRESOLVED'} and not receipts:
            return validate_outcome(ToolOutcome('system',action['tool'],
                digest({'binding':binding_hash,'tool':action['tool'],'args':action['args']}),action_id,
                binding_hash,'INTERRUPTED','UNKNOWN','UNKNOWN','UNKNOWN','PARTIAL_RECEIPT_MISSING'))
        execution, effects = 'COMPLETED', 'OBSERVATION_COMMITTED' if receipts else 'NONE'
        normalized = 'PARTIAL' if status in {'PARTIAL','TRUNCATED','UNRESOLVED'} else 'EMPTY' if status in {'EMPTY','NOT_FOUND'} else 'SUCCESS'
        return validate_outcome(ToolOutcome('system',action['tool'],
            digest({'binding':binding_hash,'tool':action['tool'],'args':action['args']}),action_id,
            binding_hash,normalized,execution,effects,receipt_refs=receipts))
    else: kind, code = 'UNKNOWN', 'UNRECOGNIZED_TOOL_STATUS'
    return validate_outcome(ToolOutcome('system',action['tool'],
        digest({'binding':binding_hash,'tool':action['tool'],'args':action['args']}),action_id,
        binding_hash,'BLOCKED' if kind in {'AUTH','INTEGRITY','STATE'} else 'FAILED',execution,effects,
        kind,code or 'LEGACY_TOOL_FAILURE', receipts))


def failure_details(error, *, execution='COMPLETED'):
    kind, code = classify_exception(error)
    return {'kind':kind,'cause_code':code,'execution':execution,'effects':'NONE',
            'error_type':type(error).__name__,'sqlite_errorcode':getattr(error,'sqlite_errorcode',None)}
