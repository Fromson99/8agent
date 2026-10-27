"""Synthetic frozen-codec audit contracts; no model, source store or service."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wire_audit import digest, explicit_spans, reconstruct, request_view, WireAuditError
from semantic_runtime.legal_agent.gateway import compact_wire_view, WIRE_PROJECTION
from semantic_runtime.legal_agent.navigation_input import NavigationReferences, expand_cards
from semantic_runtime.legal_agent.numbered_references import NumberedReferences
from semantic_runtime.legal_agent.model_input_projection import Projection, restore_wire_view
from semantic_runtime.legal_agent.shared_input_values import TABLE

CODECS = {'compact': compact_wire_view, 'wire_projection': WIRE_PROJECTION,
          'navigation': NavigationReferences, 'numbered': NumberedReferences,
          'expand': expand_cards, 'restore': restore_wire_view}
BODY = '정확한 원문 😀 가\u0301과 가는 다르다.\r\n' * 80


def fixture():
    did, sid = 'a' * 16, 'article:' + 'b' * 24
    sources = [{'id': 'S' + str(n), 'document_id': did, 'source_id': sid,
        'scope_id': str(n) * 64, 'selected_scope_complete': n == 1, 'text': BODY,
        'spans': [{'block_id': 'block-' + 'c' * 256, 'start_cp': i * 10, 'end_cp': i * 10 + 10,
            'evidence_id': 'E' + str(n) + '-' + str(i), 'text': BODY[i * 10:i * 10 + 10]}
            for i in range(12)]} for n in (1, 2)]
    stored = {'view_id': 'V1', 'phase': 'investigate', 'base_state_revision': 7,
        'source_stage': 'source-law-navigation-2-read-choice',
        'input_projection': 'compact-selection-source-v3', 'sources': sources,
        'query_scope': {'document_ids': [did]}}
    refs = NavigationReferences(stored)
    compact = compact_wire_view(refs.view(stored), stored['phase'])
    assert TABLE in compact, 'fixture must exercise actual shared source/coordinate codecs'
    codec = Projection(compact)
    request = {'messages': [{'role': 'user', 'content': json.dumps({'view': codec.wire}, ensure_ascii=False)}]}
    events = [
        {'kind': 'NUMBERED_REFERENCES', 'payload': {**refs.receipt(stored), 'wire_view_hash': digest(codec.wire)}},
        {'kind': 'WIRE_PROJECTION', 'payload': {'projection': WIRE_PROJECTION,
            'stored_view_hash': digest(stored), 'wire_view_hash': digest(codec.wire)}},
        {'kind': 'MODEL_INPUT_PROJECTION', 'payload': {'attempt_id': 'M1', **codec.receipt}},
    ]
    return stored, request, events


def test_shared_source_coordinate_table_alias_and_text_slice_restore_exactly():
    stored, request, events = fixture()
    before = deepcopy((stored, request, events))
    result = reconstruct(stored, request, events, CODECS)
    assert result['status'] == 'VERIFIED_EXACT_RECONSTRUCTION'
    assert result['missing_text_spans'] == 0 and len(result['spans']) == 24
    assert result['spans'][0]['document_id'] == 'a' * 16
    assert result['spans'][0]['source_id'] == 'article:' + 'b' * 24
    assert [s['text'] for s in result['spans']] == [BODY[i * 10:i * 10 + 10] for _ in (1, 2) for i in range(12)]
    assert (stored, request, events) == before


def test_different_actual_wire_is_never_reconstructed_from_canonical_alone():
    stored, request, events = fixture()
    payload = json.loads(request['messages'][0]['content'])
    payload['view']['query_scope']['document_ids'] = ['another-scope']
    request['messages'][0]['content'] = json.dumps(payload)
    with pytest.raises(WireAuditError, match='WIRE_HASH_MISMATCH'):
        reconstruct(stored, request, events, CODECS)


def test_metadata_stripped_wire_requires_projection_receipt():
    stored, request, events = fixture()
    with pytest.raises(WireAuditError, match='WIRE_VIEW_DIFFERS'):
        reconstruct(stored, request, events[:-1], CODECS)


def test_stale_or_duplicate_receipt_is_rejected():
    stored, request, events = fixture()
    with pytest.raises(WireAuditError, match='DUPLICATE_CODEC_EVENT'):
        reconstruct(stored, request, events + [events[0]], CODECS)
    events[0]['payload']['view_hash'] = 'stale'
    with pytest.raises(WireAuditError, match='REFERENCE_RECEIPT_MISMATCH'):
        reconstruct(stored, request, events, CODECS)


def test_text_ref_must_bind_exact_source_owner_and_unicode_extent():
    view = {'sources': [{'document_id': 'D1', 'source_id': 'S1', 'text_id': 'TEXT1',
        'text': '가\u0301😀나', 'spans': [{'block_id': '10', 'start_cp': 5, 'end_cp': 7,
            'text_ref': {'id': 'TEXT1', 'start': 1, 'end': 3}}]}]}
    rows, missing = explicit_spans(view)
    assert rows[0]['text'] == '\u0301😀' and missing == 0
    view['evidence_options'] = [{'document_id': 'D2', 'source_id': 'S1', 'block_id': '10',
        'start_cp': 5, 'end_cp': 7, 'text_ref': {'id': 'TEXT1', 'start': 1, 'end': 3}}]
    with pytest.raises(WireAuditError, match='OWNER_MISMATCH'):
        explicit_spans(view)


def test_quote_only_or_missing_text_does_not_invent_coordinate_delivery():
    rows, missing = explicit_spans({'sources': [{'document_id': 'D1', 'source_id': 'S1',
        'text': '정확한 원문', 'spans': [{'block_id': '10', 'start_cp': 0, 'end_cp': 4}]}],
        'claims': [{'quote': '정확한 원문'}]})
    assert rows == [] and missing == 1


def test_multiple_model_views_are_ambiguous_not_first_match():
    request = {'messages': [{'role': 'user', 'content': '{"view":{}}'}] * 2}
    with pytest.raises(WireAuditError, match='MULTIPLE_WIRE_VIEWS'):
        request_view(request)
