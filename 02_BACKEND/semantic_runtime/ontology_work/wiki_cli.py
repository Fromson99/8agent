"""Workspace actions inside the existing ontology-work command."""
import os
from .configuration import workspace_workflow, domain_workflow
from .domain_cli import read
from ..legal_agent.errors import ContractError

ACTIONS = ['workspace-ingest', 'workspace-propose', 'workspace-apply', 'workspace-list',
           'workspace-status', 'workspace-lint', 'workspace-preview', 'workspace-compile',
           'workspace-reconcile', 'workspace-compare']


def run(args):
    actor = os.environ.get('GENOS_ONTOLOGY_OPERATOR', '')
    w = workspace_workflow(actor=actor)
    if args.action == 'workspace-ingest':
        spec = read(args.input)
        return w.ingest(spec) if 'raw_event_id' in spec else w.import_payload(**spec)
    if args.action == 'workspace-propose': return w.propose(**read(args.input))
    if args.action == 'workspace-apply': return w.apply(**read(args.input))
    if args.action == 'workspace-list':
        return w.list_items(kind=args.kind, query=args.query or '', cursor=read(args.cursor) if args.cursor else None)
    if args.action == 'workspace-status': return w.item(args.bundle, args.revision)
    if args.action == 'workspace-lint': return w.lint(args.bundle)
    if args.action == 'workspace-reconcile': return w.reconcile_change(args.work_hash)
    domain = domain_workflow(actor=actor)
    try:
        if args.action == 'workspace-compare':
            from .wiki_projection import compare_judgment
            return compare_judgment(domain, w, **read(args.input))
        if args.action == 'workspace-preview': return domain.preview(args.bundle)
        if args.action == 'workspace-compile':
            from .wiki_projection import compile_selection
            return compile_selection(domain, w, **read(args.input))
        raise ContractError('unknown workspace action')
    finally:
        domain.glossary.reader.close()
