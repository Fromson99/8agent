"""All retry and JSON repair calls consume the same persistent physical budget."""
import json
import logging
import time
import uuid
from copy import deepcopy
from jsonschema import ValidationError
from ..contracts import digest
from .. import observability as obs
from . import protocol
from .errors import BudgetExhausted, ContractError, ProposalError, StaleProposal, TransportError
from .repository import encoded
from .views import SYSTEM, PROMPTS

log = obs.get_logger('legal_agent.model')
DIAGNOSTICS_VERSION = 'thinking-log-20260928-r1'
WIRE_PROJECTION = 'compact-v5-v1'
NUMBER_INSTRUCTIONS = (
    ' References are request-local integer choices, separate for each field type. '
    'Copy the matching card number; never an original ID or card text. '
    'Preserve legal numbers and quoted text. Copy supplied tool arguments.')


def compact_wire_view(view, phase):
    """Project redundant wire data only; original views and receipts stay intact."""
    result = deepcopy(view)
    if result.get('source_stage') in ('memory-assess', 'memory-assess-repair'):
        # The durable exact_evidence cards bind current-request presentation.
        # Compact assessment already transmits these exact subspans as options.
        # Drop a duplicate container only when every coordinate and byte is
        # present under the same source/document identity in that wire input.
        exact = result.get('exact_evidence', [])
        options = result.get('evidence_options', [])
        def option_carries(card):
            spans = card.get('spans', [])
            if len(spans) != 1 or card.get('text') != spans[0].get('text'):
                return False
            span = spans[0]
            return bool(card.get('source_id') and card.get('document_id')) and any(
                (o.get('source_id'), o.get('document_id')) == (card['source_id'], card['document_id'])
                and all(o.get(k) == span.get(k) for k in ('block_id', 'start_cp', 'end_cp', 'text'))
                for o in options)
        if exact and all(option_carries(card) for card in exact):
            result.pop('exact_evidence')
        if result.get('input_projection')=='compact-selection-source-v3':
            # Both the sender and durable wire-receipt verifier call this exact
            # projection, after canonical source/span/ACL verification. Persisted
            # evidence keeps its coordinates; models see exact text and IDs once.
            from .completion_execution import assessment_original_view
            result['sources'], result['evidence_options'] = assessment_original_view(
                result.get('sources',[]),result.get('evidence_options',[]))
    if result.get('input_projection')=='compact-selection-source-v1':
        compact_original_text(result)
    for evidence in result.get('exact_evidence', []):
        text = evidence.get('text')
        if not isinstance(text, str):
            continue
        for span in evidence.get('spans', []):
            # Keep coordinates and any text not present in the authoritative body.
            if isinstance(span.get('text'), str) and span['text'] in text:
                span.pop('text')
    if phase == 'compose':
        # Draft has no tool actions. These fields are used by investigation/review.
        for key in ('navigation_choices', 'continuations', 'offered_handles',
                    'corpus_root', 'tool_capabilities', 'last_action_results',
                    'omitted_action_results', 'relation_menu', 'budgets', 'next_actions'):
            result.pop(key, None)
        numbers = result.get('reference_numbers', {})
        for kind in ('targets', 'blocks', 'cursors'):
            numbers.pop(kind, None)
    if result.get('input_projection') in ('compact-selection-source-v2','compact-selection-source-v3'):
        compact_original_text(result)
        compact_evidence_metadata(result)
    if result.get('input_projection')=='compact-selection-source-v3':
        from .navigation_input import compact_cards
        result=compact_cards(result)
    return result


def compact_evidence_metadata(view):
    """Omit opaque integrity hashes from the model copy; journal verification retains them."""
    def walk(node):
        if isinstance(node,list):
            for x in node:walk(x)
        elif isinstance(node,dict):
            if ('block_id' in node and 'start_cp' in node and 'end_cp' in node
                    and ('text' in node or 'text_ref' in node)):
                for key in ('block_hash','span_hash','text_hash'):
                    node.pop(key,None)
            for child in node.values():walk(child)
    walk(view)


