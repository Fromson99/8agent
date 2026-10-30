from common import *
S=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1221/graph-refs/snapshot'
p=S/'02_BACKEND/semantic_runtime/ontology_work/accumulation.py';s=p.read_text()
s=s.replace("from .assembly_ir import validate_graph, check_basis, diff", "from .assembly_ir import validate_graph, check_basis, diff\nfrom .assembly_compiler import compile_package")
pos=s.index('\n\ndef observation_rows')
s=s[:pos]+'''

PROMPT += (' ID 공간을 구분한다. 입력 observations의 키(o-...)는 관찰 참조이고, 관찰 안 semantic_elements.id는 '
           '원래 관찰의 요소 ID다. 출력 graph.nodes.id는 이번에 제안하는 규칙 노드 ID이며 이들과 다르다. '
           'comparisons.node_ids는 이번 graph.nodes.id만 선택한다. 관찰 요소를 제외/반박했더라도 그 요소 ID를 '
           '적지 말고, 대응하는 제안 노드가 없으면 빈 배열을 쓴다. removed_nodes는 이전 base.proposal.graph.nodes에서 '
           '이번 graph.nodes로 사라진 ID만 적는다. base가 없으면 반드시 빈 배열이다. '
           'graph.unused_nodes에는 이번 graph.nodes 중 어느 purpose의 루트·의존·예외 경로에도 포함되지 않은 '
           '노드만 빠짐없이 적는다. 관찰 ID/폐기된 관찰 요소는 여기에 적지 않는다. '
           '비교 판정의 이유와 원문 인용은 그대로 남기며, 참조 오류를 고치려고 원래 관찰을 삭제하지 않는다.')


def reference_contract(observations, base=None):
    incoming = observation_rows(observations)
    prior = (base or {}).get('proposal', {}).get('graph', {}).get('nodes', [])
    return {'incoming_observation_refs': sorted(incoming),
            'allowed_provenance_refs': sorted(set(incoming) | set((base or {}).get('observation_ledger', {}))),
            'previous_graph_node_ids': sorted(n['id'] for n in prior),
            'comparison_node_ids': 'Only IDs in this output graph.nodes; never input semantic_elements IDs. Empty if no proposed node applies.',
            'removed_nodes': 'Exact previous graph IDs absent from this proposed graph. Empty when no previous graph.',
            'unused_nodes': 'Only proposed graph nodes not reached by any purpose including dependencies and exceptions.'}


def accumulation_schema(profile, observations, base=None):
    schema = deepcopy(profile['accumulation_schema'])
    refs = reference_contract(observations, base)
    comparisons = schema['properties']['comparisons']
    comparisons['minItems'] = comparisons['maxItems'] = len(refs['incoming_observation_refs'])
    if refs['incoming_observation_refs']:
        comparisons['items']['properties']['observation_ref']['enum'] = refs['incoming_observation_refs']
    removed = schema['properties']['removed_nodes']
    if refs['previous_graph_node_ids']:
        removed['items']['properties']['id']['enum'] = refs['previous_graph_node_ids']
    else:
        removed['maxItems'] = 0
    def bind(value):
        if isinstance(value, dict):
            field = value.get('properties', {}).get('observation_refs')
            if field is not None:
                if refs['allowed_provenance_refs']:
                    field['items']['enum'] = refs['allowed_provenance_refs']
                else:
                    field['maxItems'] = 0
            for child in value.values():
                bind(child)
        elif isinstance(value, list):
            for child in value:
                bind(child)
    bind(schema)
    return schema


def check_graph_references(proposal, incoming, base):
    nodes = index(proposal['graph']['nodes'])
    previous = index((base or {}).get('proposal', {}).get('graph', {}).get('nodes', []))
    comparisons = index(proposal['comparisons'], 'observation_ref')
    removed = index(proposal['removed_nodes'])
    unused = index(proposal['graph']['unused_nodes'])
    errors = []
    if set(comparisons) != set(incoming):
        errors.append(f"comparisons observation_ref missing={sorted(set(incoming)-comparisons.keys())}, unexpected={sorted(comparisons.keys()-set(incoming))}")
    for ref, row in comparisons.items():
        invalid = set(row['node_ids']) - nodes.keys()
        if invalid:
            errors.append(f"comparisons[{ref}].node_ids unknown={sorted(invalid)}; allowed proposed graph.nodes.id={sorted(nodes)}; observation semantic_elements.id is not this namespace; use [] if no proposed node applies")
    expected = previous.keys() - nodes.keys()
    if set(removed) != expected:
        errors.append(f"removed_nodes expected={sorted(expected)}, actual={sorted(removed)}; only previous graph deletions, never observation elements")
    invalid = unused.keys() - nodes.keys()
    if invalid:
        errors.append(f"graph.unused_nodes unknown={sorted(invalid)}; allowed proposed graph.nodes.id={sorted(nodes)}; never observation IDs")
    if errors:
        raise ContractError('accumulation reference errors: ' + '; '.join(errors))
''' + s[pos:]
s=s.replace("    validate_graph(proposal['graph'], profile, originals)\n    sources = index(originals); incoming = observation_rows(observations)", "    incoming = observation_rows(observations)\n    check_graph_references(proposal, incoming, base)\n    validate_graph(proposal['graph'], profile, originals)\n    sources = index(originals)")
s=s.replace("    conflicts = [r for r in comparisons.values()", "    # Run the unchanged compiler while the existing one-repair owner can still report errors.\n    compile_package(proposal['graph'], profile, originals, bundle_id='validation-only', revision=0)\n    conflicts = [r for r in comparisons.values()")
p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/ontology_work/domain_workflow.py';s=p.read_text();s=s.replace("'expected_revision': kwargs['expected_revision']}", "'expected_revision': kwargs['expected_revision'],\n                   'reference_contract': acc.reference_contract(observations, base)}")
s=s.replace("self._job('ACCUMULATE', context, acc.PROMPT, profile['accumulation_schema'],", "self._job('ACCUMULATE', context, acc.PROMPT, acc.accumulation_schema(profile, observations, base),")
p.write_text(s)
print('accumulation namespace/schema/repair boundary changed; compiler/profile immutable')
