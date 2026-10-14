"""Closed-output contract for candidate-bound reference resolution."""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from .legal_agent.errors import ProposalError


SCHEMA_PATH = Path(__file__).resolve().parents[2] / '00_SYSTEM/SCHEMAS/reference-resolution-v1.schema.json'
DOCUMENT = json.loads(SCHEMA_PATH.read_text())
DEFINITIONS = DOCUMENT['$defs']


def schema(name):
    value = deepcopy(DEFINITIONS[name])
    value['$defs'] = deepcopy(DEFINITIONS)
    return value


def validate(name, value):
    try:
        Draft202012Validator(schema(name)).validate(value)
    except ValidationError as exc:
        raise ProposalError(f'{name}: {exc.message}') from exc
    return value


def validate_batch(value, cases):
    """Validate closed IDs and derive cardinality state on the server."""
    validate('ReferenceResolutionOutput', value)
    expected = {case['case_id']: case for case in cases}
    supplied = [row['case_id'] for row in value['cases']]
    if len(supplied) != len(set(supplied)) or set(supplied) != set(expected):
        raise ProposalError('model output must cover each supplied case exactly once')
    normalized = []
    for row in value['cases']:
        case = expected[row['case_id']]
        candidates = {candidate['id'] for candidate in case['candidates']}
        evidence = {item['id'] for item in case['evidence']}
        selected = row['selected_candidate_ids']
        if not set(selected) <= candidates or not set(row['evidence_ids']) <= evidence:
            raise ProposalError('model selected an ID outside the closed view')
        if selected and row['abstain_reason'] is not None:
            raise ProposalError('selected candidates and abstention are mutually exclusive')
        if not selected and not (row['abstain_reason'] or '').strip():
            raise ProposalError('empty selection requires an abstain reason')
        state = 'UNKNOWN' if not selected else 'RESOLVED' if len(selected) == 1 else 'MULTI_TARGET'
        normalized.append({**row, 'resolution_state': state})
    return normalized
