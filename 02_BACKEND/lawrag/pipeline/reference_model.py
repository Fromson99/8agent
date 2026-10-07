"""Public-source OpenRouter adapter for the MAIN reference construction stage."""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from dotenv import dotenv_values

from semantic_runtime.contracts import sha
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.legal_agent.transport import GenosTransport
from lawrag.platform.paths import repository_root


ENDPOINT = 'https://openrouter.ai/api/v1'
MODEL = 'qwen/qwen3.8-27b'
ROUTE = {'only': ['parasail/fp8'], 'order': ['parasail/fp8'],
         'quantizations': ['fp8'], 'allow_fallbacks': False, 'require_parameters': True}


class OpenRouterReferenceTransport(GenosTransport):
    def __init__(self, settings, profile):
        self.binding = dict(settings['model_binding'])
        if (self.binding.get('provider') != 'openrouter' or self.binding.get('model') != MODEL
                or self.binding.get('trust_zone') != 'external'
                or self.binding.get('adapter_version') != 'openrouter-reference-v1'
                or self.binding.get('endpoint_identity') != hashlib.sha256(ENDPOINT.encode()).hexdigest()):
            raise ContractError('OpenRouter reference binding mismatch')
        self.grant_path = (Path(profile).parent / settings['export_grant']).resolve()
        self.grant_hash = settings['export_grant_sha256']
        if sha(self.grant_path) != self.grant_hash:
            raise ContractError('reference export grant hash mismatch')
        self.grant = json.loads(self.grant_path.read_text())
        if (self.grant.get('enabled') is not True or self.grant.get('purpose') != 'explicit_reference_resolution'
                or self.grant.get('model') != MODEL or self.grant.get('endpoint') != ENDPOINT
                or self.grant.get('private_documents_allowed') is not False
                or self.grant.get('private_questions_allowed') is not False):
            raise ContractError('reference export grant scope mismatch')
        key = os.environ.get('OPEN_ROUTER') or dotenv_values(repository_root() / '.env').get('OPEN_ROUTER')
        if not key:
            raise ContractError('OpenRouter credential is not configured')
        self.target = SimpleNamespace(root=ENDPOINT, connect_timeout=10, read_timeout=60,
                                      headers={'Authorization': 'Bearer ' + key},
                                      url=lambda path: ENDPOINT + path)

    def validate_model(self):
        # The pinned deployment is verified again from each actual response.
        return {'verified': True, 'model': MODEL, 'provider': 'Parasail',
                'quantization': 'fp8', 'grant_sha256': self.grant_hash}

    def validate_authorization(self, context):
        if sha(self.grant_path) != self.grant_hash:
            raise ContractError('reference export grant changed during execution')
        identity = context.binding.get('reference_identity') or {}
        if (identity.get('generation_id') != self.grant['generation_id']
                or identity.get('source_store_sha256') != self.grant['source_store_sha256']):
            raise ContractError('reference source generation is outside the public export grant')
        allowed = set(self.grant['public_document_ids'])
        cases = context.binding.get('reference_cases') or []
        if not cases:
            raise ContractError('reference export requires a closed case batch')
        for case in cases:
            ids = {case['source']['document_id'], *(c['document_id'] for c in case['candidates'])}
            if ids - allowed:
                raise ContractError('reference batch contains a document outside the public export grant')

    def prepare_body(self, body):
        payload = copy.deepcopy(body)
        payload.pop('chat_template_kwargs', None)
        payload.update(provider=copy.deepcopy(ROUTE), reasoning={'effort': 'none'}, usage={'include': True})
        return payload

    def send_once(self, *, body, ticket):
        if (body.get('model') != MODEL or body.get('provider') != ROUTE
                or body.get('reasoning') != {'effort': 'none'} or body.get('stream') is not False):
            raise ContractError('reference wire request differs from pinned Qwen FP8 binding')
        with asyncio.Runner() as runner:
            envelope = runner.run(self._request('POST', '/chat/completions', body,
                                                ticket['remaining_seconds'], attempt_id=ticket.get('attempt_id')))
        data = envelope['body_json'] or {}
        if data.get('provider') != 'Parasail' or data.get('model') != MODEL:
            raise ContractError('reference response model/provider mismatch')
        choices = data.get('choices') or []
        if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
            error = ProposalError('reference model returned an incomplete response')
            error.response = envelope
            raise error
        details = (data.get('usage') or {}).get('completion_tokens_details') or {}
        if details.get('reasoning_tokens') or choices[0].get('message', {}).get('reasoning'):
            raise ContractError('reference model reasoning was not disabled')
        return envelope
