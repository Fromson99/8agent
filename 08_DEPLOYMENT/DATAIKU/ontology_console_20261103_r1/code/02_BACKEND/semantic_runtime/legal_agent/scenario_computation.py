"""Host-owned calculation facts. Never invent a legal claim or rewrite model prose."""
from copy import deepcopy
from ..contracts import digest
from ..ontology_work.evaluation_plan import run, fields
from .errors import ContractError, ProposalError
from . import output_contract as output

VERSION = 'scenario-computation-v1'
APPLICATION_VERSION = 'scenario-application-v4'
PROMPT = '''가정의 현재 입력·조건 계산·변경 전후 비교는 서버가 최종 답변에 직접 표시한다. 같은 숫자와 비교문을 claims에 다시 작성하거나 application_links를 만들 필요가 없다. 모델은 원문 적용 범위·예외·해석과 실제 근거를 판단한다. 계산 결과와 다른 주장을 만들지 않는다. 계산기에서 알려준 미확인 사실을 gap으로 채택할 때는 computed_gap_options의 computed_gap_ref와 issue_id만 선택할 수 있다. 추가적인 원문 부족이나 다른 사실 부족은 기존 gaps로 작성한다. 제시되지 않은 gap 번호나 참조를 사유에 만들지 않는다. 수치 TRUE는 최종 법적 허용이 아니며 실제 사실과 승인 규칙을 변경하지 않는다.'''


def catalog(explanation):
    plans = []; specs = {}; seen = set()
    for bundle in explanation['ontology']['bundles']:
        assembly = bundle.get('assembly') or {}
        plan = assembly.get('evaluation_plan')
        if not plan:
            continue
        package = assembly['package_sha256']
        if package in seen:
            raise ContractError('duplicate scenario calculation package')
        seen.add(package)
        for name, spec in plan['spec']['fields'].items():
            if name in specs and specs[name] != spec:
                raise ContractError('scenario calculation field identity conflict')
            specs[name] = deepcopy(spec)
        plans.append({'package_sha256': package, 'plan': deepcopy(plan)})
    return {'schema_version': VERSION, 'fields': specs, 'plans': plans}


def enabled(context):
    return bool(context and context.get('calculation_catalog', {}).get('schema_version') == VERSION
        and any(r.get('plan', {}).get('spec', {}).get('rules') for r in context['calculation_catalog'].get('plans', [])))


def build(context):
    """Re-evaluate the approved plans; check recorded current predicates exactly."""
    if not enabled(context) or context.get('content_sha256') != digest({k:v for k,v in context.items() if k != 'content_sha256'}):
        raise ContractError('scenario calculation context hash or version changed')
    cat = context['calculation_catalog']; specs = cat['fields']
    current = deepcopy(context['typed_inputs']); before = deepcopy(current)
    if set(current) - specs.keys():
        raise ContractError('scenario calculation input is not registered')
    for name, change in context['changed_fields'].items():
        if specs.get(name) != change['field'] or current.get(name) != change['after'] or context['changes'].get(name) != change['after']:
            raise ContractError('scenario calculation changed input binding differs')
        if change['before'] is None:
            before.pop(name, None)
        else:
            before[name] = deepcopy(change['before'])
    if set(context['changes']) != set(context['changed_fields']):
        raise ContractError('scenario calculation change is not typed')
    recorded = {(r['package_sha256'], r['node_id']): r for r in context['evaluations']}
    if len(recorded) != len(context['evaluations']):
        raise ContractError('duplicate scenario predicate result')
    calculated = {}; plan_specs = {}; plan_keys = set(); predicates = []
    for item in cat['plans']:
        package = item['package_sha256']; plan = item['plan']
        if package in plan_keys:
            raise ContractError('duplicate scenario calculation plan')
        plan_keys.add(package)
        for name, spec in plan['spec']['fields'].items():
            if name in plan_specs and plan_specs[name] != spec:
                raise ContractError('scenario calculation plan fields conflict')
            plan_specs[name] = spec
        keys = plan['spec']['fields'].keys()
        bindings = {recorded.get((package, r['node_id']), {}).get('result', {}).get('binding') for r in plan['spec']['rules']}
        if plan['spec']['rules'] and (len(bindings) != 1 or not all(isinstance(v, str) and v for v in bindings)):
            raise ContractError('scenario calculation predicate binding differs')
        results = run(plan, {k:v for k,v in current.items() if k in keys}, binding=next(iter(bindings), 'calculation:current'))
        previous = run(plan, {k:v for k,v in before.items() if k in keys}, binding='calculation:before')
        for rule in plan['spec']['rules']:
            key = (package, rule['node_id']); row = recorded.get(key)
            expected = results[rule['node_id']]
            if not row or row.get('input_fields') != sorted(fields(rule['expression'])):
                raise ContractError('scenario calculation predicate inputs changed')
            if {k:v for k,v in row['result'].items() if k != 'binding'} != {k:v for k,v in expected.items() if k != 'binding'}:
                raise ContractError('scenario calculation predicate differs from approved plan')
            calculated[key] = expected
            predicates.append({'package_sha256': package, 'node_id': rule['node_id'],
                'plan_hash': plan['plan_hash'], 'approval_ref': plan['approval_ref'],
                'input_fields': row['input_fields'], 'expression': deepcopy(rule['expression']),
                'before': {k:v for k,v in previous[rule['node_id']].items() if k != 'binding'},
                'current': {k:v for k,v in expected.items() if k != 'binding'}})
    if plan_specs != specs or set(calculated) != set(recorded):
        raise ContractError('scenario calculation plan set changed')
    inputs = [{'field': name, 'concept': spec['concept'], 'kind': spec['kind'],
        'type': spec['type'], 'unit': spec['unit'], 'period': spec['period'], 'as_of': spec['as_of'],
        'value': deepcopy(current.get(name, spec['baseline'] if spec['kind'] == 'RULE' else None))}
        for name, spec in sorted(specs.items())]
    missing = sorted({name for r in predicates for name in r['current']['missing']
        if name in specs and specs[name]['kind'] == 'FACT' and current.get(name) is None})
    body = {'schema_version': VERSION, 'context_sha256': context['content_sha256'],
        'hypothetical': True, 'legal_conclusion_confirmed': False, 'inputs': inputs,
        'changes': [{'field': name, 'concept': specs[name]['concept'],
            'before': deepcopy(row['before']), 'current': deepcopy(row['after'])}
            for name,row in sorted(context['changed_fields'].items())],
        'predicates': predicates, 'missing_fields': missing,
        'unresolved_effects': [deepcopy(r) for r in context.get('typed_comparisons', [])
            if (r['package_sha256'], r['node_id']) not in calculated]}
    return {**body, 'content_sha256': digest(body)}


