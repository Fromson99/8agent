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

def load_policy(root: Path) -> dict:
    path = root / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'
    policy = json.loads(path.read_text())
    if (policy.get('schema_version') != 'experiment-model-policy-v1'
            or policy.get('provider') != 'gemini' or policy.get('model') != MODEL
            or policy.get('allowed_models') != [MODEL] or policy.get('endpoint') != ENDPOINT
            or policy.get('fallback_allowed') is not False):
        raise ValueError('Invalid experiment model policy')
    return policy

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
        env=dotenv_values(self.root/'.env')
        names=[self.policy['key_env'],*self.policy.get('key_env_aliases',[])]
        self._key=next((os.environ.get(k) or env.get(k) for k in names if os.environ.get(k) or env.get(k)),None)
        if not self._key:raise ExperimentCallError('Missing GEMINI_API_KEY')
        self.max_calls=max_calls;self.calls=0;self.usage=[];self.transport=transport
        self.max_output_tokens=max_output_tokens or self.policy['max_output_tokens']
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
                    'maxOutputTokens':self.max_output_tokens,'thinkingConfig':{'thinkingLevel':self.policy['thinking_level']},
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
