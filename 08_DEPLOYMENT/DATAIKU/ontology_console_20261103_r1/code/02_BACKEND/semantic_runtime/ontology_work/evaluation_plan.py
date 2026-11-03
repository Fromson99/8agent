"""Explicit, reviewed AST bindings. Assembly prose is never executable."""
from copy import deepcopy
from ..contracts import digest
from ..legal_agent.errors import ContractError
from lawrag.legal_knowledge.ontology import evaluate, validate_expression

VERSION = 'ontology-evaluation-plan-v1'
EVALUATOR = 'typed-ontology-v1'


def fields(expression):
    if 'field' in expression:
        return {expression['field']}
    return set().union(*(fields(a) for a in expression.get('args', [])))


def compile_plan(spec, package):
    if not isinstance(spec, dict) or set(spec) != {'fields', 'rules'}:
        raise ContractError('evaluation specification requires fields and rules')
    if not isinstance(spec['fields'], dict) or not isinstance(spec['rules'], list) or len(spec['rules']) > 128 or len(spec['fields']) > 128:
        raise ContractError('invalid evaluation specification size')
    nodes = {n['id']: n for n in package['graph']['nodes']}
    originals = {s['id'] for s in package['originals']}
    for key, field in spec['fields'].items():
        if set(field) != {'kind', 'type', 'unit', 'concept', 'period', 'as_of', 'baseline'} or field['kind'] not in ('FACT', 'RULE'):
            raise ContractError('evaluation field requires kind/type/unit/concept/period/as_of/baseline')
        if not all(isinstance(field[k], str) for k in ('type', 'unit', 'concept', 'period', 'as_of')) or not field['concept']:
            raise ContractError('evaluation field semantic identity missing')
        if field['type'] not in ('boolean','decimal','money','ratio','duration','text','date','set'):
            raise ContractError('unsupported evaluation field type')
        validate_expression({'field': key})
        if field['baseline'] is not None:
            validate_expression({'literal': field['baseline']})
            if (field['baseline']['type'], field['baseline']['unit']) != (field['type'], field['unit']):
                raise ContractError('evaluation baseline type/unit changed')
        if field['kind'] == 'FACT' and field['baseline'] is not None:
            raise ContractError('case facts cannot be approved as shared rule constants')
    seen = set()
    for rule in spec['rules']:
        if set(rule) != {'node_id', 'expression', 'source_ids', 'rounding'} or rule['node_id'] not in nodes or rule['node_id'] in seen:
            raise ContractError('evaluation rule requires unique assembly node')
        seen.add(rule['node_id'])
        validate_expression(rule['expression'])
        if fields(rule['expression']) - spec['fields'].keys():
            raise ContractError('evaluation input not registered')
        basis = {b['source'] for b in nodes[rule['node_id']]['basis']}
        if not rule['source_ids'] or not set(rule['source_ids']) <= originals or not basis <= set(rule['source_ids']):
            raise ContractError('evaluation rule source binding missing')
        if rule['rounding'] != 'EXACT_ONLY':
            raise ContractError('unsupported rounding policy')
    body = {'schema_version': VERSION, 'evaluator_revision': EVALUATOR,
        'bundle_id': package['bundle_id'], 'revision': package['revision'],
        'approval_ref': package['approval_ref'], 'graph_hash': digest(package['graph']),
        'profile_hash': package['profile_hash'], 'source_hash': digest(package['originals']),
        'spec': deepcopy(spec)}
    return {**body, 'plan_hash': digest(body)}


def run(plan, inputs, *, binding):
    if (plan.get('schema_version') != VERSION or plan.get('evaluator_revision') != EVALUATOR
            or not plan.get('approval_ref') or plan.get('plan_hash') != digest({k:v for k,v in plan.items() if k != 'plan_hash'})):
        raise ContractError('evaluation plan authority or hash changed')
    facts = {}
    for key, field in plan['spec']['fields'].items():
        value = inputs.get(key)
        if value is None and field['kind'] == 'RULE':
            value = field['baseline']
        if value is not None:
            validate_expression({'literal': value})
            if (value['type'], value['unit']) != (field['type'], field['unit']):
                # Preserve a typed mismatch in the evaluator rather than coerce.
                facts[key] = {'status': 'CONFLICT', 'origin_ref': binding, 'value': value}
            else:
                facts[key] = {'status': 'ASSERTED', 'origin_ref': binding, 'value': value}
    if set(inputs) - plan['spec']['fields'].keys():
        raise ContractError('unknown scenario field')
    return {r['node_id']: evaluate(r['expression'], facts, binding=binding) for r in plan['spec']['rules']}