def compact_original_text(view):
    """Lossless source-local references in the wire copy; never summarize originals.

    Each sources[].text remains complete. Other text values are replaced only
    when a delivered source with the same identity contains those exact bytes.
    Offsets in text_ref address this presentation, not original block offsets.
    """
    originals=[];evidence_sources={}
    for i,source in enumerate(view.get('sources',[])):
        if not isinstance(source.get('text'),str) or not source.get('source_id'):continue
        source['text_id']='TEXT'+str(i+1)
        originals.append(source)
        for span in source.get('spans',[])+source.get('adopted_spans',[]):
            if span.get('evidence_id'):evidence_sources[span['evidence_id']]=source['source_id']
        for eid in source.get('evidence_ids',[]):evidence_sources[eid]=source['source_id']
    protected={id(s) for s in originals}
    def walk(node,source_id=None):
        if isinstance(node,list):
            for row in node:walk(row,source_id)
        elif isinstance(node,dict):
            sid=node.get('source_id') or evidence_sources.get(node.get('evidence')) or source_id
            if id(node) not in protected:
                text=node.get('text')
                if isinstance(text,str) and text and sid:
                    match=next((s for s in originals if s['source_id']==sid and text in s['text']),None)
                    if match:
                        start=match['text'].find(text)
                        node.pop('text')
                        node['text_ref']={'id':match['text_id'],'start':start,'end':start+len(text)}
            for key,child in list(node.items()):
                if key!='text_ref':walk(child,sid)
    walk(view)


def compact_empty_arrays(schema):
    """Keep the complete action union; an empty array has no item decisions."""
    value=deepcopy(schema)
    def walk(node):
        if isinstance(node,list):
            for child in node:walk(child)
        elif isinstance(node,dict):
            if node.get('type')=='array' and node.get('maxItems')==0:
                node['items']={'type':'string'}
            for child in node.values():walk(child)
    walk(value)
    return value


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _response_diagnostics(body):
    """Project counts and presence flags only; absence never proves thinking OFF."""
    body = body if isinstance(body, dict) else {}
    usage = body.get('usage')
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get('completion_tokens_details')
    details = details if isinstance(details, dict) else {}
    prompt_details = usage.get('prompt_tokens_details')
    prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
    reasoning_tokens = _count(details.get('reasoning_tokens'))
    if reasoning_tokens is None:
        reasoning_tokens = _count(usage.get('reasoning_tokens'))
    choices = body.get('choices')
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get('message')
    message = message if isinstance(message, dict) else {}
    reasoning_keys = ('reasoning', 'reasoning_content', 'thinking')
    reasoning_present = any(key in message for key in reasoning_keys)
    reasoning_nonempty = any(bool(message.get(key)) for key in reasoning_keys)
    reasoning_chars = sum(len(message[key]) for key in reasoning_keys if isinstance(message.get(key), str))
    content = message.get('content')
    content = content if isinstance(content, str) else ''
    calls = message.get('tool_calls')
    calls = calls if isinstance(calls, list) else []
    argument_chars = 0
    for call in calls:
        function = call.get('function') if isinstance(call, dict) else None
        args = function.get('arguments') if isinstance(function, dict) else None
        if isinstance(args, str):
            argument_chars += len(args)
    if reasoning_nonempty or (reasoning_tokens is not None and reasoning_tokens > 0):
        observed = 'reasoning_reported'
    elif reasoning_present or reasoning_tokens is not None:
        observed = 'no_reasoning_reported'
    else:
        observed = 'unknown'
    finish = choice.get('finish_reason')
    if finish not in ('stop', 'length', 'tool_calls', 'function_call', 'content_filter'):
        finish = None
    return {'diagnostics_version': DIAGNOSTICS_VERSION,
            'prompt_tokens': _count(usage.get('prompt_tokens')),
            'completion_tokens': _count(usage.get('completion_tokens')),
            'total_tokens': _count(usage.get('total_tokens')),
            'cached_tokens': _count(prompt_details.get('cached_tokens')),
            'reasoning_tokens': reasoning_tokens,
            'reasoning_field_present': reasoning_present,
            'reasoning_nonempty': reasoning_nonempty,
            'reasoning_chars': reasoning_chars,
            'thinking_observation': observed,
            'thought_channel_marker_present': '<|channel>thought' in content or '<think>' in content,
            'response_content_chars': len(content), 'tool_argument_chars': argument_chars,
            'finish_reason': finish}


from . import output_contract as output
from .model_contract import (genos_wire_schema, structured_request, structured_content,
                             request_metrics, response_length_metrics,
                             response_model_metadata, validate_response_model)


