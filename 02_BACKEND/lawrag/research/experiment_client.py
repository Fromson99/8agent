"""Audited Gemini transport for new external experiments, never a serving fallback."""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import time
import httpx
import jsonschema
from dotenv import dotenv_values

ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta'
MODEL = 'gemini-3.1-flash-lite'

class ExperimentCallError(RuntimeError):
    pass

class ExperimentTransportError(ExperimentCallError):
    """No valid provider response was received."""
    def __init__(self, message, *, retryable=True, unknown=True):
        super().__init__(message)
        self.retryable=retryable;self.unknown=unknown

class ExperimentFormatError(ExperimentCallError):
    """The provider replied, but the model output violated its contract."""
    format_error = True
    def __init__(self, message, *, response=None):
        super().__init__(message);self.response=response

class ExperimentProviderError(ExperimentCallError):
    """The provider replied with an HTTP, routing, model, or policy error."""
    def __init__(self, message, *, response=None, retryable=False):
        super().__init__(message)
        self.response=response;self.retryable=retryable

def load_policy(root: Path) -> dict:
    path = root / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'
    policy = json.loads(path.read_text())
    selected = (policy.get('provider'), policy.get('model'), policy.get('endpoint'))
    if (policy.get('schema_version') != 'experiment-model-policy-v1'
            or selected not in {('gemini', MODEL, ENDPOINT),
                ('openrouter', 'qwen/qwen3.5-122b-a10b', 'https://openrouter.ai/api/v1'),
                ('openrouter', 'google/gemma-4-31b-it', 'https://openrouter.ai/api/v1'),
                ('openrouter', 'qwen/qwen3.8-27b', 'https://openrouter.ai/api/v1')}
            or policy.get('allowed_models') != [policy.get('model')]
            or policy.get('fallback_allowed') is not False):
        raise ValueError('Invalid experiment model policy')
    return policy

def _output_tokens(policy, requested):
    """A provider-managed policy cannot be capped by an older experiment runner."""
    return None if policy['max_output_tokens'] is None else requested or policy['max_output_tokens']

def _apply_output_policy(payload, policy):
    if policy['max_output_tokens'] is None:
        for key in ('max_tokens', 'max_completion_tokens', 'max_output_tokens'):
            payload.pop(key, None)

def _schema_for_api(schema: dict) -> dict:
    # Keep full original schema for local validation, including uniqueness/length.
    unsupported = {'uniqueItems', 'minLength', 'maxLength', 'pattern', '$schema'}
    def convert(value):
        if isinstance(value,list):return [convert(x) for x in value]
        if not isinstance(value,dict):return value
        out={}
        for k,v in value.items():
            if k in unsupported:continue
            if k in {'properties','$defs','definitions'}:
                out[k]={name:convert(child) for name,child in v.items()}
            else:out[k]=convert(v)
        return out
    return convert(schema)

