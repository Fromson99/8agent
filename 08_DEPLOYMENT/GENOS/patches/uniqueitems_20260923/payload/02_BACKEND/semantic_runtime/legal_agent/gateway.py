"""All retry and JSON repair calls consume the same persistent physical budget."""
import json
import logging
import time
import uuid
from .. import observability as obs
from . import protocol
from .errors import BudgetExhausted, ContractError, ProposalError, StaleProposal, TransportError
from .repository import encoded
from .views import SYSTEM, PROMPTS

log = obs.get_logger('legal_agent.model')


def genos_wire_schema(value):
    """Omit JSON Schema keywords unsupported by GENOS's grammar compiler.

    Keep the protocol definitions intact: validate_wire/validate still enforce
    uniqueness on the decoded model response inside the application.
    """
    if isinstance(value, dict):
        return {key: genos_wire_schema(child) for key, child in value.items()
                if key != 'uniqueItems'}
    if isinstance(value, list):
        return [genos_wire_schema(child) for child in value]
    return value


class ModelGateway:
    def __init__(self, repo, context, profile, domain, transport, *, message_protocol=None, system=None, prompts=None):
        self.repo, self.context, self.profile, self.domain, self.transport = repo, context, profile, domain, transport
        self.protocol = message_protocol or protocol
        self.system, self.prompts = system or SYSTEM, prompts or PROMPTS
        if transport.binding != profile['model_binding']:
            raise ContractError('transport and AgentProfile bindings differ')
        if not context.binding['export_allowed'] and transport.binding['trust_zone'] != 'internal':
            raise ContractError('source generation forbids external transmission')

    def request(self, phase, view, schema_name, *, references=None):
        schema = self.protocol.schema(schema_name)
        if schema_name=='ReviewDecision':
            claims=[c.get('claim') or c.get('entity_id') for c in view.get('claims',[])]
            if claims:
                schema['properties']['checks']['items']['properties']['claim']={'type':'string','enum':claims}
                schema['properties']['checks']['minItems']=len(claims)
                schema['properties']['checks']['maxItems']=len(claims)
        numbered_instructions = ''
        if self.profile.get('numbered_references_enabled', False):
            from .numbered_references import NumberedReferences, INSTRUCTIONS
            references = references or NumberedReferences(view)
            view, schema = references.view(view), references.schema(schema)
            numbered_instructions = INSTRUCTIONS
        schema = genos_wire_schema(schema)
        prompt = self.prompts[phase]
        if numbered_instructions:
            prompt = prompt.replace('the ID, such as C1', 'the number, such as 1')
        return {'model': self.transport.binding['model'], 'max_tokens': self.profile['max_output_tokens'],
                   'temperature': 0, 'stream': False, 'chat_template_kwargs': {'enable_thinking': False},
                   'messages': [{'role': 'system', 'content': self.system+'\n'+prompt+'\nDomainSpec: '+encoded(self.domain)+numbered_instructions},
                                {'role': 'user', 'content': encoded({'view': view, 'output_schema': schema})}],
                   'response_format': {'type': 'json_schema', 'json_schema': {'name': schema_name, 'strict': True, 'schema': schema}}}

    def generate(self, phase, view, schema_name):
        references = None
        if self.profile.get('numbered_references_enabled', False):
            from .numbered_references import NumberedReferences
            references = NumberedReferences(view)
        request = self.request(phase, view, schema_name, references=references)
        logical = 'L'+uuid.uuid4().hex
        retries = repairs = attempt = 0
        while True:
            remaining = self.context.remaining()
            request_bytes = len(encoded(request).encode())
            if request_bytes > self.transport.binding['max_input_bytes']:
                obs.event(log, 'model.attempt.blocked', level=logging.ERROR,
                          run_id=self.context.run_id, phase=phase, schema=schema_name,
                          reason='input_byte_limit', request_bytes=request_bytes,
                          max_input_bytes=self.transport.binding['max_input_bytes'])
                raise BudgetExhausted('model input exceeds deployment-validated conservative byte limit')
            attempt += 1
            numbered_args = {'numbered_references': references} if references is not None else {}
            ident = self.repo.reserve_attempt(view, request, logical, attempt, phase, **numbered_args)
            self.repo.attempt_sent(ident)
            attempt_started = time.perf_counter()
            fields = {'run_id': self.context.run_id, 'attempt_id': ident,
                      'logical_call_id': logical, 'phase': phase, 'schema': schema_name,
                      'attempt_no': attempt, 'model': self.transport.binding['model']}
            obs.event(log, 'model.attempt.started', **fields,
                      request_bytes=request_bytes, max_tokens=request['max_tokens'],
                      remaining_ms=int(remaining * 1000))
            try:
                raw = self.transport.send_once(body=request, ticket={'attempt_id': ident, 'remaining_seconds': remaining})
            except TransportError as exc:
                self.repo.finish_attempt(ident, 'UNKNOWN' if exc.unknown else 'FAILED', exc.response,
                                         {'model': self.transport.binding['model'], 'usage': None, 'error': exc.code})
                retry_scheduled = exc.retryable and retries < self.profile['max_transport_retries']
                response = exc.response if isinstance(exc.response, dict) else {}
                obs.event(log, 'model.attempt.failed', level=logging.ERROR, **fields,
                          failure_kind='transport', error_code=exc.code,
                          http_status=response.get('status_code'), unknown=exc.unknown,
                          retryable=exc.retryable, retry_scheduled=retry_scheduled,
                          duration_ms=int((time.perf_counter() - attempt_started) * 1000))
                if retry_scheduled:
                    retries += 1
                    continue
                raise
            except ProposalError as exc:
                self.repo.finish_attempt(ident, 'FAILED', getattr(exc, 'response', None),
                                         {'model': self.transport.binding['model'], 'usage': None, 'error': exc.code})
                obs.event(log, 'model.attempt.failed', level=logging.ERROR, **fields,
                          failure_kind='proposal', error_code=exc.code,
                          duration_ms=int((time.perf_counter() - attempt_started) * 1000))
                raise
            except Exception as exc:
                self.repo.finish_attempt(ident, 'UNKNOWN', None, {'model': self.transport.binding['model'], 'usage': None, 'error': type(exc).__name__})
                obs.event(log, 'model.attempt.failed', level=logging.ERROR, **fields,
                          failure_kind='adapter', error_type=type(exc).__name__,
                          duration_ms=int((time.perf_counter() - attempt_started) * 1000))
                raise TransportError('single-send adapter failed', unknown=True) from exc
            body = raw.get('body_json')
            receipt = {'model': body.get('model') if isinstance(body, dict) else None,
                       'usage': body.get('usage') if isinstance(body, dict) else None, 'attempt_id': ident}
            status = self.repo.finish_attempt(ident, 'SUCCEEDED', raw, receipt)
            usage = receipt['usage'] if isinstance(receipt['usage'], dict) else {}
            obs.event(log, 'model.attempt.received', **fields,
                      http_status=raw.get('status_code'), journal_status=status,
                      duration_ms=int((time.perf_counter() - attempt_started) * 1000),
                      response_bytes=raw.get('response_bytes'),
                      prompt_tokens=usage.get('prompt_tokens'),
                      completion_tokens=usage.get('completion_tokens'))
            self.context.remaining()
            if status != 'SUCCEEDED':
                raise StaleProposal('late model response ignored')
            if receipt['model'] != self.transport.binding['model']:
                obs.event(log, 'model.attempt.failed', level=logging.ERROR, **fields,
                          failure_kind='model_mismatch', actual_model=receipt['model'])
                raise ContractError('actual response model differs from pinned model')
            try:
                if not isinstance(body, dict) or not isinstance(body.get('choices'), list) or len(body['choices']) != 1:
                    raise ProposalError('expected one structured choice')
                message = body['choices'][0]['message']
                content = message.get('content')
                if not content and len(message.get('tool_calls', [])) == 1:
                    content = message['tool_calls'][0]['function']['arguments']
                value = json.loads(content) if isinstance(content, str) else content
                if references is not None:
                    value = references.decode(value, request['response_format']['json_schema']['schema'], schema_name)
                getattr(self.protocol, "validate_wire", self.protocol.validate)(schema_name, value)
                obs.event(log, 'model.attempt.accepted', **fields, schema_repairs=repairs)
                return value
            except (ProposalError, ValueError, KeyError, TypeError) as exc:
                obs.event(log, 'model.output.invalid', level=logging.WARNING, **fields,
                          error_type=type(exc).__name__, schema_repairs=repairs,
                          repair_scheduled=repairs < self.profile['max_schema_repairs'])
                with self.repo.transaction():
                    self.repo.event('OUTPUT_SCHEMA_INVALID', {'attempt_id': ident, 'error': str(exc)[:2000]})
                if repairs >= self.profile['max_schema_repairs']:
                    error = ProposalError('structured model output invalid after bounded repair')
                    error.format_error = True
                    raise error from exc
                repairs += 1
                # Raw output is already durable. Repair changes syntax only; IDs,
                # evidence visibility and semantic state are checked by repository.
                # Server validation after decoding may mention internal IDs.
                # Keep repair instructions in the same request-local vocabulary.
                repair_error = str(exc)[:1000]
                if references is not None:
                    for kind, ids in references.ids.items():
                        for number, ident in sorted(enumerate(ids, 1), key=lambda pair: -len(pair[1])):
                            repair_error = repair_error.replace(ident, f'<{kind} choice {number}>')
                valid_claims = (list(range(1, len(references.ids['claims'])+1)) if references is not None
                               else [c.get('claim') or c.get('entity_id') for c in view.get('claims',[])])
                request = {**request, 'messages': request['messages'][:2]+[{
                    'role': 'user', 'content': encoded({'repair': 'Return a complete object matching output_schema.',
                                                       'invalid_response_excerpt': str(body)[:4000], 'error': repair_error,
                                                       'valid_claim_ids':valid_claims})}]}