def available_tool_schema(schema, view):
    """Limit model choices to search modes available in this serving generation."""
    if (view.get('tool_capabilities') or {}).get('fulltext') is not False:
        return schema

    def restrict(node):
        if isinstance(node, list):
            for child in node:
                restrict(child)
        elif isinstance(node, dict):
            properties = node.get('properties') or {}
            if properties.get('tool', {}).get('const') == 'search':
                mode = (properties.get('args', {}).get('properties') or {}).get('mode', {})
                if 'enum' in mode:
                    mode['enum'] = [value for value in mode['enum'] if value != 'fulltext']
            for child in node.values():
                restrict(child)

    restrict(schema)
    return schema


class ModelGateway:
    def __init__(self, repo, context, profile, domain, transport, *, message_protocol=None, system=None, prompts=None):
        self.repo, self.context, self.profile, self.domain, self.transport = repo, context, profile, domain, transport
        self.protocol = message_protocol or protocol
        source_scope = context.binding.get('requested_source_category')
        source_notice = {
            'internal': '현재 내규 데이터에 한정해서 작업하고 있다. 검색·목록·답변은 허용된 내규 문서만 사용하고 다른 자료의 존재나 부재를 추정하지 마라.',
            'external': '현재 외규 데이터에 한정해서 작업하고 있다. 검색·목록·답변은 허용된 외규 문서만 사용하고 다른 자료의 존재나 부재를 추정하지 마라.',
        }
        if source_scope is not None and source_scope not in source_notice:
            raise ContractError('invalid requested source category')
        self.system = (system or SYSTEM) + ('\n' + source_notice[source_scope] if source_scope else '')
        self.prompts = prompts or PROMPTS
        self.compact = profile.get('schema_version') == 'system-harness-profile-v5'
        if transport.binding != profile['model_binding']:
            raise ContractError('transport and AgentProfile bindings differ')
        if not context.binding['export_allowed'] and transport.binding['trust_zone'] != 'internal':
            validator = getattr(transport, 'validate_authorization', None)
            if validator is None:
                raise ContractError('source generation forbids external transmission')
            validator(context)

    def request(self, phase, view, schema_name, *, references=None):
        schema = self.protocol.schema(schema_name)
        if schema_name=='ReviewDecision':
            claims=[c.get('claim') or c.get('entity_id') for c in view.get('claims',[])]
            if claims:
                schema['properties']['checks']['items']['properties']['claim']={'type':'string','enum':claims}
                schema['properties']['checks']['minItems']=len(claims)
                schema['properties']['checks']['maxItems']=len(claims)
        numbered_instructions = ''
        if view.get('input_projection')=='compact-selection-source-v3':
            from .navigation_input import NavigationReferences, INSTRUCTIONS, STABLE_INSTRUCTIONS
            references=references or NavigationReferences(view)
            view,schema=references.view(view),references.schema(schema)
            numbered_instructions=STABLE_INSTRUCTIONS if references.stable else INSTRUCTIONS
        elif self.profile.get('numbered_references_enabled', False):
            from .numbered_references import NumberedReferences, INSTRUCTIONS
            references = references or NumberedReferences(view)
            view, schema = references.view(view), references.schema(schema)
            numbered_instructions = NUMBER_INSTRUCTIONS if self.compact else INSTRUCTIONS
        schema = available_tool_schema(schema, view)
        self._generation_schema = deepcopy(schema)
        schema = genos_wire_schema(schema)
        prompt = self.prompts[phase]
        if numbered_instructions and view.get('input_projection')!='compact-selection-source-v3':
            prompt = prompt.replace('the ID, such as C1', 'the number, such as 1')
        if self.compact:
            view = compact_wire_view(view, phase)
        if view.get('input_projection') in ('compact-selection-source-v1','compact-selection-source-v2','compact-selection-source-v3'):
            schema=compact_empty_arrays(schema)
            prompt+='\n원문은 sources[].text 또는 evidence_options[].text에 제공한다. text_ref가 있으면 해당 sources[].text_id의 본문에서 start 이상 end 미만(유니코드 문자 위치)의 정확한 원문이다. evidence_options의 text_ref도 같은 원문이며 인용에는 기존 S ID를 선택한다. 위치·해시는 서버가 검증한다.'
        from . import compact_model_input as minimal
        if minimal.applies(self.profile, view):
            view = minimal.project(view, schema)
            numbered_instructions = minimal.INSTRUCTIONS
        user = {'view': view}
        if not self.compact:
            user['output_schema'] = schema
        domain = '' if self.compact else '\nDomainSpec: '+encoded(self.domain)
        return structured_request(model=self.transport.binding['model'],
            max_tokens=self.profile['max_output_tokens'], schema_name=schema_name, schema=schema,
            messages=[{'role': 'system', 'content': self.system+'\n'+prompt+domain+numbered_instructions},
                      {'role': 'user', 'content': encoded(user)}])

    def validate_output(self, schema_name, value, view):
        getattr(self.protocol, "validate_wire", self.protocol.validate)(schema_name,value)

    def generate(self, phase, view, schema_name, *, repair_owner=None):
        from .answer_stream import current_sink, DraftText
        sink = current_sink()
        from . import narrative_answer as narrative
        rich = (narrative.enabled(self.profile) and schema_name == narrative.SCHEMA
                and view.get('source_stage') == narrative.PHASE
                and view.get('answer_presentation') == narrative.VERSION)
        def new_projection():
            return narrative.TokenStream(sink, view['answer_claim_ids']) if rich else DraftText(sink)
        streaming = (sink is not None and not getattr(sink, 'started', False)
                     and phase == 'compose' and (schema_name == 'Draft' or rich)
                     and not self.profile.get('final_review_enabled', True)
                     and self.transport.binding['trust_zone'] == 'internal'
                     and callable(getattr(self.transport, 'send_stream_once', None)))
        projection = new_projection() if streaming else None
        references = None
        if view.get('input_projection')=='compact-selection-source-v3':
            from .navigation_input import NavigationReferences
            references=NavigationReferences(view)
        elif self.profile.get('numbered_references_enabled', False):
            from .numbered_references import NumberedReferences
            references = NumberedReferences(view)
        from .. import query_latency as latency
        with latency.span('model.request_build',phase=phase):
            self._generation_schema = None
            request = self.request(phase, view, schema_name, references=references)
            from .minimal_output import prepare_request
            request, minimal_output = prepare_request(request, getattr(self, '_generation_schema', None),
                partial_contract=schema_name in ('TurnDecision', 'SourceSelectionDecision'))
        self.repo.event('MODEL_MINIMAL_OUTPUT_CONTRACT', {
            'source_stage':view.get('source_stage') or phase, **minimal_output.receipt})
        if streaming:
            request = {**request, 'stream': True, 'stream_options': {'include_usage': True}}
        role = view.get('source_stage') or phase
        spec = output.ContractSpec.from_schema(role, self.protocol.schema(schema_name))
        if repair_owner is not None:
            spec=output.ContractSpec(spec.role,spec.schema_hash,repair_owner)
        repair_limit=min(1,self.profile['max_schema_repairs']) if spec.owner=='gateway' else 0
        self.repo.event('MODEL_OUTPUT_CONTRACT', {**spec.receipt(view, self.transport.binding),
            'wire_schema_hash':digest(request['response_format']['json_schema']['schema']),
            'codec':type(references).__name__ if references is not None else 'canonical-v1',
            'wire_projection':getattr(self.transport,'wire_projection','genos-unique-items-server-v1')})
        journal = (output.DecisionJournal(self.repo, 'gateway',
            {'role':role,'view':{k:v for k,v in view.items() if k != 'view_id'}},
            self.protocol.schema(schema_name)) if spec.owner == 'gateway' else None)
        repairs=0
        if journal:
            previous = journal.state()
            if previous and previous['status'] == 'ACCEPTED':
                self.validate_output(schema_name,previous['value'],view)
                return deepcopy(previous['value'])
            if previous and previous['status']=='REJECTED':
                repairs=previous['attempt']+1
                request={**request,'messages':request['messages'][:2]+[{'role':'user','content':encoded({
                    'repair':'Return the complete corrected object for the same task, evidence and schema.',
                    'validation':previous['failure'],'invalid_response_excerpt':str(previous.get('proposal'))[:4000]})}]}
            journal.reserve(repairs, max_repairs=repair_limit)
        logical = 'L'+uuid.uuid4().hex
        retries = attempt = 0
        while True:
            routing=getattr(self.transport,'provider_policy',None)
            provider_index=None
            if routing:
                from . import provider_routing
                provider_state,_=provider_routing.current(self.repo,routing,self.transport.routing_hash,self.context.binding_hash)
                provider_index=provider_state['index']
                request={**request,'provider':provider_routing.route(routing['providers'][provider_index]),'reasoning':{'effort':'none'}}
            remaining = self.context.remaining()
            with latency.span('model.request_encode',phase=phase) as metrics:
                input_metrics = request_metrics(request)
                request_bytes = input_metrics['request_bytes']
                metrics['request_bytes'] = request_bytes
            attempt += 1
            numbered_args = {'numbered_references': references} if references is not None else {}
            if self.compact:
                numbered_args['wire_projection'] = WIRE_PROJECTION
            from . import compact_model_input as minimal
            if minimal.applies(self.profile, view):
                if view.get('minimal_input_binding') != minimal.bind(view, self.protocol.schema(schema_name), stable=self.profile.get('candidate_navigation',{}).get('stable_navigation_references',False),
                    document_names=view.get('minimal_input_binding',{}).get('document_names'))['minimal_input_binding']:
                    raise ContractError('minimal input schema binding differs from canonical view')
                numbered_args['minimal_input_projection'] = minimal.VERSION
            with latency.span('model.attempt_reserve',phase=phase):
                ident = self.repo.reserve_attempt(view, request, logical, attempt, phase, **numbered_args)
                self.repo.attempt_sent(ident)
            attempt_started = time.perf_counter()
            fields = {'run_id': self.context.run_id, 'attempt_id': ident,
                      'logical_call_id': logical, 'phase': phase, 'schema': schema_name,
                      'attempt_no': attempt, 'model': self.transport.binding['model'],
                      'source_stage': view.get('source_stage')}
            template = request.get('chat_template_kwargs')
            template = template if isinstance(template, dict) else {}
            thinking = template.get('enable_thinking')
            thinking = thinking if type(thinking) is bool else None
            obs.event(log, 'model.attempt.started', **fields,
                      **input_metrics, max_tokens=request.get('max_tokens'),
                      diagnostics_version=DIAGNOSTICS_VERSION,
                      thinking_requested=thinking,
                      thinking_control_present='enable_thinking' in template,
                      stream_requested=request.get('stream') is True,
                      remaining_ms=int(remaining * 1000))
            try:
                if self.transport.binding['trust_zone'] == 'external':
                    self.transport.validate_authorization(self.context)
                ticket = {'attempt_id': ident, 'remaining_seconds': self.context.remaining(), 'deadline': self.context.deadline, **({'provider_index':provider_index} if routing else {})}
                try:
                    from ..execution_metrics import transport_attempt
                    with latency.span('model.transport',phase=phase,request_bytes=request_bytes,pressure=True), transport_attempt(view.get('source_stage') or view.get('phase') or phase, ident):
                        if streaming:
                            raw = self.transport.send_stream_once(body=request, ticket=ticket, on_content=projection.feed)
                        else:
                            raw = self.transport.send_once(body=request, ticket=ticket)
                        if time.monotonic() >= self.context.deadline:
                            error = TransportError('model response arrived after stage deadline', unknown=True)
                            error.code = 'MODEL_DEADLINE_EXCEEDED'; error.http_status = 504
                            raise error
                except (TransportError, ProposalError, ContractError):
                    raise
                except Exception as adapter_error:
                    from .completion_contracts import enabled
                    response=getattr(adapter_error,'response',None)
                    if enabled(self.profile) and isinstance(response,dict) and isinstance(response.get('status_code'),int):
                        status=response['status_code']
                        if 200 <= status < 300:
                            if getattr(adapter_error,'format_error',False) is True:
                                body=response.get('body_json') or {}
                                validate_response_model(self.transport.binding, body)
                                error=ProposalError('model response is incomplete or invalid')
                                error.format_error=True
                                error.response=response
                                raise error from adapter_error
                            # Successful HTTP does not waive an adapter policy/binding rejection.
                            raise ContractError('adapter rejected successful response policy') from adapter_error
                        raise TransportError('model provider rejected request',response=response,
                            retryable=status==429 and bool(getattr(adapter_error,'retryable',False)),
                            unknown=status>=500) from adapter_error
                    raise
            except TransportError as exc:
                self.repo.finish_attempt(ident, 'UNKNOWN' if exc.unknown else 'FAILED', exc.response,
                                         {'model': self.transport.binding['model'], 'usage': None, 'error': exc.code})
                retry_scheduled = (exc.retryable and retries < self.profile['max_transport_retries']
                                   and not (projection and projection.emitted))
                response = exc.response if isinstance(exc.response, dict) else {}
                from .completion_contracts import enabled
                completion=enabled(self.profile)
                retry_delay=0.0
                if completion:
                    retry_scheduled=retry_scheduled and not exc.unknown and response.get('status_code')==429
                    if retry_scheduled:
                        try: retry_delay=max(1.0,float(response.get('retry_after') or 1.0))
                        except (TypeError,ValueError):
                            from email.utils import parsedate_to_datetime
                            from datetime import datetime,timezone
                            try:retry_delay=max(1.0,(parsedate_to_datetime(response['retry_after'])-datetime.now(timezone.utc)).total_seconds())
                            except (TypeError,ValueError,KeyError,OverflowError):retry_delay=1.0
                        retry_scheduled=retry_delay<=30 and self.context.remaining()>retry_delay+1
                    if response.get('status_code')==429:
                        exc.http_status=503
                        exc.code='MODEL_UPSTREAM_UNAVAILABLE'
                if routing:
                    budget=self.repo.budget()
                    limit=budget['model_limit']-(budget['finalization_reserve'] if phase=='investigate' else 0)
                    retry_scheduled=(not exc.unknown and response.get('status_code')==429 and response.get('acceptance')=='KNOWN_REJECTED'
                        and not (projection and projection.emitted) and budget['model_reserved']<limit and self.context.remaining()>1)
                    retry_scheduled=retry_scheduled and provider_routing.switch(self.repo,routing,self.transport.routing_hash,self.context.binding_hash,ident,response)
                    retry_delay=0.0
                obs.event(log, 'model.attempt.failed', level=logging.ERROR, **fields,
                          failure_kind='transport', error_code=exc.code,
                          http_status=response.get('status_code'), unknown=exc.unknown,
                          retryable=exc.retryable, retry_scheduled=retry_scheduled,
                          duration_ms=int((time.perf_counter() - attempt_started) * 1000))
                if retry_scheduled:
                    if retry_delay:
                        self.repo.event('TRANSPORT_RETRY_WAIT',{'seconds':retry_delay,'source_stage':view.get('source_stage'),
                            'acceptance':'KNOWN_REJECTED','effective_retry_limit':self.profile['max_transport_retries']})
                        time.sleep(retry_delay)
                    retries += 1
                    if streaming:
                        projection = new_projection()
                    continue
                raise
            except ProposalError as exc:
                failed_response = getattr(exc, 'response', None)
                failed_body = failed_response.get('body_json', failed_response) if isinstance(failed_response, dict) else {}
                if _response_diagnostics(failed_body).get('finish_reason') == 'length':
                    exc.generation_failure = 'OUTPUT_LENGTH_LIMIT'
                self.repo.finish_attempt(ident, 'FAILED', getattr(exc, 'response', None),
                                         {'model': self.transport.binding['model'], 'usage': None, 'error': exc.code})
                if routing:
                    budget=self.repo.budget()
                    limit=budget['model_limit']-(budget['finalization_reserve'] if phase=='investigate' else 0)
                    retry_scheduled=(not exc.unknown and response.get('status_code')==429 and response.get('acceptance')=='KNOWN_REJECTED'
                        and not (projection and projection.emitted) and budget['model_reserved']<limit and self.context.remaining()>1)
                    retry_scheduled=retry_scheduled and provider_routing.switch(self.repo,routing,self.transport.routing_hash,self.context.binding_hash,ident,response)
                    retry_delay=0.0
                obs.event(log, 'model.attempt.failed', level=logging.ERROR, **fields,
                          failure_kind='proposal', error_code=exc.code,
                          duration_ms=int((time.perf_counter() - attempt_started) * 1000))
                raise
            except ContractError as exc:
                self.repo.finish_attempt(ident, 'FAILED', getattr(exc, 'response', None),
                                         {'model': self.transport.binding['model'], 'usage': None, 'error': exc.code})
                raise
            except Exception as exc:
                self.repo.finish_attempt(ident, 'UNKNOWN', None, {'model': self.transport.binding['model'], 'usage': None, 'error': type(exc).__name__})
                if routing:
                    budget=self.repo.budget()
                    limit=budget['model_limit']-(budget['finalization_reserve'] if phase=='investigate' else 0)
                    retry_scheduled=(not exc.unknown and response.get('status_code')==429 and response.get('acceptance')=='KNOWN_REJECTED'
                        and not (projection and projection.emitted) and budget['model_reserved']<limit and self.context.remaining()>1)
                    retry_scheduled=retry_scheduled and provider_routing.switch(self.repo,routing,self.transport.routing_hash,self.context.binding_hash,ident,response)
                    retry_delay=0.0
                obs.event(log, 'model.attempt.failed', level=logging.ERROR, **fields,
                          failure_kind='adapter', error_type=type(exc).__name__,
                          duration_ms=int((time.perf_counter() - attempt_started) * 1000))
                raise TransportError('single-send adapter failed', unknown=True) from exc
            body = raw.get('body_json')
            receipt = {'model': body.get('model') if isinstance(body, dict) else None,
                       'usage': body.get('usage') if isinstance(body, dict) else None, 'attempt_id': ident,
                       **response_model_metadata(self.transport.binding, body)}
            length_metrics = response_length_metrics(request, body)
            receipt['input_metrics'] = {**input_metrics, **length_metrics}
            status = self.repo.finish_attempt(ident, 'SUCCEEDED', raw, receipt)
            obs.event(log, 'model.attempt.received', **fields,
                      http_status=raw.get('status_code'), journal_status=status,
                      duration_ms=int((time.perf_counter() - attempt_started) * 1000),
                      response_bytes=raw.get('response_bytes'),
                      **response_model_metadata(self.transport.binding, body),
                      **{**_response_diagnostics(body), **length_metrics})
            self.context.remaining()
            if status != 'SUCCEEDED':
                raise StaleProposal('late model response ignored')
            try:
                validate_response_model(self.transport.binding, body)
            except ContractError:
                if routing:
                    budget=self.repo.budget()
                    limit=budget['model_limit']-(budget['finalization_reserve'] if phase=='investigate' else 0)
                    retry_scheduled=(not exc.unknown and response.get('status_code')==429 and response.get('acceptance')=='KNOWN_REJECTED'
                        and not (projection and projection.emitted) and budget['model_reserved']<limit and self.context.remaining()>1)
                    retry_scheduled=retry_scheduled and provider_routing.switch(self.repo,routing,self.transport.routing_hash,self.context.binding_hash,ident,response)
                    retry_delay=0.0
                obs.event(log, 'model.attempt.failed', level=logging.ERROR, **fields,
                          failure_kind='model_mismatch', actual_model=receipt['model'])
                raise
            content = None
            raw_value = None
            try:
                from .completion_contracts import enabled
                content = structured_content(body,
                    require_complete=enabled(self.profile) or 'max_tokens' not in request,
                    allow_length_repair='max_tokens' in request)
                from .evidence_inventory import record_delivery
                record_delivery(self.repo, view, ident)
                value = output.strict_json(content)
                raw_value = deepcopy(value)
                raw_hash = digest(value)
                if str(role).startswith('source-law-navigation-'):
                    from . import request_repair
                    if request_repair.enabled(self.profile):
                        before = digest(value)
                        value, changes = request_repair.deduplicate_decision(value)
                        if changes:
                            self.repo.event('MODEL_OUTPUT_NORMALIZED', {'contract_version':output.VERSION,
                                'attempt_id':ident, 'rule':'exact-decision-duplicates-v1',
                                'raw_proposal_hash':before,'normalized_hash':digest(value),'changes':changes})
                value = minimal_output.expand(value)
                self.repo.event('MODEL_OUTPUT_RECONSTRUCTED', {
                    'attempt_id':ident, **minimal_output.receipt,
                    'raw_value_sha256':raw_hash, 'reconstructed_value_sha256':digest(value)})
                if references is not None:
                    # Generation may omit host-owned optional properties. Decode against
                    # the full request-local contract, then validate canonical IDs.
                    decoding_schema=(references.schema(self.protocol.schema(schema_name))
                        if schema_name=='BoundedSourceDecision' else minimal_output.schema)
                    value = references.decode(value, decoding_schema, schema_name)
                self.validate_output(schema_name,value,view)
                obs.event(log, 'model.attempt.accepted', **fields, schema_repairs=repairs)
                if journal:journal.accept(repairs, value)
                return value
            except StaleProposal:
                # A stale view is a runtime consistency failure, not bad JSON.
                raise
            except (ProposalError, ValidationError) as exc:
                if (role in ('memory-assess', 'memory-assess-repair')
                        and isinstance(exc, output.OutputContractError)
                        and exc.category == 'OUTPUT_SHAPE_INVALID'):
                    from .read_judgment_final import independent_core
                    core = independent_core(raw_value, minimal_output.schema, references, schema_name)
                    if core is not None:
                        # Keep this attempt rejected. The owning assessment stage
                        # still validates source semantics and its bounded recovery.
                        exc.proposal = core
                        exc.raw_proposal_hash = digest(raw_value)
                        self.repo.event('REJECTED_FINAL_CORE_RECONSTRUCTED', {
                            'attempt_id':ident, 'raw_proposal_hash':digest(raw_value),
                            'core_hash':digest(core), 'accepted':False})
                if _response_diagnostics(body).get('finish_reason') == 'length':
                    exc.generation_failure = 'OUTPUT_LENGTH_LIMIT'
                repair_scheduled = (output.repairable(exc) and repairs < repair_limit
                                    and not (projection and projection.emitted))
                if journal:journal.reject(repairs, exc, content,can_retry=repair_scheduled)
                obs.event(log, 'model.output.invalid', level=logging.WARNING, **fields,
                          error_type=type(exc).__name__, schema_repairs=repairs,
                          repair_scheduled=repair_scheduled,
                          **{**_response_diagnostics(body), **length_metrics})
                with self.repo.transaction():
                    from .investigation_diagnostics import exception_diagnostics
                    self.repo.event('OUTPUT_SCHEMA_INVALID', {
                        'attempt_id': ident, 'error': str(exc),
                        'input_metrics': {**input_metrics, **length_metrics},
                        'diagnostics':exception_diagnostics(exc,stage=phase),
                        'schema': schema_name, 'phase': phase,
                        'source_stage': view.get('source_stage'),
                        'error_type': type(exc).__name__,
                        'repair_scheduled': repair_scheduled, 'schema_repairs': repairs})
                if not repair_scheduled:
                    if isinstance(exc, output.OutputContractError):
                        exc.format_error = True
                        raise
                    error = ProposalError('structured model output invalid after bounded repair: '+str(exc)[:3000])
                    error.format_error = True
                    if hasattr(exc, 'generation_failure'):
                        error.generation_failure = exc.generation_failure
                    raise error from exc
                # Append-only chat cannot retract a draft. Repair still uses the
                # bounded journal path; only the final canonical result is shown.
                if streaming:
                    streaming = False
                    request = {**request, 'stream': False}
                    request.pop('stream_options', None)
                repairs += 1
                if journal:journal.reserve(repairs, max_repairs=repair_limit)
                # Raw output is already durable. Repair must pass the same schema
                # and decision checks; it grants no additional source visibility.
                # Server validation after decoding may mention internal IDs.
                # Keep repair instructions in the same request-local vocabulary.
                repair_error = str(exc)[:1000]
                if references is not None:
                    if hasattr(references, 'forward') and all(isinstance(x,str) for x in references.forward.values()):
                        for ident, handle in references.forward.items():
                            repair_error=repair_error.replace(ident,handle)
                    else:
                        for kind, ids in references.ids.items():
                            for number, ident in sorted(enumerate(ids, 1), key=lambda pair: -len(pair[1])):
                                repair_error = repair_error.replace(ident, f'<{kind} choice {number}>')
                valid_claims = (list(range(1, len(references.ids['claims'])+1)) if references is not None
                               else [c.get('claim') or c.get('entity_id') for c in view.get('claims',[])])
                request = {**request, 'messages': request['messages'][:2]+[{
                    'role': 'user', 'content': encoded({'repair': 'Respond again to the original task with the complete object matching the response schema. Correct the reported validation error using the same view and allowed references.',
                                                       'error_code': 'MODEL_OUTPUT_INVALID', 'schema': schema_name,
                                                       'validation':output.diagnostics(exc),
                                                       'invalid_response_excerpt': content[:4000] if isinstance(content, str) else encoded(content)[:4000], 'error': repair_error,
                                                       'valid_claim_ids':valid_claims})}]}
