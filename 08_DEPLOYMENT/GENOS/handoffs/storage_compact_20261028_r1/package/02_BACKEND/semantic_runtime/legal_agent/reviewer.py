"""Claim-version review plus a separate original-question/whole-answer comparison."""
import uuid
from . import protocol
from .errors import ProposalError


def commit_review(repo, view, review):
    protocol.validate('Review', review)
    with repo.transaction():
        repo.check_view(view['view_id'], 'review')
        claims = {h['entity_id']: h for h in repo.heads('claim', current=True)}
        ids = [r['claim_id'] for r in review['claims']]
        if len(ids) != len(set(ids)) or set(ids) != set(claims):
            raise ProposalError('review must cover each current claim exactly once')
        questions = [p['id'] for p in repo.context.pieces]
        qids = [q['question_piece_id'] for q in review['question_checks']]
        if sorted(qids) != sorted(questions):
            raise ProposalError('direct question review must cover each server question piece')
        for q in review['question_checks']:
            if not set(q['claim_ids']) <= {i for i, c in claims.items() if c['payload']['purpose'] == 'answer'}:
                raise ProposalError('question check cites unknown or internal-only claim')
            if q['status'] == 'RESOLVED' and not q['claim_ids']:
                raise ProposalError('resolved question requires actual answer claims')
        if review['whole_question']['status'] == 'RESOLVED' and any(q['status'] != 'RESOLVED' for q in review['question_checks']):
            raise ProposalError('whole-question verdict conflicts with individual omissions')
        seq = repo.event('REVIEW', {'review': review}, advance=True)
        for r in review['claims']:
            claim = repo.head('claim', r['claim_id'], expected=r['claim_version'])
            repo.visible(view['view_id'], r['evidence_ids'])
            if r['verdict'] == 'SUPPORTED' and not set(claim['payload']['evidence_ids']) <= set(r['evidence_ids']):
                raise ProposalError('supported review must anchor all cited evidence')
            repo.put('review', 'R:'+r['claim_id'], r, seq,
                     dependencies=[('claim', r['claim_id'])], evidence_ids=r['evidence_ids'])
            if r['verdict'] != 'SUPPORTED':
                repo.put('challenge', 'CH'+uuid.uuid4().hex, r, seq,
                         dependencies=[('claim', r['claim_id'])], evidence_ids=r['evidence_ids'])
            for action in r['follow_up_reads']:
                repo.enqueue(action, r['reason'], seq)
        for q in review['question_checks']+[review['whole_question']]:
            for action in q['follow_up_reads']:
                repo.enqueue(action, q['reason'], seq)
        repo.put('review', 'R:question', {'purpose': 'question', 'question_checks': review['question_checks'],
                 'whole_question': review['whole_question']}, seq,
                 dependencies=[('claim', i) for i in claims])
    return review