class GeminiExperimentClient:
    def __init__(self, root: Path, output: Path, *, max_calls=24,
                 max_output_tokens=None, transport=None):
        self.root=Path(root).resolve();self.output=Path(output)
        self.policy=load_policy(self.root);self.model=self.policy['model']
        if self.policy['provider'] != 'gemini':
            raise ValueError('Gemini is no longer the experiment default; use ExperimentClient')
        env=dotenv_values(self.root/'.env')
        names=[self.policy['key_env'],*self.policy.get('key_env_aliases',[])]
        self._key=next((os.environ.get(k) or env.get(k) for k in names if os.environ.get(k) or env.get(k)),None)
        if not self._key:raise ExperimentCallError('Missing GEMINI_API_KEY')
        self.max_calls=max_calls;self.calls=0;self.usage=[];self.transport=transport
        self.max_output_tokens=_output_tokens(self.policy,max_output_tokens)
        self.output.mkdir(parents=True,exist_ok=True)
        self.policy_hash=hashlib.sha256((self.root/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_bytes()).hexdigest()

    def _write(self,path,value):
        text=json.dumps(value,ensure_ascii=False,indent=2)
        if self._key in text:raise ExperimentCallError('Credential found in artifact; refusing to save')
        path.write_text(text+'\n')

    def generate(self, system: str, data, schema: dict, *, images=(), phase='generate'):
        if self.calls >= self.max_calls:raise ExperimentCallError('model_call_budget_exhausted')
        if not phase or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in phase):
            raise ValueError('Invalid phase name')
        jsonschema.Draft202012Validator.check_schema(schema)
        parts=[{'text':json.dumps(data,ensure_ascii=False)}]
        for uri in images:
            header,blob=uri.split(',',1)
            if header not in {'data:image/png;base64','data:image/jpeg;base64','data:image/webp;base64'}:
                raise ValueError('Only inline PNG/JPEG/WebP evidence supported')
            base64.b64decode(blob,validate=True)
            parts.append({'inlineData':{'mimeType':header[5:].split(';')[0],'data':blob}})
        payload={'systemInstruction':{'parts':[{'text':system}]},
                 'contents':[{'role':'user','parts':parts}],
                 'generationConfig':{'temperature':self.policy['temperature'],
                    **({'maxOutputTokens':self.max_output_tokens} if self.max_output_tokens is not None else {}),'thinkingConfig':{'thinkingLevel':self.policy['thinking_level']},
                    'responseMimeType':'application/json','responseJsonSchema':_schema_for_api(schema)}}
        self.calls+=1;out=self.output/f'call-{self.calls:03d}-{phase}';out.mkdir(exist_ok=False)
        self._write(out/'request.json',payload)
        self._write(out/'validation-schema.json',schema)
        self._write(out/'binding.json',{'provider':'gemini','model':self.model,'endpoint':ENDPOINT,'policy_sha256':self.policy_hash,'images':len(images)})
        start=time.monotonic()
        try:
            with httpx.Client(timeout=120,trust_env=False,follow_redirects=False,transport=self.transport) as client:
                response=client.post(f'{ENDPOINT}/models/{self.model}:generateContent',headers={'x-goog-api-key':self._key},json=payload)
        except httpx.HTTPError as exc:
            self._write(out/'error.json',{'error':type(exc).__name__,'seconds':time.monotonic()-start})
            raise ExperimentCallError('Gemini transport failed: '+type(exc).__name__) from None
        try:raw=response.json()
        except ValueError:
            self._write(out/'error.json',{'http_status':response.status_code,'error':'Non-JSON response'})
            raise ExperimentCallError('Gemini returned non-JSON response') from None
        self._write(out/'response.json',raw)
        if not response.is_success:
            raise ExperimentCallError(f'Gemini HTTP {response.status_code}; response saved without request headers')
        usage=raw.get('usageMetadata',{})
        receipt={'call':self.calls,'phase':phase,'provider':'gemini','model':raw.get('modelVersion'),
                 'seconds':round(time.monotonic()-start,3),'input_tokens':usage.get('promptTokenCount'),
                 'output_tokens':usage.get('candidatesTokenCount'), 'thinking_tokens':usage.get('thoughtsTokenCount',0),
                 'total_tokens':usage.get('totalTokenCount'),'usage':usage,'image_count':len(images)}
        self.usage.append(receipt);self._write(self.output/'usage.json',self.usage)
        candidates=raw.get('candidates',[])
        if len(candidates)!=1 or candidates[0].get('finishReason')!='STOP':
            raise ExperimentCallError('Incomplete or blocked Gemini response')
        if not (raw.get('modelVersion')==self.model or str(raw.get('modelVersion','')).startswith(self.model+'-')):
            raise ExperimentCallError('Unexpected Gemini model version')
        texts=[p['text'] for p in candidates[0].get('content',{}).get('parts',[]) if 'text' in p and not p.get('thought')]
        try:result=json.loads(''.join(texts))
        except ValueError:raise ExperimentCallError('Gemini output is not complete JSON') from None
        self._write(out/'output.json',result)
        jsonschema.validate(result,schema)
        return result

