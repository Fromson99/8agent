"""Pack exact selected spans, keeping exception and conflict evidence together."""
from .repository import encoded
from .errors import ContractError


def pack(repo, profile):
    findings = repo.heads('finding', current=True)
    evidence_ids = set()
    for f in findings:
        evidence_ids.update(f['payload']['evidence_ids'])
        # Contradicting/qualifying sources for the same issue must stay visible even
        # when the model omitted them from its preferred finding.
        for a in repo.heads('assessment', current=True):
            if a['payload']['issue_id'] == f['payload']['issue_id'] and a['payload']['relation'] != 'irrelevant':
                evidence_ids.update(a['payload']['evidence_ids'])
    for c in repo.heads('challenge', current=True):
        evidence_ids.update(c['payload'].get('evidence_ids', []))
    evidence = [repo.evidence(e) for e in sorted(evidence_ids)]
    incomplete = len(encoded(evidence)) > profile['max_context_chars']//2
    if incomplete:
        return {'contexts': [], 'evidence_ids': [], 'finding_ids': [], 'incomplete': True,
                'unresolved': ['필요한 원문·예외·충돌 근거 묶음이 문맥 상한을 초과했습니다.']}
    by_source = {}
    for e in evidence:
        item = by_source.setdefault(e['source_id'], {
            'id': e['source_id'], 'document_id': e['document_id'], 'unit_id': e['unit_id'],
            'document_name': e['metadata']['document_name'], 'source_artifact_sha256': e['source_artifact_hash'],
            'ancestors': [], 'evidence_ids': [], 'evidence_spans': [], 'blocks': [], 'text': '',
        })
        item['evidence_ids'].append(e['evidence_id'])
        item['evidence_spans'].extend({**s, 'evidence_id': e['evidence_id']} for s in e['spans'])
    for item in by_source.values():
        item['evidence_spans'].sort(key=lambda s: (int(s['block_id']), s['start_cp'], s['end_cp']))
        # Merge only actual overlap, retaining every original evidence anchor.
        # Never use a bounding range to fill unread text between fragments.
        merged = []
        for span in item['evidence_spans']:
            last = merged[-1] if merged else None
            if last and last['block_id'] == span['block_id'] and span['start_cp'] < last['end_cp']:
                start = span['start_cp']-last['start_cp']
                overlap = min(last['end_cp'], span['end_cp'])-span['start_cp']
                if last['block_hash'] != span['block_hash'] or last['text'][start:start+overlap] != span['text'][:overlap]:
                    raise ContractError('overlapping evidence disagrees')
                if span['end_cp'] > last['end_cp']:
                    last['text'] += span['text'][overlap:]
                    last['end_cp'] = span['end_cp']
            else:
                merged.append(dict(span))
        item['text'] = '\n'.join(s['text'] for s in merged)
        item['blocks'] = [{k: s[k] for k in ('block_id', 'text', 'start_cp', 'end_cp')} for s in merged]
        item['block_id'] = item['evidence_spans'][0]['block_id']
    return {'contexts': list(by_source.values()), 'evidence_ids': sorted(evidence_ids),
            'finding_ids': [f['entity_id'] for f in findings], 'incomplete': False, 'unresolved': []}
