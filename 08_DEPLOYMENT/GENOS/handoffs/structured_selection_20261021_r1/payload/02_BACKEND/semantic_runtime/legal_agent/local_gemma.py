"""Public-only local Qwen3.8 transport; GENOS model binding remains independent."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values

from .errors import ContractError, ProposalError, TransportError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provider_request(body: dict) -> dict:
    """Adapt only the external grammar; the gateway validates the original.

    Parasail rejects uniqueItems in otherwise supported complete action unions.
    Keep it in runtime validation and strip it from a separate wire schema.
    """
    payload = copy.deepcopy(body)
    def adapt(node):
        if not isinstance(node, dict): return
        node.pop('uniqueItems', None)
        for key in ('properties', '$defs', 'definitions', 'dependentSchemas'):
            for child in (node.get(key) or {}).values(): adapt(child)
        for key in ('items', 'additionalProperties', 'not', 'if', 'then', 'else', 'contains'):
            child = node.get(key)
            if isinstance(child, list):
                for value in child: adapt(value)
            else: adapt(child)
        for key in ('anyOf', 'oneOf', 'allOf', 'prefixItems'):
            for child in node.get(key, []): adapt(child)
    adapt(((payload.get('response_format') or {}).get('json_schema') or {}).get('schema'))
    from .wire_schema import factor_schema, navigation_shape
    envelope=(payload.get('response_format') or {}).get('json_schema')
    if envelope and isinstance(envelope.get('schema'),dict):
        envelope['schema']=factor_schema(navigation_shape(envelope['schema']))
    return payload


class LocalGemmaTransport:
    """Stable import name for release compatibility; model is policy-bound."""
    wire_projection = 'external-navigation-shape-server-validation-v1'

    def __init__(self, code_root: Path, workspace_root: Path):
        self.code_root = Path(code_root).resolve()
        self.grant_path = self.code_root / '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'
        self.policy_path = self.code_root / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'
        self.grant_hash = _sha(self.grant_path)
        self.policy_hash = _sha(self.policy_path)
        self.grant = json.loads(self.grant_path.read_text())
        self.policy = json.loads(self.policy_path.read_text())
        route = {'only': ['parasail/fp8'], 'order': ['parasail/fp8'],
                 'quantizations': ['fp8'], 'allow_fallbacks': False,
                 'require_parameters': True}
        if (self.grant.get('schema_version') != 'local-public-model-binding-v2'
                or self.policy.get('policy_version') != 'qwen38-experiments-v1'
                or self.policy.get('provider') != 'openrouter'
                or self.policy.get('model') != 'qwen/qwen3.8-27b'
                or self.policy.get('provider_routing') != route
                or self.policy.get('reasoning') != {'effort': 'none'}
                or self.policy.get('allowed_upstream_providers') != ['Parasail']
                or self.policy.get('fallback_allowed') is not False
                or self.grant.get('policy_sha256') != self.policy_hash
                or self.grant.get('model') != self.policy['model']
                or self.grant.get('endpoint') != self.policy['endpoint']
                or self.grant.get('public_question_required') is not True
                or self.grant.get('source_manifest_export_allowed') is not False):
            raise ContractError('local Qwen3.8 public policy mismatch')
        key_name = self.policy['key_env']
        self._key = os.environ.get(key_name) or dotenv_values(Path(workspace_root)/'.env').get(key_name)
        if not self._key:
            raise ContractError('local Qwen3.8 credential is not configured')
        self.binding = {
            'provider': 'openrouter', 'model': self.policy['model'],
            'adapter_version': 'openrouter-local-public-v2',
            'endpoint_identity': hashlib.sha256(self.policy['endpoint'].encode()).hexdigest(),
            'trust_zone': 'external', 'max_input_bytes': 2_000_000,
        }

    @property
    def public_scope(self) -> tuple[str, ...]:
        return tuple(self.grant['public_document_ids'])

    def validate_model(self):
        return {'verified': True, 'mode': 'local-public-qwen38-policy',
                'model': self.binding['model'], 'policy_sha256': self.policy_hash}

    def authorize_workflow(self, request, binding):
        grant = self.grant.get('workflow_authorization') or {}
        if (_sha(self.grant_path) != self.grant_hash or _sha(self.policy_path) != self.policy_hash
                or grant.get('authorized_by') != 'user' or not grant.get('authorization_text')
                or request.get('workflow_id') not in grant.get('workflow_ids',['risk_team_compare_workflow'])
                or request['principal']['team_id'] not in grant.get('teams', [])
                or not request['document_ids'] or set(request['document_ids'])-set(grant.get('document_ids', []))
                or binding['generation_id'] != grant.get('generation_id')
                or binding['store_sha256'] != grant.get('store_sha256')
                or binding['generation_manifest_sha256'] != grant.get('generation_manifest_sha256')):
            raise ContractError('workflow source/model authorization mismatch')
        return {'kind':'USER_AUTHORIZED_WORKFLOW', 'grant_sha256':self.grant_hash,
                'policy_sha256':self.policy_hash, 'scope_document_ids':request['document_ids'],
                'generation_id':binding['generation_id'], 'store_sha256':binding['store_sha256'],
                'principal':request['principal'], 'public_question_asserted':False}

    def authorize(self, query, request, manifest, *, public_question: bool):
        if _sha(self.grant_path) != self.grant_hash or _sha(self.policy_path) != self.policy_hash:
            raise ContractError('local Qwen3.8 policy changed during serving')
        scope = set(query['scope']['document_version_ids'])
        from .workflow_execution import authorization
        parent = authorization()
        if parent is not None:
            if (parent.get('kind') != 'USER_AUTHORIZED_WORKFLOW' or parent['grant_sha256'] != self.grant_hash
                    or parent['policy_sha256'] != self.policy_hash or not scope
                    or scope-set(parent['scope_document_ids'])
                    or manifest['generation_id'] != parent['generation_id']
                    or manifest['store_sha256'] != parent['store_sha256']):
                raise ContractError('child RAG workflow authorization mismatch')
            return {**parent, 'scope_document_ids':sorted(scope)}
        allowed = set(self.public_scope)
        if (not public_question or not request['use_llm'] or not scope or scope-allowed
                or len(allowed) != len(self.public_scope)
                or manifest['generation_id'] != self.grant['generation_id']
                or manifest['store_sha256'] != self.grant['source_store_sha256']
                or manifest['export_allowed'] is not False):
            raise ContractError('local Qwen3.8 requires an asserted public question and approved public source scope')
        return {'grant_sha256': self.grant_hash, 'policy_sha256': self.policy_hash,
                'public_question_asserted': True, 'scope_document_ids': sorted(scope)}

    def validate_authorization(self, context):
        receipt = context.binding.get('external_authorization') or {}
        if context.request.get('workflow_id'):
            expected = self.authorize_workflow(context.request, context.binding)
            if receipt != expected or context.binding['model'] != self.binding:
                raise ContractError('workflow model authorization drift')
            return
        expected = self.authorize(context.query, context.request, {
            'generation_id': context.binding['generation_id'],
            'store_sha256': context.binding['store_sha256'],
            'export_allowed': context.binding['export_allowed'],
        }, public_question=receipt.get('public_question_asserted') is True)
        if receipt != expected or context.binding['model'] != self.binding:
            raise ContractError('local Qwen3.8 authorization drift')

    def send_once(self, *, body, ticket):
        if body.get('model') != self.binding['model'] or body.get('stream') is not False:
            raise ContractError('local Qwen3.8 request differs from pinned model')
        payload = provider_request(body)
        payload['provider'] = copy.deepcopy(self.policy['provider_routing'])
        payload['reasoning'] = copy.deepcopy(self.policy['reasoning'])
        payload['usage'] = {'include': True}
        seconds = max(.001, min(180, float(ticket['remaining_seconds'])))
        try:
            with httpx.Client(timeout=seconds, trust_env=False, follow_redirects=False) as client:
                response = client.post(self.policy['endpoint']+'/chat/completions',
                                       headers={'Authorization': 'Bearer '+self._key}, json=payload)
        except httpx.HTTPError as exc:
            preaccept=isinstance(exc,(httpx.ConnectError,httpx.ConnectTimeout,httpx.PoolTimeout))
            raise TransportError('local Qwen3.8 transmission failed: '+type(exc).__name__,
                retryable=preaccept, unknown=not preaccept) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise TransportError('local Qwen3.8 returned non-JSON response', retryable=False) from exc
        envelope = {'status_code': response.status_code, 'body_json': data,
                    'body_text': None, 'body_sha256': hashlib.sha256(response.content).hexdigest(),
                    'response_bytes': len(response.content),
                    'retry_after': response.headers.get('retry-after'),
                    'acceptance': 'KNOWN_REJECTED' if response.status_code==429 else 'UNKNOWN' if response.status_code>=500 else 'ACCEPTED'}
        if not response.is_success or data.get('error'):
            raise TransportError('local Qwen3.8 provider error', retryable=response.status_code==429,
                                 unknown=response.status_code>=500, response=envelope)
        if data.get('provider') != 'Parasail' or data.get('model') != self.binding['model']:
            raise ContractError('local Qwen3.8 response model/provider mismatch')
        choices = data.get('choices') or []
        if ((data.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') or any(
                choice.get('message', {}).get('reasoning') for choice in choices):
            raise ContractError('local Qwen3.8 reasoning was not disabled')
        if len(choices) == 1 and choices[0].get('finish_reason') in ('length', 'content_filter', 'refusal'):
            from .model_contract import structured_content
            from .output_contract import OutputContractError
            try:
                structured_content(data)
            except OutputContractError as error:
                # Let the existing decision owner see the same typed cause as
                # GENOS. Preserve the complete provider envelope for the journal.
                error.response = envelope
                raise
        if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
            error = ProposalError('local Qwen3.8 returned an incomplete response')
            error.response = envelope
            raise error
        return envelope


LocalQwen38Transport = LocalGemmaTransport
