"""Tool exploration, revisable evidence judgments and claim-local review in one request."""
import json
import uuid
from ..contracts import digest
from . import tools_protocol as protocol
from .tools_policy import IMPLEMENTATION
from .session import LegalSession
from .repository import encoded
from .errors import BudgetExhausted, DeadlineExceeded, ProposalError, ContractError, TransportError


def strings(value):
    if isinstance(value, str): return {value}
    if isinstance(value, dict): return set().union(set(), *(strings(v) for v in value.values()))
    if isinstance(value, list): return set().union(set(), *(strings(v) for v in value))
    return set()


class ToolsSession(LegalSession):
    def __init__(self, *args):
        super().__init__(*args)
        self.pending = []
        self.errors = []
        self.intent = 'CONTINUE'
        self.next_mode = 'RESEARCH'
        self.disputes = {}
        self.rebuttals = []
        self.question_review = None
        self.metadata_only = False

    def metadata(self, *, final=False, gate=None):
        meta = super().metadata(final=final, gate=gate)
        meta['implementation'] = IMPLEMENTATION
        meta['exploration_v2'] = {'schema_version': 'tool-exploration-v2', 'status': gate or 'INVESTIGATING',
            'capabilities': self.sources.capabilities, 'evidence_decisions': [h['payload'] for h in self.work.heads('assessment', current=True)],
            'trace_binding': self.context.binding_hash, 'model_attempts': self.work.budget()['model_reserved'],
            'finish_reason': '; '.join(self.limitations)}
        return meta

    def view(self, phase, *, required=(), extra=None):
        evidence = {e['evidence_id']: e for e in self.work.evidence()}
        recent = self.work.observations(8)
        preferred = list(dict.fromkeys(list(required)+[e for o in reversed(recent) for e in o.get('evidence_ids', [])]))
        body = {'original_question': self.context.request['question'], 'question_pieces': self.context.pieces,
                'corpus_root': self.sources.root, 'tool_capabilities': self.sources.capabilities,
                'last_action_results': recent, 'exact_evidence': [], 'omitted_evidence': [], 'omitted_action_results': [],
                'assessments': self.work.heads('assessment', current=True),
                'questions': self.work.heads('intent', current=True), 'budgets': self.work.budget(),
                'errors': self.errors[-2:], **(extra or {})}
        # Observations identify E; exact text has one authoritative copy in this view.
        def strip_text(value):
            if isinstance(value, dict):
                return {k: strip_text(v) for k,v in value.items() if k not in ('text', 'spans', 'metadata_json')}
            if isinstance(value, list): return [strip_text(v) for v in value]
            return value
        body['last_action_results'] = strip_text(recent)
        limit = self.profile['max_context_chars']
        while len(encoded(body)) > limit//2 and len(body['last_action_results']) > 1:
            omitted = body['last_action_results'].pop(0)
            body['omitted_action_results'].append({'observation_id':omitted['observation_id'],
                'tool':omitted['action']['tool'], 'status':omitted['status'], 'evidence_ids':omitted.get('evidence_ids',[]),
                'reason':'context limit; inspect history/evidence or rerun the paged tool'})
        for ident in preferred:
            e = evidence[ident]
            item = {'evidence': ident, 'text': e['text'], 'text_hash': e['text_hash'],
                    'source_id': e['source_id'], 'document_name': e['metadata'].get('document_name'),
                    'role': e['role'], 'temporal_status': e['temporal_status'], **self.sources.location(ident)}
            if len(encoded(body))+len(encoded(item)) > limit:
                if ident in required:
                    raise BudgetExhausted('required support/challenge text does not fit context')
                body['omitted_evidence'].append(ident)
            else: body['exact_evidence'].append(item)
        if len(encoded(body)) > limit:
            raise BudgetExhausted('required state exceeds context limit')
        return self.work.save_view(phase, body, [e['evidence'] for e in body['exact_evidence']])

    def qrefs(self, refs):
        if set(refs)-{q['id'] for q in self.context.pieces}:
            raise ProposalError('unknown original question segment')

    def apply_turn(self, view, decision):
        protocol.validate('TurnDecision', decision)
        key = 'turn:'+view['view_id']
        signature = digest(decision)
        old = self.work.db.execute('SELECT payload_json FROM event WHERE event_id=?', (key,)).fetchone()
        if old:
            if json.loads(old[0])['hash'] != signature: raise ProposalError('view reused with different decision')
            return False
        self.work.check_view(view['view_id'], 'investigate')
        offered = strings(view)
        for action in decision['actions']:
            self.sources.validate_action(action, offered)
        if decision['intent']=='DRAFT' and view.get('omitted_action_results'):
            delivered_before = set()
            for row in self.work.db.execute("SELECT DISTINCT v.body_json FROM model_view v JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED' AND v.view_id!=?",(view['view_id'],)):
                delivered_before.update(o['observation_id'] for o in json.loads(row[0]).get('last_action_results',[]))
            if any(o['observation_id'] not in delivered_before for o in view['omitted_action_results']):
                raise ProposalError('new tool result omitted from input; inspect or narrow the tool result before drafting')
        seen = set()
        for a in decision['assessments']:
            if a['evidence'] in seen: raise ProposalError('conflicting duplicate evidence assessment')
            seen.add(a['evidence']); self.work.visible(view['view_id'], [a['evidence']]); self.qrefs(a['question_refs'])
        for field, name, kind in [('candidate_decisions','candidate','P'),('route_decisions','route','L')]:
            for d in decision[field]:
                self.sources.resolve(d[name], kind)
                if d[name] not in offered: raise ProposalError('decision target not offered')
        for q in decision['question_updates']: self.qrefs(q['question_refs'])
        with self.work.transaction():
            seq = self.work.event('TOOL_TURN', {'hash': signature, 'decision': decision}, event_id=key, advance=True)
            for a in decision['assessments']:
                existing = next((h for h in self.work.heads('assessment', current=True) if h['entity_id']==a['evidence']), None)
                if existing and existing['payload']==a: continue
                if a['role']=='CHALLENGE' and existing is None:
                    for r in self.work.heads('review', current=True): self.work.invalidate('review', r['entity_id'], r['version'])
                self.work.put('assessment', a['evidence'], a, seq, evidence_ids=[a['evidence']])
            for field, name in [('candidate_decisions','candidate'),('route_decisions','route')]:
                for d in decision[field]: self.work.put('intent', d[name], d, seq)
            for q in decision['question_updates']:
                for ident in q['question_refs']:
                    for c in self.work.heads('claim', current=True):
                        if ident in c['payload']['question_refs']: self.work.invalidate('claim', c['entity_id'], c['version'])
                    self.work.put('intent', ident, q, seq)
            self.work.db.execute('UPDATE stage_artifact SET valid=0')
        self.intent = decision['intent']
        for i, action in enumerate(decision['actions']):
            self.sources.execute(action, f'{view["view_id"]}:{i}')
        return True

    def progress_key(self):
        return digest({'evidence': [e['evidence_id'] for e in self.work.evidence()],
                       'assessments': [(h['entity_id'], h['payload']) for h in self.work.heads('assessment', current=True)],
                       'intent': [(h['entity_id'], h['payload']) for h in self.work.heads('intent', current=True)],
                       'actions': sorted({o['args_hash'] for o in self.work.observations(self.profile['max_tool_actions']) if o['status'] in ('OK','PARTIAL')})})

    def investigate(self):
        from .tools_policy import metadata_only_request
        plain_catalogue = metadata_only_request(self.context.request['question'])
        if not self.context.request['use_llm'] or plain_catalogue:
            self.work.event('REQUEST_ROUTED', {
                'mode': 'BROWSE', 'agent_required': True,
                'reason': '현재 요청 범위에서 문서 목록을 확인합니다.'})
            target = self.sources.root
            if plain_catalogue:
                from ..folder_navigation import request as parse_catalogue
                filters = parse_catalogue(self.context.request['question'])
                documents, offset = [], 0
                while offset is not None:
                    page = self.sources.source.navigator.catalogue(self.sources.scope, **filters, offset=offset, limit=500)
                    documents.extend(d['id'] for d in page['documents']); offset = page['next_offset']
                target = self.sources.handle('F', {'documents': sorted(documents), 'filter': filters})
            self.sources.execute({'tool': 'browse', 'args': {'target': target, 'relation': 'self',
                'view': 'outline', 'depth': 1, 'cursor': None}, 'reason': '모델 미사용 자료 목록'}, 'metadata')
            self.metadata_only = True
            if self.work.observations(1)[0]['next_cursor'] is not None:
                self.limitations.append('자료 목록의 첫 페이지입니다. 문서 목록 API에서 이어서 확인할 수 있습니다.')
            return self.retrieval()
        try:
            for i, action in enumerate(self.pending):
                self.sources.execute(action, f'review:{self.cycles}:{i}')
        except (BudgetExhausted, DeadlineExceeded) as exc:
            self.limitations.append('검토 후 추가 탐색을 완료하지 못했습니다: '+str(exc))
            self.pending = []
            return self.retrieval()
        self.pending = []
        no_progress, errors = 0, {}
        while True:
            before = self.progress_key()
            try:
                decision = self.generate_checked('investigate','TurnDecision',self.apply_turn,required=())
                # New tool results must be observed by a subsequent decision.
                if not decision['actions'] and decision['intent'] != 'CONTINUE':
                    break
                no_progress = no_progress+1 if before == self.progress_key() else 0
                if no_progress >= self.profile['max_no_progress']:
                    self.limitations.append('추가 원문이나 판단 변화 없이 탐색이 반복되었습니다.'); break
            except ProposalError as exc:
                fingerprint = str(exc)
                if getattr(exc, 'format_error', False):
                    self.limitations.append('모델 응답 형식의 정정을 완료하지 못했습니다.'); break
                errors[fingerprint] = errors.get(fingerprint, 0)+1
                self.errors.append({'code': exc.code, 'message': fingerprint})
                with self.work.transaction(): self.work.event('SEMANTIC_REPAIR', self.errors[-1])
                self.limitations.append('도구·근거 선택 오류의 정정을 완료하지 못했습니다.'); break
            except (BudgetExhausted, DeadlineExceeded, TransportError) as exc:
                self.limitations.append('탐색을 완료하지 못했습니다: '+str(exc)); break
        return self.retrieval()

    def select(self, retrieved):
        assessments = [h['payload'] for h in self.work.heads('assessment', current=True)]
        support = [a['evidence'] for a in assessments if a['disposition']=='ADOPT' and a['role']=='SUPPORT']
        challenge = [a['evidence'] for a in assessments if a['role']=='CHALLENGE']
        contextual = [a['evidence'] for a in assessments if a['disposition']=='ADOPT' and a['role']=='CONTEXT']
        ids = list(dict.fromkeys(support+challenge+contextual))
        contexts = {}
        for ident in ids:
            e = self.work.evidence(ident)
            c = contexts.setdefault(e['source_id'], {'id': e['source_id'], 'document_id': e['document_id'],
                'document_name': e['metadata']['document_name'], 'unit_id': e['unit_id'], 'text': '', 'evidence_ids': []})
            c['text'] += ('\n' if c['text'] else '')+e['text']; c['evidence_ids'].append(ident)
        self.packed = {'support': support, 'challenge': challenge, 'contextual': contextual, 'evidence_ids': ids,
                       'contexts': list(contexts.values()), 'unresolved': []}
        return {'selected': list(contexts.values()), 'discarded_ids': [c['id'] for c in retrieved['retrieval']['candidates'] if c['id'] not in contexts],
                'method': 'term-agent', 'term_agent': self.metadata()}

    def commit_draft(self, view, draft):
        self.work.check_view(view['view_id'], 'compose')
        valid = set(self.packed['support']+self.packed['contextual'])
        for p in draft['paragraphs']:
            self.qrefs(p['question_refs'])
            self.work.visible(view['view_id'], p['evidence'])
            if set(p['evidence'])-valid or not set(p['evidence']).intersection(self.packed['support']):
                raise ProposalError('draft must cite adopted support, never rejected or challenge-only evidence')
        with self.work.transaction():
            seq = self.work.event('DRAFT_V2', {'draft': draft}, advance=True)
            retained = []
            for old in self.work.heads('claim', current=True):
                try: accepted = self.work.head('review', old['entity_id'])['payload']['verdict']=='SUPPORTED'
                except ProposalError: accepted = False
                if accepted: retained.append(old['payload'])
                else: self.work.invalidate('claim', old['entity_id'], old['version'])
            for p in draft['paragraphs']:
                if p in retained: continue
                ident = 'C'+str(self.work.db.execute("SELECT count(*) FROM entity_head WHERE kind='claim'").fetchone()[0]+1)
                deps = [('assessment', e) for e in p['evidence']]
                deps += [('intent', q) for q in p['question_refs'] if self.work.db.execute("SELECT 1 FROM entity_head WHERE kind='intent' AND entity_id=?", (q,)).fetchone()]
                self.work.put('claim', ident, p, seq, dependencies=deps, evidence_ids=p['evidence'])
        self.question_review = None

    def commit_review(self, view, review):
        self.work.check_view(view['view_id'], 'review')
        self.qrefs(review['question']['question_refs'])
        claims = {h['entity_id']: h for h in self.work.heads('claim', current=True)}
        if len({c['claim'] for c in review['checks']}) != len(review['checks']):
            raise ProposalError('duplicate claim review')
        if {c['claim'] for c in review['checks']} != set(claims):
            raise ProposalError('each current claim requires a review')
        if set(review['question']['question_refs']) != {q['id'] for q in self.context.pieces}:
            raise ProposalError('review must address the complete original question')
        for check in review['checks']:
            self.work.visible(view['view_id'], check['evidence'])
            if not check['evidence']:
                raise ProposalError('review objection/support requires exact evidence')
            if check['verdict']=='SUPPORTED' and set(claims[check['claim']]['payload']['evidence'])-set(check['evidence']):
                raise ProposalError('review must compare every cited evidence')
            relevant_challenges = {a['payload']['evidence'] for a in self.work.heads('assessment', current=True)
                if a['payload']['role']=='CHALLENGE' and (not a['payload']['question_refs'] or
                    set(a['payload']['question_refs']) & set(claims[check['claim']]['payload']['question_refs']))}
            if check['verdict']=='SUPPORTED' and relevant_challenges-set(check['evidence']):
                raise ProposalError('review must address presented challenges related to this claim')
            if check['verdict']=='NEEDS_RESEARCH' and not check['actions']:
                raise ProposalError('research review requires an executable action')
            for action in check['actions']: self.sources.validate_action(action, strings(view))
        # All packed challenge sources must actually be present, including rejected E.
        self.work.visible(view['view_id'], self.packed['evidence_ids'])
        with self.work.transaction():
            seq = self.work.event('REVIEW_V2', review, advance=True)
            for check in review['checks']:
                self.work.put('review', check['claim'], check, seq,
                    dependencies=[('claim', check['claim'])]+[('assessment', e) for e in self.packed['evidence_ids']], evidence_ids=check['evidence'])
        self.question_review = review['question']

    def generate_checked(self, phase, name, commit, *, extra=None, initial_view=None, required=None):
        from . import output_contract as output
        from .answer_stream import current_sink
        required=self.packed['evidence_ids'] if required is None else required
        view = initial_view or self.view(phase, required=required, extra=extra)
        identity={k:v for k,v in view.items() if k not in ('view_id','budgets','errors')}
        journal=output.DecisionJournal(self.work,'tool-'+phase,identity,self.gateway.protocol.schema(name))
        previous=journal.state()
        def reuse(saved):
            self.work.check_view(view['view_id'],phase)
            self.gateway.protocol.validate(name,saved['value'])
            return saved['value']
        if previous and previous['status']=='ACCEPTED':return reuse(previous)
        start=previous['attempt']+1 if previous and previous['status']=='REJECTED' else 0
        limit=min(1,self.profile['max_same_error_repairs'])
        for attempt in range(start,limit+1):
            cached=journal.reserve(attempt,max_repairs=limit)
            if cached:return reuse(cached)
            value=None
            try:
                value=self.gateway.generate(phase,view,name,repair_owner='tool-'+phase)
                # Existing commit methods validate all dependencies before their
                # transaction. A crash during commit remains unknown, never replayed.
                commit(view,value)
            except ProposalError as exc:
                retry=(attempt<limit and output.repairable(exc)
                    and self.work.run()['state_revision']==(exc.committed_revision if isinstance(exc,output.PartialOperationError) else view['base_state_revision'])
                    and not (current_sink() and getattr(current_sink(),'started',False)))
                journal.reject(attempt,exc,value,can_retry=retry)
                detail={'code':exc.code,'message':str(exc),'validation':output.diagnostics(exc)}
                self.errors.append(detail)
                with self.work.transaction():self.work.event('SEMANTIC_REPAIR',detail)
                if not retry:raise
                view=self.view(phase,required=required,extra={**(extra or {}),
                    'rejected_decision':value,'repair_contract':detail})
                continue
            journal.accept(attempt,value)
            return value
        raise output.OutputContractError('tool correction budget exhausted',
            [output.issue('CORRECTION_BUDGET_EXHAUSTED',repairable=False)],repairable=False)

    def answer_and_review(self, assembled):
        self.cycles += 1
        mode = self.next_mode
        self.next_mode = 'FINAL'
        try:
            if self.context.request['use_llm'] and self.packed['support']:
                if mode != 'REVIEW':
                    self.generate_checked('compose', 'Draft', self.commit_draft,
                                          extra={'evidence_roles': {k: self.packed[k] for k in ('support','challenge','contextual')},
                                                 'current_claims': self.work.heads('claim', current=True),
                                                 'previous_reviews': self.work.heads('review', current=True)})
                claims = self.work.heads('claim', current=True)
                if claims and self.profile.get('final_review_enabled', True):
                    self.generate_checked('review', 'ReviewDecision', self.commit_review,
                                          extra={'claims': claims, 'rebuttals': self.rebuttals,
                                                 'evidence_roles': {k: self.packed[k] for k in ('support','challenge','contextual')}})
                elif claims:
                    with self.work.transaction():
                        self.work.event('FINAL_REVIEW_SKIPPED', {
                            'reason': 'disabled_by_profile',
                            'claim_versions': {h['entity_id']: h['version'] for h in claims}})
                reviews = self.work.heads('review', current=True)
                if getattr(self, 'final_review_advisory', False):
                    # v5 publishes the chosen draft with legal review notes. A
                    # reviewer objection must not start another rewrite/search.
                    reviews = []
                    self.pending.clear()
                    self.next_mode = 'FINAL'
                for r in reviews:
                    check = r['payload']; c = self.work.head('claim', check['claim'])
                    if check['verdict']=='NEEDS_RESEARCH': self.pending.extend(check['actions'])
                    elif check['verdict']=='NEEDS_REWRITE':
                        key = (c['entity_id'], c['version'])
                        if self.disputes.get(key, 0) < self.profile['max_review_disputes']:
                            def rebut(view, value):
                                self.work.check_view(view['view_id'], 'rebuttal')
                                if value['claim'] != c['entity_id']: raise ProposalError('rebuttal claim mismatch')
                                self.work.visible(view['view_id'], value['evidence'])
                                with self.work.transaction():
                                    self.work.event('REBUTTAL', {'claim_version': c['version'], **value})
                                self.rebuttals.append(value)
                            value = self.generate_checked('rebuttal', 'Rebuttal', rebut, extra={'claim': c, 'objection': check})
                            self.disputes[key] = self.disputes.get(key, 0)+1
                            self.next_mode = 'REVIEW' if value['requested_resolution']=='REVIEW_AGAIN' else 'RECOMPOSE'
                        else: self.next_mode = 'RECOMPOSE'
                if self.pending: self.next_mode = 'RESEARCH'
        except (BudgetExhausted, DeadlineExceeded, ProposalError, TransportError) as exc:
            stage = '작성·검토' if self.profile.get('final_review_enabled', True) else '답변 작성'
            self.limitations.append(stage+'을 완료하지 못했습니다: '+str(exc))
            self.next_mode = 'FINAL'
        if self.cycles >= self.profile['max_cycles'] or self.work.budget()['model_reserved'] >= self.profile['max_model_attempts']:
            if self.next_mode != 'FINAL': self.limitations.append('추가 탐색·검토 예산이 소진되었습니다.')
            self.next_mode = 'FINAL'
        current_claims = self.work.heads('claim', current=True)
        supported = []
        for c in current_claims:
            try: review = self.work.head('review', c['entity_id'])
            except ProposalError: continue
            if review['payload']['verdict']=='SUPPORTED': supported.append(c)
        complete = bool(supported) and len(supported)==len(current_claims) and self.question_review and self.question_review['status']=='RESOLVED'
        missing = self.intent=='CLARIFY' or (self.question_review and self.question_review['status']=='MISSING_FACT')
        gate = 'CLARIFY' if missing else 'READY' if complete and not self.limitations else 'BOUNDED'
        if self.metadata_only: gate = 'BOUNDED' if self.limitations else 'READY'
        reason = ('주장별 원문·질문 검토와 실행 한도' if self.profile.get('final_review_enabled', True)
                  else '선택 원문 기반 답변 작성과 실행 한도')
        control = {'decision': self.next_mode, 'gate': gate, 'reason': reason,
                   'state_revision': self.work.run()['state_revision'], 'evidence_revision': self.work.run()['evidence_revision']}
        with self.work.transaction():
            self.work.event('CONTROL', control)
            self.work.db.execute('UPDATE run SET gate=?,cycle=? WHERE singleton=1', (gate, self.cycles))
        final = control['decision']=='FINAL'
        limitations = list(self.limitations)
        if not complete and not self.metadata_only:
            limitations.append(self.question_review['reason'] if self.question_review else '원문에 근거한 답변 검토가 완료되지 않았습니다.')
        for r in self.work.heads('review', current=True):
            if r['payload']['verdict'] != 'SUPPORTED': limitations.append(r['payload']['reason'])
        for h in self.work.heads('intent', current=True):
            if h['payload'].get('missing_fact'): limitations.append('확인할 사실: '+h['payload']['missing_fact'])
        claims = [{'id': c['entity_id'], 'text': c['payload']['text'],
                   'source_ids': sorted({self.work.evidence(e)['source_id'] for e in c['payload']['evidence']})} for c in supported]
        text = '\n\n'.join(c['text'] for c in claims)
        if self.metadata_only:
            text = '등록 자료: '+', '.join(i.get('name','') for o in self.work.observations() for i in o['items'])
        if limitations: text += ('\n\n' if text else '')+'확인 한계: '+' / '.join(dict.fromkeys(limitations))
        result = {**assembled, 'assembly': {**assembled['assembly'], 'term_agent': self.metadata(final=final, gate=gate)},
                  'answer': {'schema_version': 'term-runtime-v1', 'id': 'answer:'+self.context.run_id,
                    'scope': self.context.query['scope'], 'query_id': self.context.query['id'],
                    'generation_id': self.context.query['generation_id'], 'source_store_sha256': self.context.binding['store_sha256'],
                    'text': text, 'claims': claims, 'unresolved': [{'reason': r} for r in dict.fromkeys(limitations)],
                    'provider_receipt': {'implementation': IMPLEMENTATION, 'model_binding': self.profile['model_binding'],
                        'physical_attempts': self.work.budget()['model_reserved'], 'quality_certified': False}}}
        return result, control
