"""Deterministic purpose closure and exact approved text. No model or expression execution."""
from copy import deepcopy
from ..contracts import digest
from ..legal_agent.errors import ContractError
from ..legal_agent.ontology_compiler import content_hash
from .profile import index
from .assembly_ir import validate_graph

VERSION = 'ontology-assembly-package-v1'


def compile_package(graph, profile, originals, *, bundle_id, revision, approval_ref=None, glossary_refs=()):
    validate_graph(graph, profile, originals)
    nodes = index(graph['nodes']); kinds = index(profile['effective']['node_types'], 'kind')
    purposes = index(profile['effective']['purposes']); relations = index(profile['effective']['relations'])
    dependencies = {key: [] for key in nodes}; exceptions = {key: [] for key in nodes}
    for e in graph['edges']:
        role = relations[e['type']]['assembly_role']
        if role == 'DEPENDENCY':
            dependencies[e['from']].append(e['to'])
        elif role == 'INCOMING_EXCEPTION':
            exceptions[e['to']].append(e['from'])
    def ordered(roots):
        done = set(); active = set(); output = []
        def visit(key):
            if key in active:
                raise ContractError('assembly dependency cycle')
            if key in done:
                return
            active.add(key)
            for dep in sorted(dependencies[key]):
                visit(dep)
            active.remove(key); done.add(key); output.append(key)
        for root in sorted(roots):
            visit(root)
        return output
    ordered(nodes)
    paths = []; used = set()
    for purpose in graph['purposes']:
        selected = set(ordered(purpose['roots']))
        while True:
            expanded = set(ordered(selected | {e for n in selected for e in exceptions[n]}))
            if expanded == selected:
                break
            selected = expanded
        order = ordered(selected); used.update(selected)
        edges = [deepcopy(e) for e in graph['edges'] if e['from'] in selected and e['to'] in selected]
        missing = []
        for n in order:
            required = set(kinds[nodes[n]['kind']]['required_review_slots'])
            if n in purpose['roots']:
                required.update(purposes[purpose['purpose']]['required_review_slots'])
            for slot in sorted(required | set(nodes[n]['slots'])):
                value = nodes[n]['slots'].get(slot, {'state': 'NOT_RECORDED'})
                if value['state'] not in ('PRESENT', 'NOT_APPLICABLE'):
                    missing.append({'node_id': n, 'slot': slot, 'state': value['state']})
        source_ids = sorted({b['source'] for n in order for b in nodes[n]['basis']}
                            | {b['source'] for e in edges for b in e['basis']})
        # Exact approved text is kept beside every typed slot/edge. A display never
        # substitutes a scenario-v1 components/text/requires projection for the IR.
        body = '\n\n'.join(nodes[n]['text'] for n in order)
        paths.append({'id': purpose['id'], 'purpose': purpose['purpose'], 'title': purpose['title'],
                      'root_ids': deepcopy(purpose['roots']), 'node_ids': order, 'edges': edges,
                      'nodes': [deepcopy(nodes[n]) for n in order], 'source_ids': source_ids,
                      'unresolved': missing, 'status': 'PARTIAL' if missing or graph['unresolved'] else 'READY',
                      'body': body, 'body_sha256': digest(body)})
    if set(index(graph['unused_nodes'])) != nodes.keys() - used:
        raise ContractError('every unused node needs an explicit review reason')
    body = {'version': VERSION, 'authority': 'APPROVED' if approval_ref else 'PREVIEW',
            'bundle_id': bundle_id, 'revision': revision, 'approval_ref': approval_ref,
            'profile': {k: deepcopy(profile[k]) for k in ('domain','business','profile_hash','code_binding','schema_binding')},
            'profile_hash': profile['profile_hash'], 'graph': deepcopy(graph),
            'originals': deepcopy(originals), 'glossary_refs': deepcopy(list(glossary_refs)),
            'paths': paths, 'numeric_execution': False, 'runtime_compilation': False}
    return {**body, 'package_sha256': digest(body)}


def verify_package(package, *, approved=False, recompile=False):
    if package.get('version') != VERSION or (approved and (package.get('authority') != 'APPROVED'
                                                        or not package.get('approval_ref'))):
        raise ContractError('assembly publication authority')
    if package.get('package_sha256') != digest({k: v for k, v in package.items() if k != 'package_sha256'}):
        raise ContractError('assembly package changed')
    from .profile import compile_profile
    from .assembly_ir import validate_originals
    compiled_profile = compile_profile(package['profile']['domain'], package['profile']['business'])
    descriptor = {k: deepcopy(compiled_profile[k]) for k in ('domain','business','profile_hash','code_binding','schema_binding')}
    validate_originals(package['originals'])
    if package['profile_hash'] != compiled_profile['profile_hash'] or package['profile'] != descriptor:
        raise ContractError('assembly profile binding changed')
    for path in package['paths']:
        if path['body_sha256'] != digest(path['body']):
            raise ContractError('assembly body changed')
    if recompile:
        expected = compile_package(package['graph'], compiled_profile, package['originals'],
            bundle_id=package['bundle_id'], revision=package['revision'], approval_ref=package['approval_ref'],
            glossary_refs=package['glossary_refs'])
        if expected != package:
            raise ContractError('assembly compiled result differs')
    return package


def bind_current(package, fragments):
    # No runtime recompile: durable verification is performed at repository load;
    # check package integrity and bind the actual current evidence on every use.
    if package['package_sha256'] != digest({k: v for k, v in package.items() if k != 'package_sha256'}):
        raise ContractError('assembly package changed')
    available = {}; originals = {digest(s['anchor']): s for s in package['originals']}
    for fragment in fragments:
        source = originals.get(digest(fragment['anchor']))
        if source is None:
            continue
        if (fragment['text'] != source['text'] or content_hash(fragment['text']) != source['anchor']['content_sha256']
                or not fragment.get('evidence_refs') or source['id'] in available):
            raise ContractError('assembly current original/reference changed')
        available[source['id']] = list(fragment['evidence_refs'])
    ready = []; withheld = []
    for path in package['paths']:
        missing = sorted(set(path['source_ids']) - available.keys())
        if missing:
            withheld.append({'id': path['id'], 'missing_originals': missing})
        else:
            ready.append({**deepcopy(path), 'source_refs': list(dict.fromkeys(
                r for s in path['source_ids'] for r in available[s]))})
    return {'version': VERSION, 'bundle_id': package['bundle_id'], 'revision': package['revision'],
            'profile_hash': package['profile_hash'], 'package_sha256': package['package_sha256'],
            'paths': ready, 'withheld': withheld, 'unresolved': deepcopy(package['graph']['unresolved']),
            'runtime_compilation': False, 'automatic_adoption': False}
