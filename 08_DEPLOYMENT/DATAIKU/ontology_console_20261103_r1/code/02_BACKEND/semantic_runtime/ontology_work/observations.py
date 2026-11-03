"""Format-independent raw indexing; source receipts never come from model prose."""
from copy import deepcopy
import json
import re
from ..contracts import digest
from ..legal_agent.errors import ContractError
from ..legal_agent.ontology_compiler import _bounded_json
from .profile import validate, index

VERSION = 'normalized-observation-v1'


def lookup_queries(raw, limit=16):
    """Bounded literal candidates, with omissions explicit; no synonym generation."""
    values = []
    for row in raw['index']:
        text = row['text'].strip()
        if 2 <= len(text) <= 120:
            values.append(text)
        values.extend(token for token in re.findall(r'[\w가-힣]+', text) if 2 <= len(token) <= 120)
    values = list(dict.fromkeys(values))
    return values[:limit], len(values) - min(len(values), limit)


def raw_index(payload):
    _bounded_json(payload)
    result = []
    def visit(value, pointer):
        if isinstance(value, dict):
            if not value:
                result.append({'pointer': pointer, 'text': '{}'})
            for key in sorted(value):
                visit(value[key], pointer + '/' + key.replace('~', '~0').replace('/', '~1'))
        elif isinstance(value, list):
            if not value:
                result.append({'pointer': pointer, 'text': '[]'})
            for i, item in enumerate(value):
                visit(item, pointer + '/' + str(i))
        else:
            result.append({'pointer': pointer, 'text': value if isinstance(value, str)
                           else json.dumps(value, ensure_ascii=False, allow_nan=False)})
    visit(payload, '')
    if len(result) > 2048:
        raise ContractError('raw input requires an explicitly planned partition')
    return result


def envelope(payload, *, namespace, run_id, event_id, sequence, source_snapshot,
             producer_binding, acl_ref, document_ids, parent_refs=(), source_receipts=(),
             format_description='', origin='AUTHENTICATED_IMPORT'):
    if not all(isinstance(x, str) and x.strip() for x in
               (namespace, run_id, event_id, source_snapshot, producer_binding, acl_ref)):
        raise ContractError('raw exporter binding required')
    if type(sequence) is not int or sequence < 0:
        raise ContractError('raw sequence must be nonnegative')
    indexed = raw_index(payload)
    return {'version': 'raw-observation-envelope-v1', 'namespace': namespace, 'run_id': run_id,
            'raw_event_id': event_id, 'sequence': sequence, 'parent_refs': list(parent_refs),
            'payload': deepcopy(payload), 'payload_hash': digest(payload), 'index': indexed,
            'media_type': 'text/plain' if isinstance(payload, str) else 'application/json',
            'source_snapshot': source_snapshot, 'producer_binding': producer_binding,
            'acl_ref': acl_ref, 'document_ids': sorted(set(document_ids)),
            'verified_source_receipts': deepcopy(list(source_receipts)),
            'format_description': format_description, 'origin': origin}


def check_envelope(raw):
    if (raw.get('version') != 'raw-observation-envelope-v1'
            or digest(raw['payload']) != raw['payload_hash'] or raw_index(raw['payload']) != raw['index']):
        raise ContractError('raw envelope content changed')


def check_locator(locator, raw):
    segments = {r['pointer']: r['text'] for r in raw['index']}
    start, end = locator['start'], locator['end']
    text = segments.get(locator['pointer'])
    if (locator['payload_hash'] != raw['payload_hash'] or text is None
            or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
            or text[start:end] != locator['quote']):
        raise ContractError('raw locator hash/pointer/code-point/quote mismatch')


