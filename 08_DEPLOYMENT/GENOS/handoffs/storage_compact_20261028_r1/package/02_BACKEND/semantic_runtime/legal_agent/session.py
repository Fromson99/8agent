"""One request's investigation, composition, review and externally compatible ports."""
import uuid
from ..contracts import digest
from .errors import BudgetExhausted, DeadlineExceeded, ProposalError
from .views import build_view
from .packer import pack
from .composer import commit_draft
from .reviewer import commit_review
from .gate import evaluate


class LegalSession:
    def __init__(self, context, repo, sources, gateway, profile, data_status):
        self.context, self.work, self.sources, self.gateway = context, repo, sources, gateway
        self.profile, self.data_status = profile, data_status
        self.packed = None
        self.limitations = []
        self.cycles = 0

    def metadata(self, *, final=False, gate=None):
        r = self.work.run()
        return {'implementation': 'legal-agent-v1', 'run_id': self.context.run_id,
                'status': gate or 'INVESTIGATING', 'final': final, 'state_revision': r['state_revision'],
                'evidence_revision': r['evidence_revision'], 'quality_certified': False,
                'use_llm': self.context.request['use_llm'], 'binding_hash': self.context.binding_hash,
                'model_attempts_reserved': self.work.budget()['model_reserved']}

    def view(self, phase, **kwargs):
        return build_view(self.work, self.context, self.profile, phase, **kwargs)

    def progress_key(self):
        # Event IDs, attempts, and repeated empty observations are not progress.
        return digest({'entities': sorted({(h['kind'], digest(h['payload']), h['validity']) for h in self.work.heads()}),
                       'evidence': [e['evidence_id'] for e in self.work.evidence()],
                       'discoveries': sorted({digest({k: v for k, v in o.items() if k not in ('observation_id', 'request_key', 'action')})
                                              for o in self.work.observations(1000) if o['status'] in ('OK', 'TRUNCATED')})})

    def execute_read(self, action):
        try:
            return self.sources.execute(action)
        except ProposalError as exc:
            result = {'status': 'DENIED', 'items': [], 'evidence_ids': [], 'next_cursor': None,
                      'coverage': {'complete': False}, 'error_code': exc.code}
            return self.work.record_observation(action, result, verify=self.sources.verify)

    def investigate(self):
        if not self.work.observations(1):
            self.execute_read({'tool': 'list_documents', 'args': {'query': '', 'cursor': None},
                               'reason': '질문 해석·쟁점 확정 전 허용 문서 탐색 시작'})
        if not self.context.request['use_llm']:
            return self.retrieval()
        no_progress = 0
        while True:
            before = self.progress_key()
            try:
                for item in self.work.frontier():
                    if item['status'] == 'PENDING':
                        result = self.execute_read(item['action'])
                        self.work.finish_frontier(item['item_id'], result)
                view = self.view('investigate')
                proposal = self.gateway.generate('investigate', view, 'InvestigateDecision')
                self.work.apply_proposal(view, proposal, event_id='proposal:'+view['view_id'])
                for action in proposal['reads']:
                    self.execute_read(action)
                if proposal['intent'] == 'DRAFT':
                    break
                no_progress = no_progress+1 if before == self.progress_key() else 0
                if no_progress >= self.profile['max_no_progress']:
                    self.limitations.append('추가 원문·판단 진전 없이 탐색이 반복되어 중단했습니다.')
                    break
            except DeadlineExceeded:
                self.limitations.append('요청 시간 상한에 도달했습니다.')
                break
            except BudgetExhausted as exc:
                self.limitations.append('조사 예산 또는 문맥 상한에 도달했습니다: '+str(exc))
                break
        return self.retrieval()

    def retrieval(self):
        candidates = {}
        for e in self.work.evidence():
            # These candidates contain only materialized exact fragments, not an
            # unread whole article fetched from a metadata search hit.
            c = candidates.setdefault(e['source_id'], {'id': e['source_id'], 'document_id': e['document_id'],
                'document_name': e['metadata']['document_name'], 'unit_id': e['unit_id'], 'evidence_ids': [], 'text': ''})
            c['evidence_ids'].append(e['evidence_id'])
            c['text'] += ('\n' if c['text'] else '')+e['text']
        return {'candidates': list(candidates.values()), 'routes': {'legal_agent': len(candidates)},
                'vector_status': 'NOT_USED', 'generation_id': self.context.query['generation_id'], 'term_agent': self.metadata()}

    def select(self, retrieved):
        self.packed = pack(self.work, self.profile)
        ids = {x['id'] for x in self.packed['contexts']}
        candidates = retrieved['retrieval']['candidates']
        return {'selected': [c for c in candidates if c['id'] in ids],
                'discarded_ids': [c['id'] for c in candidates if c['id'] not in ids],
                'method': 'term-agent', 'term_agent': self.metadata()}

    def assemble(self):
        return {'context': self.packed['contexts'], 'unresolved': self.packed['unresolved'],
                'data_status': self.data_status, 'term_agent': self.metadata()}

    def answer_and_review(self, assembled):
        self.cycles += 1
        if self.context.request['use_llm'] and self.packed['finding_ids']:
            try:
                view = self.view('compose', evidence_ids=self.packed['evidence_ids'])
                draft = self.gateway.generate('compose', view, 'Draft')
                commit_draft(self.work, view, draft, self.packed)
                if draft['limitations']:
                    # Free-form composer notes are not reviewed claims. Preserve
                    # them in the journal/reviewer input, never publish them as law.
                    self.limitations.append('답변 작성 단계에서 추가 확인이 필요한 사항을 보고했습니다.')
                view = self.view('review', evidence_ids=self.packed['evidence_ids'],
                                 extra={'answer_text': '\n\n'.join(p['text'] for p in draft['paragraphs']),
                                        'unverified_composer_notes': draft['limitations']})
                review = self.gateway.generate('review', view, 'Review')
                commit_review(self.work, view, review)
            except DeadlineExceeded:
                self.limitations.append('답변 검토 전에 요청 시간 상한에 도달했습니다.')
            except BudgetExhausted:
                self.limitations.append('답변 작성·검토 예산 또는 문맥 상한에 도달했습니다.')
        elif not self.context.request['use_llm']:
            self.limitations.append('모델 미사용: 문서 탐색 시작점만 제공하며 법률 판단은 수행하지 않았습니다.')
        b = self.work.budget()
        exhausted = self.cycles >= self.profile['max_cycles'] or b['model_reserved']+2 > b['model_limit']
        decision = evaluate(self.work, self.packed, exhausted=exhausted, limitations=self.limitations)
        control = decision['control']
        final = control['decision'] == 'FINAL'
        claims = [{'id': c['entity_id'], 'text': c['payload']['text'],
                   'source_ids': sorted({self.work.evidence(e)['source_id'] for e in c['payload']['evidence_ids']})}
                  for c in decision['claims']]
        text = '\n\n'.join(c['text'] for c in claims)
        if decision['unresolved']:
            text += ('\n\n' if text else '')+'확인 한계: '+' / '.join(decision['unresolved'])
        answer = {'schema_version': 'term-runtime-v1', 'id': 'answer:'+self.context.run_id,
                  'scope': self.context.query['scope'], 'query_id': self.context.query['id'],
                  'generation_id': self.context.query['generation_id'],
                  'source_store_sha256': self.context.binding['store_sha256'], 'text': text, 'claims': claims,
                  'unresolved': [{'reason': r} for r in decision['unresolved']],
                  'provider_receipt': {'binding': self.profile['model_binding'],
                                       'attempts_reserved': b['model_reserved'], 'quality_certified': False}}
        result = {**assembled, 'answer': answer}
        for part in ('retrieval', 'selection', 'assembly'):
            result[part] = {**result[part], 'term_agent': self.metadata(final=final, gate=control['gate'])}
        with self.work.transaction():
            self.work.event('CONTROL', control)
            self.work.db.execute('UPDATE run SET gate=?,cycle=? WHERE singleton=1', (control['gate'], self.cycles))
        return result, control
