from common import *
S=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1219/complete-coverage/snapshot'
p=S/'02_BACKEND/semantic_runtime/ontology_work/observations.py';s=p.read_text()
start=s.index('    if set(coverage) != {r[\'pointer\'] for r in raw[\'index\']}:');end=s.index('    candidates_by_id =',start)
s=s[:start]+'''    expected = {r['pointer'] for r in raw['index']}
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
''' +s[end:]
s+='''

NORMALIZATION_WIRE_VERSION = 'normalization-source-map-v1'
NORMALIZATION_INSTRUCTIONS = (
    '\\n출력 coverage는 raw.index의 pointer를 키로 하는 객체다. 모든 키를 정확히 한 번 작성한다. '
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
'''
p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/ontology_work/domain_workflow.py';s=p.read_text()
a="""        def validate(proposal):
            obs.validate_observations(proposal, raw, profile, candidates)
        proposal, receipt = self._job('NORMALIZE', context, profile['prompt'], profile['output_schema'], validate,
                                     lambda:self.glossary.verify_candidates(candidates))
        normalized = obs.normalized(proposal, raw, profile, candidates, receipt)"""
b="""        output_schema = obs.normalization_schema(raw, profile)
        def validate(proposal):
            canonical, _ = obs.restore_normalization(proposal, raw)
            obs.validate_observations(canonical, raw, profile, candidates)
        proposal, receipt = self._job('NORMALIZE', context,
            profile['prompt'] + obs.NORMALIZATION_INSTRUCTIONS, output_schema, validate,
            lambda:self.glossary.verify_candidates(candidates))
        canonical, assembly = obs.restore_normalization(proposal, raw)
        # The job/provider retain the original proposal; the stored observation keeps
        # the existing canonical contract plus a source-bound assembly receipt.
        receipt = {**receipt, 'normalization_assembly': assembly}
        normalized = obs.normalized(canonical, raw, profile, candidates, receipt)"""
assert a in s;s=s.replace(a,b);p.write_text(s)
print('Edited two candidate files; canonical/profile/storage and MAIN121 unchanged')
