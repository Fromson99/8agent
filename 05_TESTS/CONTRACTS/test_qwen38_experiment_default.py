"""The new research default stays on the pinned Qwen3.8 FP8 route."""
import json
from pathlib import Path

import httpx
import pytest

from lawrag.research.experiment_client import ExperimentClient, load_policy


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = {'type':'object','properties':{'ok':{'type':'boolean'}},
          'required':['ok'],'additionalProperties':False}


def test_default_qwen38_route_and_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv('OPEN_ROUTER','test-only-secret')
    seen=[]
    def handler(request):
        body=json.loads(request.content)
        seen.append(body)
        assert body['model']=='qwen/qwen3.8-27b'
        assert body['provider']=={'only':['parasail/fp8'],'order':['parasail/fp8'],
            'quantizations':['fp8'],'allow_fallbacks':False,'require_parameters':True}
        assert body['reasoning']=={'effort':'none'}
        return httpx.Response(200,json={'provider':'Parasail','model':'qwen/qwen3.8-27b',
            'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}],
            'usage':{'prompt_tokens':12,'completion_tokens':3,'total_tokens':15}})
    client=ExperimentClient(ROOT,tmp_path/'calls',max_calls=1,
        transport=httpx.MockTransport(handler))
    assert client.generate('Return JSON',{'public':'test'},SCHEMA)=={'ok':True}
    assert len(seen)==1
    assert client.usage[0]['model']=='qwen/qwen3.8-27b'
    assert all('test-only-secret' not in p.read_text() for p in (tmp_path/'calls').rglob('*.json'))


def test_policy_rejects_model_alias(tmp_path):
    policy=load_policy(ROOT)
    assert policy['policy_version']=='qwen38-experiments-v1'
    assert policy['allowed_models']==['qwen/qwen3.8-27b']
    assert policy['fallback_allowed'] is False