def verify_saved(assessment, context):
    expected = build(context)
    if assessment.get('scenario_calculation') != expected:
        raise ContractError('saved scenario calculation missing or changed')


def gap_options(context):
    receipt = build(context); specs = context['calculation_catalog']['fields']
    options = [{'computed_gap_ref': 'computed-gap:' + digest([context['content_sha256'], name]),
        'field': name, 'concept': specs[name]['concept'],
        'reason': specs[name]['concept'] + ' 입력이 미확인입니다. 이 값을 사용하는 조건의 확인이 필요합니다.'}
        for name in receipt['missing_fields']]
    # A long concept remains complete in the calculation display. Do not offer
    # a shorthand whose deterministic reason cannot satisfy the canonical schema.
    return [r for r in options if 1 <= len(r['reason']) <= 600]


def projection(schema, context):
    """Add an explicit gap shorthand; expand in place before canonical validators."""
    options = {r['computed_gap_ref']:r for r in gap_options(context) if 1 <= len(r['reason']) <= 600}
    if not options:
        return schema, lambda value: value
    shape = deepcopy(schema); original = deepcopy(shape['properties']['gaps']['items'])
    issue_shape = deepcopy(original['properties']['issue_id'])
    shorthand = {'type':'object', 'additionalProperties':False,
        'properties': {'computed_gap_ref': {'type':'string', 'enum':list(options)}, 'issue_id':issue_shape},
        'required':['computed_gap_ref', 'issue_id']}
    shape['properties']['gaps']['items'] = {'anyOf':[original, shorthand]}
    def decode(raw):
        output.validate_shape(raw, shape)
        value = deepcopy(raw)
        seen = set()
        for index, row in enumerate(value['gaps']):
            if 'computed_gap_ref' not in row:
                if any(ref in row.get('reason', '') for ref in options):
                    raise output.OutputContractError(
                        '미확인 입력 ID는 이유문에 쓰지 말고 computed_gap_ref와 issue_id 필드로 선택하세요. 원래 설명은 원제안에 보존됩니다.',
                        [output.issue('COMPUTED_GAP_IN_REASON', '/gaps/'+str(index)+'/reason')],
                        category='SCENARIO_REVIEW_INVALID')
                continue
            key = (row['computed_gap_ref'], row['issue_id'])
            if key in seen:
                raise output.OutputContractError('같은 미확인 입력은 쟁점마다 한 번만 연결하세요.',
                    [output.issue('COMPUTED_GAP_DUPLICATE', '/gaps/'+str(index))], category='SCENARIO_REVIEW_INVALID')
            seen.add(key); offered = options[row['computed_gap_ref']]
            value['gaps'][index] = {'kind':'MISSING_FACT', 'material':True,
                'reason':offered['reason'], 'issue_id':row['issue_id'], 'material_id':None,
                'missing_target':'', 'suggested_action':'REQUEST_FACT'}
        return value
    def expand(raw):
        try:
            return decode(raw)
        except ProposalError as exc:
            exc.proposal=deepcopy(raw)
            raise
    return shape, expand


def render(receipt):
    if receipt.get('content_sha256') != digest({k:v for k,v in receipt.items() if k != 'content_sha256'}):
        raise ContractError('scenario calculation presentation changed')
    from .scenario_application import literal_text
    def literal(value):
        if value is None:
            return '미확인'
        if value['type'] == 'boolean':
            return '참' if value['value'] else '거짓'
        return literal_text(value)
    labels = {'TRUE':'충족', 'FALSE':'불충족', 'UNKNOWN':'미확인', 'CONFLICT':'입력 충돌', 'VALUE':'계산값'}
    concepts = {r['field']:r['concept'] for r in receipt['inputs']}
    lines = ['가정의 계산 결과', '현재 입력: '+'; '.join(r['concept']+' '+literal(r['value']) for r in receipt['inputs'])]
    for row in receipt['changes']:
        lines.append('변경 전후: '+row['concept']+' '+literal(row['before'])+' → '+literal(row['current']))
    for row in receipt['predicates']:
        title = ' / '.join(concepts[k] for k in row['input_fields'])
        text = title+': '+labels[row['before']['status']]+' → '+labels[row['current']['status']]
        if row['current']['status'] == 'VALUE':
            text += ' ('+literal(row['current']['value'])+')'
        lines.append(text)
    if receipt['missing_fields']:
        lines.append('미확인 입력: '+', '.join(concepts[k] for k in receipt['missing_fields']))
    if receipt['unresolved_effects']:
        lines.append('계산식이 등록되지 않은 효과는 미확인으로 남습니다.')
    lines.append('가정하의 등록 조건 계산이며, 적용 범위·예외를 포함한 최종 허용 판단은 별도입니다.')
    return '\n\n'.join(lines)
