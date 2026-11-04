"""Pure scenario comparison. Never mutates facts, approved rules or claims."""
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError
from ..ontology_work.evaluation_plan import run, fields

VERSION = 'scenario-branch-v1'


def compare(explanation, state, changes, *, kind, operation_id, bindings=None):
    if kind not in ('FACT', 'RULE') or not isinstance(changes, dict) or not changes or len(changes) > 64:
        raise ContractError('scenario requires FACT/RULE and bounded changed fields')
    catalogs = [b['assembly'] for b in explanation['ontology']['bundles'] if b.get('assembly')]
    plans = [c['evaluation_plan'] for c in catalogs if c.get('evaluation_plan')]
    field_specs = {}
    for plan in plans:
        for key, field in plan['spec']['fields'].items():
            if key in field_specs and field_specs[key] != field:
                raise ContractError('scenario field has conflicting concept/unit/period bindings')
            field_specs[key] = field
    from . import scenario_facts
    fact_bindings, baseline, fact_options = scenario_facts.bind(state, field_specs, bindings)
    if plans:
        if set(changes) - field_specs.keys():
            raise ContractError('scenario field is not registered')
        for key in changes:
            if field_specs[key]['kind'] != kind:
                raise ContractError('fact and rule assumptions must be separate branches')
    elif kind == 'FACT' and set(changes) - {f['name'] for f in state.get('facts', [])}:
        raise ContractError('unregistered case fact')
    elif kind == 'RULE':
        raise ContractError('rule assumptions require reviewed typed fields')
    binding = digest([explanation['content_sha256'], state, changes, kind, operation_id, fact_bindings])
    comparisons = []; evaluations = []; affected = set(); unresolved = []
    for catalog in catalogs:
        plan = catalog.get('evaluation_plan')
        paths = catalog.get('paths', [])
        if not plan:
            unresolved.append({'package_sha256': catalog['package_sha256'], 'reason': 'NO_APPROVED_TYPED_EXPRESSION'})
            continue
        keys = plan['spec']['fields'].keys()
        before = run(plan, {k:v for k,v in baseline.items() if k in keys}, binding=binding + ':baseline')
        after = run(plan, {k:v for k,v in {**baseline, **changes}.items() if k in keys}, binding=binding + ':assumption')
        evaluations.extend({'package_sha256':catalog['package_sha256'], 'node_id':node, 'result':result,
                'input_fields':sorted(fields(next(r['expression'] for r in plan['spec']['rules'] if r['node_id']==node)))}
            for node,result in sorted(after.items()))
        affected_local = {r['node_id'] for r in plan['spec']['rules'] if fields(r['expression']) & changes.keys()}
        edges = [e for p in paths for e in p['edges']]
        # Dependencies run dependent -> prerequisite; MODIFIES runs exception -> target.
        while True:
            expanded = affected_local | {e['from'] for e in edges if e['to'] in affected_local and e['type'].startswith('REQUIRES_')} | {e['to'] for e in edges if e['from'] in affected_local and e['type'] == 'MODIFIES'}
            if expanded == affected_local:break
            affected_local = expanded
        affected.update(affected_local)
        for node in sorted(affected_local):
            comparisons.append({'package_sha256': catalog['package_sha256'], 'node_id': node,
                'before': before.get(node, {'status': 'UNKNOWN', 'missing': ['NO_TYPED_EXPRESSION']}),
                'after': after.get(node, {'status': 'UNKNOWN', 'missing': ['NO_TYPED_EXPRESSION']})})
        unresolved.extend({'package_sha256': catalog['package_sha256'], **u} for p in paths for u in p.get('unresolved', []))
    if not plans:
        unresolved.append({'reason': 'NO_APPROVED_TYPED_EXPRESSION'})
    unresolved.extend({'item_id': i['id'], 'reason': i['reason'], 'next_action': i['next_action']}
        for i in explanation['items'] if i['review'] not in ('RESOLVED', 'NOT_NEEDED'))
    body = {'schema_version': VERSION, 'id': 'scenario:' + binding, 'operation_id': operation_id,
        'baseline_hash': explanation['content_sha256'], 'state_hash': digest(state),
        'kind': kind, 'changes': deepcopy(changes),
        'changed_fields':{k:{'field':deepcopy(field_specs[k]), 'before':deepcopy(field_specs[k]['baseline'] if kind=='RULE' else baseline.get(k)), 'after':deepcopy(v)} for k,v in changes.items() if k in field_specs}, 'comparisons': comparisons,
        'fact_bindings': fact_bindings, 'fact_options': fact_options, 'evaluations': evaluations,
        'unbound_changes': [k for k in changes if kind == 'FACT' and state.get('facts') and not fact_bindings.get(k)],
        'affected_nodes': sorted(affected), 'unresolved': unresolved,
        'legal_conclusion': 'UNCONFIRMED', 'semantic_review': 'REQUIRED',
        'baseline_outcome': explanation['outcome'], 'hypothetical': True,
        'actual_case_changed': False, 'shared_rules_changed': False, 'model_calls': 0}
    return {**body, 'content_sha256': digest(body)}
