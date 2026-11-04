"""AD uses the configured GENOS internal LLM and existing single-send transport."""
import hashlib
import json
import math
import time
from .genos import from_env, advertised_model
from .legal_agent.transport import GenosTransport
from contextlib import contextmanager
from contextvars import ContextVar
from .legal_agent.model_contract import (structured_request, structured_value, REVISION,
                                        validate_response_model, response_model_metadata)
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
    payload=structured_request(model=model,max_tokens=None,schema_name='ad_command_v1',schema=schema,
        messages=[{'role':'system','content':system},
                  {'role':'user','content':json.dumps(context,ensure_ascii=False)}])
    from .legal_agent.minimal_output import prepare_request
    payload,projection=prepare_request(payload,schema)
    recorder=_REQUEST_RECORDER.get()
    if recorder is not None:recorder(payload)
    started=time.monotonic()
    envelope=transport.send_once(body=payload,ticket={'remaining_seconds':seconds,'attempt_id':context.get('model_call_id') or context['request_id']})
    raw=envelope['body_json'];plan=None;decode_error=None;failure=None
    try:
        if not isinstance(raw,dict):raise output.OutputContractError('model response is not an object',[output.issue('MODEL_ENVELOPE_INVALID')])
        validate_response_model(binding,raw)
        plan=structured_value(raw, allow_length_repair=False)
        plan=projection.expand(plan)
    except (output.ProposalError,ContractError) as exc:
        decode_error=str(exc);failure=output.diagnostics(exc)
    receipt={**binding,'model_contract_revision':REVISION,'model_call_id':context.get('model_call_id') or context['request_id'],
        'http_status':envelope.get('status_code'),'response_bytes':envelope.get('response_bytes'),
        **response_model_metadata(binding,raw),
        'seconds':time.monotonic()-started,'usage':raw.get('usage') if isinstance(raw,dict) else None,
        'request_sha256':hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        'response_sha256':envelope.get('body_sha256'),'decode_error':decode_error,
        'output_contract':failure,'correction_owner':'ad-language',
        'minimal_output':projection.receipt}
    return {'plan':plan,'receipt':receipt,'raw':raw}
