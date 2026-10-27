"""Read-only exact wire audit using the frozen product's pure presentation codecs.

The stored presentation alone is not delivery evidence. A reconstruction is
usable only after its native request/hash, codec events and actual wire view
all agree. No source database, model, service or product decision is run here.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys

from common import ROOT, canonical_digest as digest, sha


class WireAuditError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise WireAuditError(code)


def load_frozen_codecs(frozen):
    root = (ROOT / frozen['code_root']).resolve()
    for relative, expected in frozen['files'].items():
        require(sha(root / relative) == expected, 'FROZEN_CODEC_FILE_DRIFT')
    for name, module in list(sys.modules.items()):
        if name == 'semantic_runtime' or name.startswith('semantic_runtime.'):
            require(Path(module.__file__).resolve().is_relative_to(root), 'CODEC_IMPORT_OUTSIDE_CANDIDATE')
    sys.path.insert(0, str(root / '02_BACKEND'))
    from semantic_runtime.legal_agent.gateway import compact_wire_view, WIRE_PROJECTION
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences, expand_cards
    from semantic_runtime.legal_agent.numbered_references import NumberedReferences
    from semantic_runtime.legal_agent.model_input_projection import restore_wire_view
    for name, module in list(sys.modules.items()):
        if name == 'semantic_runtime' or name.startswith('semantic_runtime.'):
            location = Path(module.__file__).resolve()
            require(location.is_relative_to(root), 'CODEC_IMPORT_OUTSIDE_CANDIDATE')
            require(frozen['files'].get(str(location.relative_to(root))) == sha(location), 'UNPINNED_CODEC_IMPORT')
    return {'compact': compact_wire_view, 'wire_projection': WIRE_PROJECTION,
        'navigation': NavigationReferences, 'numbered': NumberedReferences,
        'expand': expand_cards, 'restore': restore_wire_view}


def request_view(request):
    views = []
    for message in request.get('messages', []):
        if message.get('role') != 'user' or not isinstance(message.get('content'), str):
            continue
        try:
            value = json.loads(message['content'])
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get('view'), dict):
            views.append(value['view'])
    require(len(views) <= 1, 'MULTIPLE_WIRE_VIEWS')
    return views[0] if views else None


def reconstruct(stored, native_request, events, codecs):
    """Events are already hash checked rows for this exact native attempt."""
    wire = request_view(native_request)
    require(wire is not None, 'NATIVE_WIRE_VIEW_MISSING')
    grouped = {}
    for event in events:
        require(event['kind'] not in grouped, 'DUPLICATE_CODEC_EVENT')
        grouped[event['kind']] = event['payload']
    expected = stored
    refs = None
    navigation = stored.get('input_projection') == 'compact-selection-source-v3'
    numbered = grouped.get('NUMBERED_REFERENCES')
    if numbered is not None:
        refs = codecs['navigation' if navigation else 'numbered'](stored)
        receipt = refs.receipt(stored)
        require(all(numbered.get(k) == v for k, v in receipt.items()), 'REFERENCE_RECEIPT_MISMATCH')
        require(numbered.get('wire_view_hash') == digest(wire), 'REFERENCE_WIRE_HASH_MISMATCH')
        expected = refs.view(stored)
    projection = grouped.get('WIRE_PROJECTION')
    if projection is not None:
        require(projection.get('projection') == codecs['wire_projection'], 'UNKNOWN_WIRE_PROJECTION')
        require(projection.get('stored_view_hash') == digest(stored), 'STORED_VIEW_PROJECTION_MISMATCH')
        require(projection.get('wire_view_hash') == digest(wire), 'PROJECTED_WIRE_HASH_MISMATCH')
        expected = codecs['compact'](expected, stored['phase'])
    model_projection = grouped.get('MODEL_INPUT_PROJECTION')
    if model_projection is not None:
        require(projection is not None, 'MODEL_PROJECTION_WITHOUT_WIRE_PROJECTION')
        restored = codecs['restore'](expected, wire, model_projection)
    else:
        require(wire == expected, 'WIRE_VIEW_DIFFERS_FROM_NATIVE_PRESENTATION')
        restored = deepcopy(expected)
    restored = codecs['expand'](restored) if navigation else restored
    if refs is not None and navigation:
        restored = refs.restore(restored)
    # Older numbered projections deliberately hide document identities. Do not
    # invent those from a stored view or call them explicit wire coordinates.
    if refs is not None and not navigation:
        return {'wire_view_sha256': digest(wire), 'status': 'VERIFIED_REDACTED_IDENTIFIERS',
                'spans': [], 'missing_text_spans': None}
    spans, missing = explicit_spans(restored)
    return {'wire_view_sha256': digest(wire), 'status': 'VERIFIED_EXACT_RECONSTRUCTION',
            'spans': spans, 'missing_text_spans': missing}


def explicit_spans(view):
    """Expand only declared text_ref slices; never infer a quote's coordinates."""
    sources = {}
    for source in view.get('sources', []):
        if isinstance(source, dict) and source.get('text_id'):
            require(source['text_id'] not in sources, 'DUPLICATE_TEXT_ID')
            sources[source['text_id']] = source
    result, missing = [], 0

    def append(row, document_id, source_id):
        nonlocal missing
        if not all(k in row for k in ('block_id', 'start_cp', 'end_cp')):
            return
        require(type(row['start_cp']) is int and type(row['end_cp']) is int
                and 0 <= row['start_cp'] <= row['end_cp'], 'INVALID_WIRE_SPAN_EXTENT')
        text = row.get('text')
        if 'text_ref' in row:
            ref = row['text_ref']
            require(isinstance(ref, dict) and set(ref) == {'id', 'start', 'end'}, 'INVALID_TEXT_REFERENCE')
            source = sources.get(ref['id'])
            require(source is not None and isinstance(source.get('text'), str), 'UNRESOLVED_TEXT_REFERENCE')
            require(source.get('document_id') == document_id and source.get('source_id') == source_id,
                    'TEXT_REFERENCE_OWNER_MISMATCH')
            require(type(ref['start']) is int and type(ref['end']) is int
                    and 0 <= ref['start'] <= ref['end'] <= len(source['text']), 'TEXT_REFERENCE_OUT_OF_RANGE')
            exact = source['text'][ref['start']:ref['end']]
            require(text is None or text == exact, 'TEXT_REFERENCE_VALUE_MISMATCH')
            text = exact
        if not isinstance(text, str):
            missing += 1
            return
        require(isinstance(document_id, str) and bool(document_id), 'WIRE_DOCUMENT_ID_MISSING')
        require(len(text) == row['end_cp'] - row['start_cp'], 'WIRE_TEXT_EXTENT_MISMATCH')
        result.append({'document_id': document_id, 'source_id': source_id,
            'block_id': row['block_id'], 'start_cp': row['start_cp'], 'end_cp': row['end_cp'], 'text': text})

    # Restrict inspection to actual source/evidence containers. A table-shaped
    # object or text_ref appearing inside legal source text is never executable.
    for key in ('sources', 'exact_evidence', 'evidence_options'):
        for card in view.get(key, []):
            if not isinstance(card, dict):
                continue
            did, sid = card.get('document_id'), card.get('source_id')
            append(card, did, sid)
            for span in card.get('spans', []):
                if isinstance(span, dict):
                    append(span, did, sid)
    return result, missing


