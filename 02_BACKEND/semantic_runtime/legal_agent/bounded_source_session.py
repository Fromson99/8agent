"""Serving adapter for ADR0513 recall and ADR0517 two-call source selection.

Frozen algorithms live in ordinary runtime modules. No experiment output, gold,
external experiment transport, or recursive closure candidate is loaded here.
"""
import time
from dataclasses import replace
from copy import deepcopy
import jsonschema

from ..contracts import digest
from .. import observability as obs
from .gateway import ModelGateway, genos_wire_schema, compact_wire_view
from .repository import encoded
from . import output_contract as output
from .question_obligations import ObligationSession
from .workflow_tiers_views import span_choices
from .errors import BudgetExhausted, DeadlineExceeded, ProposalError, TransportError, ContractError
from . import source_query_planning, source_selection, obligation_protocol
from .source_recall import SourceRecall
from .structure_query import navigation_context, resolve as resolve_structure_query
log = obs.get_logger('legal_agent.bounded_source')


def compact_assessment_evidence(data, acquired):
    """Bind only the exact option spans actually included in this assessment.

    Compact source cards contain metadata; evidence_options carries the text.
    Reused originals may have new request-local evidence IDs, so match their
    immutable source/document/block coordinates and bytes, then verify again
    against the current source session before storing a delivery receipt.
    """
    from .source_tools import canonical_evidence
    from .repository import text_hash
    offered = {}
    for source in data.get('sources', []):
        if 'text' not in source:
            key = (source.get('source_id'), source.get('document_id'))
            offered.setdefault(key, set()).update(source.get('evidence_refs', []))
    if not offered:
        return []
    identities = ('source_id', 'document_id', 'block_id', 'start_cp', 'end_cp', 'evidence_id', 'text_hash')
    result = {}
    for option in data.get('evidence_options', []):
        if (not isinstance(option, dict) or set(option) != set(identities) | {'id', 'text'}
                or not isinstance(option['text'], str) or not option['text'].strip()
                or type(option['start_cp']) is not int or type(option['end_cp']) is not int
                or not 0 <= option['start_cp'] < option['end_cp']
                or option['end_cp'] - option['start_cp'] != len(option['text'])
                or option['text_hash'] != digest(option['text'])
                or option['id'] != 'S' + digest({k: option[k] for k in identities})[:28]
                or option['id'] not in offered.get((option['source_id'], option['document_id']), set())):
            raise ContractError('compact assessment option identity or source binding differs')
        matches = [(e, span) for e in acquired
                   if (e['source_id'], e['document_id']) == (option['source_id'], option['document_id'])
                   for span in e['spans'] if span['block_id'] == option['block_id']
                   and span['start_cp'] <= option['start_cp'] < option['end_cp'] <= span['end_cp']
                   and span['text'][option['start_cp']-span['start_cp']:option['end_cp']-span['start_cp']] == option['text']]
        if not matches:
            raise ContractError('compact assessment option was not acquired in this request')
        origin, span = matches[0]
        exact = {**span, 'start_cp': option['start_cp'], 'end_cp': option['end_cp'],
                 'text': option['text'], 'span_hash': text_hash(option['text'])}
        evidence = canonical_evidence(origin, [exact])
        result[evidence['evidence_id']] = evidence
    return list(result.values())


class _Protocol:
    def __init__(self, schema, validator=None):
        self.definition = schema
        self.validator = validator

    def schema(self, name):
        return deepcopy(self.definition)

    def validate(self, name, value):
        output.validate_shape(value, self.definition)
        if self.validator is not None:
            # Only explicit, read-only model-decision validation belongs here.
            # Storage, binding, deadline and transport failures retain their types.
            try:
                self.validator(value)
            except ValueError as exc:
                raise ProposalError('bounded source decision: '+str(exc)) from exc


class _Gateway(ModelGateway):
    def request(self, phase, view, schema_name, *, references=None):
        schema = self.protocol.schema(schema_name)
        instructions=''
        if view.get('input_projection')=='compact-selection-source-v3':
            from .navigation_input import NavigationReferences, INSTRUCTIONS, STABLE_INSTRUCTIONS
            references=references or NavigationReferences(view)
            view,schema=references.view(view),references.schema(schema)
            instructions='\n'+(STABLE_INSTRUCTIONS if references.stable else INSTRUCTIONS)+' text_ref는 sources의 text_id와 start/end 유니코드 문자 위치로 지정한 정확한 원문이다.'
        self._generation_schema = deepcopy(schema)
        schema = genos_wire_schema(schema)
        from . import compact_model_input as minimal
        wire_view = compact_wire_view(view, phase) if self.compact or view.get('source_stage')=='memory-guided-answer' else view
        if minimal.applies(self.profile, view):
            wire_view = minimal.project(wire_view, schema)
            instructions = '\n' + minimal.instructions(wire_view)
        user = {'view': wire_view}
        if not self.compact:
            user['output_schema'] = schema
        return {'model': self.transport.binding['model'], 'temperature': 0,
                **({'max_tokens': self.profile['max_output_tokens']}
                   if self.profile['max_output_tokens'] is not None else {}), 'stream': False,
                'chat_template_kwargs': {'enable_thinking': False},
                'messages': [{'role': 'system', 'content': self.system+instructions},
                             {'role': 'user', 'content': encoded(user)}],
                'response_format': {'type': 'json_schema', 'json_schema': {
                    'name': schema_name, 'strict': True, 'schema': schema}}}