PROXY_ENDPOINT = 'https://openrouter.ai/api/v1'

def load_proxy_policy(root: Path) -> dict:
    """GenOS proxy (ADR-0463): product role only, FP8 providers only, thinking off, no fallback."""
    proxy = load_policy(root).get('genos_proxy')
    routing = (proxy or {}).get('provider_routing', {})
    if (not isinstance(proxy, dict) or proxy.get('schema_version') != 'genos-proxy-model-v1'
            or proxy.get('provider') != 'openrouter' or proxy.get('endpoint') != PROXY_ENDPOINT
            or proxy.get('allowed_classes') != ['product'] or proxy.get('fallback_allowed') is not False
            or routing.get('allow_fallbacks') is not False or routing.get('quantizations') != ['fp8']
            or proxy.get('reasoning') != {'enabled': False} or not proxy.get('models')
            or not proxy.get('allowed_upstream_providers')):
        raise ValueError('Invalid GenOS proxy policy')
    return proxy

class OpenRouterProxyClient:
    """Audited GenOS-proxy product calls through OpenRouter; never an evaluator or serving fallback."""
    # schema_in_prompt/max_repairs defaults keep ADR-0463 (v1) reproducible; v2 (ADR-0464) opts in.
    def __init__(self, root: Path, output: Path, *, model=None, max_calls=24,
                 max_output_tokens=None, transport=None, schema_in_prompt=False, max_repairs=0):
        self.root=Path(root).resolve();self.output=Path(output)
        self.schema_in_prompt=bool(schema_in_prompt);self.max_repairs=int(max_repairs)
        if self.max_repairs not in (0,1):raise ValueError('max_repairs must be 0 or 1')
        self.proxy=load_proxy_policy(self.root);self.model=model or self.proxy['models'][0]
        if self.model not in self.proxy['models']:raise ValueError('Model outside GenOS proxy policy')
        env=dotenv_values(self.root/'.env');name=self.proxy['key_env']
        self._key=os.environ.get(name) or env.get(name)
        if not self._key:raise ExperimentCallError('Missing '+name)
        self.max_calls=max_calls;self.calls=0;self.usage=[];self.transport=transport
        self.max_output_tokens=_output_tokens(self.proxy,max_output_tokens)
        self.output.mkdir(parents=True,exist_ok=True)
        self.policy_hash=hashlib.sha256((self.root/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_bytes()).hexdigest()

    _write=GeminiExperimentClient._write

    SCHEMA_PROMPT=('\n\n[출력 형식] 아래 JSON Schema 를 만족하는 JSON 객체 **하나만** 출력한다. '
                   '설명·머리말·코드 울타리 없이 JSON 만.\n')

    def generate(self, system: str, data, schema: dict, *, phase='generate'):
        """v2: schema also in the prompt; on local validation failure one repair turn with the error."""
        if not phase or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in phase):
            raise ValueError('Invalid phase name')
        jsonschema.Draft202012Validator.check_schema(schema)
        sys_text=system+(self.SCHEMA_PROMPT+json.dumps(schema,ensure_ascii=False) if self.schema_in_prompt else '')
        messages=[{'role':'system','content':sys_text},{'role':'user','content':json.dumps(data,ensure_ascii=False)}]
        try:
            return self._call(messages,schema,phase)
        except _FormatError as exc:
            if not self.max_repairs:raise ExperimentCallError(str(exc)) from None
            repair=messages+[{'role':'assistant','content':exc.content},
                             {'role':'user','content':'직전 출력이 출력 형식을 어겼다: '+exc.reason[:300]+
                              '\n같은 내용으로, 스키마를 만족하는 JSON 객체 하나만 다시 출력한다.'}]
            try:
                return self._call(repair,schema,phase+'-repair')
            except _FormatError as again:
                raise ExperimentFormatError('Repair failed: '+again.reason[:300]) from None

    def chat_completions(self, body: dict, *, phase='generate', timeout_seconds=180):
        """Send one exact chat-completions request under the pinned proxy policy.

        Caller-owned messages are preserved; the output-cap policy is applied
        to a copy. No hidden repair: one invocation is one physical request.
        """
        if self.calls >= self.max_calls:raise ExperimentCallError('model_call_budget_exhausted')
        if not isinstance(body,dict):raise ValueError('chat completion body must be an object')
        if not phase or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in phase):
            raise ValueError('Invalid phase name')
        if body.get('model') != self.model:raise ValueError('Request model differs from pinned proxy model')
        if not isinstance(body.get('messages'),list) or not body['messages']:
            raise ValueError('Request messages must be a non-empty list')
        if body.get('stream') not in (None,False):raise ValueError('Streaming is not supported by audited transport')
        if 'provider' in body and body['provider'] != self.proxy['provider_routing']:
            raise ValueError('Request provider routing differs from pinned proxy policy')
        if 'reasoning' in body and body['reasoning'] != self.proxy['reasoning']:
            raise ValueError('Request reasoning setting differs from pinned proxy policy')
        payload=copy.deepcopy(body)
        _apply_output_policy(payload,self.proxy)
        payload['provider']=copy.deepcopy(self.proxy['provider_routing'])
        payload['reasoning']=dict(self.proxy['reasoning'])
        payload['usage']={'include':True}
        self.calls+=1;out=self.output/f'call-{self.calls:03d}-{phase}';out.mkdir(exist_ok=False)
        self._write(out/'request.json',payload)
        schema=(((payload.get('response_format') or {}).get('json_schema') or {}).get('schema'))
        if schema is not None:self._write(out/'validation-schema.json',schema)
        self._write(out/'binding.json',{'provider':'openrouter','model':self.model,'endpoint':PROXY_ENDPOINT,
                                        'genos_model':self.proxy['genos_model'],'policy_sha256':self.policy_hash})
        start=time.monotonic()
        try:
            timeout=max(.001,min(180,float(timeout_seconds)))
            with httpx.Client(timeout=timeout,trust_env=False,follow_redirects=False,transport=self.transport) as client:
                response=client.post(f'{PROXY_ENDPOINT}/chat/completions',headers={'Authorization':'Bearer '+self._key},json=payload)
        except httpx.HTTPError as exc:
            self._write(out/'error.json',{'error':type(exc).__name__,'seconds':time.monotonic()-start})
            raise ExperimentTransportError('OpenRouter transport failed: '+type(exc).__name__,
                retryable=isinstance(exc,(httpx.ConnectError,httpx.ConnectTimeout,httpx.PoolTimeout)),
                unknown=not isinstance(exc,(httpx.ConnectError,httpx.ConnectTimeout,httpx.PoolTimeout))) from None
        try:raw=response.json()
        except ValueError:
            self._write(out/'error.json',{'http_status':response.status_code,'error':'Non-JSON response'})
            raise ExperimentProviderError('OpenRouter returned non-JSON response') from None
        self._write(out/'response.json',raw)
        envelope={'status_code':response.status_code,'retry_after':response.headers.get('retry-after'),'body_json':raw,'body_text':None,
                  'body_sha256':hashlib.sha256(response.content).hexdigest()}
        if not response.is_success or raw.get('error'):
            raise ExperimentProviderError(f'OpenRouter HTTP {response.status_code}; response saved without request headers',
                                          response=envelope,retryable=response.status_code in (408,409,429,500,502,503,504))
        usage=raw.get('usage') or {};details=usage.get('completion_tokens_details') or {}
        receipt={'call':self.calls,'phase':phase,'provider':'openrouter','upstream_provider':raw.get('provider'),
                 'model':raw.get('model'),'seconds':round(time.monotonic()-start,3),'input_tokens':usage.get('prompt_tokens'),
                 'output_tokens':usage.get('completion_tokens'),'thinking_tokens':details.get('reasoning_tokens',0) or 0,
                 'total_tokens':usage.get('total_tokens'),'cost_usd':usage.get('cost'),'usage':usage}
        self.usage.append(receipt);self._write(self.output/'usage.json',self.usage)
        if raw.get('provider') not in self.proxy['allowed_upstream_providers']:
            raise ExperimentProviderError('Unexpected upstream provider: '+str(raw.get('provider')),response=envelope)
        if not str(raw.get('model','')).startswith(self.model):
            raise ExperimentProviderError('Unexpected OpenRouter model',response=envelope)
        choices=raw.get('choices') or []
        if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
            raise ExperimentFormatError('Incomplete or blocked OpenRouter response',response=envelope)
        message=choices[0].get('message') or {}
        if receipt['thinking_tokens'] or message.get('reasoning'):
            raise ExperimentProviderError('Reasoning was not disabled',response=envelope)
        return envelope

    def _call(self, messages, schema, phase):
        if self.calls >= self.max_calls:raise ExperimentCallError('model_call_budget_exhausted')
        payload={'model':self.model,
                 'messages':messages,
                 'temperature':self.proxy['temperature'],
                 **({'max_tokens':self.max_output_tokens} if self.max_output_tokens is not None else {}),
                 'response_format':{'type':'json_schema','json_schema':{'name':'output','strict':True,'schema':_schema_for_api(schema)}},
                 'provider':copy.deepcopy(self.proxy['provider_routing']),'reasoning':dict(self.proxy['reasoning']),
                 'usage':{'include':True}}
        self.calls+=1;out=self.output/f'call-{self.calls:03d}-{phase}';out.mkdir(exist_ok=False)
        self._write(out/'request.json',payload)
        self._write(out/'validation-schema.json',schema)
        self._write(out/'binding.json',{'provider':'openrouter','model':self.model,'endpoint':PROXY_ENDPOINT,
                                        'genos_model':self.proxy['genos_model'],'policy_sha256':self.policy_hash})
        start=time.monotonic()
        try:
            with httpx.Client(timeout=180,trust_env=False,follow_redirects=False,transport=self.transport) as client:
                response=client.post(f'{PROXY_ENDPOINT}/chat/completions',headers={'Authorization':'Bearer '+self._key},json=payload)
        except httpx.HTTPError as exc:
            self._write(out/'error.json',{'error':type(exc).__name__,'seconds':time.monotonic()-start})
            raise ExperimentTransportError('OpenRouter transport failed: '+type(exc).__name__,
                retryable=isinstance(exc,(httpx.ConnectError,httpx.ConnectTimeout,httpx.PoolTimeout)),
                unknown=not isinstance(exc,(httpx.ConnectError,httpx.ConnectTimeout,httpx.PoolTimeout))) from None
        try:raw=response.json()
        except ValueError:
            self._write(out/'error.json',{'http_status':response.status_code,'error':'Non-JSON response'})
            raise ExperimentProviderError('OpenRouter returned non-JSON response') from None
        self._write(out/'response.json',raw)
        envelope={'status_code':response.status_code,'retry_after':response.headers.get('retry-after'),'body_json':raw,'body_text':None,
                  'body_sha256':hashlib.sha256(response.content).hexdigest()}
        if not response.is_success or raw.get('error'):
            raise ExperimentProviderError(f'OpenRouter HTTP {response.status_code}; response saved without request headers',
                                          response=envelope,retryable=response.status_code in (408,409,429,500,502,503,504))
        usage=raw.get('usage') or {};details=usage.get('completion_tokens_details') or {}
        receipt={'call':self.calls,'phase':phase,'provider':'openrouter','upstream_provider':raw.get('provider'),
                 'model':raw.get('model'),'seconds':round(time.monotonic()-start,3),'input_tokens':usage.get('prompt_tokens'),
                 'output_tokens':usage.get('completion_tokens'),'thinking_tokens':details.get('reasoning_tokens',0) or 0,
                 'total_tokens':usage.get('total_tokens'),'cost_usd':usage.get('cost'),'usage':usage}
        self.usage.append(receipt);self._write(self.output/'usage.json',self.usage)
        if raw.get('provider') not in self.proxy['allowed_upstream_providers']:
            raise ExperimentProviderError('Unexpected upstream provider: '+str(raw.get('provider')),response=envelope)
        if not str(raw.get('model','')).startswith(self.model):
            raise ExperimentProviderError('Unexpected OpenRouter model',response=envelope)
        choices=raw.get('choices') or []
        if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
            raise ExperimentFormatError('Incomplete or blocked OpenRouter response',response=envelope)
        message=choices[0].get('message') or {}
        if receipt['thinking_tokens'] or message.get('reasoning'):
            raise ExperimentProviderError('Reasoning was not disabled',response=envelope)
        content=message.get('content') or ''
        try:result=json.loads(content)
        except ValueError:raise _FormatError('output is not complete JSON',content,response=envelope) from None
        self._write(out/'output.json',result)
        try:jsonschema.validate(result,schema)
        except jsonschema.ValidationError as exc:raise _FormatError('schema: '+exc.message,content,response=envelope) from None
        return result

