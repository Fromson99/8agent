"""AD uses the configured GENOS internal LLM and existing single-send transport."""
import hashlib
import json
import math
import os
import time
from .genos import from_env, advertised_model
from .legal_agent.transport import GenosTransport
from .legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
from contextlib import contextmanager
from contextvars import ContextVar
from .legal_agent.model_contract import structured_request, structured_value, REVISION
from .legal_agent.errors import ContractError
from .legal_agent import output_contract as output

_REQUEST_RECORDER = ContextVar('ad_model_request_recorder', default=None)


@contextmanager
def capture_requests(recorder):
    token = _REQUEST_RECORDER.set(recorder)
    try:
        yield
    finally:
        _REQUEST_RECORDER.reset(token)


def interpret(context,schema,system):
    target,configured=from_env('llm')
    if not target.headers.get('Authorization'):raise ValueError('AD_MODEL: GENOS_LLM_KEY is required')
    # Same serving ID/model selection as the legal service; no external client,
    # alternate provider, model fallback or legal pipeline bootstrap is used.
    model=configured or advertised_model(target)
    binding={'provider':'genos','trust_zone':'internal','adapter_version':'genos-single-send-v1',
             'model':model,'endpoint_identity':hashlib.sha256(target.root.encode()).hexdigest()}
    transport=GenosTransport(target,binding)
    seconds=target.read_timeout
    if not math.isfinite(seconds) or seconds<=0:raise ValueError('AD_MODEL: GENOS_LLM_TIMEOUT must be positive and finite')
    tokens=int(os.environ.get('GENOS_RAG_MAX_OUTPUT_TOKENS') or DEFAULT_PROFILE['max_output_tokens'])
    if tokens<1:raise ValueError('AD_MODEL: GENOS_RAG_MAX_OUTPUT_TOKENS must be positive')
    payload=structured_request(model=model,max_tokens=tokens,schema_name='ad_command_v1',schema=schema,
        messages=[{'role':'system','content':system},
                  {'role':'user','content':json.dumps(context,ensure_ascii=False)}])
    recorder=_REQUEST_RECORDER.get()
    if recorder is not None:recorder(payload)
    started=time.monotonic()
    envelope=transport.send_once(body=payload,ticket={'remaining_seconds':seconds,'attempt_id':context.get('model_call_id') or context['request_id']})
    raw=envelope['body_json'];plan=None;decode_error=None;failure=None
    try:
        if not isinstance(raw,dict):raise output.OutputContractError('model response is not an object',[output.issue('MODEL_ENVELOPE_INVALID')])
        if raw.get('model')!=model:raise ContractError('AD_MODEL: response model differs from configured model')
        plan=structured_value(raw)
    except (output.ProposalError,ContractError) as exc:
        decode_error=str(exc);failure=output.diagnostics(exc)
    receipt={**binding,'model_contract_revision':REVISION,'model_call_id':context.get('model_call_id') or context['request_id'],
        'http_status':envelope.get('status_code'),'response_bytes':envelope.get('response_bytes'),
        'actual_response_model':raw.get('model') if isinstance(raw,dict) else None,
        'seconds':time.monotonic()-started,'usage':raw.get('usage') if isinstance(raw,dict) else None,
        'request_sha256':hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        'response_sha256':envelope.get('body_sha256'),'decode_error':decode_error,
        'output_contract':failure,'correction_owner':'ad-language'}
    return {'plan':plan,'receipt':receipt,'raw':raw}