def validate_observations(proposal, raw, profile, candidates):
    check_envelope(raw)
    validate(proposal, profile['output_schema'])
    observations = index(proposal['observations'])
    coverage = index(proposal['coverage'], 'pointer')
    expected = {r['pointer'] for r in raw['index']}
    errors = []
    if set(coverage) != expected:
        errors.append('coverage pointers: missing=' + repr(sorted(expected - coverage.keys()))
                      + ', unexpected=' + repr(sorted(coverage.keys() - expected)))
    for pointer, row in coverage.items():
        unknown = set(row['observation_ids']) - observations.keys()
        if unknown:
            errors.append('coverage ' + repr(pointer) + ': unknown observation IDs ' + repr(sorted(unknown)))
        if row['state'] == 'USED' and not row['observation_ids']:
            errors.append('coverage ' + repr(pointer) + ': USED requires observation_ids')
        elif row['state'] != 'USED' and row['observation_ids']:
            errors.append('coverage ' + repr(pointer) + ': ' + row['state']
                          + ' requires empty observation_ids; linked segments must be USED')
    used = {oid for row in coverage.values() for oid in row['observation_ids']}
    if observations.keys() - used:
        errors.append('unaccounted observation IDs: ' + repr(sorted(observations.keys() - used)))
    if errors:
        raise ContractError('; '.join(errors))
    candidates_by_id = {c['concept_id']: c for c in candidates['candidates']}
    def walk(value):
        if isinstance(value, dict):
            if set(value) == {'payload_hash', 'pointer', 'start', 'end', 'quote'}:
                check_locator(value, raw)
            else:
                for child in value.values():
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(proposal)
    for obs in observations.values():
        if obs['statement']['state'] != 'PRESENT':
            raise ContractError('an observed statement must have a raw location')
        for key in ('statement', 'reason', 'purpose', 'scope'):
            field = obs[key]
            if field['state'] == 'PRESENT' and field['value'] not in [l['quote'] for l in field['locators']]:
                raise ContractError('observed text must preserve an exact raw quote')
        nodes = index(obs['semantic_elements'])
        for node in nodes.values():
            for slot, value in node['slots'].items():
                definition = next(s for s in profile['effective']['slots'] if s['id'] == slot)
                if definition['value_type'] == 'NODE_REFS' and value['state'] == 'PRESENT':
                    if not set(value['value']) <= nodes.keys():
                        raise ContractError('observation node reference outside extraction')
        for link in obs['glossary_refs']:
            if link['concept_id'] not in candidates_by_id:
                raise ContractError('glossary ID not offered in this extraction')
    return deepcopy(proposal)


def normalized(proposal, raw, profile, candidates, model_receipt):
    validate_observations(proposal, raw, profile, candidates)
    revision = digest([digest(raw), profile['profile_hash'], digest(candidates), model_receipt])
    return {'version': VERSION, 'raw_event_ref': digest(raw), 'raw_event_id': raw['raw_event_id'],
            'run_id': raw['run_id'], 'extraction_revision': revision,
            'profile_hash': profile['profile_hash'], 'glossary_candidates': deepcopy(candidates),
            'model_receipt': deepcopy(model_receipt), 'proposal': deepcopy(proposal),
            'verified_source_receipts': deepcopy(raw['verified_source_receipts']),
            'publication_lineage': deepcopy(raw['parent_refs']), 'legal_truth_certified': False}


def export_journal(db, *, after, limit, authorize, metadata):
    """Use journal_storage.connect, or the running repository's decoding connection.

    authorize inspects the *whole run* ACL before any event is exported. Exporting
    current heads only would destroy withdrawn and superseded opinions.
    """
    if type(limit) is not int or not 1 <= limit <= 64:
        raise ContractError('journal export page limit')
    run = dict(db.execute('SELECT * FROM run WHERE singleton=1').fetchone())
    authorize(run)
    rows = db.execute('SELECT seq,event_id,payload_json,payload_hash FROM event WHERE seq>? ORDER BY seq LIMIT ?',
                      (after, limit)).fetchall()
    out = []
    for row in rows:
        payload = json.loads(row['payload_json'])
        if digest(payload) != row['payload_hash']:
            raise ContractError('journal logical payload hash mismatch')
        out.append(envelope(payload, run_id=run['run_id'], event_id=row['event_id'], sequence=row['seq'],
                            producer_binding=run['binding_hash'], origin='JOURNAL_EXPORT', **metadata))
    return {'events': out, 'checkpoint': rows[-1]['seq'] if rows else after, 'page_full': len(rows) == limit}


NORMALIZATION_WIRE_VERSION = 'normalization-source-map-v1'
NORMALIZATION_INSTRUCTIONS = (
    '\n출력 coverage는 raw.index의 pointer를 키로 하는 객체다. 모든 키를 정확히 한 번 작성한다. '
    '각 입력 구간을 관찰과 연결했다면 USED와 비어 있지 않은 observation_ids를 쓴다. '
    'USED는 관찰에 연결했다는 뜻이며 법률적으로 옳다는 뜻이 아니다. '
    'NON_JUDGMENT와 NEEDS_CONTEXT의 observation_ids는 반드시 빈 배열이다. '
    '모든 observation은 coverage에서 최소 한 번 연결한다. '
    '인용 위치는 raw.index에 제시된 상대 pointer와 그 구간 안의 정확한 quote, '
    '같은 quote의 0부터 세는 occurrence로 선택한다. raw_event_id나 이전 파일의 경로를 pointer로 쓰지 않는다. '
    '해시와 글자 시작·끝 위치는 서버가 계산한다. '
    'statement/reason/purpose/scope의 PRESENT value는 해당 locator의 정확한 quote와 같아야 한다. '
    '동일 문구가 한 번만 있으면 occurrence=0이다. 기록에 없는 판단·원문·용어는 만들지 않는다.'
)


