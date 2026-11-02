"""Actions dispatched by the existing ontology-work CLI, not a second pipeline."""
import json
import os
from ..oracle_runtime_paths import Path
from .configuration import domain_workflow, settings
from .profile import compile_profile
from ..legal_agent.errors import ContractError

ACTIONS = ['profile-validate', 'profile-register', 'profile-review', 'domain-status',
           'import-raw', 'export-journal', 'normalize', 'accumulate', 'save-accumulation',
           'domain-preview', 'domain-review', 'stage-publication', 'verify-publication',
           'activate-publication', 'reconcile-result', 'evaluation-spec-save']


def read(path):
    if path is None or path.stat().st_size > 2_000_000:
        raise ContractError('bounded input file required')
    return json.loads(path.read_text(encoding='utf-8'))


def run(args):
    if args.action == 'profile-validate':
        p = compile_profile(read(args.input), read(args.business) if args.business else None)
        return {'profile_hash': p['profile_hash'], 'status': 'VALIDATED_NOT_APPROVED',
                'output_schema': p['output_schema'], 'validation_plan': p['validation_plan']}
    w = domain_workflow(actor=os.environ.get('GENOS_ONTOLOGY_OPERATOR', ''))
    try:
        a = args.action
        if a == 'profile-register':
            return w.save_profile(read(args.input), read(args.business) if args.business else None,
                                  expected_revision=args.revision or 0)
        if a in ('profile-review', 'domain-review'):
            return {'approval': w.review(args.bundle, args.revision, args.work_hash, args.approve, args.reason or '')}
        if a == 'domain-status':
            if args.bundle:
                return w.load(args.bundle, args.revision)
            visible = []
            for row in w.repo.list(prefix=args.prefix or 'cb-kb-'):
                try:
                    w.load(row['bundle_id']); visible.append(row)
                except ContractError:
                    continue
            return visible
        if a == 'import-raw':
            spec = read(args.input)
            return w.import_payload(**spec)
        if a == 'export-journal':
            from ..legal_agent import journal_storage
            from .observations import export_journal
            cfg = settings()['domain_profile']['journals'][args.journal]
            w.scope(cfg['document_ids'])
            def authorize(run):
                if run['binding_hash'] != cfg['binding_hash']:
                    raise ContractError('export journal binding changed')
            db = journal_storage.connect(Path(cfg['path']).resolve().as_uri() + '?mode=ro', uri=True)
            try:
                page = export_journal(db, after=args.after, limit=32, authorize=authorize,
                    metadata={'namespace': w.namespace, 'source_snapshot': w.source_snapshot,
                              'acl_ref': w.acl_ref, 'document_ids': cfg['document_ids']})
                receipts = [w.ingest(raw) for raw in page['events']]
                return {'receipts': receipts, 'checkpoint': page['checkpoint'], 'page_full': page['page_full']}
            finally:
                db.close()
        if a == 'normalize':
            return w.normalize(args.bundle, **read(args.input))
        if a in ('accumulate', 'save-accumulation'):
            spec = read(args.input)
            if a == 'save-accumulation':
                return w.save_accumulation(**spec, proposal=read(args.proposal))
            return w.accumulate(**spec)
        if a == 'evaluation-spec-save':
            return w.save_evaluation_spec(args.bundle, args.revision, args.work_hash, read(args.input))
        if a == 'domain-preview':
            return w.preview(args.bundle)
        if a == 'stage-publication':
            return w.stage_publication(args.bundle, args.revision, args.work_hash, args.expected_sequence)
        if a == 'verify-publication':
            return w.verify_publication(args.publication_id)
        if a == 'activate-publication':
            return w.activate_publication(args.publication_id, args.expected_sequence, read(args.receipt),rollback=args.rollback)
        if a == 'reconcile-result':
            return w.reconcile(args.work_hash, args.revision)
        raise ContractError('unknown domain action')
    finally:
        w.glossary.reader.close()
