"""Typed operational IR. It validates relations; it never infers legal relations."""
from copy import deepcopy
from ..contracts import digest
from ..legal_agent.errors import ContractError
from .profile import validate, index, verify_profile
from .profile_schema import graph_schema
from .schema import validate_input

VERSION = 'ontology-assembly-ir-v1'


def validate_originals(originals):
    validate_input({'version': 'ontology-work-v1', 'concept': 'source validation',
                    'originals': originals, 'judgments': [], 'origin': {'run_id': 'assembly'}})


def check_basis(basis, originals):
    for b in basis:
        s = originals.get(b['source'])
        if not s or not b['quote'].strip() or b['quote'] not in s['text']:
            raise ContractError('source basis must quote the verified original exactly')


def validate_graph(graph, profile, originals):
    verify_profile(profile)
    p = profile['effective']
    validate(graph, graph_schema(p)); validate_originals(originals)
    sources = index(originals); nodes = index(graph['nodes']); edges = index(graph['edges'])
    kinds = index(p['node_types'], 'kind'); rels = index(p['relations']); purposes = index(p['purposes'])
    slots = index(p['slots']); index(graph['purposes']); index(graph['unused_nodes'])
    triples = set()
    for edge in edges.values():
        r = rels[edge['type']]
        left, right = nodes.get(edge['from']), nodes.get(edge['to'])
        if not left or not right or left['kind'] not in r['allowed_from'] or right['kind'] not in r['allowed_to']:
            raise ContractError('typed edge endpoint mismatch')
        triple = (edge['type'], edge['from'], edge['to'])
        if triple in triples:
            raise ContractError('duplicate typed edge')
        triples.add(triple); check_basis(edge['basis'], sources)
    correspondence = {'conditions': 'REQUIRES_CONDITION', 'inputs': 'REQUIRES_INPUT',
                      'modified_targets': 'MODIFIES', 'exceptions': 'MODIFIES'}
    for node in nodes.values():
        check_basis(node['basis'], sources)
        if node['slots']['statement']['state'] != 'PRESENT' or node['slots']['statement']['value'] != node['text']:
            raise ContractError('node text must preserve the approved statement slot')
        for name, slot in node['slots'].items():
            if slots[name]['value_type'] != 'NODE_REFS' or slot['state'] != 'PRESENT':
                continue
            if len(set(slot['value'])) != len(slot['value']) or not set(slot['value']) <= nodes.keys():
                raise ContractError('dangling/duplicate typed slot reference')
            if name in correspondence:
                expected = {(correspondence[name], target, node['id']) if name == 'exceptions'
                            else (correspondence[name], node['id'], target) for target in slot['value']}
                actual = {t for t in triples if t[0] == correspondence[name]
                          and (t[2] if name == 'exceptions' else t[1]) == node['id']}
                if expected != actual:
                    raise ContractError('typed slots and explicit edges disagree: ' + name)
            elif slot['value']:
                # All other node references also need an explicit executable edge;
                # RELATED_TO is deliberately insufficient for required inputs.
                executable = {e['to'] for e in edges.values() if e['from'] == node['id']
                              and rels[e['type']]['assembly_role'] == 'DEPENDENCY'}
                if not set(slot['value']) <= executable:
                    raise ContractError('typed reference needs explicit dependency: ' + name)
        if kinds[node['kind']]['core_role'] == 'EXCEPTION' and not any(
                t[0] == 'MODIFIES' and t[1] == node['id'] for t in triples):
            raise ContractError('exception needs an explicit modified target')
    for purpose in graph['purposes']:
        rule = purposes[purpose['purpose']]
        if not set(purpose['roots']) <= nodes.keys() or any(
                kinds[nodes[n]['kind']]['core_role'] not in rule['root_roles'] for n in purpose['roots']):
            raise ContractError('purpose root role mismatch')
    return deepcopy(graph)


def diff(before, after):
    result = {}
    for collection in ('nodes', 'edges', 'purposes'):
        old = index((before or {}).get(collection, [])); new = index(after[collection])
        result[collection] = {'added': sorted(new.keys() - old.keys()), 'removed': sorted(old.keys() - new.keys()),
            'changed': sorted(k for k in new.keys() & old.keys() if digest(new[k]) != digest(old[k]))}
    return result
