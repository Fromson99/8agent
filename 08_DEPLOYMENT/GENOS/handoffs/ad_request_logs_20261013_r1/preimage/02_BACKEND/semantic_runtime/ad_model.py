"""AD uses the configured GENOS internal LLM and existing single-send transport."""
import hashlib
import json
import math
import os
import time
from .genos import from_env, advertised_model
from .legal_agent.transport import GenosTransport
from .legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
from .provider import _structured_genos_value


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
    payload={'model':model,'temperature':0,'stream':False,'max_tokens':tokens,
        'chat_template_kwargs':{'enable_thinking':False},
        'messages':[{'role':'system','content':system},
                    {'role':'user','content':json.dumps(context,ensure_ascii=False)}],
        'response_format':{'type':'json_schema','json_schema':{'name':'ad_command_v1','strict':True,'schema':schema}}}
    started=time.monotonic()
    envelope=transport.send_once(body=payload,ticket={'remaining_seconds':seconds,'attempt_id':context.get('model_call_id') or context['request_id']})
    raw=envelope['body_json'];plan=None;decode_error=None
    try:
        if not isinstance(raw,dict):raise ValueError('AD_MODEL: model response is not an object')
        if raw.get('model') and raw['model']!=model:raise ValueError('AD_MODEL: response model differs from configured model')
        choices=raw.get('choices') or []
        if not choices or choices[0].get('finish_reason')=='length':raise ValueError('AD_MODEL: incomplete model response')
        plan=_structured_genos_value(raw)
    except Exception as exc:decode_error=str(exc)
    receipt={**binding,'model_call_id':context.get('model_call_id') or context['request_id'],
        'actual_response_model':raw.get('model') if isinstance(raw,dict) else None,
        'seconds':time.monotonic()-started,'usage':raw.get('usage') if isinstance(raw,dict) else None,
        'request_sha256':hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        'response_sha256':envelope.get('body_sha256'),'decode_error':decode_error}
    return {'plan':plan,'receipt':receipt,'raw':raw}
