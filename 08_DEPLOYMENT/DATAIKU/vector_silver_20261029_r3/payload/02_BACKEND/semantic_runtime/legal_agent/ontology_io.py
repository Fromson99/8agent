"""Bounded reads from the request journal; never a corpus or Oracle cache."""
import json

from .errors import ContractError, ProposalError
from .repository import text_hash

BATCH_SIZE = 128
RECEIPT_INDEX = 'ontology_delivery_presentation_v1'


def evidence(repo, identifiers):
    """Read only selected evidence, preserving the repository's exact hash gate."""
    ids = list(dict.fromkeys(identifiers))
    result = {}
    for start in range(0, len(ids), BATCH_SIZE):
        batch = ids[start:start + BATCH_SIZE]
        marks = ','.join('?' for _ in batch)
        rows = list(repo.db.execute(
            'SELECT * FROM evidence_unit WHERE evidence_id IN (' + marks + ') ORDER BY evidence_id', batch))
        spans = {}
        for row in repo.db.execute(
                'SELECT * FROM evidence_span WHERE evidence_id IN (' + marks + ') ORDER BY evidence_id,ordinal', batch):
            spans.setdefault(row['evidence_id'], []).append(dict(row))
        for row in rows:
            parts = spans.get(row['evidence_id'], [])
            text = '\n'.join(part['text'] for part in parts)
            if text_hash(text) != row['text_hash']:
                raise ContractError('stored evidence hash mismatch')
            result[row['evidence_id']] = {
                **dict(row), 'metadata': json.loads(row['metadata_json']), 'spans': parts, 'text': text}
        for ident in batch:
            if ident not in result:
                raise ProposalError('unknown evidence: ' + str(ident))
    return result


def delivery_events(repo, presentation_id):
    """Index existing receipt bytes once per journal, then select one display.

    The index is derived; it grants no authority. Callers still check every
    selected event hash, model view, successful attempt and original range.
    SQLite errors propagate through the existing owner. Old receipts are not
    rewritten, and a reopened journal uses the same persistent index.
    """
    if not getattr(repo, '_ontology_delivery_index_ready', False):
        repo.db.execute("CREATE INDEX IF NOT EXISTS " + RECEIPT_INDEX +
            " ON event(json_extract(payload_json,'$.presentation_id'),seq)"
            " WHERE kind='NAVIGATION_INPUT_DELIVERED'")
        repo._ontology_delivery_index_ready = not repo.db.in_transaction
    return repo.db.execute(
        "SELECT payload_json,payload_hash FROM event WHERE kind='NAVIGATION_INPUT_DELIVERED'"
        " AND json_extract(payload_json,'$.presentation_id') IS ? ORDER BY seq", (presentation_id,))
