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
from .question_obligations import ObligationSession
from .workflow_tiers_views import span_choices
from .tools_policy import metadata_only_request
from .errors import BudgetExhausted, DeadlineExceeded, ProposalError, TransportError
from . import source_query_planning, source_selection, obligation_protocol
from .source_recall import SourceRecall
log = obs.get_logger('legal_agent.bounded_source')


class _Protocol:
    def __init__(self, schema):
        self.definition = schema

    def schema(self, name):
        return deepcopy(self.definition)

    def validate(self, name, value):
        try:
            jsonschema.Draft202012Validator(self.definition).validate(value)
        except jsonschema.ValidationError as exc:
            raise ProposalError('bounded source response: '+exc.message) from exc


class _Gateway(ModelGateway):
    def request(self, phase, view, schema_name, *, references=None):
        schema = genos_wire_schema(self.protocol.schema(schema_name))
        user = {'view': compact_wire_view(view, phase) if self.compact else view}
        if not self.compact:
            user['output_schema'] = schema
        return {'model': self.transport.binding['model'], 'temperature': 0,
                'max_tokens': self.profile['max_output_tokens'], 'stream': False,
                'chat_template_kwargs': {'enable_thinking': False},
                'messages': [{'role': 'system', 'content': self.system},
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

    def structured(self, system, data, schema, phase, timeout, max_tokens=1536):
        # A title inventory or excerpt is never a receipt for a full original.
        view = self.work.save_view('investigate', {**data, 'source_stage': phase}, [])
        profile = {**self.profile, 'numbered_references_enabled': False,
                   'max_output_tokens': max_tokens, 'max_schema_repairs': 0,
                   'max_transport_retries': 0}
        context = replace(self.context, deadline=min(self.context.deadline, time.monotonic()+timeout))
        gateway = _Gateway(self.work, context, profile, self.gateway.domain,
                           self.gateway.transport, message_protocol=_Protocol(schema),
                           system=system, prompts={phase: ''})
        value = gateway.generate('investigate', view, 'BoundedSourceDecision')
        self.selection_views[phase] = view['view_id']
        return value

    def prepare_source_recall(self):
        if self.source_recall_record is None:
            self.source_recall_record = SourceRecall(self.sources).prepare()
        return self.source_recall_record

    def persist_bounded_selection(self, result, record):
        evidence = self.work.evidence()
        reasons = {}
        for row in result['decisions']:
            phase = 'source-triage' if row['phase'] == 'triage' else 'source-omission-review'
            for choice in row['decision']['choices']:
                reasons[result['label_to_source'][choice['id']]] = (choice['reason'], self.selection_views[phase])
        if set(result['final_ids'])-set(record['read_complete']):
            raise ProposalError('selection requires fully acquired originals')
        with self.work.transaction():
            seq = self.work.event('BOUNDED_SOURCE_SELECTION', {
                k: v for k, v in result.items() if k not in ('final_packets', 'actual_selector_excerpts', 'paths')}, advance=True)
            for e in evidence:
                if e['source_id'] not in result['final_ids']:
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
                    'selection_basis': 'ADR0517_TITLE_ROUTE_AND_EXCERPT_REVIEW'}
                self.work.put('source_selection', key, payload, seq, evidence_ids=[e['evidence_id']])
            self.work.db.execute('UPDATE stage_artifact SET valid=0')

    def prepare_question_plan(self):
        schema = obligation_protocol.schema('TurnDecision')['properties']['question_plan']['anyOf'][0]
        value = self.structured(
            '원질문의 실제 답변 요구와 배경을 구분한다. 모든 question_ref를 빠짐없이 포함한다. '
            '질문에 없는 조건을 추가하지 않는다. 요구 문구는 완전한 문장으로 쓴다.',
            {'original_question': self.context.request['question'], 'question_pieces': self.context.pieces},
            schema, 'bounded-question-plan', min(30, self.context.remaining()), 4096)
        self.commit_question_plan({'view_id': self.selection_views['bounded-question-plan']}, {'question_plan': value})

    def investigate(self):
        if not self.context.request['use_llm'] or metadata_only_request(self.context.request['question']):
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
            names = sorted({name for did, name in self.sources.matcher.documents.items() if did in self.sources.scope})
            cases = [{'case_id': 'request', 'question': self.context.request['question']}]
            value = self.structured(source_query_planning.SYSTEM,
                {'cases': cases, 'law_names': names}, source_query_planning.schema(['request'], names),
                'source-query-plan', min(45, self.context.remaining()), 4096)
            plan = source_query_planning.validate(value, cases, names)['request']
            obs.event(log, 'bounded_source.query_plan.finished', run_id=self.context.run_id,
                      duration_ms=int((time.monotonic()-started)*1000))
            self.sources.recall_query_plan = plan
            record = self.prepare_source_recall()
            record.update(evidence=self.work.evidence(), query_plan=plan)
            self.work.event('SOURCE_RECALL_POOL', {k: record[k] for k in (
                'selected_for_read', 'read_complete', 'read_partial', 'routes', 'query_plan', 'limits')})
            if not record['read_complete']:
                self.limitations.append('완전히 확보된 원문이 없어 선별을 수행하지 못했습니다.')
                return self.retrieval()
            remaining = min(240-(time.monotonic()-started), self.context.remaining()-30)
            result = source_selection.select_sources(self.context.request['question'], record,
                        self.structured, remaining_seconds=remaining)
            self.persist_bounded_selection(result, record)
            self.source_selection_record = result
            obs.event(log, 'bounded_source.selection.finished', run_id=self.context.run_id,
                      selected_count=len(result['final_ids']), duration_ms=int((time.monotonic()-started)*1000))
            if record['read_partial']:
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

    def metadata(self, *, final=False, gate=None):
        meta = super().metadata(final=final, gate=gate)
        record, selected = self.source_recall_record or {}, self.source_selection_record or {}
        meta['bounded_source_workflow'] = {
            'version': 'adr0513-recall-adr0517-selection-v1',
            'status': selected.get('status', 'NOT_COMPLETED' if self.bounded_started else 'NOT_STARTED'),
            'read_complete_count': len(record.get('read_complete', [])),
            'first_ids': selected.get('first_ids', []), 'recovered_ids': selected.get('recovered_ids', []),
            'final_ids': selected.get('final_ids', []), 'limits': record.get('limits', []),
            'source_selection_is_legal_approval': False, 'serving_recall_measured': False}
        return meta

    def select(self, retrieved):
        result = super().select(retrieved)
        if self.source_selection_record:
            # Journal head ordering is by identity, not original page offsets.
            originals = source_selection.originals(self.source_recall_record)
            for context in self.packed['contexts']:
                context['text'] = originals[context['id']]['text']
        return result
