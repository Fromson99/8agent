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
            raise TransportError('model transmission failed', retryable=exc.retryable,
                                 unknown=exc.unknown) from exc
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
