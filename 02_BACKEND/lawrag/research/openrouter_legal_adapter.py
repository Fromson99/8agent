"""One-physical-send adapter for legal-agent OpenRouter experiments."""
import hashlib

from .experiment_client import (
    PROXY_ENDPOINT,
    ExperimentCallError,
    ExperimentFormatError,
    ExperimentProviderError,
    ExperimentTransportError,
)
from semantic_runtime.legal_agent.errors import (
    BudgetExhausted,
    ContractError,
    ProposalError,
    TransportError,
)


class OpenRouterSingleSendAdapter:
    """Preserve ModelGateway's request and keep physical calls auditable."""

    def __init__(self, client):
        self.client = client
        self.binding = {
            'provider': 'openrouter-experiment',
            'model': client.model,
            'adapter_version': 'openrouter-single-send-v2',
            'endpoint_identity': hashlib.sha256(PROXY_ENDPOINT.encode()).hexdigest(),
            'trust_zone': 'external',
            'max_input_bytes': 2_000_000,
        }

    @property
    def physical_calls(self):
        return self.client.calls

    def validate_model(self):
        return {'verified': True, 'model': self.client.model,
                'mode': 'policy-pinned-experiment-client'}

    def send_once(self, *, body, ticket):
        phase = 'product-' + ticket['attempt_id'][-12:]
        try:
            return self.client.chat_completions(
                body, phase=phase, timeout_seconds=ticket['remaining_seconds'])
        except ExperimentFormatError as exc:
            error = ProposalError('model output format invalid')
            error.response = exc.response
            raise error from exc
        except ExperimentTransportError as exc:
            raise transport_error(exc) from exc
        except ExperimentProviderError as exc:
            if exc.retryable:
                raise TransportError('model provider temporarily failed', retryable=True,
                                     response=exc.response) from exc
            raise ContractError('model provider violated pinned execution policy') from exc
        except ExperimentCallError as exc:
            if str(exc) == 'model_call_budget_exhausted':
                raise BudgetExhausted('experiment client physical call limit') from exc
            raise ContractError('experiment client failed outside transport') from exc
        except ValueError as exc:
            raise ContractError('model request differs from pinned execution policy') from exc


def transport_error(exc, *, error_type=TransportError):
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
