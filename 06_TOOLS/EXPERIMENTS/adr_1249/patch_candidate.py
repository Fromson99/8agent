from pathlib import Path
S=Path('/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_1249/repaired/snapshot')
p=S/'02_BACKEND/semantic_runtime/legal_agent/gateway.py';s=p.read_text()
start=s.index('            except ProposalError as exc:',s.index('raw = self.transport.send_once'))
end=s.index('            body = raw.get',start)
piece=s[start:end]
block="""                if routing:
                    budget=self.repo.budget()
                    limit=budget['model_limit']-(budget['finalization_reserve'] if phase=='investigate' else 0)
                    retry_scheduled=(not exc.unknown and response.get('status_code')==429 and response.get('acceptance')=='KNOWN_REJECTED'
                        and not (projection and projection.emitted) and budget['model_reserved']<limit and self.context.remaining()>1)
                    retry_scheduled=retry_scheduled and provider_routing.switch(self.repo,routing,self.transport.routing_hash,self.context.binding_hash,ident,response)
                    retry_delay=0.0
"""
assert piece.count(block)==2
piece=piece.replace(block,'')
s=s[:start]+piece+s[end:];p.write_text(s)
p=S/'02_BACKEND/lawrag/research/experiment_client.py';s=p.read_text();old="unknown=not isinstance(exc,(httpx.ConnectError,httpx.ConnectTimeout,httpx.PoolTimeout))) from None";assert s.count(old)>=1;s=s.replace(old,old.replace('from None','from exc'),1);p.write_text(s)
p=S/'02_BACKEND/lawrag/research/openrouter_legal_adapter.py';s=p.read_text();s=s.replace("raise TransportError('model transmission failed', retryable=exc.retryable,\n                                 unknown=exc.unknown) from exc", "raise transport_error(exc) from exc")
s+='''\n\ndef transport_error(exc, *, error_type=TransportError):
    """Map a preserved experimental transport cause to the active runtime class."""
    from lawrag.core.request_deadline import AbsoluteDeadlineExceeded
    cause = exc.__cause__
    error = error_type('model transmission failed', retryable=exc.retryable,
                       unknown=exc.unknown,
                       response={'transport_diagnostics': getattr(cause, 'diagnostics', {})})
    if isinstance(cause, AbsoluteDeadlineExceeded):
        error.code = 'MODEL_DEADLINE_EXCEEDED'
        error.http_status = 504
    return error


def send_reserved(client, *, body, ticket, phase, error_module, request_encoder):
    """Honor the native gateway's reservation; no nested provider retry or repair."""
    import time
    client.provider_index = ticket['provider_index']
    client._apply_provider()
    remaining = min(180, float(ticket['remaining_seconds']),
                    float(ticket['deadline']) - time.monotonic())
    if remaining <= 0:
        raise error_module.ContractError('reserved transport deadline exhausted')
    payload = request_encoder(body)
    try:
        # ExperimentClient owns a provider switch for standalone use. Here the
        # native gateway owns that decision and has already reserved one send.
        return super(type(client), client).chat_completions(
            payload, phase=phase, timeout_seconds=remaining)
    except ExperimentTransportError as exc:
        raise transport_error(exc, error_type=error_module.TransportError) from exc
    except (ExperimentProviderError, ExperimentFormatError) as exc:
        response = getattr(exc, 'response', None)
        if not isinstance(response, dict) or type(response.get('status_code')) is not int:
            raise error_module.TransportError('Experiment adapter has no complete response',
                                             retryable=False, unknown=True) from exc
        status = response['status_code']
        if not 200 <= status < 300:
            response = {**response, 'acceptance': 'KNOWN_REJECTED' if status == 429
                        else 'UNKNOWN' if status >= 500 else 'ACCEPTED'}
            raise error_module.TransportError('Experiment provider rejected request',
                response=response, retryable=status == 429, unknown=status >= 500) from exc
        if isinstance(exc, ExperimentFormatError):
            error = error_module.ProposalError('model output format invalid')
            error.format_error = True
            error.response = response
            raise error from exc
        raise error_module.ContractError('Experiment adapter rejected response policy') from exc
'''
p.write_text(s)
print('Candidate changed: gateway, experiment client cause, shared reserved-send adapter')