def normalization_schema(raw, profile):
    """Close the request over exact source segments; stored canonical schema stays intact."""
    check_envelope(raw)
    schema = deepcopy(profile['output_schema'])
    pointers = [row['pointer'] for row in raw['index']]
    row = deepcopy(schema['properties']['coverage']['items'])
    del row['properties']['pointer']; row['required'].remove('pointer')
    used, unused = deepcopy(row), deepcopy(row)
    used['properties']['state'] = {'const': 'USED'}
    used['properties']['observation_ids']['minItems'] = 1
    unused['properties']['state'] = {'enum': ['NON_JUDGMENT', 'NEEDS_CONTEXT']}
    unused['properties']['observation_ids']['maxItems'] = 0
    schema['properties']['coverage'] = {'type': 'object', 'additionalProperties': False,
        'properties': {pointer: {'anyOf': [deepcopy(used), deepcopy(unused)]} for pointer in pointers},
        'required': pointers}
    locator_fields = {'payload_hash', 'pointer', 'start', 'end', 'quote'}
    def visit(node):
        if not isinstance(node, dict):
            return
        if node.get('type') == 'object' and set(node.get('properties', {})) == locator_fields:
            quote_schema = deepcopy(node['properties']['quote'])
            node.clear()
            node.update(type='object', additionalProperties=False,
                required=['pointer', 'quote', 'occurrence'],
                properties={'pointer': {'enum': pointers}, 'quote': quote_schema,
                            'occurrence': {'type': 'integer', 'minimum': 0}})
            return
        for name in ('properties', 'patternProperties', 'dependentSchemas', '$defs', 'definitions'):
            for child in node.get(name, {}).values():
                visit(child)
        for name in ('items', 'additionalProperties', 'not', 'if', 'then', 'else', 'contains'):
            child = node.get(name)
            if isinstance(child, dict): visit(child)
            elif isinstance(child, list):
                for item in child: visit(item)
        for name in ('anyOf', 'oneOf', 'allOf', 'prefixItems'):
            for child in node.get(name, []): visit(child)
    visit(schema)
    return schema


def restore_normalization(proposal, raw):
    """Assemble only source coordinates. Never infer a missing row, state or reference."""
    check_envelope(raw)
    if not isinstance(proposal, dict):
        raise ContractError('normalization response must be an object')
    segments = {row['pointer']: row['text'] for row in raw['index']}
    result = deepcopy(proposal)
    coverage = result.get('coverage')
    mapped = isinstance(coverage, dict)
    if mapped:
        if coverage.keys() != segments.keys():
            raise ContractError('coverage pointers: missing=' + repr(sorted(segments.keys() - coverage.keys()))
                                + ', unexpected=' + repr(sorted(coverage.keys() - segments.keys())))
        if any(not isinstance(value, dict) or set(value) != {'state', 'observation_ids', 'reason'}
               for value in coverage.values()):
            raise ContractError('coverage map row requires state, observation_ids and reason only')
        result['coverage'] = [{'pointer': pointer, **coverage[pointer]} for pointer in segments]
    count = 0
    def restore(value):
        nonlocal count
        if isinstance(value, dict):
            if set(value) == {'pointer', 'quote', 'occurrence'}:
                pointer, quote, occurrence = value['pointer'], value['quote'], value['occurrence']
                if (not isinstance(pointer, str) or pointer not in segments or not isinstance(quote, str)
                        or not quote or type(occurrence) is not int or occurrence < 0):
                    raise ContractError('compact raw locator has invalid pointer, quote or occurrence')
                text = segments[pointer]; start = -1
                # Bound the scan by the input length even for a malicious huge occurrence.
                if occurrence >= len(text):
                    raise ContractError('compact raw locator occurrence outside input at ' + repr(pointer))
                for _ in range(occurrence + 1):
                    start = text.find(quote, start + 1)
                    if start < 0:
                        raise ContractError('exact raw quote/occurrence not found at ' + repr(pointer))
                count += 1
                return {'payload_hash': raw['payload_hash'], 'pointer': pointer, 'start': start,
                        'end': start + len(quote), 'quote': quote}
            return {key: restore(child) for key, child in value.items()}
        if isinstance(value, list):
            return [restore(child) for child in value]
        return value
    result = restore(result)
    receipt = {'version': NORMALIZATION_WIRE_VERSION, 'proposal_sha256': digest(proposal),
        'canonical_sha256': digest(result), 'raw_payload_sha256': raw['payload_hash'],
        'raw_index_sha256': digest(raw['index']), 'coverage_map': mapped,
        'coverage_count': len(coverage) if isinstance(coverage, (list, dict)) else None,
        'assembled_locators': count}
    return result, receipt
