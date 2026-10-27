"""Publish the chosen v5 draft and keep review observations in the journal.

Only committed claims receive source attribution. A delivered draft with a
selection-reference mismatch keeps its prose without registering claims.
"""
import re
from .errors import ProposalError


DIMENSIONS = {
    'concept': '법률 개념', 'scope': '적용 대상·범위',
    'conditions': '적용 요건과 요건 사이의 관계', 'exceptions': '예외·단서',
    'certainty': '단정의 정도와 유보 조건', 'question_fit': '질문에 대한 직접적인 답변 여부',
}


class LegalNotes:
    def __init__(self, session):
        self.s = session
        self.notes = []
        self.evidence = {e['evidence_id']: e for e in session.work.evidence()}
        self.relations = {n['relation_id']: n for n in session.work.notices()}

    def unit_label(self, document_id, unit_id, fallback=''):
        units = self.s.sources.matcher.units
        labels, seen = [], set()
        while unit_id is not None and str(unit_id) not in seen:
            seen.add(str(unit_id))
            unit = units.get((document_id, str(unit_id)))
            if not unit:
                break
            label = ' '.join(str(unit[k]) for k in ('surface', 'title') if unit.get(k))
            if label:
                labels.append(label)
            unit_id = unit.get('parent')
        return ' '.join(reversed(labels)) or fallback

    def source(self, ident):
        e = self.evidence.get(ident)
        if not e:
            return '해당 근거 조문'
        name = e['metadata'].get('document_name') or '근거 문서'
        location = self.unit_label(e['document_id'], e['unit_id'], e['metadata'].get('heading') or '')
        return (name + ' ' + location).strip()

    def sources(self, ids):
        return ' · '.join(dict.fromkeys(self.source(e) for e in ids)) or '해당 답변'

    def relation(self, ident):
        n = self.relations.get(ident)
        if not n:
            return '답변에 사용한 조문 사이의 연결'
        origins = self.sources(n.get('source_evidence', []))
        targets = []
        for target in n.get('targets', []):
            try:
                node = self.s.sources.resolve(target['target'], 'RFDUPE') if target.get('target') else target
            except ProposalError:
                node = target
            location = self.unit_label(node.get('document_id'), node.get('unit_id'), target.get('title') or '')
            label = ' '.join(x for x in (target.get('document_name'), location) if x)
            if label:
                targets.append(label)
        if not targets:
            targets = [self.source(e) for e in n.get('target_evidence', [])]
        return origins + '와 ' + (' · '.join(dict.fromkeys(targets)) or '연결된 조문')

    def legal_text(self, value, fallback):
        """Never copy runtime failures, paths or opaque handles to legal readers."""
        value = str(value or '').strip()
        for ident in sorted(self.evidence, key=len, reverse=True):
            value = value.replace(ident, self.source(ident))
        for ident in sorted(self.relations, key=len, reverse=True):
            if ident in value:
                value = value.replace(ident, self.relation(ident))
        if not value or re.search(r'[A-Za-z_]{3,}|[A-Z][0-9a-f]{8,}|(?:/[^\s/]+){2,}|[COQ]\d+\b', value):
            return fallback
        return ' '.join(value.split())

    def add(self, value):
        if value not in self.notes:
            self.notes.append(value)

    def collect(self, claims, review):
        checks = review.get('checks', [])
        for head in claims:
            claim = head['payload']
            label = self.sources(claim['evidence'])
            matches = [c for c in checks if c.get('claim') == head['entity_id']]
            if len(matches) != 1:
                self.add(f'{label}: 이 근거를 사용한 답변의 최종 원문 대조가 완료되지 않았습니다.')
                for rid in claim.get('relation_dependencies', []):
                    self.add(f'{self.relation(rid)}: 답변에 사용한 조문 사이의 적용·인용 관계를 최종 대조하지 못했습니다.')
                continue
            check = matches[0]
            for rid in claim.get('relation_dependencies', []):
                if rid not in check.get('relation_checks', []):
                    self.add(f'{self.relation(rid)}: 답변에 사용한 조문 사이의 적용·인용 관계에 대한 최종 대조가 빠졌습니다. 함께 적용할 수 있는지 확인하십시오.')
            if set(check.get('relation_checks', [])) - set(claim.get('relation_dependencies', [])):
                self.add(f'{label}: 답변에서 사용한 조문 연결과 검토한 조문 연결의 범위가 다릅니다. 실제 적용한 조문을 확인하십시오.')
            for eid in claim['evidence']:
                if eid not in check.get('evidence', []):
                    self.add(f'{self.source(eid)}: 답변의 근거로 사용했으나 최종 대조 대상에서 빠졌습니다.')
            rows = check.get('source_checks', [])
            for eid in dict.fromkeys(claim['evidence'] + check.get('evidence', [])):
                comparisons = [row for row in rows if row.get('source') == eid]
                if len(comparisons) != 1:
                    self.add(f'{self.source(eid)}: 해당 조문과 답변 문장의 개별 대조를 완료하지 못했습니다.')
            for row in rows:
                eid = row.get('source')
                source = self.source(eid)
                evidence = self.evidence.get(eid)
                if evidence and not any(row.get('quote') and row['quote'] in span['text'] for span in evidence['spans']):
                    self.add(f'{source}: 검토에 사용한 인용 문구가 확보한 원문과 일치하지 않습니다. 조문 원문을 직접 대조하십시오.')
                if not row.get('draft_quote') or row['draft_quote'] not in claim['text']:
                    self.add(f'{source}: 대조한 답변 문구가 최종 답변 문장과 일치하지 않습니다. 최종 문장을 기준으로 다시 확인하십시오.')
                for key, title in DIMENSIONS.items():
                    state = row.get('dimensions', {}).get(key)
                    if state in ('CHANGED', 'UNCERTAIN') or (key == 'question_fit' and state != 'PRESERVED'):
                        concern = '원문과 다를 수 있습니다' if state == 'CHANGED' else '확인되지 않았습니다'
                        self.add(f'{source}: {title} — {concern}. ' + self.legal_text(row.get('reason'), '해당 조문과 답변을 함께 확인하십시오.'))
            if check.get('verdict') != 'SUPPORTED':
                self.add(f'{label}: ' + self.legal_text(check.get('reason'), '답변의 법적 결론과 근거의 부합 여부를 추가로 확인하십시오.'))

        plan = self.s.plan() or {'demands': []}
        for demand in plan['demands']:
            rows = [r for r in review.get('obligation_checks', []) if r.get('obligation') == demand['id']]
            requirement = self.legal_text(demand['requirement'], '질문의 해당 쟁점')
            if len(rows) != 1:
                self.add(f'{requirement}: 이 쟁점에 대한 답변과 근거의 최종 확인이 완료되지 않았습니다.')
                continue
            row = rows[0]
            linked = {h['entity_id'] for h in claims if demand['id'] in h['payload'].get('obligation_refs', [])}
            if set(row.get('claims', [])) != linked or (row.get('status') in ('ANSWERED', 'CONDITIONAL') and not linked):
                self.add(f'{requirement}: 이 쟁점과 최종 답변 문장 사이의 연결을 확인하십시오. 검토한 내용이 실제 답변에 모두 포함됐는지 불명확합니다.')
            if row.get('status') not in ('ANSWERED', 'CONDITIONAL'):
                self.add(f'{requirement}: ' + self.legal_text(row.get('reason'), '결론에 필요한 사실·근거 또는 답변의 보완 사항을 확인하십시오.'))
        question = review.get('question', {})
        if question and question.get('status') != 'RESOLVED':
            self.add(self.legal_text(question.get('reason'), '질문의 전체 범위에 답했는지 확인하십시오.'))