class BoundedSourceSession(ObligationSession):
    def __init__(self, *args):
        super().__init__(*args)
        self.source_recall_record = None
        self.source_selection_record = None
        self.bounded_started = False
        self.selection_views = {}
        self.request_route = None
        self.direct_answer = None
        self.structure_first_record = None
        self.navigation_context = None

    def prepare_navigation_context(self):
        if self.navigation_context is None:
            from . import definition_entry
            self.sources.question_matches = self.sources.matcher.starts(
                self.context.request['question'], self.sources.scope)
            hints = navigation_context(
                self.context.request['question'], self.sources.matcher, self.sources.scope,
                matches=self.sources.question_matches)
            # Reuse the original/span/scope verifier before the first planner.
            # Its exact reference destinations are locations, never evidence or
            # applicability decisions. Acquisition keeps its own shared budget.
            definitions = [definition_entry.verified(self.sources, row)
                           for row in definition_entry.matches(self.sources)]
            hints['definitions'] = [{'definition_id': row['definition_id'], 'term': row['label'],
                **row['definition'], 'question_span': row['question_span'],
                'scope_status': row['scope_status'], 'scope_hint': row['scope_hint'],
                'connections': row['connections'], 'verification': row['verification'],
                'citation_eligible': False} for row in definitions]
            locations = {}
            for row in hints['definitions']:
                locations.setdefault(row['term'], set()).add(
                    (row['document_id'], row['unit_id'], row['source_id']))
            hints['definition_candidates_ambiguous'] = any(len(rows) > 1 for rows in locations.values())
            hints['location_counts'] = {key: len(hints[key])
                                       for key in ('documents', 'structures', 'terms', 'definitions')}
            hints['location_inventory_complete'] = True
            self.navigation_context = hints
            self.work.event('QUESTION_NAVIGATION_CONTEXT', self.navigation_context)
        return self.navigation_context

    def plan_request_search(self):
        hints = self.prepare_navigation_context()
        names = sorted({name for did, name in self.sources.matcher.documents.items() if did in self.sources.scope})
        from . import structure_selection as selection_sets, query_scope as qs
        records = []
        def validate_plan(value):
            source_query_planning.validate_catalogue(value, names)
            proposed = []
            for row in value.get('structure_selections', []):
                if row['user_quote'] not in self.context.request['question']:
                    raise ValueError('structure selection quote outside current request')
                docs = [did for did in self.sources.scope if self.sources.matcher.documents[did] == row['document']]
                if len(docs) != 1:
                    raise ValueError('structure selection document is ambiguous')
                record = selection_sets.resolve(row['selection'], self.sources.matcher, docs[0], self.sources.scope)
                if any(not qs.direct(self.sources, docs[0], uid) for uid in record['unit_ids']):
                    raise ValueError('structure selection escaped the existing direct search scope')
                proposed.append(record)
            qs.check_selection_exclusions(self.sources.matcher,
                [{'document_id':r['document_id'],'unit_id':uid} for r in proposed for uid in r['unit_ids']], proposed)
            records[:] = proposed
        value = self.structured(source_query_planning.CATALOGUE_SYSTEM,
            {'question': self.context.request['question'], 'law_names': names,
             'capabilities': source_query_planning.CAPABILITIES,
             'navigation_context': hints},
            source_query_planning.catalogue_schema(names, model=True),
            'source-query-plan', min(45, self.context.remaining()), 4096,
            validator=validate_plan)
        routed = source_query_planning.validate_catalogue(value, names)
        if records and not qs.active(self.sources):
            scope = {'contract': qs.CONTRACT, 'targets': [], 'selections': records}
            for record in records:
                for uid in record['unit_ids']:
                    target = qs.target(self.sources.matcher, record['document_id'], uid)
                    if target not in scope['targets']: scope['targets'].append(target)
            from ..contracts import digest
            qs.attach(self.sources, {**scope, 'hash': digest(scope)})
            self.work.event('MODEL_STRUCTURE_SCOPE_BOUND', {'scope': qs.active(self.sources)})
        routed['agent_required'] = routed['mode'] in ('BROWSE', 'SEARCH')
        return routed

    def structured(self, system, data, schema, phase, timeout, max_tokens=1536, *, validator=None):
        # A provider-managed profile takes precedence over every stage-local
        # default, including reference, planning and corrective calls.
        if self.profile['max_output_tokens'] is None:
            max_tokens = None
        if phase.startswith('source-reference-') and max_tokens is not None:
            max_tokens=max(max_tokens,4096)
        # The navigation owner gets one complete correction. A length failure
        # uses a separate explicit profile ceiling; ordinary output caps and
        # profiles without this opt-in retain their existing wire behavior.
        navigation = phase.startswith('source-law-navigation-')
        ceiling = self.profile.get('candidate_navigation', {}).get('length_recovery_max_tokens', 0)
        validation = (data.get('repair_contract') or {}).get('validation') or {}
        length_repair = (navigation and max_tokens is not None and ceiling > 0 and phase.endswith('-repair')
            and validation.get('category') == 'OUTPUT_INCOMPLETE'
            and any(row.get('code') == 'OUTPUT_LENGTH' for row in validation.get('issues', [])))
        if length_repair:
            original_max = max_tokens
            max_tokens = max(max_tokens, ceiling)
            self.work.event('LENGTH_RECOVERY_POLICY', {
                'version':'navigation-length-recovery-v1', 'source_stage':phase,
                'owner':'law-navigation', 'action':'FULL_DECISION',
                'original_max_tokens':original_max, 'max_tokens':max_tokens,
                'recovery_max_tokens':ceiling, 'max_corrections':1,
                'shared_request_budget':True, 'context_limit_known':False})
        # A title inventory or excerpt is never a receipt for a full original.
        evidence_ids=[]
        if self.profile.get('candidate_navigation',{}).get('compact_input') and (phase.startswith('source-law-navigation-') or phase in ('memory-assess','memory-assess-repair')):
            data={**data,'input_projection':('compact-selection-source-v3' if self.profile.get('candidate_navigation',{}).get('completion_policy_version')in ('investigation-completion-v6','investigation-completion-v7','investigation-completion-v8') else 'compact-selection-source-v2')}
        if self.work.VERSION==6:
            offered={s['source_id']:s['text'] for s in data.get('sources',[]) if 'source_id' in s and 'text' in s}
            acquired = {e['evidence_id']: e for e in self.work.evidence()}
            evidence_ids=[e['evidence_id'] for e in acquired.values()
                if e['source_id'] in offered and all(p['text'] in offered[e['source_id']] for p in e['spans'])]
            if evidence_ids:
                data={**data,'exact_evidence':[{'evidence':ident,'text':acquired[ident]['text'],
                    'spans':acquired[ident]['spans']} for ident in evidence_ids]}
            if phase in ('memory-assess', 'memory-assess-repair','memory-guided-answer'):
                projected = compact_assessment_evidence(data, list(acquired.values()))
                if projected:
                    existing = set(acquired)
                    new = [e for e in projected if e['evidence_id'] not in existing]
                    for e in projected:
                        self.sources.source.verify(e)
                    if new:
                        self.work.record_observation(
                            {'tool': 'assessment_option_projection', 'args': {'options_hash': digest(data['evidence_options'])}},
                            {'status': 'REUSED', 'kind': 'EXACT_ACQUIRED_SUBSPANS', 'model_delivery': 'NOT_YET_SENT'},
                            new, verify=self.sources.source.verify)
                    if new:
                        acquired = {e['evidence_id']: e for e in self.work.evidence()}
                    evidence_ids = list(dict.fromkeys(evidence_ids + [e['evidence_id'] for e in projected]))
                    data = {**data, 'exact_evidence': [
                        {'evidence': ident, 'text': acquired[ident]['text'],
                         'source_id': acquired[ident]['source_id'],
                         'document_id': acquired[ident]['document_id'],
                         'spans': acquired[ident]['spans']} for ident in evidence_ids]}
        from .completion_contracts import enabled
        completion = enabled(self.profile)
        finalizing = completion and phase in ('memory-guided-answer','memory-assess','memory-assess-repair','memory-ontology-supervisor','memory-final-reason-review','memory-compose','memory-compose-repair')
        diagnostic = output.owner_for(phase)=='reason-decision-review'
        self.work.event('MODEL_CORRECTION_OWNER', {'contract_version':output.VERSION,
            'source_stage':phase,'owner':output.owner_for(phase),'max_corrections':0 if diagnostic or phase=='memory-guided-answer' else 1,
            'shared_request_budget':True})
        native_phase = 'compose' if finalizing else 'investigate'
        budget_class = 'FINALIZE' if finalizing else 'INVESTIGATE'
        from . import compact_model_input as minimal
        data = {**data, 'source_stage': phase}
        if minimal.applies(self.profile, data):
            data = minimal.bind(data, schema, stable=self.profile.get('candidate_navigation',{}).get('stable_navigation_references',False),
                document_names=self.sources.matcher.documents)
        view = self.work.save_view(native_phase, {**data, **({'budget_class':budget_class} if completion else {})}, evidence_ids)
        profile = {**self.profile, 'numbered_references_enabled': False,
                   'max_output_tokens': max_tokens,
                   'max_transport_retries': self.profile['max_transport_retries'] if completion else 0}
        if output.owner_for(phase) != 'gateway':
            # Investigation owns the single correction; avoid a nested wire retry.
            profile['max_schema_repairs'] = 0
        if phase in ('source-law-navigation-supervisor-read-choice','memory-guided-answer') or diagnostic:
            # Each durable supervisor reservation is exactly one physical attempt.
            profile['max_transport_retries'] = 0
            profile['max_schema_repairs'] = 0
        if completion:
            self.work.event('EFFECTIVE_CALL_POLICY', {'source_stage':phase,'native_phase':native_phase,
                'budget_class':budget_class,'max_transport_retries':profile['max_transport_retries'],
                'override_reason':'durable diagnostic sends once' if diagnostic else 'release-bound completion contract'})
        if phase in ('source-triage', 'source-omission-review'):
            choices = schema['properties']['choices']
            allowed = choices['items']['properties']['id']['enum']
            def validate_selection(value):
                checked_value = value
                legacy_positive_choices = (
                    not self.profile.get('candidate_navigation', {}).get('investigation_control', False)
                    and 'status' not in choices['items']['properties']
                    and 'status' not in choices['items']['required'])
                if legacy_positive_choices:
                    # The existing legacy wire lists positive selections only.
                    # Validate that exact contract without changing the returned
                    # proposal; source_selection.call owns its normalization.
                    checked_value = deepcopy(value)
                    for choice in checked_value['choices']:
                        choice['status'] = 'ADOPT'
                source_selection.checked_choices(checked_value, allowed, choices['maxItems'])
                if any(not choice['reason'].strip() for choice in value['choices']):
                    raise ProposalError('source relevance reason must not be blank')
                if validator is not None:
                    validator(value)
            checked = validate_selection
        else:
            checked = validator
        context = replace(self.context, deadline=min(self.context.deadline, time.monotonic()+timeout))
        gateway = _Gateway(self.work, context, profile, self.gateway.domain,
                           self.gateway.transport, message_protocol=_Protocol(schema, checked),
                           system=system, prompts={phase: ''})
        if phase == 'source-query-plan':
            # Build the same read-only request as generate: include the actual
            # saved view, scope notice and wire schema without reserving a call.
            request = gateway.request(native_phase, view, 'BoundedSourceDecision')
            chars = len(encoded(request))
            limit = self.profile['max_context_chars']
            exceeded = bool(limit and chars > limit)
            self.work.event('QUESTION_NAVIGATION_CONTEXT_BUDGET', {
                'view_id': view['view_id'], 'request_sha256': digest(request),
                'binding_hash': self.context.binding_hash, 'actual_request_chars': chars,
                'max_context_chars': limit, 'location_counts': data.get('navigation_context', {}).get('location_counts', {}),
                'status': 'INCOMPLETE' if exceeded else 'WITHIN_BUDGET',
                'omitted_locations': 0, 'source_absence_proven': False, 'model_calls': 0})
            if exceeded:
                raise BudgetExhausted('complete initial navigation input exceeds request context budget')
        from . import narrative_answer as narrative
        rich = narrative.enabled(profile) and phase == narrative.PHASE
        if rich:
            # Coverage and references are checked in the gateway before accepting JSON.
            prior_checked = gateway.protocol.validator
            def check_answer(value):
                narrative.checked(value, data['answer_claim_ids'])
                if prior_checked is not None:prior_checked(value)
            gateway.protocol.validator = check_answer
        try:
            value = gateway.generate(native_phase, view, narrative.SCHEMA if rich else 'BoundedSourceDecision')
        except output.OutputContractError as exc:
            if navigation and max_tokens is not None and ceiling > 0 and any(row.get('code') == 'OUTPUT_LENGTH' for row in exc.issues):
                can_grow = not phase.endswith('-repair') and max_tokens < ceiling
                self.work.event('LENGTH_RECOVERY_POLICY', {
                    'version':'navigation-length-recovery-v1', 'source_stage':phase,
                    'owner':'law-navigation', 'action':'OWNER_CORRECTION' if can_grow else 'STOP',
                    'max_tokens':max_tokens, 'recovery_max_tokens':ceiling,
                    'max_corrections':1, 'shared_request_budget':True,
                    'context_limit_known':False})
                if not can_grow:
                    # Preserve the original typed cause and durable raw output.
                    # A second request with the same exhausted cap is not repair.
                    raise output.OutputContractError(str(exc),
                        [{**row, 'repairable':False} for row in exc.issues],
                        category=exc.category, repairable=False) from exc
            raise
        self.selection_views[phase] = view['view_id']
        return value

    def prepare_source_recall(self):
        if self.source_recall_record is None:
            self.source_recall_record = SourceRecall(self.sources).prepare()
        return self.source_recall_record

    def persist_bounded_selection(self, result, record):
        evidence = self.work.evidence()
        reasons = {}
        if result.get('law_navigation'):
            latest=next((self.selection_views[row['phase']] for row in reversed(result['decisions']) if row['phase'] in self.selection_views),None)
            for branch in result['law_navigation']['branches']:
                if branch['status']=='ACTIVE':reasons[branch['source_id']]=(branch['reason'],latest)
        for row in result['decisions']:
            phase = row['phase'] if row['phase'].startswith('source-unit-') else ('source-triage' if row['phase'] == 'triage' else 'source-omission-review')
            for choice in row['decision'].get('choices',[]):
                if choice.get('status') != 'ADOPT': continue
                reasons[result['label_to_source'][choice['id']]] = (choice['reason'], self.selection_views[phase])
        eligible=set(record.get('selection_complete',record['read_complete']))
        if result.get('reference_navigation'):
            from .unit_reading import reassemble
            for original in result.get('selected_originals',[]):
                acquired=[self.work.evidence(eid) for eid in original['evidence_ids']]
                if not acquired or any(e['source_id']!=original['source_id'] for e in acquired):
                    raise ProposalError('reference selection requires exact acquired evidence')
                for e in acquired:self.sources.source.verify(e)
                if reassemble(acquired)!=original['text']:
                    raise ProposalError('reference original differs from acquired evidence')
                eligible.add(original['source_id'])
            for batch in result['reference_navigation']['batches']:
                if not batch['decision']:continue
                targets={g['id']:g['target']['source_id'] for g in batch['data']['groups']}
                view_id=self.selection_views[batch.get('phase','source-reference-batch-'+str(batch['round']))]
                for choice in batch['decision']['decisions']:
                    if choice['action']=='FOLLOW':
                        reasons[targets[choice['id']]]=(choice['reason'],view_id)
        if set(result['final_ids'])-eligible:
            raise ProposalError('selection requires fully acquired originals')
        with self.work.transaction():
            seq = self.work.event('BOUNDED_SOURCE_SELECTION', {
                k: v for k, v in result.items() if k not in ('final_packets', 'actual_selector_excerpts', 'paths')}, advance=True)
            for e in evidence:
                if e['source_id'] not in result['final_ids'] or (result.get('final_evidence_ids') is not None and e['evidence_id'] not in result['final_evidence_ids']):
                    continue
                reason, view_id = reasons[e['source_id']]
                if not reason.strip():
                    raise ProposalError('source relevance reason must not be blank')
                self.sources.source.verify(e)
                # The model selected a source; every acquired page is retained.
                # Claim review later requires genuine full-text delivery receipts.
                key = 'SS'+digest([self.goal_id, e['evidence_id']])[:28]
                payload = {'evidence_id': e['evidence_id'], 'tier': 'CORE',
                    'basis_spans': span_choices(e, self.profile['max_source_excerpt_chars']),
                    'relevance_reason': reason, 'relation_refs': [],
                    'interpretation_status': 'UNASSESSED', 'status': 'SELECTED',
                    'goal_id': self.goal_id, 'question_revision': 1, 'view_id': view_id,
                    'binding_hash': self.context.binding_hash,
                    'selection_basis': ('STRUCTURE_FULL_ORIGINAL_COVERAGE_CHECK'
                                        if record.get('discovery_mode') == 'structure'
                                        else 'ADR0517_TITLE_ROUTE_AND_EXCERPT_REVIEW')}
                self.work.put('source_selection', key, payload, seq, evidence_ids=[e['evidence_id']])
            self.work.db.execute('UPDATE stage_artifact SET valid=0')

    def prepare_question_plan(self):
        schema = obligation_protocol.schema('TurnDecision')['properties']['question_plan']['anyOf'][0]
        def validate_plan(value):
            obligation_protocol.meaningful(value)
            self.prepare_plan(value)

        value = self.structured(
            '원질문의 실제 답변 요구와 배경을 구분한다. 모든 question_ref를 빠짐없이 포함한다. '
            'context_refs와 demands의 question_refs는 서로 겹치면 안 된다. '
            '질문에 없는 조건을 추가하지 않는다. 요구 문구는 완전한 문장으로 쓴다.',
            {'original_question': self.context.request['question'], 'question_pieces': self.context.pieces},
            schema, 'bounded-question-plan', min(30, self.context.remaining()), 4096,
            validator=validate_plan)
        self.commit_question_plan({'view_id': self.selection_views['bounded-question-plan']}, {'question_plan': value})

    def investigate(self):
        if not self.context.request['use_llm']:
            return super().investigate()
        if self.bounded_started:
            # Selection recovery is the second ADR0517 call, not a new graph walk.
            if self.pending:
                self.limitations.append('추가 근거 조사가 필요하지만 현재 선별·복구 실행 범위에서는 완료하지 못했습니다.')
                self.pending = []
            return self.retrieval()
        self.bounded_started = True
        started = time.monotonic()
        obs.event(log, 'bounded_source.started', run_id=self.context.run_id)
        try:
            routed = self.plan_request_search()
            self.request_route = {'agent_required': routed['agent_required'], 'mode': routed['mode'], 'reason': routed['reason'],
                                  'view_id': self.selection_views['source-query-plan']}
            if routed['mode']=='SEARCH':
                # Resolve only coordinates in the model-selected search terms;
                # a background or excluded coordinate in the question is not a command.
                from . import query_scope as qs, structure_selection as ss
                selected_sets = (qs.active(self.sources) or {}).get('selections', [])
                if selected_sets:
                    route = ss.route(selected_sets, self.sources.matcher, self.sources.scope)
                else:
                    route=resolve_structure_query(' '.join(routed['queries'] or routed['law_names']),
                        self.sources.matcher,self.sources.scope)
                self.sources.structure_query_route=route
                self.structure_first_record={**route,'fulltext_fallback':False}
                self.work.event('STRUCTURE_QUERY_RESOLVED',route)
            with self.work.transaction():
                self.work.event('REQUEST_ROUTED', {**self.request_route, 'answer': routed['answer']})
            obs.event(log, 'bounded_source.query_plan.finished', run_id=self.context.run_id,
                      agent_required=routed['agent_required'], duration_ms=int((time.monotonic()-started)*1000))
            if routed['mode'] == 'BROWSE':
                self.direct_answer, plan = self.catalogue_observation(routed)
                if self.direct_answer is not None:
                    self.metadata_only = True
                    self.intent = 'DRAFT'
                    self.next_mode = 'FINAL'
                    return self.retrieval()
            elif not routed['agent_required']:
                self.direct_answer = routed['answer'].strip()
                self.metadata_only = True
                self.intent = 'DRAFT'
                self.next_mode = 'FINAL'
                return self.retrieval()
            else:
                plan = {k: routed[k] for k in ('law_names', 'queries')}
            self.sources.recall_query_plan = plan
            record = self.prepare_source_recall()
            record.update(evidence=self.work.evidence(), query_plan=plan)
            self.work.event('SOURCE_RECALL_POOL', {k: record[k] for k in (
                'selected_for_read', 'read_complete', 'read_partial', 'routes', 'query_plan', 'limits')})
            result = None
            if (record.get('selection_complete',record['read_complete']) and
                    (record.get('discovery_mode') != 'structure'
                     or set(record['selected_for_read']) <= set(record.get('selection_complete',record['read_complete'])))):
                remaining = min(240-(time.monotonic()-started), self.context.remaining()-30)
                result = source_selection.select_sources(self.context.request['question'], record,
                    self.structured, remaining_seconds=remaining,
                    max_fulltext_chars=max(0, self.profile['max_context_chars']-12000), session=self.sources)
            if record.get('discovery_mode') == 'structure' and (result is None or result.get('needs_fulltext')):
                self.structure_first_record.update(fulltext_fallback=True,
                    fallback_reason=(result or {}).get('fallback_reason', 'INSUFFICIENT_STRUCTURAL_ORIGINALS'))
                self.work.event('STRUCTURE_QUERY_FULLTEXT_FALLBACK', {
                    **self.structure_first_record,
                    'structural_selection': result and {k: result[k] for k in ('first_ids', 'decisions')}})
                self.sources.force_fulltext_recall = True
                expanded = self.plan_request_search()
                if expanded['mode'] != 'SEARCH':
                    raise ProposalError('an explicit source question cannot become a direct response during fallback')
                self.sources.recall_query_plan = {k: expanded[k] for k in ('law_names', 'queries')}
                self.source_recall_record = None
                record = self.prepare_source_recall()
                record.update(evidence=self.work.evidence(), query_plan=self.sources.recall_query_plan)
                self.work.event('SOURCE_RECALL_POOL', {k: record[k] for k in (
                    'selected_for_read', 'read_complete', 'read_partial', 'routes', 'query_plan', 'limits')})
                if record.get('selection_complete',record['read_complete']):
                    remaining = min(240-(time.monotonic()-started), self.context.remaining()-30)
                    result = source_selection.select_sources(self.context.request['question'], record,
                        self.structured, remaining_seconds=remaining, session=self.sources)
                else:
                    result = None
            if result is None:
                self.limitations.append('완전히 확보된 원문이 없어 선별을 수행하지 못했습니다.')
                return self.retrieval()
            if result.get('status')=='pending':
                raise ProposalError('unit investigation remains pending; required originals are unresolved')
            self.persist_bounded_selection(result, record)
            self.source_selection_record = result
            obs.event(log, 'bounded_source.selection.finished', run_id=self.context.run_id,
                      selected_count=len(result['final_ids']), duration_ms=int((time.monotonic()-started)*1000))
            if record['read_partial'] and not record.get('unit_read_contract'):
                self.limitations.append('일부 원문 확보가 미완료여서 완전히 읽은 후보에서만 선별했습니다.')
            self.prepare_question_plan()
            obs.event(log, 'bounded_source.question_plan.finished', run_id=self.context.run_id,
                      duration_ms=int((time.monotonic()-started)*1000))
            self.intent = 'DRAFT'
        except (BudgetExhausted, DeadlineExceeded, ProposalError, TransportError, TimeoutError, ValueError) as exc:
            self.limitations.append('원문 회수·선별·복구를 완료하지 못했습니다: '+str(exc))
            self.work.event('BOUNDED_SOURCE_FAILURE', {'type': type(exc).__name__, 'message': str(exc)})
            obs.event(log, 'bounded_source.failed', run_id=self.context.run_id,
                      error_type=type(exc).__name__, duration_ms=int((time.monotonic()-started)*1000))
        return self.retrieval()

    def catalogue_pages(self, tool, args, label, max_pages=32):
        items, receipts, cursor = [], [], None
        for page in range(max_pages):
            action = {'tool': tool, 'args': {**args, 'cursor': cursor}, 'reason': '요청 분기에 따른 허용 문서 탐색',
                      'question_refs': [], 'expected_information': '현재 허용된 문서 제목과 목차; 본문·법률 판단 근거는 별도'}
            result = self.sources.execute(action, 'catalogue-'+label+'-'+str(page), actor='SYSTEM_POLICY')
            receipts.append(result)
            if result['status'] not in ('OK', 'EMPTY', 'PARTIAL', 'REUSED'):
                raise ProposalError('catalogue tool failed: '+result['status'])
            items.extend(result['items'])
            cursor = result['next_cursor']
            if cursor is None:
                break
        return items, receipts, cursor is None

    def catalogue_observation(self, routed, *, document_scope=None):
        scope=set(self.sources.scope)
        if document_scope is not None:scope.intersection_update(document_scope)
        documents = [did for did in sorted(scope) if routed['document_category'] == 'all' or
                     self.sources.matcher.document_catalogue[did]['category'] == routed['document_category']]
        target = self.sources.handle('R', {'documents': sorted(documents)})
        if routed['title_query']:
            tool, args = 'search', {'target': target, 'mode': 'title', 'query': routed['title_query']}
        else:
            tool, args = 'browse', {'target': target, 'relation': 'self',
                                   'view': 'children' if routed['browse_view'] == 'folders' else 'outline', 'depth': 1}
        items, receipts, complete = self.catalogue_pages(tool, args, 'root')
        self.catalogue_receipts = receipts
        with self.work.transaction():
            self.work.event('CATALOGUE_OBSERVED', {'items': len(items), 'complete': complete,
                                                 'operation': tool, 'mode': routed['mode']})
        if not routed['inspect_documents']:
            labels = list(dict.fromkeys(i.get('name') or i.get('title') or i.get('document_name', '') for i in items))
            heading = '조회 가능한 폴더' if routed['browse_view'] == 'folders' else '조회 가능한 문서·목차'
            text = heading+' ('+str(len(labels))+'개):\n'+'\n'.join('- '+s for s in labels)
            if not labels:
                text = '현재 요청에 허용된 자료에서 해당 조건의 문서를 찾지 못했습니다. 전체 시스템에 자료가 없다는 의미는 아닙니다.'
            if not complete:
                text += '\n목록 일부를 조회했습니다. 전체 목록 조회는 완료되지 않았습니다.'
            return text, None
        docs = [i for i in items if i['target'].startswith('D')]
        offered = [i['target'] for i in docs]
        if not offered:
            return '현재 허용된 목록에서 선택할 문서를 찾지 못했습니다.', None
        schema = {'type': 'object', 'properties': {'targets': {'type': 'array', 'minItems': 1, 'maxItems': 3,
                  'uniqueItems': True, 'items': {'type': 'string', 'enum': offered}},
                  'reason': {'type': 'string', 'minLength': 1}}, 'required': ['targets', 'reason'], 'additionalProperties': False}
        selected = self.structured('질문에 맞춰 실제 목록에서 목차를 볼 문서를 최대3개 선택한다. 법률 결론을 만들지 않는다.',
            {'question': self.context.request['question'], 'catalogue': docs, 'complete': complete},
            schema, 'catalogue-document-choice', min(45, self.context.remaining()), 2048)
        outlines = []
        for target in selected['targets']:
            rows, received, done = self.catalogue_pages('browse', {'target': target, 'relation': 'self',
                'view': 'outline', 'depth': 1}, target, max_pages=6)
            self.catalogue_receipts.extend(received)
            outlines.append({'document': next(i for i in docs if i['target'] == target), 'outline': rows, 'complete': done})
        names = sorted({i['name'] for i in docs})
        schema = {'type': 'object', 'properties': {
            'search_required': {'type': 'boolean'}, 'answer': {'type': 'string'},
            'law_names': {'type': 'array', 'maxItems': 3, 'items': {'type': 'string', 'enum': names}},
            'queries': {'type': 'array', 'maxItems': 4, 'items': {'type': 'string', 'minLength': 2}}},
            'required': ['search_required', 'answer', 'law_names', 'queries'], 'additionalProperties': False}
        def validate_next_step(value):
            if value['search_required']:
                if not value['queries'] or value['answer']:
                    raise ProposalError('catalogue search requires queries and no answer')
            elif not value['answer'].strip() or value['queries'] or value['law_names']:
                raise ProposalError('catalogue recommendation requires observation-based answer only')

        decision = self.structured('실제 목록·목차를 보고 다음 행동을 정한다. 문서·읽을 곳 추천은 관찰한 제목과 조문명만으로 answer를 작성하고 search_required=false,검색어/법령명은 비운다. 내용·법률 판단이 필요한 질문은 search_required=true,answer=""로 검색어와 정확한 문서명을 만든다. 목차는 본문을 읽은 근거가 아니다. 법률 결론·수치·본문 인용을 추측하지 않는다.',
            {'question': self.context.request['question'], 'observed_outlines': outlines}, schema,
            'catalogue-next-step', min(45, self.context.remaining()), 4096,
            validator=validate_next_step)
        if decision['search_required']:
            return None, {k: decision[k] for k in ('law_names', 'queries')}
        return decision['answer'], None


    def metadata(self, *, final=False, gate=None):
        meta = super().metadata(final=final, gate=gate)
        record, selected = self.source_recall_record or {}, self.source_selection_record or {}
        meta['bounded_source_workflow'] = {
            'version': 'adr0513-recall-adr0517-selection-v1',
            'search_policy': 'structure-first-v1',
            'status': 'DIRECT_RESPONSE' if self.direct_answer is not None else
                      selected.get('status', 'NOT_COMPLETED' if self.bounded_started else 'NOT_STARTED'),
            'read_complete_count': len(record.get('read_complete', [])),
            'first_ids': selected.get('first_ids', []), 'recovered_ids': selected.get('recovered_ids', []),
            'final_ids': selected.get('final_ids', []), 'limits': record.get('limits', []),
            'source_selection_is_legal_approval': False, 'serving_recall_measured': False}
        if self.request_route is not None:
            meta['request_routing'] = {**self.request_route,
                'mode': self.request_route['mode']}
        if self.structure_first_record is not None:
            meta['structure_first_search'] = self.structure_first_record
        return meta

    def answer_and_review(self, assembled):
        result, control = super().answer_and_review(assembled)
        if self.direct_answer is not None:
            result['answer']['text'] = self.direct_answer
            result['answer']['provider_receipt'].update(response_mode=self.request_route['mode'],
                                                       agent_required=self.request_route['agent_required'])
        return result, control

    def select(self, retrieved):
        result = super().select(retrieved)
        if self.source_selection_record:
            # Journal head ordering is by identity, not original page offsets.
            originals = {x['source_id']:x for x in self.source_selection_record.get('selected_originals',[])} or source_selection.originals(self.source_recall_record)
            for context in self.packed['contexts']:
                context['text'] = originals[context['id']]['text']
        return result
