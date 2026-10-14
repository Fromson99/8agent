"""Model/runtime failures must not become HTTP request-validation errors."""


class LegalAgentError(RuntimeError):
    code = 'LEGAL_AGENT_FAILURE'
    http_status = 500


class ContractError(LegalAgentError):
    code = 'INTERNAL_CONTRACT_ERROR'


class ToolExecutionError(LegalAgentError):
    code = 'SOURCE_TOOL_ERROR'


class ProposalError(LegalAgentError):
    code = 'MODEL_PROPOSAL_INVALID'
    http_status = 502


class StaleProposal(ProposalError):
    code = 'STALE_PROPOSAL'


class BudgetExhausted(LegalAgentError):
    code = 'BUDGET_EXHAUSTED'


class DeadlineExceeded(BudgetExhausted):
    code = 'DEADLINE_EXCEEDED'
    http_status = 504


class AdmissionRejected(LegalAgentError):
    code = 'ADMISSION_REJECTED'
    http_status = 503


class TransportError(LegalAgentError):
    code = 'MODEL_TRANSPORT_ERROR'
    http_status = 502

    def __init__(self, message, *, retryable=False, unknown=False, response=None):
        super().__init__(message)
        self.retryable, self.unknown, self.response = retryable, unknown, response


class PublicationConflict(LegalAgentError):
    code = 'PUBLICATION_CONFLICT'


class InvestigationPending(LegalAgentError):
    code = 'SOURCE_INVESTIGATION_INCOMPLETE'
    http_status = 422

    def __init__(self, message, *, stage='SELECT', diagnostics=None):
        super().__init__(message)
        self.failure_stage = stage
        self.diagnostics = diagnostics or {}
