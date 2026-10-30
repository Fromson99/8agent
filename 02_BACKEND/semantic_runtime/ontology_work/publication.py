"""Assembly publication envelope consumed by the existing source/ASSESS path."""
from copy import deepcopy
from ..contracts import digest
from ..legal_agent.errors import ContractError
from . import assembly_compiler as compiler


def publication_context(package, *, approved_at):
    compiler.verify_package(package, approved=True, recompile=True)
    bundle = {'schema_version': 'ontology-bundle-v0', 'bundle_id': package['bundle_id'],
        'revision': package['revision'], 'status': 'APPROVED',
        'concept': {'label': package['profile']['domain']['profile_id'], 'kind': 'SOURCE_ASSEMBLY', 'glossary_ref': None},
        'provisions': [{'anchor': deepcopy(s['anchor']), 'role': 'SCOPE', 'value': None, 'note': ''}
                       for s in package['originals']],
        'relations': [], 'review_notes': [], 'evidence_judgments': [],
        'proposed_by': {'model': None, 'run_id': package['package_sha256'], 'at': approved_at},
        'history': [{'approval_ref': package['approval_ref'], 'profile_hash': package['profile_hash']} ]}
    snapshot = {'schema_version': 'ontology-snapshot-v0', 'bundles': [bundle]}
    from ..legal_agent.ontology_context import configuration
    return configuration({'mode': 'A1', 'snapshot': snapshot, 'snapshot_sha256': digest(snapshot),
                          'assembly_package': deepcopy(package)})


def verify_consumer(context):
    from ..legal_agent.ontology_context import configuration
    configuration(context)
    p = context['assembly_package']; compiler.verify_package(p, approved=True, recompile=True)
    fragments = [{'anchor': s['anchor'], 'text': s['text'], 'evidence_refs': ['VERIFY:' + s['id']]}
                 for s in p['originals']]
    bound = compiler.bind_current(p, fragments)
    if bound['withheld'] or {r['id'] for r in bound['paths']} != {r['id'] for r in p['paths']}:
        raise ContractError('staged package not consumable')
    return {'version': 'assembly-consumer-receipt-v1', 'package_hash': digest(context),
            'profile_hash': p['profile_hash'], 'source_hash': digest(p['originals']),
            'glossary_hash': digest(p['glossary_refs']), 'bound_hash': digest(bound),
            'actual_model_delivery': False, 'claim_usage': False}
