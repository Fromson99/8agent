"""Bind an authenticated mapped Gold reader and a separate administrative writer.

The host owns connection lifetimes and supplies the already selected request.
This module never discovers credentials or changes RAG runtime scopes.
"""
from contextlib import contextmanager
from . import configuration
from .wiki_contracts import scope_key
from ..legal_agent.errors import ContractError
from ..legal_agent.ontology_compiler import content_hash


@contextmanager
def context(*, actor, store, request, writer_connect, agent_owner, config):
    if config != configuration.settings() or actor not in config.get('operators', {}):
        raise ContractError('mapped authoring operator settings mismatch')
    ports = store.gold_ports
    selected = config['domain_profile']
    documents = frozenset(config['operators'][actor]['document_ids'])
    if not documents or not documents <= set(request.sources.allowed):
        raise ContractError('mapped authoring source scope mismatch')
    if selected['source_snapshot'] != request.snapshot.dataset_version:
        raise ContractError('mapped authoring source snapshot mismatch')
    if not callable(writer_connect) or not agent_owner:
        raise ContractError('separate administrative writer required')
    repo = ports.mapping.ontology_repository(writer_connect, agent_owner=agent_owner, read_only=False)
    # Writer permissions never register the namespace with the RAG reader.
    repo.workspace_scopes = frozenset(scope_key(s) for s in config.get('workspace_runtime_scopes', []))
    def source_reader(anchor):
        if anchor['document_id'] not in documents:
            raise ContractError('source outside operator scope')
        return ports.source_reader(anchor)
    def verify_glossary(refs):
        binding = ports.glossary_binding()
        try:
            if binding.binding['snapshot'] != selected['source_snapshot']:
                raise ContractError('mapped glossary snapshot mismatch')
            for ref in refs:
                if ref != binding.restore(ref['source'], ref['node_id']):
                    raise ContractError('published glossary snapshot changed')
        finally:
            binding.reader.close()
    repo.glossary_validator = verify_glossary
    base = configuration._make_workflow(actor, config, repo, source_reader)
    def probe():
        if not store.gold_profile['candidate_navigation']['ontology_enabled']:
            return {'status':'OFF'}
        scope = {'namespace':selected['namespace'], 'source_snapshot':selected['source_snapshot'],
            'acl_ref':selected['acl_ref'], 'actor':actor}
        if scope_key(scope) not in getattr(ports.ontology, 'workspace_scopes', ()):
            return {'status':'NO_SCOPE'}
        anchors = config.get('readiness_anchors', [])
        if not anchors or len(anchors) > 16:
            raise ContractError('explicit bounded readiness anchors required')
        found = False
        for anchor in anchors:
            text = source_reader(anchor)
            if content_hash(text) != anchor['content_sha256']:
                raise ContractError('readiness source content changed')
            rows = ports.ontology.lookup(anchor, documents)
            prefix = 'cb-kb-ws-' + scope_key(scope) + '-'
            found = found or any(row['context']['snapshot']['bundles'][0]['bundle_id'].startswith(prefix) for row in rows)
        return {'status':'READY' if found else 'EMPTY'}
    with configuration.authoring_context(actor=actor, workflow=base,
            glossary_factory=ports.glossary_binding, config=config, runtime_probe=probe):
        yield
