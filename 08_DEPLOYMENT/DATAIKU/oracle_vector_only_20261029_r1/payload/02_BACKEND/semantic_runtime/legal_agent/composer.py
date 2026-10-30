"""Whole answer paragraphs are versioned claims; no untracked free-form answer."""
import uuid
from . import protocol
from .errors import ProposalError


def commit_draft(repo, view, draft, packed):
    protocol.validate('Draft', draft)
    with repo.transaction():
        repo.check_view(view['view_id'], 'compose')
        seq = repo.event('DRAFT', {'draft': draft}, advance=True)
        for old in repo.heads('claim', current=True):
            if old['payload']['purpose'] == 'answer':
                repo.invalidate('claim', old['entity_id'], old['version'])
        ids = []
        for paragraph in draft['paragraphs']:
            if not set(paragraph['finding_ids']) <= set(packed['finding_ids']):
                raise ProposalError('draft cites unpacked finding')
            findings = [repo.head('finding', f) for f in paragraph['finding_ids']]
            allowed = {e for f in findings for e in f['payload']['evidence_ids']}
            if not set(paragraph['evidence_ids']) <= allowed & set(packed['evidence_ids']):
                raise ProposalError('draft cites evidence outside its findings or assembly')
            repo.visible(view['view_id'], paragraph['evidence_ids'])
            ident = 'C'+uuid.uuid4().hex
            repo.put('claim', ident, {**paragraph, 'purpose': 'answer'}, seq,
                     dependencies=[('finding', f) for f in paragraph['finding_ids']], evidence_ids=paragraph['evidence_ids'])
            ids.append(ident)
    return ids
