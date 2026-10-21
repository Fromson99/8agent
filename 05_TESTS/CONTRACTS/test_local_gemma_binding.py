"""The local public model must reject private scope while GENOS keeps its own binding."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport


ROOT = Path(__file__).resolve().parents[2]


def test_local_gemma_public_scope_and_question_assertion(monkeypatch):
    monkeypatch.setenv('OPEN_ROUTER', 'test-only-key')
    transport = LocalGemmaTransport(ROOT, ROOT)
    active=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    release=json.loads((ROOT/active['manifest_path']).read_text())
    manifest=json.loads((ROOT/release['data_path']/'manifest.json').read_text())
    approved = transport.public_scope[0]
    private = next(d for d in manifest['scope']['document_version_ids'] if d not in transport.public_scope)
    request = {'question': '정관 변경의 결의요건은?', 'document_ids': [approved], 'use_llm': True}
    query = {'question': request['question'], 'scope': {'document_version_ids': [approved]}}

    receipt = transport.authorize(query, request, manifest, public_question=True)
    transport.validate_authorization(SimpleNamespace(query=query, request=request, binding={
        'generation_id': manifest['generation_id'], 'store_sha256': manifest['store_sha256'],
        'export_allowed': False, 'model': transport.binding,
        'external_authorization': receipt,
    }))
    with pytest.raises(ContractError):
        transport.authorize(query, request, manifest, public_question=False)
    with pytest.raises(ContractError):
        transport.authorize({**query, 'scope': {'document_version_ids': [private]}}, request,
                            manifest, public_question=True)
    with pytest.raises(ContractError):
        transport.authorize(query, request, {**manifest, 'store_sha256': 'stale'},
                            public_question=True)


def test_genos_transport_cannot_take_external_binding():
    from semantic_runtime.legal_agent.transport import GenosTransport

    with pytest.raises(ContractError):
        GenosTransport(SimpleNamespace(root='https://example.test'), {
            'provider': 'openrouter', 'trust_zone': 'external',
            'adapter_version': 'openrouter-local-public-v1',
            'endpoint_identity': 'irrelevant', 'model': 'qwen/qwen3.8-27b',
            'max_input_bytes': 2_000_000,
        })
