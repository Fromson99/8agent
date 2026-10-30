"""Attach failure receipts to the existing action journal; no retry owner here."""
from functools import wraps
import json
from dataclasses import replace
from ..contracts import digest
from .repository import encoded
from .errors import ContractError, ProposalError, StaleProposal, ToolExecutionError
from .tool_outcome import FAILURE_STATUSES, exception_outcome, normalize_result


def _save(session, action_id, result, outcome):
    payload = outcome.to_dict()
    result = {**result, 'tool_outcome':payload, 'outcome_version':outcome.version,
              'outcome_ref':'action_context:'+action_id}
    with session.repo.transaction():
        session.repo.event('TOOL_OUTCOME_RECORDED', {'action_id':action_id,'outcome':payload})
        session.repo.db.execute('UPDATE action_context SET status=?,result_json=? WHERE action_id=?',
                               (result['status'],encoded(result),action_id))
    return result


def recorded_execution(function):
    @wraps(function)
    def execute(session, action, action_id, **kwargs):
        # Same ID is a journal read, including failed executions. Check identity
        # before inspecting the outcome so another action cannot borrow it.
        old = session.repo.db.execute('SELECT * FROM action_context WHERE action_id=?',(action_id,)).fetchone()
        if old and (old['proposal_hash'] != digest(action) or old['actor'] != (kwargs.get('actor') or session._actor)):
            error=ProposalError('action ID reused with different canonical proposal')
            error.tool_outcome=exception_outcome(StaleProposal('action identity conflict'),action=action,
                binding_hash=session.context.binding_hash,action_id=action_id,execution='NOT_STARTED')
            raise error
        if old and old['result_json']:
            prior = json.loads(old['result_json'])
            if prior.get('tool_outcome'):
                outcome = normalize_result(prior,action=action,binding_hash=session.context.binding_hash,action_id=action_id)
                if prior.get('raised_exception'):
                    raise ToolExecutionError('recorded source tool failure: '+str(outcome.cause_code),outcome=outcome)
        prior_phase = getattr(session, '_tool_receipt_phase', None)
        session._tool_receipt_phase = 'admission'
        try:
            result = function(session, action, action_id, **kwargs)
            if result.get('status') in FAILURE_STATUSES and not result.get('tool_outcome'):
                outcome = normalize_result(result,action=action,binding_hash=session.context.binding_hash,action_id=action_id)
                session._tool_receipt_phase = 'receipt'
                result = _save(session,action_id,result,outcome)
            return result
        except Exception as error:
            try:
                row = session.repo.db.execute('SELECT * FROM action_context WHERE action_id=?',(action_id,)).fetchone()
            except Exception as storage_error:
                outcome=exception_outcome(error,action=action,binding_hash=session.context.binding_hash,
                    action_id=action_id,execution='UNKNOWN',effects='UNKNOWN')
                raised=ToolExecutionError('tool journal could not be inspected',outcome=outcome)
                raised.receipt_error_type=type(storage_error).__name__
                raise raised from error
            if row is None: raise  # Intent was not saved: do not execute or invent a receipt.
            if row['result_json'] and json.loads(row['result_json']).get('status') not in FAILURE_STATUSES:
                # A later prefetch may fail after this action committed. Its own
                # receipt owns that failure; never overwrite this success.
                raise
            phase = session._tool_receipt_phase
            unknown = phase in ('observation','receipt') or (old is not None and not old['result_json'])
            outcome = exception_outcome(error,action=action,binding_hash=session.context.binding_hash,
                action_id=action_id, execution='UNKNOWN' if unknown else 'NOT_STARTED' if phase=='admission' else 'COMPLETED',
                effects='UNKNOWN' if unknown else 'NONE')
            result = {'status':'UNKNOWN' if unknown else 'ERROR', 'items':[], 'evidence_ids':[],
                      'next_cursor':None,'raised_exception':True,'error_code':outcome.cause_code,
                      'server_reason':str(error),'failure_stage':phase}
            if not unknown and row['result_json']:
                # Admission already committed its established NOT_EXECUTED
                # result (including budget exhaustion). Preserve replay shape.
                result=json.loads(row['result_json'])
            try:
                _save(session,action_id,result,outcome)
            except Exception as storage_error:
                # A failed mandatory write cannot become a recoverable read.
                outcome = replace(outcome,status='INTERRUPTED',execution='UNKNOWN',effects='UNKNOWN',
                                  failure_kind='UNKNOWN',cause_code='TOOL_RECEIPT_WRITE_FAILED')
                raised = ToolExecutionError('tool failure receipt could not be saved',outcome=outcome)
                raised.receipt_error_type = type(storage_error).__name__
                raise raised from error
            if isinstance(error, ToolExecutionError):
                error.tool_outcome = outcome
                raise
            # Preserve established exception catches for admission/deadline/ACL.
            error.tool_outcome = outcome
            raise
        finally:
            session._tool_receipt_phase = prior_phase
    return execute