def finalize(session, result, control):
    if session.metadata_only:
        return result, control
    claims = session.work.heads('claim', current=True)
    notes = LegalNotes(session)
    review_enabled = session.profile.get('final_review_enabled', True)
    versions = {h['entity_id']: h['version'] for h in claims}
    observation = getattr(session, 'final_review_observation', None)
    if getattr(session, 'final_review_claim_versions', None) != versions:
        observation = None
    if observation is None:
        observation = {
            'checks': [h['payload'] for h in session.work.heads('review', current=True)],
            'obligation_checks': [h['payload'] for h in session.work.heads('obligation_review', current=True)],
            'question': session.question_review or {},
        }
    if not session.metadata_only:
        if review_enabled:
            notes.collect(claims, observation)
        reviewed = {h['entity_id'] for h in session.work.heads('review', current=True)}
        if review_enabled and claims and any(h['entity_id'] not in reviewed for h in claims) and not notes.notes:
            notes.add('최종 검토에서 확인한 주장과 근거의 대응이 불완전합니다. 답변의 각 결론을 해당 조문과 다시 대조하십시오.')
        for limitation in list(session.limitations) + getattr(session, 'final_draft_limitations', []):
            if limitation.startswith('원문 미평가 ') or '검토 인용문 일부' in limitation:
                # The v4 display status is not a legal defect; detailed quote
                # notes are produced from the actual review observation above.
                continue
            notes.add(notes.legal_text(limitation, '작성한 답변의 원문 근거와 적용 요건에 대한 최종 확인이 완료되지 않았습니다.'))
        unverified = getattr(session, 'unverified_draft', None) if not review_enabled else None
        if not claims and not unverified:
            notes.add('최종 답변으로 작성된 내용이 없습니다. 관련 근거의 확보 여부와 답변 작성 범위를 확인하십시오.')
        result['answer']['claims'] = [
            {'id': h['entity_id'], 'text': h['payload']['text'],
             'source_ids': sorted({notes.evidence[e]['source_id'] for e in h['payload']['evidence']})}
            for h in claims]
        result['answer']['text'] = ('\n\n'.join(p['text'] for p in unverified['paragraphs'])
                                    if unverified else '\n\n'.join(h['payload']['text'] for h in claims))
    result['answer']['unresolved'] = [{'reason': note} for note in notes.notes]
    if notes.notes:
        heading = '**법률 검토 필요사항**' if review_enabled else '확인 한계'
        result['answer']['text'] += ('\n\n' if result['answer']['text'] else '') + heading + '\n' + '\n'.join('- ' + note for note in notes.notes)
        if control['gate'] == 'READY':
            control['gate'] = 'BOUNDED'
    review_states = ({h['entity_id']: h['payload']['verdict'] for h in session.work.heads('review', current=True)}
                     if review_enabled else {})
    receipt = result['answer']['provider_receipt']
    receipt.update(final_review_policy='advisory' if review_enabled else 'disabled', quality_certified=False,
                   claim_review_status={h['entity_id']: review_states.get(h['entity_id'], 'UNREVIEWED') for h in claims})
    if not review_enabled:
        receipt['final_review_status'] = 'SKIPPED'
    with session.work.transaction():
        session.work.event('FINAL_LEGAL_REVIEW_NOTES', {
            'claim_versions': versions, 'notes': notes.notes, 'claim_review_status': receipt['claim_review_status']})
        session.work.event('CONTROL', control)
        session.work.db.execute('UPDATE run SET gate=? WHERE singleton=1', (control['gate'],))
    result['assembly']['term_agent'].update(gate=control['gate'], final=control['decision'] == 'FINAL')
    return result, control