def journal_records(db, codecs, journal_path):
    """Return small wire-keyed span records; retain invalid attempts explicitly."""
    records, failures = {}, []
    events = {}
    for row in db.execute("SELECT kind,payload_json,payload_hash FROM event WHERE kind IN "
            "('NUMBERED_REFERENCES','WIRE_PROJECTION','MODEL_INPUT_PROJECTION')"):
        payload = json.loads(row['payload_json'])
        if digest(payload) != row['payload_hash']:
            failures.append({'kind': 'WIRE_CODEC_EVENT_HASH_MISMATCH', 'journal': journal_path})
            continue
        events.setdefault(payload.get('attempt_id'), []).append({'kind': row['kind'], 'payload': payload})
    for row in db.execute('SELECT a.attempt_id,a.request_json,a.request_hash,v.body_json,v.body_hash '
            'FROM model_attempt a JOIN model_view v USING(view_id)'):
        try:
            request, stored = json.loads(row['request_json']), json.loads(row['body_json'])
            require(digest(request) == row['request_hash'], 'NATIVE_REQUEST_HASH_MISMATCH')
            require(digest(stored) == row['body_hash'], 'NATIVE_VIEW_HASH_MISMATCH')
            record = reconstruct(stored, request, events.get(row['attempt_id'], []), codecs)
            record.update(attempt_id=row['attempt_id'], journal=journal_path)
            records.setdefault(record['wire_view_sha256'], []).append(record)
        except Exception as error:
            # Do not copy data-bearing codec exceptions or silently count zero.
            failures.append({'kind': 'WIRE_RECONSTRUCTION_INVALID', 'journal': journal_path,
                'attempt_id': row['attempt_id'], 'reason': str(error) if isinstance(error, WireAuditError)
                else type(error).__name__})
    return records, failures