class _FormatError(ExperimentFormatError):
    def __init__(self, reason, content, *, response=None):
        super().__init__(reason,response=response);self.reason=reason;self.content=content


class QwenExperimentClient(OpenRouterProxyClient):
    """Default public/synthetic experimental client, including offline evaluation."""
    def __init__(self, root, output, **kwargs):
        policy = load_policy(Path(root))
        if policy.get('policy_version') != 'qwen-experiments-v1' or policy['provider'] != 'openrouter':
            raise ValueError('Qwen default policy required')
        proxy = load_proxy_policy(Path(root))
        for name in ('provider_routing', 'reasoning', 'allowed_upstream_providers'):
            if policy.get(name) != proxy[name]:
                raise ValueError('Default Qwen routing differs from approved FP8 policy')
        super().__init__(root, output, **kwargs)
        self.policy = policy

    def generate(self, system, data, schema, *, images=(), phase='generate'):
        if not images:
            return super().generate(system, data, schema, phase=phase)
        jsonschema.Draft202012Validator.check_schema(schema)
        parts = [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}]
        for uri in images:
            header, blob = uri.split(',', 1)
            if header not in {'data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64'}:
                raise ValueError('Only inline PNG/JPEG/WebP evidence supported')
            base64.b64decode(blob, validate=True)
            parts.append({'type': 'image_url', 'image_url': {'url': uri}})
        body = {'model': self.model, 'messages': [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': parts}], 'temperature': self.proxy['temperature'],
                **({'max_tokens': self.max_output_tokens} if self.max_output_tokens is not None else {}),
                'response_format': {'type': 'json_schema',
                    'json_schema': {'name': 'output', 'strict': True, 'schema': _schema_for_api(schema)}}}
        raw = self.chat_completions(body, phase=phase)
        try:
            value = json.loads(raw['body_json']['choices'][0]['message']['content'])
            jsonschema.validate(value, schema)
        except (ValueError, KeyError, TypeError, jsonschema.ValidationError) as exc:
            raise ExperimentFormatError('Qwen image response failed schema validation', response=raw) from exc
        self._write(self.output/f'call-{self.calls:03d}-{phase}'/'output.json', value)
        return value


class GemmaExperimentClient(QwenExperimentClient):
    """Default Gemma FP8 experiment route, independent of the GENOS Qwen proxy."""
    def __init__(self, root, output, *, max_calls=24, max_output_tokens=None,
                 transport=None, schema_in_prompt=False, max_repairs=0):
        self.root=Path(root).resolve();self.output=Path(output)
        policy=load_policy(self.root)
        route=policy.get('provider_routing')
        if (policy.get('policy_version') != 'gemma-experiments-v1'
                or policy['provider'] != 'openrouter'
                or route != {'only':['parasail/fp8'], 'order':['parasail/fp8'],
                    'quantizations':['fp8'], 'allow_fallbacks':False,
                    'require_parameters':True}
                or policy.get('allowed_upstream_providers') != ['Parasail']
                or policy.get('reasoning') != {'enabled':False}
                or policy.get('fallback_allowed') is not False):
            raise ValueError('Gemma experiment route differs from approved FP8 policy')
        self.proxy={**policy,'genos_model':None}
        self.policy=policy;self.model=policy['model']
        env=dotenv_values(self.root/'.env');name=policy['key_env']
        self._key=os.environ.get(name) or env.get(name)
        if not self._key:raise ExperimentCallError('Missing '+name)
        self.max_calls=max_calls;self.calls=0;self.usage=[];self.transport=transport
        self.max_output_tokens=_output_tokens(policy,max_output_tokens)
        self.schema_in_prompt=bool(schema_in_prompt);self.max_repairs=int(max_repairs)
        if self.max_repairs not in (0,1):raise ValueError('max_repairs must be 0 or 1')
        self.output.mkdir(parents=True,exist_ok=True)
        self.policy_hash=hashlib.sha256(
            (self.root/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_bytes()).hexdigest()


class Qwen38ExperimentClient(GemmaExperimentClient):
    """Default Qwen3.8 Parasail FP8 experiment route; no provider fallback."""
    def __init__(self, root, output, *, max_calls=24, max_output_tokens=None,
                 transport=None, schema_in_prompt=False, max_repairs=0):
        self.root=Path(root).resolve();self.output=Path(output)
        policy=load_policy(self.root)
        route={'only':['parasail/fp8'],'order':['parasail/fp8'],
               'quantizations':['fp8'],'allow_fallbacks':False,
               'require_parameters':True}
        if (policy.get('policy_version')!='qwen38-experiments-v1'
                or policy.get('provider')!='openrouter'
                or policy.get('model')!='qwen/qwen3.8-27b'
                or policy.get('provider_routing')!=route
                or policy.get('reasoning')!={'effort':'none'}
                or policy.get('allowed_upstream_providers')!=['Parasail']
                or policy.get('fallback_allowed') is not False):
            raise ValueError('Qwen3.8 experiment route differs from approved FP8 policy')
        self.proxy={**policy,'genos_model':None}
        self.policy=policy;self.model=policy['model']
        env=dotenv_values(self.root/'.env');name=policy['key_env']
        self._key=os.environ.get(name) or env.get(name)
        if not self._key:raise ExperimentCallError('Missing '+name)
        self.max_calls=max_calls;self.calls=0;self.usage=[];self.transport=transport
        self.max_output_tokens=_output_tokens(policy,max_output_tokens)
        self.schema_in_prompt=bool(schema_in_prompt);self.max_repairs=int(max_repairs)
        if self.max_repairs not in (0,1):raise ValueError('max_repairs must be 0 or 1')
        self.output.mkdir(parents=True,exist_ok=True)
        self.policy_hash=hashlib.sha256(
            (self.root/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_bytes()).hexdigest()


def ExperimentClient(root, output, **kwargs):
    """Dispatch only the explicitly configured policy; never provider fallback."""
    policy = load_policy(Path(root))
    if policy['policy_version'] == 'qwen38-experiments-v1':
        client=Qwen38ExperimentClient
    elif policy['policy_version'] == 'gemma-experiments-v1':
        client=GemmaExperimentClient
    elif policy['policy_version'] == 'qwen-experiments-v1':
        client=QwenExperimentClient
    else:
        client=GeminiExperimentClient
    return client(root, output, **kwargs)
